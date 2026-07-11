"""Unit tests for scripts/memory/post_work_store_async.py.

Tests async storage of post-work summaries to Qdrant via MemoryStorage.
Covers: valid payload routing, Qdrant unavailable handling, payload validation
(missing content, missing metadata), and main() entry point.
"""

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestPostStoreMetricLabels:
    """TD-715: the post-store Prometheus push must supply the declared label set.

    aimemory_captures_total declares hook_type/status/project/collection and
    aimemory_dedup_events_total declares action/collection/project. A missing
    label raises 'Incorrect label names', which store_memory_async swallows as a
    validation_failed ERROR — so the child counter stays at 0 on the broken path.
    Asserting the child increments proves the corrected label set validated.
    """

    @pytest.mark.asyncio
    async def test_success_increments_capture_counter_with_collection_label(
        self, valid_decision_payload
    ):
        from prometheus_client import CollectorRegistry, Counter

        from memory.config import COLLECTION_DISCUSSIONS

        reg = CollectorRegistry()
        captures = Counter(
            "td715_captures_total",
            "test capture counter",
            ["hook_type", "status", "project", "collection"],
            registry=reg,
        )

        mock_storage = MagicMock()
        mock_storage.store_memory.return_value = {
            "status": "stored",
            "memory_id": "id-715-a",
            "embedding_status": "complete",
        }
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with (
            patch.object(pwsav, "MemoryStorage", mock_storage_cls),
            patch.object(pwsav, "memory_captures_total", captures),
            patch("memory.project.resolve_project_id", return_value="ai-memory-module"),
        ):
            await pwsav.store_memory_async(valid_decision_payload)

        child = captures.labels(
            hook_type="SubagentStop",
            status="success",
            project="ai-memory-module",
            collection=COLLECTION_DISCUSSIONS,
        )
        assert child._value.get() == 1.0

    @pytest.mark.asyncio
    async def test_duplicate_increments_dedup_counter_with_action_and_collection(
        self, valid_decision_payload
    ):
        from prometheus_client import CollectorRegistry, Counter

        from memory.config import COLLECTION_DISCUSSIONS

        reg = CollectorRegistry()
        dedup = Counter(
            "td715_dedup_events_total",
            "test dedup counter",
            ["action", "collection", "project"],
            registry=reg,
        )

        mock_storage = MagicMock()
        mock_storage.store_memory.return_value = {
            "status": "duplicate",
            "memory_id": "id-715-b",
            "embedding_status": "skipped",
        }
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with (
            patch.object(pwsav, "MemoryStorage", mock_storage_cls),
            patch.object(pwsav, "memory_captures_total", None),
            patch.object(pwsav, "deduplication_events_total", dedup),
            patch("memory.project.resolve_project_id", return_value="ai-memory-module"),
        ):
            await pwsav.store_memory_async(valid_decision_payload)

        child = dedup.labels(
            action="skipped_duplicate",
            collection=COLLECTION_DISCUSSIONS,
            project="ai-memory-module",
        )
        assert child._value.get() == 1.0

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_increments_failed_capture_counter(
        self, valid_decision_payload
    ):
        """QdrantUnavailable records hook_type/failed/project/collection='unknown'.

        Asserts the failure-path counter push (except QdrantUnavailable block) uses
        the declared label set; a missing label would raise 'Incorrect label names'
        (swallowed) and leave the child at 0.
        """
        from prometheus_client import CollectorRegistry, Counter

        from memory.qdrant_client import QdrantUnavailable

        reg = CollectorRegistry()
        captures = Counter(
            "td715_fail_qdrant_captures_total",
            "test failure counter (qdrant unavailable)",
            ["hook_type", "status", "project", "collection"],
            registry=reg,
        )

        mock_storage = MagicMock()
        mock_storage.store_memory.side_effect = QdrantUnavailable("down")
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with (
            patch.object(pwsav, "MemoryStorage", mock_storage_cls),
            patch.object(pwsav, "memory_captures_total", captures),
            patch.object(pwsav, "queue_operation", MagicMock()),
            patch("memory.project.resolve_project_id", return_value="ai-memory-module"),
        ):
            await pwsav.store_memory_async(valid_decision_payload)

        child = captures.labels(
            hook_type="SubagentStop",
            status="failed",
            project="ai-memory-module",
            collection="unknown",
        )
        assert child._value.get() == 1.0

    @pytest.mark.asyncio
    async def test_generic_exception_increments_failed_capture_counter(
        self, valid_decision_payload
    ):
        """Unexpected Exception records hook_type/failed/project/collection='unknown'.

        Asserts the failure-path counter push (except Exception block) uses the
        declared label set; a missing label would raise 'Incorrect label names'
        (swallowed) and leave the child at 0.
        """
        from prometheus_client import CollectorRegistry, Counter

        reg = CollectorRegistry()
        captures = Counter(
            "td715_fail_exc_captures_total",
            "test failure counter (generic exception)",
            ["hook_type", "status", "project", "collection"],
            registry=reg,
        )

        mock_storage = MagicMock()
        mock_storage.store_memory.side_effect = RuntimeError("unexpected failure")
        mock_storage_cls = MagicMock(return_value=mock_storage)

        with (
            patch.object(pwsav, "MemoryStorage", mock_storage_cls),
            patch.object(pwsav, "memory_captures_total", captures),
            patch.object(pwsav, "queue_operation", MagicMock()),
            patch("memory.project.resolve_project_id", return_value="ai-memory-module"),
        ):
            await pwsav.store_memory_async(valid_decision_payload)

        child = captures.labels(
            hook_type="SubagentStop",
            status="failed",
            project="ai-memory-module",
            collection="unknown",
        )
        assert child._value.get() == 1.0


