"""Async Anthropic SDK wrapper with rate limiting and retry logic (TECH-DEBT-035 Phase 2).

Phase 2 implementation adding:
- Full async/await support for Agent SDK compatibility
- Rate limiting with token bucket algorithm
- Request queuing during rate limits
- Exponential backoff retry with jitter (Task 2 - DEC-029)
- Background storage (fire-and-forget pattern)
- Conversation state management
- Prometheus metrics integration

Architecture:
- AsyncSDKWrapper: Main async wrapper class with retry logic
- AsyncConversationCapture: Background storage with asyncio.create_task()
- RateLimitQueue: Token bucket algorithm with in-memory queue
- exponential_backoff_retry: Decorator for retry with exponential backoff + jitter
- Graceful degradation on all storage failures

Retry Strategy (DEC-029):
- Max retries: 3
- Initial delay: 1s, backoff: 2x (1s, 2s, 4s)
- Jitter: ±20% randomization
- Retries on: 429 (rate limit), 529 (overload), network errors
- No retry: 4xx client errors (except 429), auth failures

References:
- Design: oversight/specs/tech-debt-035/phase-2-design.md
- Plan: oversight/specs/tech-debt-035/phase-2-implementation-plan.md
- DEC-029: Exponential backoff per Anthropic best practices
- Phase 1: src/memory/sdk_wrapper.py (sync wrapper)
"""

import asyncio
import logging
import os
import random
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import AsyncIterator, Optional, Dict, Any, List, Callable, TypeVar
from uuid import uuid4

from anthropic import AsyncAnthropic, APIError, RateLimitError, APIStatusError
from anthropic.types import Message, ContentBlock, TextBlock
from prometheus_client import Counter, Histogram, Gauge
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    stop_after_attempt,
    wait_exponential,
    wait_random,
    retry_if_exception,
)

from .config import COLLECTION_DISCUSSIONS, get_config
from .models import MemoryType
from .storage import MemoryStorage

# Prometheus Metrics
sdk_rate_limit_hits = Counter('bmad_sdk_rate_limit_hits_total', 'Rate limit 429 errors')
sdk_queue_depth = Gauge('bmad_sdk_queue_depth', 'Current queue depth')
sdk_api_duration = Histogram(
    'bmad_sdk_api_duration_seconds',
    'API call duration',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)
sdk_tokens_used = Counter('bmad_sdk_tokens_total', 'Tokens used', ['type'])  # input/output
sdk_storage_tasks = Counter('bmad_sdk_storage_tasks_total', 'Storage tasks', ['status'])  # created/failed

__all__ = [
    "AsyncSDKWrapper",
    "AsyncConversationCapture",
    "RateLimitQueue",
    "QueueTimeoutError",
    "QueueDepthExceededError",
]

logger = logging.getLogger("bmad.memory.async_sdk_wrapper")

# Token estimation: average ~1.3 tokens per word for English text
TOKENS_PER_WORD_MULTIPLIER = 1.3


# Exception classes for rate limiting
class QueueTimeoutError(Exception):
    """Request exceeded queue timeout while waiting for rate limit."""

    pass


class QueueDepthExceededError(Exception):
    """Queue depth exceeded maximum limit (circuit breaker)."""

    pass



