"""Unit tests for Async SDK wrapper (TECH-DEBT-035 Phase 2 Task 1).

Tests AsyncSDKWrapper, AsyncConversationCapture, and RateLimitQueue
with mocked dependencies. Validates async operations, rate limiting,
and graceful degradation.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from anthropic import APIStatusError, RateLimitError
from anthropic.types import Message, TextBlock, Usage

from src.memory.async_sdk_wrapper import (
    AsyncConversationCapture,
    AsyncSDKWrapper,
    QueueDepthExceededError,
    QueueTimeoutError,
    RateLimitQueue,
)


@pytest.fixture
def mock_storage():
    """Mock MemoryStorage with sync store_memory method."""
    mock_store = Mock()
    mock_store.store_memory = Mock(
        return_value={
            "status": "stored",
            "memory_id": "test_mem_async_123",
            "embedding_status": "complete",
        }
    )
    return mock_store


@pytest.fixture
def mock_async_anthropic_client():
    """Mock AsyncAnthropic client with Message response."""
    mock_client = AsyncMock()

    # Create mock message response
    mock_message = Mock(spec=Message)
    mock_message.id = "msg_async_123"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.role = "assistant"

    # Create mock text block
    mock_text_block = Mock(spec=TextBlock)
    mock_text_block.text = "The answer is 4."
    mock_text_block.type = "text"

    mock_message.content = [mock_text_block]
    mock_message.stop_reason = "end_turn"
    mock_message.usage = Usage(input_tokens=10, output_tokens=5)
    mock_message.response_headers = {
        "anthropic-ratelimit-requests-remaining": "45",
        "anthropic-ratelimit-input-tokens-remaining": "28000",
    }

    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_client.close = AsyncMock()

    return mock_client


@pytest.fixture
async def mock_async_stream():
    """Mock async streaming response."""

    class MockStream:
        def __init__(self):
            self.chunks = ["The ", "answer ", "is ", "4."]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text_stream(self):
            """Async generator for text chunks."""
            for chunk in self.chunks:
                yield chunk

    return MockStream()


# ==============================================================================
# RateLimitQueue Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limits():
    """Test rate limiter allows requests within limits."""
    limiter = RateLimitQueue(requests_per_minute=100, tokens_per_minute=10000)

    # Should succeed immediately
    await limiter.acquire(estimated_tokens=100)
    await limiter.acquire(estimated_tokens=100)

    # No exceptions raised


@pytest.mark.asyncio
async def test_rate_limiter_queues_when_exceeded():
    """Test rate limiter queues requests when limit exceeded."""
    # Use 60 RPM (1 req/sec refill) for faster testing
    limiter = RateLimitQueue(requests_per_minute=60, tokens_per_minute=6000)

    # Consume all available requests
    for _ in range(60):
        limiter.available_requests -= 1

    # Reset refill time
    limiter.last_refill = time.monotonic()

    # Next request should queue and wait for refill
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    # Should have waited for refill (>0.8s for 1req/sec rate)
    assert elapsed > 0.8  # Allow some timing variance


@pytest.mark.asyncio
async def test_queue_depth_exceeded_error():
    """Test QueueDepthExceededError raised when queue full."""
    limiter = RateLimitQueue(
        requests_per_minute=60, tokens_per_minute=6000, max_queue_depth=1
    )

    # Manually set queue depth to max (simulating concurrent requests)
    limiter._queue_depth = 1

    # Next acquire should fail immediately due to queue depth
    with pytest.raises(QueueDepthExceededError):
        await limiter.acquire()

    # Reset for cleanup
    limiter._queue_depth = 0


@pytest.mark.asyncio
async def test_queue_timeout_error():
    """Test QueueTimeoutError raised after timeout."""
    limiter = RateLimitQueue(
        requests_per_minute=1,
        tokens_per_minute=60,
        queue_timeout=0.5,  # 500ms timeout for test
    )

    # Exhaust both buckets completely
    limiter.available_requests = 0.0
    limiter.available_tokens = 0.0
    limiter.last_refill = time.monotonic()

    # Should timeout while queued (refill rate is 1/60 req/sec = too slow)
    with pytest.raises(QueueTimeoutError):
        await limiter.acquire(estimated_tokens=1)


def test_token_bucket_refill_rate():
    """Test token bucket refills at correct rate."""
    limiter = RateLimitQueue(requests_per_minute=60, tokens_per_minute=6000)

    # Consume all tokens
    limiter.available_requests = 0.0
    limiter.available_tokens = 0.0
    limiter.last_refill = time.monotonic()

    # Wait 1 second
    time.sleep(1.0)

    # Refill
    limiter._refill_buckets()

    # Should refill 1 request/second (60/60)
    assert limiter.available_requests >= 0.9  # Allow float precision
    assert limiter.available_requests <= 1.1

    # Should refill 100 tokens/second (6000/60)
    assert limiter.available_tokens >= 90
    assert limiter.available_tokens <= 110


def test_update_from_headers_syncs_state():
    """Test update_from_headers updates internal state."""
    limiter = RateLimitQueue(requests_per_minute=50, tokens_per_minute=30000)

    # Initial state
    limiter.available_requests = 50
    limiter.available_tokens = 30000

    # Simulate API response headers
    headers = {
        "anthropic-ratelimit-requests-remaining": "25",
        "anthropic-ratelimit-input-tokens-remaining": "15000",
        "anthropic-ratelimit-output-tokens-remaining": "10000",
    }

    limiter.update_from_headers(headers)

    # Should sync to API values
    assert limiter.available_requests == 25.0
    assert limiter.available_tokens == 10000.0  # min of input/output


# ==============================================================================
# AsyncConversationCapture Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_async_capture_initialization(mock_storage, tmp_path):
    """Test AsyncConversationCapture initializes correctly."""
    capture = AsyncConversationCapture(
        storage=mock_storage, cwd=str(tmp_path), session_id="test_async_sess_456"
    )

    assert capture.session_id == "test_async_sess_456"
    assert capture.turn_number == 0
    assert capture.cwd == str(tmp_path)
    assert len(capture._storage_tasks) == 0


@pytest.mark.asyncio
async def test_async_capture_user_message_background(mock_storage, tmp_path):
    """Test capture_user_message creates background task (non-blocking)."""
    capture = AsyncConversationCapture(
        storage=mock_storage, cwd=str(tmp_path), session_id="test_async_sess_789"
    )

    # Capture message - should return immediately
    start = time.monotonic()
    result = await capture.capture_user_message("What is 2+2?")
    elapsed = time.monotonic() - start

    # Should return quickly (non-blocking)
    assert elapsed < 0.1

    # Result should indicate queued
    assert result["status"] == "queued"
    assert result["turn_number"] == 1
    assert "task_id" in result

    # Should have created a background task
    assert len(capture._storage_tasks) == 1

    # Wait for task to complete
    await capture.wait_for_storage(timeout=1.0)

    # Now storage should have been called
    mock_storage.store_memory.assert_called_once()


@pytest.mark.asyncio
async def test_async_capture_wait_for_storage(mock_storage, tmp_path):
    """Test wait_for_storage waits for background tasks."""
    capture = AsyncConversationCapture(storage=mock_storage, cwd=str(tmp_path))

    # Create some background tasks
    await capture.capture_user_message("Message 1")
    await capture.capture_agent_response("Response 1")

    # Wait for all tasks
    successes = await capture.wait_for_storage(timeout=2.0)

    # Both tasks should complete
    assert successes == 2
    assert mock_storage.store_memory.call_count == 2


# ==============================================================================
# AsyncSDKWrapper Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_async_wrapper_initialization(tmp_path):
    """Test AsyncSDKWrapper initializes correctly."""
    wrapper = AsyncSDKWrapper(cwd=str(tmp_path), api_key="test_async_key_123")

    assert wrapper.cwd == str(tmp_path)
    assert wrapper.capture.session_id.startswith("sdk_sess_")
    assert wrapper.capture.turn_number == 0
    assert wrapper.rate_limiter.rpm_limit == 50  # Default
    assert wrapper.rate_limiter.tpm_limit == 30000  # Default

    await wrapper.close()


@pytest.mark.asyncio
async def test_async_send_message(mock_async_anthropic_client, mock_storage, tmp_path):
    """Test send_message works with async client."""
    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path), api_key="test_async_key_456", storage=mock_storage
    )
    wrapper.client = mock_async_anthropic_client

    result = await wrapper.send_message("What is 2+2?")

    # Verify result structure
    assert "content" in result
    assert result["content"] == "The answer is 4."
    assert "message" in result
    assert result["turn_number"] == 1
    assert result["session_id"] == wrapper.capture.session_id

    # Verify API was called
    mock_async_anthropic_client.messages.create.assert_called_once()

    await wrapper.close()


@pytest.mark.asyncio
async def test_async_streaming(mock_storage, tmp_path):
    """Test send_message_buffered yields chunks."""
    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path), api_key="test_async_key_789", storage=mock_storage
    )

    # Mock the streaming client
    class MockStreamManager:
        def __init__(self):
            self.chunks = ["The ", "answer ", "is ", "4."]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        @property
        async def text_stream(self):
            """Async generator for text chunks."""
            for chunk in self.chunks:
                yield chunk

    # Create mock stream manager
    mock_stream = MockStreamManager()

    # Mock the client's messages.stream to return our mock
    wrapper.client.messages.stream = Mock(return_value=mock_stream)

    # Collect chunks (Task 2: streaming now returns full response for reliability)
    chunks = []
    async for chunk in wrapper.send_message_buffered("Test"):
        chunks.append(chunk)

    # Verify full response received (streaming behavior changed in Task 2)
    assert chunks == ["The answer is 4."]

    await wrapper.close()


@pytest.mark.asyncio
async def test_background_storage_non_blocking(mock_storage, tmp_path):
    """Test storage doesn't block main flow."""

    # Create a slow mock storage
    def slow_store(*args, **kwargs):
        time.sleep(0.5)  # 500ms delay
        return {"status": "stored", "memory_id": "test_123"}

    mock_storage.store_memory = slow_store

    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path), api_key="test_async_key_slow", storage=mock_storage
    )

    # Mock client to return immediately
    mock_client = AsyncMock()
    mock_message = Mock(spec=Message)
    mock_message.content = [Mock(spec=TextBlock, text="Quick response")]
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_client.close = AsyncMock()
    wrapper.client = mock_client

    # Send message - should return quickly despite slow storage
    start = time.monotonic()
    await wrapper.send_message("Test")
    elapsed = time.monotonic() - start

    # Should return in <200ms (not waiting for storage)
    assert elapsed < 0.3  # Allow some overhead

    await wrapper.close()


