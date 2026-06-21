"""BUG-322: agent_* memory types must route to the discussions collection.

The authoritative store path (``MemoryStorage.store_agent_memory``) stores the
four agent memory types — ``agent_handoff``, ``agent_insight``,
``agent_memory``, ``agent_task`` — plus ``decision`` into
``COLLECTION_DISCUSSIONS``. Two downstream selection sites independently mapped
memory types to collections and omitted the four ``agent_*`` types, so on the
async/retry paths those records were routed to ``COLLECTION_CODE_PATTERNS``
instead. These tests pin both sites to the authoritative collection.

No live Qdrant: the retry site is a pure function; the post-work site is driven
with a mocked ``MemoryStorage``.
"""

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RETRY_SCRIPT = _REPO_ROOT / "scripts" / "memory" / "process_retry_queue.py"
_POST_WORK_SCRIPT = _REPO_ROOT / "scripts" / "memory" / "post_work_store_async.py"

AGENT_TYPES = ["agent_handoff", "agent_insight", "agent_memory", "agent_task"]


def _load_script(name: str, path: Path):
    """Import a scripts/memory/*.py file as a standalone module."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRetryQueueCollectionRouting:
    """scripts/memory/process_retry_queue.py :: get_collection_for_type."""

    @pytest.fixture(autouse=True)
    def _load(self, monkeypatch):
        if not _RETRY_SCRIPT.exists():
            pytest.skip(f"Script not found: {_RETRY_SCRIPT}")
        # The script resolves src/ from AI_MEMORY_INSTALL_DIR; point it at the repo.
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(_REPO_ROOT))
        self.mod = _load_script("process_retry_queue", _RETRY_SCRIPT)

    @pytest.mark.parametrize("memory_type", AGENT_TYPES)
    def test_agent_types_route_to_discussions(self, memory_type):
        assert self.mod.get_collection_for_type(memory_type) == COLLECTION_DISCUSSIONS

    def test_decision_routes_to_discussions(self):
        assert self.mod.get_collection_for_type("decision") == COLLECTION_DISCUSSIONS

    def test_conventions_type_routes_to_conventions(self):
        assert self.mod.get_collection_for_type("guideline") == COLLECTION_CONVENTIONS

    def test_unmapped_type_falls_through_to_code_patterns(self):
        assert (
            self.mod.get_collection_for_type("implementation")
            == COLLECTION_CODE_PATTERNS
        )


class TestPostWorkCollectionRouting:
    """scripts/memory/post_work_store_async.py :: store_memory_async."""

    @pytest.fixture(autouse=True)
    def _load(self):
        if not _POST_WORK_SCRIPT.exists():
            pytest.skip(f"Script not found: {_POST_WORK_SCRIPT}")
        self.mod = _load_script("post_work_store_async", _POST_WORK_SCRIPT)

    def _run_store(self, memory_type):
        """Drive store_memory_async with a mocked storage; return store kwargs."""
        mock_storage = MagicMock()
        mock_storage.store_memory.return_value = {
            "status": "stored",
            "memory_id": "test-id",
            "embedding_status": "complete",
        }
        payload = {
            "content": "x" * 50,
            "metadata": {
                "type": memory_type,
                "group_id": "test-project",
                "cwd": "/tmp",
            },
        }
        with (
            patch.object(self.mod, "MemoryStorage", return_value=mock_storage),
            patch("memory.project.resolve_project_id", return_value="test-project"),
            patch.object(self.mod, "_log_to_activity"),
            patch.object(self.mod, "memory_captures_total", None),
            patch.object(self.mod, "deduplication_events_total", None),
        ):
            asyncio.run(self.mod.store_memory_async(payload))

        mock_storage.store_memory.assert_called_once()
        return mock_storage.store_memory.call_args[1]

    @pytest.mark.parametrize("memory_type", AGENT_TYPES)
    def test_agent_types_route_to_discussions(self, memory_type):
        assert self._run_store(memory_type)["collection"] == COLLECTION_DISCUSSIONS

    def test_decision_routes_to_discussions(self):
        assert self._run_store("decision")["collection"] == COLLECTION_DISCUSSIONS

    def test_unmapped_type_falls_through_to_code_patterns(self):
        assert (
            self._run_store("implementation")["collection"] == COLLECTION_CODE_PATTERNS
        )
