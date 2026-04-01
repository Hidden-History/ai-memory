"""Unit tests for Qdrant client wrapper.

Tests AC 1.4.3 - Qdrant Client Wrapper functionality.
"""

import hashlib
import sys
from unittest.mock import Mock, patch

from pydantic import SecretStr

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
            assert call_kwargs["timeout"] == 30  # TASK-023: increased from 10 to 30

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

    def test_get_qdrant_client_uses_grpc(self):
        """TD-107: get_qdrant_client() passes prefer_grpc=True and grpc_port."""
        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            mock_instance = Mock()
            MockQdrantClient.return_value = mock_instance

            config = MemoryConfig()
            get_qdrant_client(config)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs.get("prefer_grpc") is True
            assert "grpc_port" in call_kwargs

    def test_get_qdrant_client_grpc_port_default(self, monkeypatch):
        """TD-107: Default gRPC port is 6334."""
        monkeypatch.delenv("QDRANT_GRPC_PORT", raising=False)
        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            mock_instance = Mock()
            MockQdrantClient.return_value = mock_instance

            config = MemoryConfig()
            get_qdrant_client(config)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["grpc_port"] == 6334

    def test_get_qdrant_client_grpc_port_from_env(self):
        """TD-107: gRPC port is read from QDRANT_GRPC_PORT env var."""
        with (
            patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient,
            patch.dict("os.environ", {"QDRANT_GRPC_PORT": "6335"}),
        ):
            mock_instance = Mock()
            MockQdrantClient.return_value = mock_instance

            config = MemoryConfig()
            get_qdrant_client(config)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["grpc_port"] == 6335

    def test_get_qdrant_client_falls_back_on_grpc_error(self):
        """TD-107: Falls back to HTTP client when gRPC init raises."""
        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("prefer_grpc"):
                raise RuntimeError("gRPC not available")
            return Mock()

        with patch("src.memory.qdrant_client.QdrantClient", side_effect=side_effect):
            config = MemoryConfig()
            client = get_qdrant_client(config)

            # Two calls: first with gRPC (fails), second without (succeeds)
            assert call_count == 2
            assert client is not None

    def test_get_qdrant_client_fallback_has_no_grpc(self):
        """TD-107: HTTP fallback client is created without prefer_grpc."""
        calls_kwargs = []

        def side_effect(**kwargs):
            calls_kwargs.append(kwargs)
            if kwargs.get("prefer_grpc"):
                raise RuntimeError("gRPC not available")
            return Mock()

        with patch("src.memory.qdrant_client.QdrantClient", side_effect=side_effect):
            config = MemoryConfig()
            get_qdrant_client(config)

            # Second call (fallback) must not include prefer_grpc
            assert len(calls_kwargs) == 2
            assert "prefer_grpc" not in calls_kwargs[1]

    def test_get_qdrant_client_falls_back_on_grpc_probe_error(self):
        """TD-107: Falls back to HTTP when gRPC probe (get_collections) raises."""
        http_client = Mock()
        grpc_client = Mock()
        grpc_client.get_collections.side_effect = RuntimeError(
            "gRPC connection refused"
        )

        def side_effect(**kwargs):
            return grpc_client if kwargs.get("prefer_grpc") else http_client

        with patch("src.memory.qdrant_client.QdrantClient", side_effect=side_effect):
            config = MemoryConfig()
            result = get_qdrant_client(config)

        assert result is http_client

    def test_cache_key_excludes_raw_api_key(self):
        """TD-371: Raw API key must not appear in _client_cache key; only the 8-char SHA-256 fingerprint."""
        from src.memory.qdrant_client import _client_cache

        raw_key = "super-secret-qdrant-api-key-value"
        # model_construct bypasses Pydantic frozen + validation intentionally:
        # MemoryConfig is immutable after construction, so we use model_construct
        # to inject a known key value without triggering validation errors.
        config = MemoryConfig.model_construct(
            qdrant_host="localhost",
            qdrant_port=6333,
            qdrant_api_key=SecretStr(raw_key),
            qdrant_use_https=False,
            qdrant_timeout=30,
        )

        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            MockQdrantClient.return_value = Mock()
            get_qdrant_client(config)

        # Exactly one cache entry should have been created
        assert len(_client_cache) == 1
        cache_key = next(iter(_client_cache))

        # Raw secret must not appear in the cache key
        assert raw_key not in cache_key

        # The key should contain the 8-character hex fingerprint derived from the key
        expected_fingerprint = hashlib.sha256(raw_key.encode()).hexdigest()[:8]
        assert expected_fingerprint in cache_key

    def test_read_only_key_used_when_available(self):
        """TD-333: read_only=True prefers qdrant_read_only_api_key."""
        ro_key = "read-only-key-value"
        rw_key = "read-write-key-value"
        config = MemoryConfig.model_construct(
            qdrant_host="localhost",
            qdrant_port=6333,
            qdrant_api_key=SecretStr(rw_key),
            qdrant_read_only_api_key=SecretStr(ro_key),
            qdrant_use_https=False,
            qdrant_timeout=30,
        )

        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            MockQdrantClient.return_value = Mock()
            get_qdrant_client(config, read_only=True)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["api_key"] == ro_key

    def test_read_only_falls_back_to_main_key(self):
        """TD-333: read_only=True falls back to qdrant_api_key when no RO key."""
        rw_key = "read-write-key-value"
        config = MemoryConfig.model_construct(
            qdrant_host="localhost",
            qdrant_port=6333,
            qdrant_api_key=SecretStr(rw_key),
            qdrant_read_only_api_key=None,
            qdrant_use_https=False,
            qdrant_timeout=30,
        )

        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            MockQdrantClient.return_value = Mock()
            get_qdrant_client(config, read_only=True)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["api_key"] == rw_key

    def test_read_only_both_keys_none(self):
        """TD-333: read_only=True with both keys None passes api_key=None to client."""
        config = MemoryConfig.model_construct(
            qdrant_host="localhost",
            qdrant_port=6333,
            qdrant_api_key=None,
            qdrant_read_only_api_key=None,
            qdrant_use_https=False,
            qdrant_timeout=30,
        )

        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            MockQdrantClient.return_value = Mock()
            get_qdrant_client(config, read_only=True)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["api_key"] is None

    def test_write_client_ignores_read_only_key(self):
        """TD-333: read_only=False (default) uses qdrant_api_key."""
        ro_key = "read-only-key-value"
        rw_key = "read-write-key-value"
        config = MemoryConfig.model_construct(
            qdrant_host="localhost",
            qdrant_port=6333,
            qdrant_api_key=SecretStr(rw_key),
            qdrant_read_only_api_key=SecretStr(ro_key),
            qdrant_use_https=False,
            qdrant_timeout=30,
        )

        with patch("src.memory.qdrant_client.QdrantClient") as MockQdrantClient:
            MockQdrantClient.return_value = Mock()
            get_qdrant_client(config, read_only=False)

            call_kwargs = MockQdrantClient.call_args.kwargs
            assert call_kwargs["api_key"] == rw_key

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
