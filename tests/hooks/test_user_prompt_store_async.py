"""Unit tests for user_prompt_store_async.py hook.

Tests async storage of user prompts to the discussions collection.
Covers: small payload routing, quality gate skip, Qdrant unavailable handling,
and main() entry point robustness.
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

import user_prompt_store_async as upsav


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
    """EmbeddingClient mock that returns a fixed 768-dim vector."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.embed = MagicMock(return_value=[[0.1] * 768])
    return mock


@pytest.fixture
def substantive_hook_input():
    """Hook input with a substantive prompt that passes the quality gate."""
    return {
        "session_id": "test-session-upsav-001",
        "prompt": "What database connection pooling strategy did we decide on for the API service?",
        "turn_number": 3,
    }


class TestUserPromptStoreAsync:
    """Tests for user_prompt_store_async.store_user_message."""

    def test_small_payload_stores_to_discussions(
        self, mock_qdrant, mock_config, mock_embedding, substantive_hook_input
    ):
        """Substantive user prompt is stored to the discussions collection.

        Verifies collection routing and that the stored point carries the
        correct type and session_id in its payload.
        """
        with (
            patch.object(upsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(upsav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embedding),
            patch.object(upsav, "log_to_activity"),
            patch.object(upsav, "queue_operation"),
            patch.object(upsav, "detect_project", return_value="test-project"),
        ):
            result = upsav.store_user_message(substantive_hook_input)

        assert result is True
        assert len(mock_qdrant.upsert_calls) == 1
        call = mock_qdrant.upsert_calls[0]
        assert call["collection_name"] == "discussions"
        stored_point = call["points"][0]
        assert stored_point.payload["type"] == "user_message"
        assert (
            stored_point.payload["session_id"] == substantive_hook_input["session_id"]
        )

    def test_quality_gate_skips_short_message(
        self, mock_qdrant, mock_config, substantive_hook_input
    ):
        """Prompts with fewer than 4 words are skipped without storing."""
        hook_input = {**substantive_hook_input, "prompt": "yes ok"}
        with (
            patch.object(upsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(upsav, "get_config", return_value=mock_config),
            patch.object(upsav, "log_to_activity"),
            patch.object(upsav, "queue_operation"),
            patch.object(upsav, "detect_project", return_value="test-project"),
        ):
            result = upsav.store_user_message(hook_input)

        assert result is True
        assert len(mock_qdrant.upsert_calls) == 0

    def test_quality_gate_skips_low_value_message(
        self, mock_qdrant, mock_config, substantive_hook_input
    ):
        """Low-value acknowledgment text is skipped without storing."""
        hook_input = {**substantive_hook_input, "prompt": "nothing to add"}
        with (
            patch.object(upsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(upsav, "get_config", return_value=mock_config),
            patch.object(upsav, "log_to_activity"),
            patch.object(upsav, "queue_operation"),
            patch.object(upsav, "detect_project", return_value="test-project"),
        ):
            result = upsav.store_user_message(hook_input)

        assert result is True
        assert len(mock_qdrant.upsert_calls) == 0

    def test_qdrant_unavailable_queues_without_crash(
        self, mock_config, substantive_hook_input
    ):
        """QdrantUnavailable is caught; operation is queued and False is returned.

        The hook must never crash — Qdrant downtime should degrade to queuing,
        not an unhandled exception propagating to Claude.
        """
        from memory.qdrant_client import QdrantUnavailable

        failing_qdrant = MagicMock()
        failing_qdrant.scroll.side_effect = QdrantUnavailable("Qdrant not running")

        queue_mock = MagicMock()
        with (
            patch.object(upsav, "get_qdrant_client", return_value=failing_qdrant),
            patch.object(upsav, "get_config", return_value=mock_config),
            patch.object(upsav, "log_to_activity"),
            patch.object(upsav, "queue_operation", queue_mock),
            patch.object(upsav, "detect_project", return_value="test-project"),
        ):
            result = upsav.store_user_message(substantive_hook_input)

        assert result is False
        queue_mock.assert_called_once()

    def test_main_returns_1_on_malformed_stdin(self):
        """main() exits with code 1 when stdin contains invalid JSON."""
        with patch.object(sys, "stdin", io.StringIO("not-valid-json")):
            result = upsav.main()
        assert result == 1

    def test_main_returns_0_on_valid_input(
        self, mock_qdrant, mock_config, mock_embedding
    ):
        """main() reads JSON from stdin and returns 0 on successful storage."""
        hook_input = {
            "session_id": "test-session-upsav-main",
            "prompt": "What was the final decision about the authentication middleware strategy?",
            "turn_number": 1,
        }
        with (
            patch.object(sys, "stdin", io.StringIO(json.dumps(hook_input))),
            patch.object(upsav, "get_qdrant_client", return_value=mock_qdrant),
            patch.object(upsav, "get_config", return_value=mock_config),
            patch("memory.embeddings.EmbeddingClient", return_value=mock_embedding),
            patch.object(upsav, "log_to_activity"),
            patch.object(upsav, "queue_operation"),
            patch.object(upsav, "detect_project", return_value="test-project"),
        ):
            result = upsav.main()
        assert result == 0
