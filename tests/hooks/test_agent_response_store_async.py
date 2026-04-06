"""Unit tests for agent_response_store_async.py hook.

Tests async storage of agent responses to the discussions collection.
Covers: small payload routing, quality gate skips (acknowledgment + too-short),
Qdrant unavailable handling, and main() entry point robustness.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add tests dir for mock imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from mocks.qdrant_mock import MockQdrantClient

# Add hook scripts dir so module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent / ".claude/hooks/scripts"))

import agent_response_store_async as arsav


@pytest.fixture
def mock_qdrant():
    """Fresh in-memory Qdrant mock, reset before each test."""
    client = MockQdrantClient()
    client.reset()
    return client


@pytest.fixture
def mock_config():
    """Minimal MemoryConfig mock — disables security scan and hybrid search."""
    config = MagicMock()
    config.embedding_dimension = 768
    config.security_scanning_enabled = False
    config.hybrid_search_enabled = False
    return config


@pytest.fixture
def mock_embedding():
    """EmbeddingClient mock returning a fixed 768-dim vector."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.embed = MagicMock(return_value=[[0.1] * 768])
    return mock


@pytest.fixture
def substantive_store_data():
    """Store data with a response long enough to pass the quality gate."""
    return {
        "session_id": "test-session-arsav-001",
        "response_text": (
            "The connection pooling strategy uses a maximum of 20 connections per worker "
            "process, with a 30-second idle timeout. This was chosen to balance throughput "
            "with resource usage based on the load testing we performed."
        ),
        "turn_number": 5,
    }


class TestAgentResponseStoreAsync:
    """Tests for agent_response_store_async.store_agent_response."""

    def test_small_payload_stores_to_discussions(
        self, mock_qdrant, mock_config, mock_embedding, substantive_store_data
    ):
        """Substantive agent response is stored to the discussions collection.

        Verifies collection routing and that the stored point carries the
        correct type and session_id in its payload.
        """
        with (
            patch.object(arsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(arsav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embedding),
            patch.object(arsav, "log_to_activity"),
            patch.object(arsav, "queue_operation"),
            patch.object(arsav, "detect_project", return_value="test-project"),
        ):
            result = arsav.store_agent_response(substantive_store_data)

        assert result is True
        assert len(mock_qdrant.upsert_calls) == 1
        call = mock_qdrant.upsert_calls[0]
        assert call["collection_name"] == "discussions"
        stored_point = call["points"][0]
        assert stored_point.payload["type"] == "agent_response"
        assert (
            stored_point.payload["session_id"] == substantive_store_data["session_id"]
        )

    def test_quality_gate_skips_acknowledgment_pattern(
        self, mock_qdrant, mock_config, substantive_store_data
    ):
        """Single-word acknowledgments matching _ACK_PATTERN are skipped."""
        store_data = {**substantive_store_data, "response_text": "understood"}
        with (
            patch.object(arsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(arsav, "get_config", return_value=mock_config),
            patch.object(arsav, "log_to_activity"),
            patch.object(arsav, "queue_operation"),
            patch.object(arsav, "detect_project", return_value="test-project"),
        ):
            result = arsav.store_agent_response(store_data)

        assert result is True
        assert len(mock_qdrant.upsert_calls) == 0

    def test_quality_gate_skips_too_short_response(
        self, mock_qdrant, mock_config, substantive_store_data
    ):
        """Responses under 50 characters are skipped without storing."""
        store_data = {
            **substantive_store_data,
            "response_text": "Done, check the logs.",
        }
        assert len(store_data["response_text"].strip()) < 50
        with (
            patch.object(arsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(arsav, "get_config", return_value=mock_config),
            patch.object(arsav, "log_to_activity"),
            patch.object(arsav, "queue_operation"),
            patch.object(arsav, "detect_project", return_value="test-project"),
        ):
            result = arsav.store_agent_response(store_data)

        assert result is True
        assert len(mock_qdrant.upsert_calls) == 0

    def test_qdrant_unavailable_queues_without_crash(
        self, mock_config, substantive_store_data
    ):
        """QdrantUnavailable is caught; operation is queued and False is returned.

        Agent responses must never crash the hook — Qdrant downtime degrades
        to queuing.
        """
        from memory.qdrant_client import QdrantUnavailable

        failing_qdrant = MagicMock()
        failing_qdrant.scroll.side_effect = QdrantUnavailable("Qdrant offline")

        queue_mock = MagicMock()
        with (
            patch.object(arsav, "get_qdrant_client", return_value=failing_qdrant),
            patch.object(arsav, "get_config", return_value=mock_config),
            patch.object(arsav, "log_to_activity"),
            patch.object(arsav, "queue_operation", queue_mock),
            patch.object(arsav, "detect_project", return_value="test-project"),
        ):
            result = arsav.store_agent_response(substantive_store_data)

        assert result is False
        queue_mock.assert_called_once()

    def test_main_returns_1_on_malformed_stdin(self):
        """main() exits with code 1 when stdin is not valid JSON."""
        with patch.object(sys, "stdin", io.StringIO("{broken json")):
            result = arsav.main()
        assert result == 1

    def test_main_returns_0_on_valid_input(
        self, mock_qdrant, mock_config, mock_embedding
    ):
        """main() reads store data from stdin and returns 0 on success."""
        store_data = {
            "session_id": "test-session-arsav-main",
            "response_text": (
                "I have updated the database migration scripts to use the new pooling "
                "configuration. The changes are in db/migrations/0042_pool_config.py "
                "and have been verified against the staging environment."
            ),
            "turn_number": 2,
        }
        with (
            patch.object(sys, "stdin", io.StringIO(json.dumps(store_data))),
            patch.object(arsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(arsav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embedding),
            patch.object(arsav, "log_to_activity"),
            patch.object(arsav, "queue_operation"),
            patch.object(arsav, "detect_project", return_value="test-project"),
        ):
            result = arsav.main()
        assert result == 0