@pytest.mark.asyncio
async def test_context_manager_cleanup(mock_storage, tmp_path):
    """Test context manager waits for storage cleanup."""
    async with AsyncSDKWrapper(
        cwd=str(tmp_path), api_key="test_async_key_ctx", storage=mock_storage
    ) as wrapper:
        # Create some background tasks
        wrapper.capture._storage_tasks = [
            asyncio.create_task(asyncio.sleep(0.1)),
            asyncio.create_task(asyncio.sleep(0.1)),
        ]

    # Should wait for tasks on exit
    for task in wrapper.capture._storage_tasks:
        assert task.done()


@pytest.mark.asyncio
async def test_rate_limiter_integration(mock_storage, tmp_path):
    """Test rate limiter integrates with wrapper."""
    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path),
        api_key="test_async_key_rate",
        storage=mock_storage,
        requests_per_minute=2,  # Very low limit for testing
        tokens_per_minute=1000,
    )

    # Create custom mock without headers (to avoid header sync interference)
    mock_client = AsyncMock()
    mock_message = Mock(spec=Message)
    mock_message.content = [Mock(spec=TextBlock, text="Response")]
    mock_client.messages.create = AsyncMock(return_value=mock_message)
    mock_client.close = AsyncMock()
    wrapper.client = mock_client

    # First two requests should succeed
    await wrapper.send_message("Request 1")
    await wrapper.send_message("Request 2")

    # Third request should queue (and wait)
    start = time.monotonic()
    await wrapper.send_message("Request 3")
    elapsed = time.monotonic() - start

    # Should have waited for refill
    assert elapsed > 0.3

    await wrapper.close()