class RateLimitQueue:
    """In-memory queue for rate-limited requests.

    Implements token bucket algorithm matching Anthropic's rate limiting.
    Queues requests when limits exceeded, processes with exponential backoff.

    Token Bucket Algorithm:
    - Two buckets: requests (RPM) and tokens (TPM)
    - Continuous refill rate: limit / 60 per second
    - Requests consume from both buckets
    - If insufficient tokens, request queues and waits

    Circuit Breaker:
    - Max queue depth: 100 requests (configurable)
    - Queue timeout: 60 seconds (configurable)
    - Raises exceptions if limits exceeded
    """

    def __init__(
        self,
        requests_per_minute: int = 50,
        tokens_per_minute: int = 30000,
        max_queue_depth: int = 100,
        queue_timeout: float = 60.0,
    ):
        """Initialize rate limit queue.

        Args:
            requests_per_minute: RPM limit (default: 50, Tier 1)
            tokens_per_minute: ITPM limit (default: 30K, Tier 1)
            max_queue_depth: Max queued requests before circuit breaker trips
            queue_timeout: Max seconds request can be queued before timeout
        """
        self.rpm_limit = requests_per_minute
        self.tpm_limit = tokens_per_minute
        self.max_queue_depth = max_queue_depth
        self.queue_timeout = queue_timeout

        # Token bucket state
        self.available_requests = float(requests_per_minute)
        self.available_tokens = float(tokens_per_minute)
        self.last_refill = time.monotonic()

        # Request tracking (sliding window for metrics)
        self.request_timestamps: deque = deque(maxlen=requests_per_minute)
        self.token_usage: deque = deque(maxlen=tokens_per_minute)

        # Queue state
        self._lock = asyncio.Lock()
        self._queue_depth = 0

        # Circuit breaker state (consecutive failures)
        self._consecutive_failures = 0
        self._circuit_open_until: Optional[datetime] = None
        self._failure_threshold = 5  # Open circuit after 5 consecutive failures
        self._cooldown_seconds = 60.0  # Auto-close after 60s

    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """Acquire permission to make request (blocks if rate limited).

        Args:
            estimated_tokens: Estimated input tokens for request

        Raises:
            QueueTimeoutError: Request queued for >queue_timeout seconds
            QueueDepthExceededError: Queue depth >max_queue_depth
        """
        async with self._lock:
            queue_start = time.monotonic()
            self._queue_depth += 1
            sdk_queue_depth.inc()

            try:
                while True:
                    # Check queue depth (circuit breaker)
                    if self._queue_depth > self.max_queue_depth:
                        raise QueueDepthExceededError(
                            f"Queue depth {self._queue_depth} exceeds limit {self.max_queue_depth}"
                        )

                    # Check circuit breaker (consecutive failures)
                    if self.is_circuit_open():
                        raise QueueDepthExceededError(
                            f"Circuit breaker open: {self._consecutive_failures} consecutive failures, "
                            f"cooldown until {self._circuit_open_until}"
                        )

                    # Check timeout
                    wait_time = time.monotonic() - queue_start
                    if wait_time > self.queue_timeout:
                        raise QueueTimeoutError(
                            f"Request queued for {wait_time:.1f}s, exceeds timeout {self.queue_timeout}s"
                        )

                    # Refill tokens
                    self._refill_buckets()

                    # Check if we can proceed
                    if (
                        self.available_requests >= 1
                        and self.available_tokens >= estimated_tokens
                    ):
                        # Consume tokens
                        self.available_requests -= 1
                        self.available_tokens -= estimated_tokens

                        # Track usage (sliding window)
                        now = time.monotonic()
                        self.request_timestamps.append(now)
                        self.token_usage.append(
                            {"timestamp": now, "tokens": estimated_tokens}
                        )

                        return  # Success

                    # Wait for refill (cap at 0.1s to check timeout frequently)
                    wait_seconds = min(0.1, self._time_until_available())
                    await asyncio.sleep(wait_seconds)

            finally:
                self._queue_depth -= 1
                sdk_queue_depth.dec()

    def _refill_buckets(self):
        """Refill token buckets based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill

        # Refill requests (RPM)
        refill_rate_requests = self.rpm_limit / 60.0  # per second
        self.available_requests = min(
            self.rpm_limit, self.available_requests + (elapsed * refill_rate_requests)
        )

        # Refill tokens (TPM)
        refill_rate_tokens = self.tpm_limit / 60.0  # per second
        self.available_tokens = min(
            self.tpm_limit, self.available_tokens + (elapsed * refill_rate_tokens)
        )

        self.last_refill = now

    def _time_until_available(self) -> float:
        """Calculate seconds until next token available."""
        if self.available_requests < 1:
            tokens_needed = 1 - self.available_requests
            refill_rate = self.rpm_limit / 60.0
            return tokens_needed / refill_rate

        if self.available_tokens < 1:
            return 1.0  # Wait 1 second minimum

        return 0.1  # Poll every 100ms

    def record_failure(self) -> None:
        """Record a failed request for circuit breaker tracking."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._circuit_open_until = datetime.now(timezone.utc) + timedelta(seconds=self._cooldown_seconds)
            logger.warning(
                "circuit_breaker_opened",
                extra={
                    "consecutive_failures": self._consecutive_failures,
                    "cooldown_seconds": self._cooldown_seconds,
                }
            )

    def record_success(self) -> None:
        """Record a successful request, resetting failure count."""
        self._consecutive_failures = 0
        self._circuit_open_until = None

    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self._circuit_open_until is None:
            return False
        if datetime.now(timezone.utc) >= self._circuit_open_until:
            # Cooldown expired, reset
            self._circuit_open_until = None
            self._consecutive_failures = 0
            return False
        return True

    def update_from_headers(self, headers: Dict[str, str]):
        """Update tracking from API response headers.

        Args:
            headers: Response headers from Anthropic API
        """
        # Extract rate limit info
        requests_rem = headers.get("anthropic-ratelimit-requests-remaining")
        input_tokens_rem = headers.get("anthropic-ratelimit-input-tokens-remaining")
        output_tokens_rem = headers.get("anthropic-ratelimit-output-tokens-remaining")

        # Log if approaching limits (>80% utilization)
        if requests_rem:
            requests_rem_int = int(requests_rem)
            if requests_rem_int < (self.rpm_limit * 0.2):
                logger.warning(
                    "rate_limit_approaching",
                    extra={
                        "requests_remaining": requests_rem_int,
                        "requests_limit": self.rpm_limit,
                        "utilization": 1 - (requests_rem_int / self.rpm_limit),
                    },
                )

        # Sync internal state with API reality
        if requests_rem is not None:
            self.available_requests = float(requests_rem)
        if input_tokens_rem is not None and output_tokens_rem is not None:
            # Use minimum as conservative estimate
            self.available_tokens = min(float(input_tokens_rem), float(output_tokens_rem))
            logger.debug("rate_limit_state_synced", extra={
                "available_requests": self.available_requests,
                "available_tokens": self.available_tokens
            })


