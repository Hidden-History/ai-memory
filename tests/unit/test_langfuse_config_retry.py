# Location: ai-memory/tests/unit/test_langfuse_config_retry.py
"""Unit tests for TD-206: tenacity retry on Langfuse client creation."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from tenacity import stop_after_attempt


@pytest.fixture(autouse=True)
def reset_client():
    """Reset the client singleton before and after each test."""
    from memory.langfuse_config import reset_langfuse_client

    reset_langfuse_client()
    yield
    reset_langfuse_client()


_BASE_ENV = {
    "LANGFUSE_ENABLED": "true",
    "LANGFUSE_PUBLIC_KEY": "pk-test",
    "LANGFUSE_SECRET_KEY": "sk-test",
}


class TestRetryDecorator:
    """Verify _create_langfuse_client_with_retry retry configuration."""

    def test_retry_stops_after_5_attempts(self):
        """Decorator is configured for 5 max attempts."""
        from memory.langfuse_config import _create_langfuse_client_with_retry

        stop = _create_langfuse_client_with_retry.retry.stop
        assert isinstance(stop, type(stop_after_attempt(5)))
        # stop_after_attempt stores max_attempt_number
        assert stop.max_attempt_number == 5

    def test_retry_uses_exponential_backoff(self):
        """Decorator uses exponential wait between 1s and 16s."""
        from memory.langfuse_config import _create_langfuse_client_with_retry

        wait = _create_langfuse_client_with_retry.retry.wait
        # wait_exponential stores multiplier/min/max
        assert wait.multiplier == 1
        assert wait.min == 1
        assert wait.max == 16

    def test_import_error_not_retried(self):
        """ImportError propagates immediately without retry (not a transient error)."""
        from memory.langfuse_config import _create_langfuse_client_with_retry

        call_count = 0

        def fake_langfuse_constructor(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ImportError("langfuse not installed")

        mock_langfuse_mod = MagicMock()
        mock_langfuse_mod.Langfuse = fake_langfuse_constructor

        with (
            patch.dict(
                sys.modules,
                {
                    "langfuse": mock_langfuse_mod,
                    "langfuse.span_filter": MagicMock(is_default_export_span=None),
                },
            ),
            patch("time.sleep"),
            pytest.raises(ImportError),
        ):
            _create_langfuse_client_with_retry()

        assert call_count == 1, "ImportError should NOT trigger retries"

    def test_transient_error_is_retried(self):
        """ConnectionError is retried; succeeds on 3rd attempt."""
        from memory.langfuse_config import _create_langfuse_client_with_retry

        mock_client = MagicMock()
        call_count = 0

        def fake_langfuse_constructor(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return mock_client

        mock_langfuse_mod = MagicMock()
        mock_langfuse_mod.Langfuse = fake_langfuse_constructor

        with (
            patch.dict(
                sys.modules,
                {
                    "langfuse": mock_langfuse_mod,
                    "langfuse.span_filter": MagicMock(is_default_export_span=None),
                },
            ),
            patch("time.sleep"),
        ):
            result = _create_langfuse_client_with_retry()

        assert result is mock_client
        assert call_count == 3

    def test_all_retries_exhausted_reraises(self):
        """After 5 failed attempts the original exception propagates."""
        from memory.langfuse_config import _create_langfuse_client_with_retry

        call_count = 0

        def fake_langfuse_constructor(**kwargs):
            nonlocal call_count
            call_count += 1
            raise OSError("always fails")

        mock_langfuse_mod = MagicMock()
        mock_langfuse_mod.Langfuse = fake_langfuse_constructor

        with (
            patch.dict(
                sys.modules,
                {
                    "langfuse": mock_langfuse_mod,
                    "langfuse.span_filter": MagicMock(is_default_export_span=None),
                },
            ),
            patch("time.sleep"),
            pytest.raises(OSError, match="always fails"),
        ):
            _create_langfuse_client_with_retry()

        assert call_count == 5


class TestGetLangfuseClient:
    """Verify get_langfuse_client() gracefully handles retry outcomes."""

    def test_returns_client_on_retry_success(self):
        """Returns client when _create_langfuse_client_with_retry eventually succeeds."""
        mock_client = MagicMock()

        with (
            patch.dict(os.environ, _BASE_ENV),
            patch(
                "memory.langfuse_config._create_langfuse_client_with_retry",
                return_value=mock_client,
            ),
        ):
            from memory.langfuse_config import get_langfuse_client

            result = get_langfuse_client()

        assert result is mock_client

    def test_returns_none_when_all_retries_exhausted(self):
        """Returns None (not crash) when all retries fail."""
        with (
            patch.dict(os.environ, _BASE_ENV),
            patch(
                "memory.langfuse_config._create_langfuse_client_with_retry",
                side_effect=OSError("server unreachable"),
            ),
        ):
            from memory.langfuse_config import get_langfuse_client

            result = get_langfuse_client()

        assert result is None

    def test_returns_none_on_import_error(self):
        """Returns None with pip-install hint when langfuse is not installed."""
        with (
            patch.dict(os.environ, _BASE_ENV),
            patch(
                "memory.langfuse_config._create_langfuse_client_with_retry",
                side_effect=ImportError("no module"),
            ),
        ):
            from memory.langfuse_config import get_langfuse_client

            result = get_langfuse_client()

        assert result is None

    def test_disabled_returns_none_without_creating_client(self):
        """When LANGFUSE_ENABLED=false, client is never created."""
        with (
            patch.dict(os.environ, {"LANGFUSE_ENABLED": "false"}),
            patch(
                "memory.langfuse_config._create_langfuse_client_with_retry"
            ) as mock_create,
        ):
            from memory.langfuse_config import get_langfuse_client

            result = get_langfuse_client()

        assert result is None
        mock_create.assert_not_called()
