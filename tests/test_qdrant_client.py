"""Unit tests for Qdrant client wrapper.

Tests AC 1.4.3 - Qdrant Client Wrapper functionality.
"""

import sys

sys.path.insert(0, ".")

from unittest.mock import Mock, patch

from src.memory.config import MemoryConfig
from src.memory.qdrant_client import (
    QdrantUnavailable,
    check_qdrant_health,
    get_qdrant_client,
)


class TestQdrantClient:
    """Test Qdrant client wrapper functionality."""

    def setup_method(self):
        """Clear client cache between tests."""
        from src.memory.qdrant_client import _client_cache

        _client_cache.clear()

    def test_get_qdrant_client_creates_client(self):
        """AC 1.4.3: get_qdrant_client() returns configured QdrantClient."""
        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            mock_instance = Mock()
            MockQdrantClient.return_value = mock_instance

            config = MemoryConfig()
            get_qdrant_client(config)

            # Verify QdrantClient was created with correct parameters
            MockQdrantClient.assert_called_once()
            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["host"] == config.qdrant_host
            assert call_kwargs["port"] == config.qdrant_port
            assert "timeout" in call_kwargs

    def test_get_qdrant_client_uses_default_config(self):
        """AC 1.4.3: Uses get_config() if no config provided."""
        with (
            patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient,
            patch("src.memory.qdrant_client.get_config") as mock_get_config,
        ):
            mock_config = MemoryConfig()
            mock_get_config.return_value = mock_config
            mock_instance = Mock()
            MockQdrantClient.return_value = mock_instance

            get_qdrant_client()

            # Verify get_config() was called
            mock_get_config.assert_called_once()
            # Verify client was created
            assert MockQdrantClient.called

    def test_get_qdrant_client_sets_timeout(self):
        """AC 1.4.3: Sets appropriate timeout values."""
        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            mock_instance = Mock()
            MockQdrantClient.return_value = mock_instance

            get_qdrant_client()

            # Verify timeout was set
            call_kwargs = MockQdrantClient.call_args.kwargs
            assert "timeout" in call_kwargs
            assert call_kwargs["timeout"] == 10

    def test_check_qdrant_health_healthy(self):
        """AC 1.4.3: check_qdrant_health() returns True when accessible."""
        mock_client = Mock()
        mock_collections = Mock()
        mock_client.get_collections.return_value = mock_collections

        result = check_qdrant_health(mock_client)

        assert result is True
        mock_client.get_collections.assert_called_once()

    def test_check_qdrant_health_unhealthy(self):
        """AC 1.4.3: check_qdrant_health() returns False on error."""
        mock_client = Mock()
        mock_client.get_collections.side_effect = Exception("Connection refused")

        result = check_qdrant_health(mock_client)

        assert result is False

    def test_check_qdrant_health_logs_failures(self):
        """AC 1.4.3: Logs failures with structured extras."""
        mock_client = Mock()
        mock_client.get_collections.side_effect = Exception("Qdrant timeout")

        with patch("src.memory.qdrant_client.logger") as mock_logger:
            check_qdrant_health(mock_client)

            # Verify structured logging was used
            assert mock_logger.warning.called
            call_args = mock_logger.warning.call_args
            assert "extra" in call_args.kwargs
            assert "error" in call_args.kwargs["extra"]

    def test_qdrant_unavailable_exception_exists(self):
        """AC 1.4.3: QdrantUnavailable exception is defined."""
        # Should be able to raise and catch
        try:
            raise QdrantUnavailable("Test error")
        except QdrantUnavailable as e:
            assert "Test error" in str(e)

    def test_module_has_all_exports(self):
        """AC 1.4.3: Module exports required functions."""
        from src.memory import qdrant_client as qc_module

        assert hasattr(qc_module, "get_qdrant_client")
        assert hasattr(qc_module, "check_qdrant_health")
        assert hasattr(qc_module, "QdrantUnavailable")
        assert hasattr(qc_module, "__all__")


if __name__ == "__main__":
    print("Running Qdrant client tests...")
    test = TestQdrantClient()

    tests = [
        (
            "test_get_qdrant_client_creates_client",
            test.test_get_qdrant_client_creates_client,
        ),
        (
            "test_get_qdrant_client_uses_default_config",
            test.test_get_qdrant_client_uses_default_config,
        ),
        (
            "test_get_qdrant_client_sets_timeout",
            test.test_get_qdrant_client_sets_timeout,
        ),
        ("test_check_qdrant_health_healthy", test.test_check_qdrant_health_healthy),
        ("test_check_qdrant_health_unhealthy", test.test_check_qdrant_health_unhealthy),
        (
            "test_check_qdrant_health_logs_failures",
            test.test_check_qdrant_health_logs_failures,
        ),
        (
            "test_qdrant_unavailable_exception_exists",
            test.test_qdrant_unavailable_exception_exists,
        ),
        ("test_module_has_all_exports", test.test_module_has_all_exports),
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
            import traceback

            traceback.print_exc()
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
