"""Unit tests for embedding service client.

Tests AC 1.4.2 - Embeddings Client Module functionality.
"""

import sys
sys.path.insert(0, '.')

from unittest.mock import Mock, MagicMock, patch
from src.memory.embeddings import EmbeddingClient, EmbeddingError
from src.memory.config import MemoryConfig


class MockResponse:
    """Mock httpx response."""
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class TestEmbeddingClient:
    """Test EmbeddingClient functionality."""

    def test_client_initialization(self):
        """AC 1.4.2: Client initializes with config."""
        config = MemoryConfig()
        client = EmbeddingClient(config)

        assert client.config is not None
        assert client.base_url == f"http://{config.embedding_host}:{config.embedding_port}"
        assert client.client is not None

    def test_embed_success(self):
        """AC 1.4.2: embed() returns embeddings for texts."""
        with patch('httpx.Client') as MockClient:
            # Setup mock
            mock_instance = Mock()
            mock_response = MockResponse(
                status_code=200,
                json_data={
                    "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
                    "model": "jina-embeddings-v2-base-code",
                    "dimensions": 768
                }
            )
            mock_instance.post.return_value = mock_response
            MockClient.return_value = mock_instance

            client = EmbeddingClient()
            embeddings = client.embed(["test1", "test2"])

            # Verify
            assert len(embeddings) == 2
            assert len(embeddings[0]) == 3
            assert embeddings[0] == [0.1, 0.2, 0.3]
            assert embeddings[1] == [0.4, 0.5, 0.6]

    def test_embed_timeout_raises_error(self):
        """AC 1.4.2: Timeout raises EmbeddingError."""
        with patch('httpx.Client') as MockClient:
            # Setup mock to raise TimeoutException
            mock_instance = Mock()
            import httpx
            mock_instance.post.side_effect = httpx.TimeoutException("Timeout")
            MockClient.return_value = mock_instance

            client = EmbeddingClient()
            try:
                client.embed(["test"])
                assert False, "Should have raised EmbeddingError"
            except EmbeddingError as e:
                assert "EMBEDDING_TIMEOUT" in str(e)

    def test_embed_http_error_raises_error(self):
        """AC 1.4.2: HTTP errors raise EmbeddingError."""
        with patch('httpx.Client') as MockClient:
            # Setup mock to raise HTTPError
            mock_instance = Mock()
            import httpx
            mock_instance.post.side_effect = httpx.HTTPError("Connection refused")
            MockClient.return_value = mock_instance

            client = EmbeddingClient()
            try:
                client.embed(["test"])
                assert False, "Should have raised EmbeddingError"
            except EmbeddingError as e:
                assert "EMBEDDING_ERROR" in str(e)

    def test_health_check_healthy(self):
        """AC 1.4.2: health_check() returns True when service healthy."""
        with patch('httpx.Client') as MockClient:
            mock_instance = Mock()
            mock_response = MockResponse(status_code=200)
            mock_instance.get.return_value = mock_response
            MockClient.return_value = mock_instance

            client = EmbeddingClient()
            assert client.health_check() is True

    def test_health_check_unhealthy(self):
        """AC 1.4.2: health_check() returns False when service down."""
        with patch('httpx.Client') as MockClient:
            mock_instance = Mock()
            import httpx
            mock_instance.get.side_effect = httpx.ConnectError("Connection refused")
            MockClient.return_value = mock_instance

            client = EmbeddingClient()
            assert client.health_check() is False

    def test_batch_embedding_support(self):
        """AC 1.4.2: Supports batch embedding operations."""
        with patch('httpx.Client') as MockClient:
            mock_instance = Mock()
            # Simulate batch response
            mock_response = MockResponse(
                status_code=200,
                json_data={
                    "embeddings": [[0.1] * 10, [0.2] * 10, [0.3] * 10],
                }
            )
            mock_instance.post.return_value = mock_response
            MockClient.return_value = mock_instance

            client = EmbeddingClient()
            embeddings = client.embed(["text1", "text2", "text3"])

            # Verify batch processing
            assert len(embeddings) == 3
            mock_instance.post.assert_called_once()  # Single request for batch

    def test_uses_structured_logging(self):
        """AC 1.4.2: Uses structured logging with extras dict."""
        # This test verifies the module imports logging correctly
        from src.memory import embeddings as embed_module
        assert hasattr(embed_module, 'logger')


if __name__ == "__main__":
    print("Running embedding client tests...")
    test = TestEmbeddingClient()

    tests = [
        ("test_client_initialization", test.test_client_initialization),
        ("test_embed_success", test.test_embed_success),
        ("test_embed_timeout_raises_error", test.test_embed_timeout_raises_error),
        ("test_embed_http_error_raises_error", test.test_embed_http_error_raises_error),
        ("test_health_check_healthy", test.test_health_check_healthy),
        ("test_health_check_unhealthy", test.test_health_check_unhealthy),
        ("test_batch_embedding_support", test.test_batch_embedding_support),
        ("test_uses_structured_logging", test.test_uses_structured_logging),
    ]

    passed = 0
    failed = 0
    for name, test_func in tests:
        try:
            test_func()
            print(f"  ✓ {name}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
