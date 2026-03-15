# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Unit tests for S-16.4: Exponential backoff retry in EvaluatorConfig.evaluate()."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from memory.evaluator.provider import EvaluatorConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(provider="ollama", max_retries=3) -> EvaluatorConfig:
    cfg = EvaluatorConfig(provider=provider, max_retries=max_retries)
    return cfg


def _http_error(status_code: int, retry_after: str | None = None):
    """Create a mock exception that looks like an HTTP error."""
    exc = RuntimeError(f"HTTP {status_code}")
    exc.status_code = status_code
    if retry_after is not None:
        response = Mock()
        response.headers = {"Retry-After": retry_after}
        exc.response = response
    return exc


def _good_openai_response(text: str = '{"score": 0.9, "reasoning": "ok"}'):
    msg = Mock()
    msg.content = text
    msg.reasoning = None
    choice = Mock()
    choice.message = msg
    resp = Mock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvaluatorRetry:

    def test_success_on_first_attempt(self):
        """Should succeed immediately with no retries."""
        cfg = _make_config(max_retries=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _good_openai_response()
        cfg._client = mock_client

        result = cfg.evaluate("test prompt")

        assert result["score"] == 0.9
        assert mock_client.chat.completions.create.call_count == 1

    def test_retry_success_after_transient_500(self):
        """Should retry on 500 and succeed on second attempt."""
        cfg = _make_config(max_retries=3)
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _http_error(500)
            return _good_openai_response()

        mock_client.chat.completions.create.side_effect = side_effect
        cfg._client = mock_client

        with patch("memory.evaluator.provider.time.sleep"):
            result = cfg.evaluate("test prompt")

        assert result["score"] == 0.9
        assert call_count == 2

    def test_exponential_backoff_timing(self):
        """Sleep durations should grow with attempt number (base * 2^n)."""
        cfg = _make_config(max_retries=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _http_error(500)
        cfg._client = mock_client

        sleep_calls = []

        with (
            patch(
                "memory.evaluator.provider.time.sleep", side_effect=sleep_calls.append
            ),
            patch("memory.evaluator.provider.random.uniform", return_value=0.0),
            pytest.raises(RuntimeError),
        ):
            cfg.evaluate("test prompt")

        # With max_retries=3 we sleep 3 times (attempts 0,1,2) before final failure
        assert len(sleep_calls) == 3
        # Base delays: 1*(2^0)=1, 1*(2^1)=2, 1*(2^2)=4
        assert sleep_calls[0] == pytest.approx(1.0)
        assert sleep_calls[1] == pytest.approx(2.0)
        assert sleep_calls[2] == pytest.approx(4.0)

    def test_max_retries_exhaustion_raises(self):
        """Should raise the last exception after all retries are exhausted."""
        cfg = _make_config(max_retries=2)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _http_error(503)
        cfg._client = mock_client

        with (
            patch("memory.evaluator.provider.time.sleep"),
            pytest.raises(Exception, match="HTTP 503"),
        ):
            cfg.evaluate("test prompt")

        assert (
            mock_client.chat.completions.create.call_count == 3
        )  # initial + 2 retries

    def test_non_retryable_400_fails_immediately(self):
        """400 errors should not be retried."""
        cfg = _make_config(max_retries=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _http_error(400)
        cfg._client = mock_client

        with pytest.raises(Exception, match="HTTP 400"):
            cfg.evaluate("test prompt")

        assert mock_client.chat.completions.create.call_count == 1

    def test_429_with_retry_after_header(self):
        """On 429, Retry-After header should override calculated backoff delay."""
        cfg = _make_config(max_retries=3)
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _http_error(429, retry_after="5")
            return _good_openai_response()

        mock_client.chat.completions.create.side_effect = side_effect
        cfg._client = mock_client

        sleep_calls = []

        with (
            patch(
                "memory.evaluator.provider.time.sleep", side_effect=sleep_calls.append
            ),
            patch("memory.evaluator.provider.random.uniform", return_value=0.0),
        ):
            result = cfg.evaluate("test prompt")

        assert result["score"] == 0.9
        # First sleep should use Retry-After=5 as base (plus zero jitter)
        assert sleep_calls[0] == pytest.approx(5.0)

    def test_retry_on_connection_error(self):
        """ConnectionError should trigger retry."""
        cfg = _make_config(max_retries=2)
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("connection refused")
            return _good_openai_response()

        mock_client.chat.completions.create.side_effect = side_effect
        cfg._client = mock_client

        with patch("memory.evaluator.provider.time.sleep"):
            result = cfg.evaluate("test prompt")

        assert result["score"] == 0.9
        assert call_count == 3

    def test_retry_on_timeout_error(self):
        """TimeoutError should trigger retry."""
        cfg = _make_config(max_retries=2)
        mock_client = MagicMock()
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("timed out")
            return _good_openai_response()

        mock_client.chat.completions.create.side_effect = side_effect
        cfg._client = mock_client

        with patch("memory.evaluator.provider.time.sleep"):
            result = cfg.evaluate("test prompt")

        assert result["score"] == 0.9
        assert call_count == 2

    def test_client_reset_after_exhaustion(self):
        """_client should be set to None after all retries are exhausted."""
        cfg = _make_config(max_retries=1)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = _http_error(500)
        cfg._client = mock_client

        with (
            patch("memory.evaluator.provider.time.sleep"),
            pytest.raises(RuntimeError),
        ):
            cfg.evaluate("test prompt")

        assert cfg._client is None

    def test_client_reset_after_connection_error_exhaustion(self):
        """_client should be set to None after ConnectionError retries are exhausted."""
        cfg = _make_config(max_retries=2)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ConnectionError("refused")
        cfg._client = mock_client

        with (
            patch("memory.evaluator.provider.time.sleep"),
            pytest.raises(ConnectionError),
        ):
            cfg.evaluate("test prompt")

        assert cfg._client is None