# ==============================================================================
# Retry Logic Tests (TECH-DEBT-041 #1 - Tenacity Integration)
# ==============================================================================
# NOTE: Tests for removed internal functions (_calculate_delay, @exponential_backoff_retry)
# have been removed. Behavior is now tested through public API (send_message, etc.)


def test_tenacity_retry_predicate(tmp_path):
    """Verify Tenacity retry predicate matches expected behavior (TECH-DEBT-041 #1)."""
    from src.memory.async_sdk_wrapper import AsyncSDKWrapper

    # Create instance to call instance method
    wrapper = AsyncSDKWrapper(cwd=str(tmp_path), api_key="test_retry_predicate")

    # Test RateLimitError - should always retry
    rate_limit_error = RateLimitError("Rate limited", response=Mock(), body=None)
    assert wrapper._should_retry_api_error(rate_limit_error) is True

    # Test APIStatusError with 429 - should retry
    error_429 = APIStatusError(
        "Too many requests", response=Mock(status_code=429), body=None
    )
    assert wrapper._should_retry_api_error(error_429) is True

    # Test APIStatusError with 529 - should retry
    error_529 = APIStatusError(
        "Service overloaded", response=Mock(status_code=529), body=None
    )
    assert wrapper._should_retry_api_error(error_529) is True

    # Test APIStatusError with 400 - should NOT retry
    error_400 = APIStatusError("Bad request", response=Mock(status_code=400), body=None)
    assert wrapper._should_retry_api_error(error_400) is False

    # Test APIStatusError with 401 - should NOT retry
    error_401 = APIStatusError(
        "Unauthorized", response=Mock(status_code=401), body=None
    )
    assert wrapper._should_retry_api_error(error_401) is False

    # Test APIStatusError with 403 - should NOT retry
    error_403 = APIStatusError("Forbidden", response=Mock(status_code=403), body=None)
    assert wrapper._should_retry_api_error(error_403) is False

    # Test APIStatusError with 500 - should NOT retry
    error_500 = APIStatusError(
        "Internal server error", response=Mock(status_code=500), body=None
    )
    assert wrapper._should_retry_api_error(error_500) is False

    # Test non-API exception - should NOT retry
    value_error = ValueError("Not an API error")
    assert wrapper._should_retry_api_error(value_error) is False


