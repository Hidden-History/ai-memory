"""Unit tests for scripts/memory/post_work_store_async.py.

Tests async storage of post-work summaries to Qdrant via MemoryStorage.
Covers: valid payload routing, Qdrant unavailable handling, payload validation
(missing content, missing metadata), and main() entry point.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts/memory to path so module can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts/memory"))

import post_work_store_async as pwsav


@pytest.fixture
def valid_decision_payload():
    """Payload representing a post-work decision memory."""
    return {
        "content": (
            "Decided to use connection pooling with max_connections=20 per worker "
            "based on load test results showing optimal throughput at this setting."
        ),
        "metadata": {
            "type": "decision",
            "group_id": "ai-memory-module",
            "session_id": "test-session-pwsav-001",
            "source_hook": "SubagentStop",
            "cwd": "/mnt/e/projects/dev-ai-memory/ai-memory",
            "story_id": "STORY-042",
            "agent": "dev-agent",
        },
    }


@pytest.fixture
def valid_convention_payload():
    """Payload representing a post-work convention memory."""
    return {
        "content": "All Qdrant collection names use kebab-case (e.g. code-patterns).",
        "metadata": {
            "type": "guideline",
            "group_id": "ai-memory-module",
            "session_id": "test-session-pwsav-002",
            "source_hook": "SubagentStop",
            "cwd": "/mnt/e/projects/dev-ai-memory/ai-memory",
            "story_id": "STORY-043",
        },
    }


class TestPostWorkStoreAsync:
    """Tests for post_work_store_async.store_memory_async and main."""

    @pytest.mark.asyncio
    async def test_decision_payload_calls_storage(self, valid_decision_payload):
        """A valid decision payload is forwarded to MemoryStorage.store_memory."""
        mock_storage = MagicMock()
        mock_storage.store_memory.return_value = {
            "status": "stored",
            "memory_id": "test-uuid-001",
            "embedding_status": "complete",
        }
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with patch.object(pwsav, "MemoryStorage", mock_storage_cls):
            await pwsav.store_memory_async(valid_decision_payload)

        mock_storage.store_memory.assert_called_once()
        call_kwargs = mock_storage.store_memory.call_args[1]
        assert call_kwargs["content"] == valid_decision_payload["content"]
        assert call_kwargs["session_id"] == "test-session-pwsav-001"

    @pytest.mark.asyncio
    async def test_convention_payload_routes_to_conventions_collection(
        self, valid_convention_payload
    ):
        """A guideline-type payload is stored to the conventions collection."""
        from memory.config import COLLECTION_CONVENTIONS

        mock_storage = MagicMock()
        mock_storage.store_memory.return_value = {
            "status": "stored",
            "memory_id": "test-uuid-002",
            "embedding_status": "complete",
        }
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with patch.object(pwsav, "MemoryStorage", mock_storage_cls):
            await pwsav.store_memory_async(valid_convention_payload)

        call_kwargs = mock_storage.store_memory.call_args[1]
        assert call_kwargs["collection"] == COLLECTION_CONVENTIONS

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_queues_without_crash(
        self, valid_decision_payload
    ):
        """QdrantUnavailable from MemoryStorage is caught; operation is queued.

        post_work_store_async must not propagate exceptions — Qdrant downtime
        degrades to queuing.
        """
        from memory.qdrant_client import QdrantUnavailable

        mock_storage = MagicMock()
        mock_storage.store_memory.side_effect = QdrantUnavailable("Qdrant not running")
        mock_storage_cls = MagicMock(return_value=mock_storage)

        queue_mock = MagicMock()
        with (
            patch.object(pwsav, "MemoryStorage", mock_storage_cls),
            patch.object(pwsav, "queue_operation", queue_mock),
            patch.object(pwsav, "memory_captures_total", None),
        ):
            # Must not raise
            await pwsav.store_memory_async(valid_decision_payload)

        queue_mock.assert_called_once()

    def test_main_returns_1_on_missing_content(self):
        """main() returns 1 when the payload is missing the 'content' field."""
        bad_payload = {"metadata": {"type": "decision", "group_id": "proj"}}
        with patch.object(sys, "stdin", io.StringIO(json.dumps(bad_payload))):
            result = pwsav.main()
        assert result == 1

    def test_main_returns_1_on_missing_metadata(self):
        """main() returns 1 when the payload is missing the 'metadata' field."""
        bad_payload = {"content": "Some content without metadata"}
        with patch.object(sys, "stdin", io.StringIO(json.dumps(bad_payload))):
            result = pwsav.main()
        assert result == 1

    def test_main_returns_1_on_malformed_json(self):
        """main() returns 1 when stdin is not valid JSON."""
        with patch.object(sys, "stdin", io.StringIO("not-json")):
            result = pwsav.main()
        assert result == 1

    def test_main_returns_0_on_valid_payload(self, valid_decision_payload):
        """main() returns 0 when payload is valid and storage succeeds."""
        mock_storage = MagicMock()
        mock_storage.store_memory.return_value = {
            "status": "stored",
            "memory_id": "test-uuid-main",
            "embedding_status": "complete",
        }
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with (
            patch.object(sys, "stdin", io.StringIO(json.dumps(valid_decision_payload))),
            patch.object(pwsav, "MemoryStorage", mock_storage_cls),
        ):
            result = pwsav.main()
        assert result == 0
