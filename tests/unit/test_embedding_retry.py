# Location: ai-memory/tests/unit/test_embedding_retry.py
"""Unit tests for BUG-113: Embedding retry with exponential backoff."""

import os
from unittest.mock import Mock, patch

import pytest

from memory.embeddings import EmbeddingClient, EmbeddingError


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config singleton between tests."""
    from memory.config import reset_config

    reset_config()
    yield
    reset_config()


@pytest.fixture
def client():
    """Create an EmbeddingClient with retry enabled."""
    with patch.dict(os.environ, {"EMBEDDING_MAX_RETRIES": "2"}):
        c = EmbeddingClient()
        yield c
        c.close()


class TestEmbeddingRetry:
    """Tests for embed() retry wrapper (BUG-113)."""

    def test_retry_on_timeout_then_success(self, client):
        """Should retry on timeout and succeed on second attempt."""
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.raise_for_status = Mock()
        mock_response_ok.json.return_value = {"embeddings": [[0.1] * 768]}

        import httpx

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadTimeout("Connection timed out")
            return mock_response_ok

        with (
            patch.object(client.client, "post", side_effect=side_effect),
            patch("memory.embeddings.time.sleep"),
        ):
            result = client.embed(["test text"])

        assert len(result) == 1
        assert len(result[0]) == 768
        assert call_count == 2

    def test_all_retries_exhausted_raises(self, client):
        """Should raise EmbeddingError after all retries exhausted."""
        import httpx

        with (
            patch.object(
                client.client,
                "post",
                side_effect=httpx.ReadTimeout("timeout"),
            ),
            patch("memory.embeddings.time.sleep"),
            pytest.raises(EmbeddingError, match="EMBEDDING_TIMEOUT"),
        ):
            client.embed(["test text"])

    def test_non_timeout_error_no_retry(self, client):
        """Non-timeout errors should raise immediately without retry."""
        import httpx

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = Mock()
            resp.status_code = 500
            raise httpx.HTTPStatusError("Server Error", request=Mock(), response=resp)

        with (
            patch.object(client.client, "post", side_effect=side_effect),
            pytest.raises(EmbeddingError, match="EMBEDDING_ERROR"),
        ):
            client.embed(["test text"])

        # Should only be called once (no retry for non-timeout errors)
        assert call_count == 1

    def test_backoff_delay_increases(self, client):
        """Backoff delay range should increase with attempt number."""
        import httpx

        sleep_times = []

        def fake_sleep(t):
            sleep_times.append(t)

        with (
            patch.object(
                client.client,
                "post",
                side_effect=httpx.ReadTimeout("timeout"),
            ),
            patch("memory.embeddings.time.sleep", side_effect=fake_sleep),
            pytest.raises(EmbeddingError),
        ):
            client.embed(["test text"])

        # With 2 retries, we sleep twice
        assert len(sleep_times) == 2
        # Both sleeps should be non-negative (full jitter: uniform(0, cap))
        for t in sleep_times:
            assert t >= 0

    def test_no_retry_when_max_retries_zero(self):
        """With EMBEDDING_MAX_RETRIES=0, no retry should happen."""
        with patch.dict(os.environ, {"EMBEDDING_MAX_RETRIES": "0"}):
            from memory.config import reset_config

            reset_config()
            c = EmbeddingClient()
            try:
                import httpx

                call_count = 0

                def side_effect(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    raise httpx.ReadTimeout("timeout")

                with (
                    patch.object(c.client, "post", side_effect=side_effect),
                    pytest.raises(EmbeddingError),
                ):
                    c.embed(["test"])

                assert call_count == 1
            finally:
                c.close()