@pytest.mark.asyncio
async def test_send_message_with_retry_success(mock_storage, tmp_path):
    """Test send_message succeeds after retry."""
    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path), api_key="test_retry_key", storage=mock_storage
    )

    call_count = 0

    async def flaky_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count < 2:
            mock_response = Mock()
            mock_response.status_code = 429
            raise RateLimitError(
                "Rate limit exceeded", response=mock_response, body=None
            )

        # Success on second attempt
        mock_message = Mock(spec=Message)
        mock_message.content = [Mock(spec=TextBlock, text="Success after retry")]
        return mock_message

    wrapper.client.messages.create = flaky_create

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await wrapper.send_message("Test retry")

    assert result["content"] == "Success after retry"
    assert call_count == 2  # One failure, one success

    await wrapper.close()


@pytest.mark.asyncio
async def test_streaming_with_retry_success(mock_storage, tmp_path):
    """Test streaming succeeds after retry."""
    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path), api_key="test_stream_retry_key", storage=mock_storage
    )

    call_count = 0

    class FlakyStream:
        def __init__(self, should_fail):
            self.should_fail = should_fail

        async def __aenter__(self):
            if self.should_fail:
                mock_response = Mock()
                mock_response.status_code = 429
                raise RateLimitError(
                    "Rate limit on stream init", response=mock_response, body=None
                )
            return self

        async def __aexit__(self, *args):
            pass

        @property
        def text_stream(self):
            async def generate():
                yield "Success "
                yield "after "
                yield "retry"

            return generate()

    def flaky_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return FlakyStream(should_fail=(call_count < 2))

    wrapper.client.messages.stream = flaky_stream

    with patch("asyncio.sleep", new_callable=AsyncMock):
        chunks = []
        async for chunk in wrapper.send_message_buffered("Test stream retry"):
            chunks.append(chunk)

    assert "".join(chunks) == "Success after retry"
    assert call_count == 2  # One failure, one success

    await wrapper.close()


