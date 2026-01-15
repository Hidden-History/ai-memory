"""Unit tests for health check utilities.

Test suite for src/memory/health.py - Service health checks and fallback mode logic.
Follows 2025 best practices for health checks with mocks.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.memory.health import check_services, get_fallback_mode


class TestCheckServices:
    """Test check_services() function with various service states."""

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_all_services_healthy(self, mock_qdrant_health, mock_embedding_client, mock_get_client):
        """All services healthy should return all True."""
        mock_get_client.return_value = Mock()
        mock_qdrant_health.return_value = True
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = True
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        assert result["qdrant"] is True
        assert result["embedding"] is True
        assert result["all_healthy"] is True

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_qdrant_down_embedding_up(self, mock_qdrant_health, mock_embedding_client, mock_get_client):
        """Qdrant down, embedding up."""
        mock_get_client.return_value = Mock()
        mock_qdrant_health.return_value = False
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = True
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        assert result["qdrant"] is False
        assert result["embedding"] is True
        assert result["all_healthy"] is False

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_qdrant_up_embedding_down(self, mock_qdrant_health, mock_embedding_client, mock_get_client):
        """Qdrant up, embedding down."""
        mock_get_client.return_value = Mock()
        mock_qdrant_health.return_value = True
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = False
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        assert result["qdrant"] is True
        assert result["embedding"] is False
        assert result["all_healthy"] is False

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_both_services_down(self, mock_qdrant_health, mock_embedding_client, mock_get_client):
        """Both services down."""
        mock_get_client.return_value = Mock()
        mock_qdrant_health.return_value = False
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = False
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        assert result["qdrant"] is False
        assert result["embedding"] is False
        assert result["all_healthy"] is False

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_never_raises_exception(self, mock_qdrant_health, mock_embedding_client, mock_get_client):
        """check_services() should never raise exceptions."""
        # Simulate exceptions from both services
        mock_get_client.return_value = Mock()
        mock_qdrant_health.side_effect = Exception("Qdrant connection error")
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.side_effect = Exception("Embedding timeout")
        mock_embedding_client.return_value = mock_ec_instance

        # Should not raise, should return status dict
        result = check_services()

        assert isinstance(result, dict)
        assert "qdrant" in result
        assert "embedding" in result
        assert "all_healthy" in result
        # Both should be False due to exceptions
        assert result["qdrant"] is False
        assert result["embedding"] is False
        assert result["all_healthy"] is False

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_logs_service_status(self, mock_qdrant_health, mock_embedding_client, mock_get_client, caplog):
        """check_services() should log health check results."""
        import logging
        caplog.set_level(logging.INFO)

        mock_get_client.return_value = Mock()
        mock_qdrant_health.return_value = True
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = False
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        # Verify logging occurred (structured logging)
        assert len(caplog.records) > 0
        # Should have logged the health check results
        assert any("service_health" in record.message for record in caplog.records)

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_completes_quickly(self, mock_qdrant_health, mock_embedding_client, mock_get_client):
        """check_services() should complete within 2 seconds (NFR-P1)."""
        import time

        mock_get_client.return_value = Mock()
        mock_qdrant_health.return_value = True
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = True
        mock_embedding_client.return_value = mock_ec_instance

        start_time = time.time()
        result = check_services()
        elapsed_time = time.time() - start_time

        # Should complete well under 2 seconds
        assert elapsed_time < 2.0
        assert result["all_healthy"] is True


class TestGetFallbackMode:
    """Test get_fallback_mode() decision logic."""

    def test_normal_mode_when_all_healthy(self):
        """All healthy → normal mode."""
        health = {"qdrant": True, "embedding": True, "all_healthy": True}
        mode = get_fallback_mode(health)
        assert mode == "normal"

    def test_queue_to_file_when_qdrant_down(self):
        """Qdrant down → queue_to_file mode."""
        health = {"qdrant": False, "embedding": True, "all_healthy": False}
        mode = get_fallback_mode(health)
        assert mode == "queue_to_file"

    def test_pending_embedding_when_embedding_down(self):
        """Embedding down → pending_embedding mode."""
        health = {"qdrant": True, "embedding": False, "all_healthy": False}
        mode = get_fallback_mode(health)
        assert mode == "pending_embedding"

    def test_passthrough_when_both_down(self):
        """Both down → passthrough mode."""
        health = {"qdrant": False, "embedding": False, "all_healthy": False}
        mode = get_fallback_mode(health)
        assert mode == "passthrough"

    def test_fallback_mode_with_edge_cases(self):
        """Test edge cases for fallback mode logic."""
        # All False
        health = {"qdrant": False, "embedding": False, "all_healthy": False}
        assert get_fallback_mode(health) == "passthrough"

        # Qdrant only down (embedding up) - should prioritize qdrant
        health = {"qdrant": False, "embedding": True, "all_healthy": False}
        assert get_fallback_mode(health) == "queue_to_file"


class TestHealthCheckIntegration:
    """Test health check integration with real client patterns."""

    @patch("src.memory.health.get_qdrant_client")
    @patch("src.memory.health.check_qdrant_health")
    @patch("src.memory.health.EmbeddingClient")
    def test_uses_get_qdrant_client(
        self, mock_embedding_client, mock_check_qdrant, mock_get_qdrant
    ):
        """check_services() should use get_qdrant_client()."""
        mock_client = Mock()
        mock_get_qdrant.return_value = mock_client
        mock_check_qdrant.return_value = True

        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = True
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        # Verify get_qdrant_client was called
        mock_get_qdrant.assert_called_once()
        # Verify check_qdrant_health was called with client
        mock_check_qdrant.assert_called_once_with(mock_client)
        assert result["qdrant"] is True

    @patch("src.memory.health.EmbeddingClient")
    @patch("src.memory.health.check_qdrant_health")
    def test_creates_embedding_client_instance(
        self, mock_qdrant_health, mock_embedding_client
    ):
        """check_services() should create EmbeddingClient instance."""
        mock_qdrant_health.return_value = True
        mock_ec_instance = Mock()
        mock_ec_instance.health_check.return_value = True
        mock_embedding_client.return_value = mock_ec_instance

        result = check_services()

        # Verify EmbeddingClient was instantiated
        mock_embedding_client.assert_called_once()
        # Verify health_check was called on instance
        mock_ec_instance.health_check.assert_called_once()
        assert result["embedding"] is True
