"""Token bucket rate limiter for LLM providers.

FIX-11: Prevents exceeding provider rate limits and controls costs.

Pattern based on:
- Token Bucket Algorithm: https://en.wikipedia.org/wiki/Token_bucket
- AWS API Gateway rate limiting patterns (2026)
- Stripe rate limiting: https://stripe.com/blog/rate-limiters

TECH-DEBT-069: LLM classification cost control.
"""

import time
import logging
import threading
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger("ai_memory.classifier.rate_limiter")

__all__ = ["RateLimiter", "rate_limiter"]


@dataclass
class TokenBucket:
    """Token bucket for rate limiting a single provider.

    Attributes:
        capacity: Maximum tokens in bucket
        tokens: Current tokens available
        refill_rate: Tokens added per second
        last_refill: Timestamp of last refill
    """
    capacity: float
    tokens: float
    refill_rate: float  # Tokens per second
    last_refill: float
    lock: threading.Lock


class RateLimiter:
    """Token bucket rate limiter with per-provider limits.

    Uses token bucket algorithm to smooth out request bursts while
    enforcing average rate limits.

    Example:
        >>> limiter = RateLimiter(requests_per_minute=60)
        >>> if limiter.allow_request("ollama"):
        ...     result = call_provider("ollama")
        ... else:
        ...     # Rate limit exceeded, wait or skip
        ...     pass
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Average requests allowed per minute per provider
            burst_size: Maximum burst size (tokens in bucket)
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size

        # Convert to tokens per second
        self.refill_rate = requests_per_minute / 60.0

        self._buckets: Dict[str, TokenBucket] = {}
        self._global_lock = threading.Lock()

        logger.info(
            "rate_limiter_initialized",
            extra={
                "requests_per_minute": requests_per_minute,
                "burst_size": burst_size,
                "refill_rate_per_second": self.refill_rate,
            }
        )

    def _get_bucket(self, provider: str) -> TokenBucket:
        """Get or create token bucket for provider.

        Args:
            provider: Provider name

        Returns:
            TokenBucket instance
        """
        with self._global_lock:
            if provider not in self._buckets:
                self._buckets[provider] = TokenBucket(
                    capacity=self.burst_size,
                    tokens=self.burst_size,  # Start full
                    refill_rate=self.refill_rate,
                    last_refill=time.time(),
                    lock=threading.Lock(),
                )
            return self._buckets[provider]

    def _refill_bucket(self, bucket: TokenBucket) -> None:
        """Refill bucket based on elapsed time.

        Args:
            bucket: TokenBucket to refill
        """
        now = time.time()
        elapsed = now - bucket.last_refill

        # Add tokens based on elapsed time
        tokens_to_add = elapsed * bucket.refill_rate
        bucket.tokens = min(bucket.capacity, bucket.tokens + tokens_to_add)
        bucket.last_refill = now

    def allow_request(self, provider: str, tokens: int = 1) -> bool:
        """Check if request is allowed under rate limit.

        Args:
            provider: Provider name
            tokens: Number of tokens to consume (default: 1)

        Returns:
            True if request allowed, False if rate limit exceeded
        """
        bucket = self._get_bucket(provider)

        with bucket.lock:
            # Refill bucket
            self._refill_bucket(bucket)

            # Check if enough tokens available
            if bucket.tokens >= tokens:
                bucket.tokens -= tokens

                logger.debug(
                    "rate_limit_allowed",
                    extra={
                        "provider": provider,
                        "tokens_consumed": tokens,
                        "tokens_remaining": bucket.tokens,
                    }
                )
                return True
            else:
                # Not enough tokens, rate limited
                wait_time = (tokens - bucket.tokens) / bucket.refill_rate

                logger.warning(
                    "rate_limit_exceeded",
                    extra={
                        "provider": provider,
                        "tokens_needed": tokens,
                        "tokens_available": bucket.tokens,
                        "wait_seconds": wait_time,
                    }
                )
                return False

    def wait_for_token(self, provider: str, tokens: int = 1, timeout: float = 30.0) -> bool:
        """Wait for tokens to become available (blocking).

        Args:
            provider: Provider name
            tokens: Number of tokens needed
            timeout: Maximum seconds to wait

        Returns:
            True if tokens acquired, False if timeout
        """
        bucket = self._get_bucket(provider)
        start_time = time.time()

        while time.time() - start_time < timeout:
            with bucket.lock:
                self._refill_bucket(bucket)

                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    logger.debug(
                        "rate_limit_tokens_acquired",
                        extra={
                            "provider": provider,
                            "tokens": tokens,
                            "wait_seconds": time.time() - start_time,
                        }
                    )
                    return True

            # Sleep for a short interval before retrying
            time.sleep(0.1)

        logger.error(
            "rate_limit_timeout",
            extra={
                "provider": provider,
                "timeout_seconds": timeout,
            }
        )
        return False

    def get_status(self, provider: str) -> dict:
        """Get current rate limit status for provider.

        Args:
            provider: Provider name

        Returns:
            Dict with status information
        """
        bucket = self._get_bucket(provider)

        with bucket.lock:
            self._refill_bucket(bucket)

            return {
                "provider": provider,
                "tokens_available": bucket.tokens,
                "capacity": bucket.capacity,
                "refill_rate_per_second": bucket.refill_rate,
                "utilization_pct": (1 - bucket.tokens / bucket.capacity) * 100,
            }

    def reset(self, provider: str = None):
        """Reset rate limiter for provider or all providers.

        Args:
            provider: Provider to reset (default: all providers)
        """
        if provider:
            bucket = self._get_bucket(provider)
            with bucket.lock:
                bucket.tokens = bucket.capacity
                bucket.last_refill = time.time()
                logger.info("rate_limiter_reset", extra={"provider": provider})
        else:
            with self._global_lock:
                for p, bucket in self._buckets.items():
                    with bucket.lock:
                        bucket.tokens = bucket.capacity
                        bucket.last_refill = time.time()
                logger.info("rate_limiter_reset_all")


# Global rate limiter instance
# Shared across all classification requests in the process
rate_limiter = RateLimiter(
    requests_per_minute=60,  # Max 60 requests/min per provider
    burst_size=10,  # Allow bursts of 10 requests
)