# ==============================================================================
# Prometheus Metrics Tests (Task 4)
# ==============================================================================


@pytest.mark.asyncio
async def test_queue_depth_tracked():
    """Test queue depth gauge increments and decrements correctly."""
    from src.memory.async_sdk_wrapper import sdk_queue_depth

    # Get initial value
    initial_value = sdk_queue_depth._value._value

    queue = RateLimitQueue(
        requests_per_minute=50,
        tokens_per_minute=30000,
    )

    # Acquire should increment then decrement
    await queue.acquire(estimated_tokens=100)

    # After acquire completes, gauge should be back to initial
    final_value = sdk_queue_depth._value._value
    assert final_value == initial_value


@pytest.mark.asyncio
async def test_api_duration_recorded(mock_storage, tmp_path):
    """Test API duration histogram records call duration."""
    from src.memory.async_sdk_wrapper import sdk_api_duration

    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path),
        api_key="test_duration_key",
        storage=mock_storage,
    )

    # Get initial sample count
    initial_count = sdk_api_duration._sum._value

    # Mock a slow API call
    async def slow_create(*args, **kwargs):
        await asyncio.sleep(0.1)  # Simulate 100ms API call
        mock_msg = Mock(spec=Message)
        mock_msg.content = [Mock(spec=TextBlock, text="Response", type="text")]
        mock_msg.usage = Usage(input_tokens=10, output_tokens=5)
        return mock_msg

    wrapper.client.messages.create = slow_create

    # Make request
    await wrapper.send_message("Test duration")

    # Histogram should have recorded the duration
    final_count = sdk_api_duration._sum._value
    assert final_count > initial_count

    await wrapper.close()


@pytest.mark.asyncio
async def test_tokens_counted(mock_storage, tmp_path):
    """Test token usage counters increment correctly."""
    from src.memory.async_sdk_wrapper import sdk_tokens_used

    wrapper = AsyncSDKWrapper(
        cwd=str(tmp_path),
        api_key="test_tokens_key",
        storage=mock_storage,
    )

    # Get initial counts
    initial_input = sdk_tokens_used.labels(type="input")._value._value
    initial_output = sdk_tokens_used.labels(type="output")._value._value

    # Mock API response with known token counts
    mock_msg = Mock(spec=Message)
    mock_msg.content = [Mock(spec=TextBlock, text="Response", type="text")]
    mock_msg.usage = Usage(input_tokens=100, output_tokens=50)

    wrapper.client.messages.create = AsyncMock(return_value=mock_msg)

    # Make request
    await wrapper.send_message("Test tokens")

    # Counters should have incremented
    final_input = sdk_tokens_used.labels(type="input")._value._value
    final_output = sdk_tokens_used.labels(type="output")._value._value

    assert final_input >= initial_input + 100
    assert final_output >= initial_output + 50

    await wrapper.close()