class TestPostWorkHookTimeoutCoherence:
    """TD-782/788: the post-work store path must inherit the SAME coherent HOOK_TIMEOUT
    ceiling as store_async/error_store_async, so its outer asyncio.wait_for cannot fire
    mid-embed (< the embedding client's coordinated budget) and cancel the store. The
    old local get_timeout() duplicate (default 60s) was consolidated onto
    memory.hooks_common.get_hook_timeout() (default 90s).
    """

    def test_uses_shared_hook_timeout_helper_not_local_duplicate(self):
        """The path routes through the consolidated helper, and the stale local
        get_timeout() duplicate is gone."""
        import memory.hooks_common as hc

        assert pwsav.get_hook_timeout is hc.get_hook_timeout
        assert not hasattr(pwsav, "get_timeout")

    def test_default_ceiling_is_coherent_90s(self, monkeypatch):
        """With HOOK_TIMEOUT unset, the post-work path's ceiling is the coherent 90s
        (was an incoherent 60s before consolidation)."""
        monkeypatch.delenv("HOOK_TIMEOUT", raising=False)
        assert pwsav.get_hook_timeout() == 90

    def test_main_applies_hook_timeout_to_wait_for(self, valid_decision_payload):
        """main_async() passes get_hook_timeout()'s value to the outer wait_for that
        bounds the whole store (incl. the embedding call)."""
        captured = {}

        async def fake_wait_for(coro, timeout=None):
            captured["timeout"] = timeout
            return await coro

        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(
                pwsav.sys, "stdin", io.StringIO(json.dumps(valid_decision_payload))
            ),
            patch.object(pwsav, "get_hook_timeout", return_value=4242),
            patch.object(pwsav, "store_memory_async", new=AsyncMock()),
            patch.object(pwsav.asyncio, "wait_for", side_effect=fake_wait_for),
        ):
            rc = pwsav.main()

        assert rc == 0
        # The coordinated ceiling (not a hardcoded 60) bounds the store coroutine.
        assert captured["timeout"] == 4242