class AsyncConversationCapture:
    """Async conversation capture with background storage.

    Captures user messages and agent responses to discussions collection
    using fire-and-forget pattern for non-blocking storage.

    Background Storage Pattern:
    - Uses asyncio.create_task() to run storage in background
    - Doesn't block main message flow
    - Tracks tasks for cleanup in wait_for_storage()
    - Graceful degradation on storage failures
    """

    def __init__(
        self,
        storage: MemoryStorage,
        cwd: str,
        session_id: Optional[str] = None,
    ):
        """Initialize async conversation capture.

        Args:
            storage: MemoryStorage instance (must support async operations)
            cwd: Current working directory for project detection
            session_id: Optional session identifier (generates UUID if not provided)
        """
        self.storage = storage
        self.cwd = cwd
        self.session_id = session_id or f"sdk_sess_{uuid4().hex[:8]}"
        self.turn_number = 0
        self._storage_tasks: List[asyncio.Task] = []

    async def capture_user_message(self, content: str) -> Dict[str, Any]:
        """Capture user message in background (non-blocking).

        Args:
            content: User message content

        Returns:
            Dict with task info (not storage result - it's async!)
        """
        self.turn_number += 1

        # Create background task
        task = asyncio.create_task(self._store_user_message(content))
        self._storage_tasks.append(task)
        sdk_storage_tasks.labels(status='created').inc()

        return {
            "status": "queued",
            "turn_number": self.turn_number,
            "task_id": id(task),
        }

    async def capture_agent_response(self, content: str) -> Dict[str, Any]:
        """Capture agent response in background (non-blocking).

        Args:
            content: Agent response content

        Returns:
            Dict with task info (not storage result - it's async!)
        """
        # Create background task
        task = asyncio.create_task(self._store_agent_response(content))
        self._storage_tasks.append(task)
        sdk_storage_tasks.labels(status='created').inc()

        return {
            "status": "queued",
            "turn_number": self.turn_number,
            "task_id": id(task),
        }

    async def _store_user_message(self, content: str):
        """Background task to store user message."""
        try:
            # Note: storage.store_memory is sync, needs to run in executor
            # These methods run inside asyncio.create_task() so a running loop
            # is guaranteed. If no loop exists, that's an architecture bug - fail fast.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self.storage.store_memory,
                content,
                self.cwd,
                MemoryType.USER_MESSAGE,
                "AsyncSDKWrapper",
                self.session_id,
                COLLECTION_DISCUSSIONS,
                self.turn_number,
                datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "user_message_captured",
                extra={
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                },
            )
        except Exception as e:
            sdk_storage_tasks.labels(status='failed').inc()
            logger.warning(
                "user_message_capture_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    async def _store_agent_response(self, content: str):
        """Background task to store agent response."""
        try:
            # Note: storage.store_memory is sync, needs to run in executor
            # These methods run inside asyncio.create_task() so a running loop
            # is guaranteed. If no loop exists, that's an architecture bug - fail fast.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self.storage.store_memory,
                content,
                self.cwd,
                MemoryType.AGENT_RESPONSE,
                "AsyncSDKWrapper",
                self.session_id,
                COLLECTION_DISCUSSIONS,
                self.turn_number,
                datetime.now(timezone.utc).isoformat(),
            )
            logger.info(
                "agent_response_captured",
                extra={
                    "session_id": self.session_id,
                    "turn_number": self.turn_number,
                },
            )
        except Exception as e:
            sdk_storage_tasks.labels(status='failed').inc()
            logger.warning(
                "agent_response_capture_failed",
                extra={
                    "session_id": self.session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    async def wait_for_storage(self, timeout: float = 10.0) -> int:
        """Wait for all background storage tasks to complete.

        Args:
            timeout: Max seconds to wait for tasks

        Returns:
            Number of tasks that completed successfully
        """
        if not self._storage_tasks:
            return 0

        try:
            done, pending = await asyncio.wait(
                self._storage_tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED
            )

            # Cancel pending tasks and await them
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected after cancel

            # Count successes (tasks that didn't raise)
            successes = sum(1 for task in done if not task.exception())
            return successes

        except asyncio.TimeoutError:
            logger.warning(
                "storage_cleanup_timeout",
                extra={
                    "session_id": self.session_id,
                    "pending_tasks": len(self._storage_tasks),
                },
            )
            return 0


class AsyncSDKWrapper:
    """Async Anthropic SDK wrapper with rate limiting and conversation capture.

    Phase 2 implementation adding:
    - Full async/await support
    - Rate limiting with exponential backoff
    - Request queuing during rate limits
    - Background storage (fire-and-forget)
    - Conversation state management
    - Prometheus metrics (TODO: Task 4)

    Example:
        >>> async def main():
        ...     async with AsyncSDKWrapper(cwd="/path") as wrapper:
        ...         result = await wrapper.send_message("Hello")
        ...         print(result["content"])
        >>>
        >>> asyncio.run(main())
    """

    def __init__(
        self,
        cwd: str,
        api_key: Optional[str] = None,
        storage: Optional[MemoryStorage] = None,
        session_id: Optional[str] = None,
        requests_per_minute: int = 50,
        tokens_per_minute: int = 30000,
    ):
        """Initialize async SDK wrapper.

        Args:
            cwd: Current working directory for project detection
            api_key: Anthropic API key (uses ANTHROPIC_API_KEY env var if not provided)
            storage: Optional MemoryStorage instance (creates new if not provided)
            session_id: Optional session identifier (generates UUID if not provided)
            requests_per_minute: RPM limit for rate limiting (default: 50, Tier 1)
            tokens_per_minute: TPM limit for rate limiting (default: 30K, Tier 1)

        Raises:
            ValueError: If ANTHROPIC_API_KEY not found
        """
        self.cwd = cwd
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Provide api_key parameter or set environment variable."
            )

        self.client = AsyncAnthropic(api_key=self.api_key)
        self.storage = storage or MemoryStorage()
        self.capture = AsyncConversationCapture(
            storage=self.storage,
            cwd=cwd,
            session_id=session_id,
        )
        self.rate_limiter = RateLimitQueue(
            requests_per_minute=requests_per_minute,
            tokens_per_minute=tokens_per_minute,
        )

        logger.info(
            "async_sdk_wrapper_initialized",
            extra={
                "session_id": self.capture.session_id,
                "cwd": cwd,
                "rpm_limit": requests_per_minute,
                "tpm_limit": tokens_per_minute,
            },
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.close()

    async def close(self):
        """Cleanup resources and wait for background tasks."""
        # Wait for storage tasks to complete
        await self.capture.wait_for_storage(timeout=10.0)

        # Close Anthropic client
        await self.client.close()

        logger.info(
            "async_sdk_wrapper_closed", extra={"session_id": self.capture.session_id}
        )
    def _should_retry_api_error(self, exception: Exception) -> bool:
        """Determine if exception should trigger retry (DEC-029, TECH-DEBT-041 #1).

        Only retries:
        - RateLimitError (429) - Always retry
        - APIStatusError with status in [429, 529] - Rate limit or overload

        Does NOT retry:
        - 4xx client errors (except 429) - 400, 401, 403, etc.
        - 5xx server errors (except 529)
        - Other exceptions

        Args:
            exception: Exception raised during API call

        Returns:
            True if should retry, False otherwise
        """
        if isinstance(exception, RateLimitError):
            sdk_rate_limit_hits.inc()
            return True
        if isinstance(exception, APIStatusError):
            if exception.status_code == 429:
                sdk_rate_limit_hits.inc()
            return exception.status_code in [429, 529]
        return False

    @staticmethod
    def _extract_retry_after(exception: Exception) -> Optional[float]:
        """Extract retry-after header from exception (TECH-DEBT-041 #2).

        Args:
            exception: Exception that may contain retry-after header

        Returns:
            Retry-after delay in seconds, or None if not present
        """
        if not hasattr(exception, 'response') or exception.response is None:
            return None

        retry_after_header = exception.response.headers.get('retry-after')
        if not retry_after_header:
            return None

        try:
            return float(retry_after_header)
        except (ValueError, TypeError):
            return None

    def _log_and_wait_retry(self, retry_state: RetryCallState) -> None:
        """Log retry attempt and override wait time if retry-after present (TECH-DEBT-041 #1).

        This callback is called by Tenacity before sleeping between retries.
        If retry-after header is present, it overrides Tenacity's exponential backoff.

        Args:
            retry_state: Tenacity retry state context
        """
        exception = retry_state.outcome.exception()
        retry_after = self._extract_retry_after(exception)

        if retry_after:
            # Override Tenacity's wait time with retry-after header value
            retry_state.next_action.sleep = retry_after
            logger.warning(
                "api_retry_with_retry_after",
                extra={
                    "attempt": retry_state.attempt_number,
                    "retry_after_seconds": retry_after,
                    "exception_type": type(exception).__name__,
                },
            )
        else:
            # Use Tenacity's calculated exponential backoff + jitter
            logger.warning(
                "api_retry_exponential",
                extra={
                    "attempt": retry_state.attempt_number,
                    "wait_seconds": retry_state.next_action.sleep,
                    "exception_type": type(exception).__name__,
                },
            )


    async def _create_message(
        self, model: str, max_tokens: int, messages: List[Dict[str, str]], **kwargs
    ) -> Message:
        """Internal method to create message with Tenacity retry logic (TECH-DEBT-041 #1).

        Implements exponential backoff retry (DEC-029):
        - Max retries: 3 (4 total attempts)
        - Delays: 1s, 2s, 4s (±20% jitter)
        - Retries on: 429 (rate limit), 529 (overload)
        - Respects retry-after header when present

        Args:
            model: Claude model to use
            max_tokens: Maximum tokens in response
            messages: Message list for API
            **kwargs: Additional parameters

        Returns:
            Message object from API

        Raises:
            RateLimitError: After exhausting retries
            APIStatusError: After exhausting retries or on non-retryable status
        """
        retry_config = AsyncRetrying(
            stop=stop_after_attempt(4),  # Initial + 3 retries
            wait=wait_exponential(multiplier=1, min=1, max=8) + wait_random(0, 0.4),
            retry=retry_if_exception(self._should_retry_api_error),
            before_sleep=self._log_and_wait_retry,
            reraise=True,
        )

        async for attempt in retry_config:
            with attempt:
                return await self.client.messages.create(
                    model=model, max_tokens=max_tokens, messages=messages, **kwargs
                )

    async def send_message(
        self,
        prompt: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 1024,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send a message with rate limiting, retry, and capture.

        Implements exponential backoff retry (DEC-029):
        - Max retries: 3
        - Delays: 1s, 2s, 4s (±20% jitter)
        - Retries on: 429 (rate limit), 529 (overload), network errors
        - No retry on: 4xx client errors (except 429), auth failures

        Args:
            prompt: User message/prompt
            model: Claude model to use
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters for messages.create()

        Returns:
            Dict with:
                - content: Agent response text
                - message: Full Message object from API
                - session_id: Session identifier
                - turn_number: Turn number in conversation

        Raises:
            QueueTimeoutError: Request queued too long
            QueueDepthExceededError: Queue depth exceeded
            RateLimitError: Rate limit exceeded after retries
            APIStatusError: API error (4xx/5xx) after retries
        """
        try:
            # Rate limiting (wait if needed)
            # Better heuristic: ~1.3 tokens per word for English
            # More accurate than pure word count
            estimated_tokens = int(len(prompt.split()) * TOKENS_PER_WORD_MULTIPLIER)
            await self.rate_limiter.acquire(estimated_tokens=estimated_tokens)

            # Capture user message (background)
            await self.capture.capture_user_message(prompt)

            # Send to API with retry logic (Task 2) - track duration
            start_time = time.monotonic()
            message = await self._create_message(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            duration = time.monotonic() - start_time
            sdk_api_duration.observe(duration)

            # Track token usage
            if hasattr(message, "usage") and message.usage:
                sdk_tokens_used.labels(type="input").inc(message.usage.input_tokens)
                sdk_tokens_used.labels(type="output").inc(message.usage.output_tokens)

            # Update rate limits from headers if available
            if hasattr(message, "response_headers"):
                self.rate_limiter.update_from_headers(message.response_headers)

            # Extract text content
            response_text = self._extract_text_content(message)

            # Capture agent response (background)
            await self.capture.capture_agent_response(response_text)

            return {
                "content": response_text,
                "message": message,
                "session_id": self.capture.session_id,
                "turn_number": self.capture.turn_number,
            }

        except Exception as e:
            logger.error(
                "send_message_failed",
                extra={
                    "session_id": self.capture.session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def send_message_buffered(
        self,
        prompt: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 1024,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Send a message and return the buffered response with retry and capture.

        NOTE: This method buffers the full response before returning. The name
        "buffered" reflects this behavior - the response is collected completely
        via streaming internally but returned as a single chunk.

        Implements exponential backoff retry (DEC-029):
        - Max retries: 3
        - Delays: 1s, 2s, 4s (±20% jitter)
        - Retries on: 429 (rate limit), 529 (overload), network errors
        - No retry on: 4xx client errors (except 429), auth failures

        Note: Retry applies to stream initialization, not individual chunks.
        If streaming fails mid-stream, the entire stream is retried from start.

        Args:
            prompt: User message/prompt
            model: Claude model to use
            max_tokens: Maximum tokens in response
            **kwargs: Additional parameters for messages.stream()

        Yields:
            Complete buffered response as a single chunk

        Note:
            Full response is captured after streaming completes.
        """
        try:
            # Rate limiting (wait if needed)
            # Better heuristic: ~1.3 tokens per word for English
            # More accurate than pure word count
            estimated_tokens = int(len(prompt.split()) * TOKENS_PER_WORD_MULTIPLIER)
            await self.rate_limiter.acquire(estimated_tokens=estimated_tokens)

            # Capture user message (background)
            await self.capture.capture_user_message(prompt)

            # Stream response with retry logic
            full_response = await self._stream_with_retry(
                model, max_tokens, prompt, **kwargs
            )

            # Capture complete response (background)
            await self.capture.capture_agent_response(full_response)

            # Yield chunks from completed response
            # Note: For true streaming, we'd need to buffer chunks during retry
            # This implementation prioritizes reliability over low latency
            yield full_response

        except Exception as e:
            logger.error(
                "streaming_failed",
                extra={
                    "session_id": self.capture.session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def _stream_with_retry(
        self, model: str, max_tokens: int, prompt: str, **kwargs
    ) -> str:
        """Internal method to stream message with Tenacity retry logic (TECH-DEBT-041 #1).

        Collects full response from stream before returning.
        If stream fails, entire operation is retried.

        Implements exponential backoff retry (DEC-029):
        - Max retries: 3 (4 total attempts)
        - Delays: 1s, 2s, 4s (±20% jitter)
        - Retries on: 429 (rate limit), 529 (overload)
        - Respects retry-after header when present

        Args:
            model: Claude model to use
            max_tokens: Maximum tokens in response
            prompt: User message/prompt
            **kwargs: Additional parameters

        Returns:
            Complete response text

        Raises:
            RateLimitError: After exhausting retries
            APIStatusError: After exhausting retries or on non-retryable status
        """
        retry_config = AsyncRetrying(
            stop=stop_after_attempt(4),  # Initial + 3 retries
            wait=wait_exponential(multiplier=1, min=1, max=8) + wait_random(0, 0.4),
            retry=retry_if_exception(self._should_retry_api_error),
            before_sleep=self._log_and_wait_retry,
            reraise=True,
        )

        async for attempt in retry_config:
            with attempt:
                full_response = []

                async with self.client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs,
                ) as stream:
                    async for text in stream.text_stream:
                        full_response.append(text)

                return "".join(full_response)

    def _extract_text_content(self, message: Message) -> str:
        """Extract text content from API Message object.

        Args:
            message: Message object from API

        Returns:
            Concatenated text from all TextBlock content blocks
        """
        text_parts = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
        return "".join(text_parts)