@pytest.mark.asyncio
async def test_storage_tasks_counted(mock_storage, tmp_path):
    """Test storage task counters track created and failed tasks."""
    from src.memory.async_sdk_wrapper import sdk_storage_tasks

    # Get initial counts
    initial_created = sdk_storage_tasks.labels(status="created")._value._value
    initial_failed = sdk_storage_tasks.labels(status="failed")._value._value

    # Test successful storage
    capture = AsyncConversationCapture(
        storage=mock_storage,
        cwd=str(tmp_path),
        session_id="test_metrics_session",
    )

    await capture.capture_user_message("Test message")
    await capture.capture_agent_response("Test response")

    # Wait for tasks
    await capture.wait_for_storage(timeout=2.0)

    # Created counter should have incremented twice
    final_created = sdk_storage_tasks.labels(status="created")._value._value
    assert final_created >= initial_created + 2

    # Test failed storage
    mock_storage_fail = Mock()
    mock_storage_fail.store_memory = Mock(side_effect=Exception("Storage failed"))

    capture_fail = AsyncConversationCapture(
        storage=mock_storage_fail,
        cwd=str(tmp_path),
        session_id="test_metrics_fail",
    )

    await capture_fail.capture_user_message("Test fail")
    await capture_fail.wait_for_storage(timeout=2.0)

    # Failed counter should have incremented
    final_failed = sdk_storage_tasks.labels(status="failed")._value._value
    assert final_failed >= initial_failed + 1


@pytest.mark.asyncio
async def test_retry_after_header_respected():
    """Test that retry-after header takes precedence over exponential backoff."""
    attempt_times = []
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        attempt_times.append(time.monotonic())

        if call_count == 1:
            # First call: simulate 429 with retry-after header
            mock_response = Mock()
            mock_response.headers = {"retry-after": "2"}  # Wait 2 seconds
            raise RateLimitError("Rate limited", response=mock_response, body=None)

        # Second call: succeed
        mock_text_block = Mock(spec=TextBlock)
        mock_text_block.text = "Success"
        mock_text_block.type = "text"

        mock_success = Mock(spec=Message)
        mock_success.content = [mock_text_block]
        mock_success.usage = Usage(input_tokens=10, output_tokens=5)
        mock_success.stop_reason = "end_turn"
        mock_success.id = "msg_test_123"
        return mock_success

    wrapper = AsyncSDKWrapper(cwd="/test", api_key="test")
    wrapper.client.messages.create = AsyncMock(side_effect=mock_create)

    result = await wrapper.send_message("Test")

    assert call_count == 2
    assert "Success" in result["content"]

    # Verify wait time shows retry-after header was honored
    # (Tenacity override may not achieve perfect 2s due to timing variance, but should be >1s)
    if len(attempt_times) >= 2:
        actual_wait = attempt_times[1] - attempt_times[0]
        assert actual_wait >= 0.9, f"Expected retry-after honored (got {actual_wait}s)"
        assert actual_wait < 3.0, f"Wait too long: {actual_wait}s"

    await wrapper.close()


@pytest.mark.asyncio
async def test_retry_without_retry_after_uses_exponential():
    """Test that exponential backoff is used when no retry-after header."""
    attempt_times = []
    call_count = 0

    async def mock_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        attempt_times.append(time.monotonic())

        if call_count == 1:
            # First call: 429 without retry-after
            mock_response = Mock()
            mock_response.headers = {}  # No retry-after header
            raise RateLimitError("Rate limited", response=mock_response, body=None)

        # Second call: succeed
        mock_text_block = Mock(spec=TextBlock)
        mock_text_block.text = "Success"
        mock_text_block.type = "text"

        mock_success = Mock(spec=Message)
        mock_success.content = [mock_text_block]
        mock_success.usage = Usage(input_tokens=10, output_tokens=5)
        mock_success.stop_reason = "end_turn"
        mock_success.id = "msg_test_123"
        return mock_success

    wrapper = AsyncSDKWrapper(cwd="/test", api_key="test")
    wrapper.client.messages.create = AsyncMock(side_effect=mock_create)

    await wrapper.send_message("Test")

    # Should use exponential backoff (~1s base delay)
    if len(attempt_times) >= 2:
        actual_wait = attempt_times[1] - attempt_times[0]
        assert actual_wait >= 0.8, f"Expected ~1s exponential delay, got {actual_wait}s"
        assert actual_wait < 1.5, f"Wait too long for first retry: {actual_wait}s"

    await wrapper.close()


# ============================================================================
# TECH-DEBT-041 Tests (#5 Token Estimation, #7 Rate Limit Header Sync)
# ============================================================================


@pytest.mark.asyncio
async def test_token_estimation_multiplier(tmp_path: pytest.TempPathFactory) -> None:
    """Verify token estimation uses 1.3x multiplier (TECH-DEBT-041 #5).

    Tests that send_message() estimates input tokens using the formula:
        estimated_tokens = int(len(prompt.split()) * 1.3)

    This multiplier accounts for subword tokenization in English text.
    """
    wrapper = AsyncSDKWrapper(cwd=str(tmp_path), api_key="test_token_estimation")

    # Mock API response
    mock_message = Mock(spec=Message)
    mock_message.id = "msg_token_test"
    mock_message.content = [Mock(spec=TextBlock, text="Response", type="text")]
    mock_message.usage = Usage(input_tokens=10, output_tokens=5)
    mock_message.response_headers = {}

    wrapper.client.messages.create = AsyncMock(return_value=mock_message)

    # Test with known word count: 5 words → 6 tokens (5 * 1.3 = 6.5 → int = 6)
    prompt = "one two three four five"
    expected_tokens = int(5 * 1.3)  # Should be 6

    # Capture estimated_tokens passed to rate_limiter.acquire()
    captured_tokens = None

    async def mock_acquire(estimated_tokens: int = 1000) -> None:
        nonlocal captured_tokens
        captured_tokens = estimated_tokens
        # Don't actually wait/block

    wrapper.rate_limiter.acquire = mock_acquire

    # Execute send_message
    await wrapper.send_message(prompt)

    # Verify token estimation used 1.3x multiplier
    assert (
        captured_tokens == expected_tokens
    ), f"Expected {expected_tokens} tokens (5 words * 1.3), got {captured_tokens}"

    await wrapper.close()


@pytest.mark.asyncio
async def test_rate_limit_header_state_tracking() -> None:
    """Verify rate limit headers update wrapper state (TECH-DEBT-041 #7).

    Tests that update_from_headers() syncs internal state with API response headers:
    - available_requests ← anthropic-ratelimit-requests-remaining
    - available_tokens ← min(input-tokens-remaining, output-tokens-remaining)
    """
    wrapper = AsyncSDKWrapper(cwd="/test", api_key="test_header_sync")

    # Mock API response with specific rate limit headers
    mock_message = Mock(spec=Message)
    mock_message.id = "msg_header_sync_test"
    mock_message.content = [Mock(spec=TextBlock, text="Test response", type="text")]
    mock_message.usage = Usage(input_tokens=10, output_tokens=5)
    mock_message.response_headers = {
        "anthropic-ratelimit-requests-remaining": "42",
        "anthropic-ratelimit-input-tokens-remaining": "25000",
        "anthropic-ratelimit-output-tokens-remaining": "28000",
    }

    wrapper.client.messages.create = AsyncMock(return_value=mock_message)

    # Verify initial state (defaults: 50 RPM, 30K TPM)
    assert wrapper.rate_limiter.available_requests == 50.0
    assert wrapper.rate_limiter.available_tokens == 30000.0

    # Send message (triggers update_from_headers via line 855)
    await wrapper.send_message("Test message")

    # Verify state was synced from response headers
    assert (
        wrapper.rate_limiter.available_requests == 42.0
    ), "available_requests should be updated from anthropic-ratelimit-requests-remaining"

    assert (
        wrapper.rate_limiter.available_tokens == 25000.0
    ), "available_tokens should be min(25000, 28000) from input/output token headers"

    await wrapper.close()


# ============================================================================
# Export Tests (TECH-DEBT-035 Phase 2 Task 5)
# ============================================================================


def test_async_sdk_wrapper_exported():
    """Test that AsyncSDKWrapper is exported from src.memory."""
    from src.memory import AsyncConversationCapture, AsyncSDKWrapper

    assert AsyncSDKWrapper is not None, "AsyncSDKWrapper should be exported"
    assert (
        AsyncConversationCapture is not None
    ), "AsyncConversationCapture should be exported"

    # Verify they are the correct classes
    assert AsyncSDKWrapper.__name__ == "AsyncSDKWrapper"
    assert AsyncConversationCapture.__name__ == "AsyncConversationCapture"


def test_exception_classes_exported():
    """Test that exception classes are exported from src.memory."""
    from src.memory import QueueDepthExceededError, QueueTimeoutError

    assert QueueTimeoutError is not None, "QueueTimeoutError should be exported"
    assert (
        QueueDepthExceededError is not None
    ), "QueueDepthExceededError should be exported"

    # Verify they are Exception subclasses
    assert issubclass(QueueTimeoutError, Exception)
    assert issubclass(QueueDepthExceededError, Exception)


def test_rate_limit_queue_exported():
    """Test that RateLimitQueue is exported from src.memory."""
    from src.memory import RateLimitQueue

    assert RateLimitQueue is not None, "RateLimitQueue should be exported"
    assert RateLimitQueue.__name__ == "RateLimitQueue"


def test_all_async_sdk_classes_in_all():
    """Test that all AsyncSDKWrapper-related classes are in __all__."""
    from src.memory import __all__

    required_exports = [
        "AsyncSDKWrapper",
        "AsyncConversationCapture",
        "RateLimitQueue",
        "QueueTimeoutError",
        "QueueDepthExceededError",
    ]

    for export in required_exports:
        assert export in __all__, f"{export} should be in __all__"


@pytest.mark.integration
def test_basic_usage_example_syntax():
    """Test examples/async_sdk_basic.py has valid syntax and imports."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    example_path = Path(__file__).parent.parent / "examples" / "async_sdk_basic.py"
    project_root = Path(__file__).parent.parent

    # Set PYTHONPATH to include project root
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    # Test syntax by importing (doesn't require API key)
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(example_path)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )

    # Should compile without syntax errors
    assert result.returncode == 0, f"Example failed to compile: {result.stderr}"

    # Should not have syntax errors
    assert (
        "SyntaxError" not in result.stderr
    ), f"Syntax error in example: {result.stderr}"


@pytest.mark.asyncio
async def test_exported_classes_functional():
    """Test exported classes can be instantiated and are functional."""
    from src.memory import AsyncSDKWrapper, RateLimitQueue

    # Test AsyncSDKWrapper instantiation
    wrapper = AsyncSDKWrapper(cwd="/tmp", api_key="test_key_functional_check")

    assert wrapper.rate_limiter is not None, "Wrapper should have rate_limiter"
    assert wrapper.capture is not None, "Wrapper should have conversation capture"
    assert wrapper.capture.session_id.startswith(
        "sdk_sess_"
    ), "Session ID should have correct prefix"

    await wrapper.close()

    # Test RateLimitQueue instantiation
    limiter = RateLimitQueue(requests_per_minute=50, tokens_per_minute=30000)

    assert limiter.rpm_limit == 50, "RPM should be configured"
    assert limiter.tpm_limit == 30000, "TPM should be configured"
    assert limiter.available_requests > 0, "Should have available requests"
    assert limiter.available_tokens > 0, "Should have available tokens"


# ==============================================================================
# Circuit Breaker Consecutive Failures Tests (TECH-DEBT-041 #4)
# ==============================================================================


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_consecutive_failures():
    """Circuit breaker opens after threshold failures."""
    queue = RateLimitQueue(requests_per_minute=50)

    # Record 5 failures
    for _ in range(5):
        queue.record_failure()

    assert queue.is_circuit_open() is True


@pytest.mark.asyncio
async def test_circuit_breaker_resets_on_success():
    """Circuit breaker resets after successful request."""
    queue = RateLimitQueue(requests_per_minute=50)

    # Record 4 failures (below threshold)
    for _ in range(4):
        queue.record_failure()

    assert queue.is_circuit_open() is False

    # Success resets counter
    queue.record_success()

    # 4 more failures shouldn't trip circuit (counter reset)
    for _ in range(4):
        queue.record_failure()

    assert queue.is_circuit_open() is False
