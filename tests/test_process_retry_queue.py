"""Hermetic tests for scripts/memory/process_retry_queue.py.

Focus (TD-713): the optional --group-id scoped drain.
  (1) --group-id X drains only group X's entries.
  (2) Omitting --group-id preserves the global (all-groups) drain default.
  (3) extract_group_id resolves the group an entry would be stored under,
      across the three payload formats.

Tests never touch the live shared Qdrant or generate embeddings: MemoryQueue
and MemoryStorage are mocked at the module call boundary.

Run: pytest tests/test_process_retry_queue.py
     AI_MEMORY_PROJECT_ID must be unset (enforced by _isolate_env).
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "memory" / "process_retry_queue.py"

_COL_CODE = "code-patterns"
_COL_CONV = "conventions"
_COL_DISC = "discussions"


def _direct_entry(entry_id: str, group_id: str) -> dict:
    """A queue entry in the direct (content) payload format."""
    return {
        "id": entry_id,
        "retry_count": 0,
        "max_retries": 3,
        "memory_data": {
            "content": "x" * 50,
            "type": "implementation",
            "group_id": group_id,
        },
    }


def _inject_mocks(monkeypatch):
    """Inject fake memory.* modules so the script imports without the real stack."""
    mem_pkg = types.ModuleType("memory")

    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.COLLECTION_CODE_PATTERNS = _COL_CODE
    cfg_mod.COLLECTION_CONVENTIONS = _COL_CONV
    cfg_mod.COLLECTION_DISCUSSIONS = _COL_DISC

    hooks_mod = types.ModuleType("memory.hooks_common")
    hooks_mod.setup_hook_logging = MagicMock(return_value=logging.getLogger("test_rq"))

    models_mod = types.ModuleType("memory.models")

    class _MemoryType:
        IMPLEMENTATION = "implementation"

        def __new__(cls, value):
            return value

    models_mod.MemoryType = _MemoryType

    queue_mod = types.ModuleType("memory.queue")
    queue_mod.MemoryQueue = MagicMock()

    storage_mod = types.ModuleType("memory.storage")
    storage_mod.MemoryStorage = MagicMock()

    project_mod = types.ModuleType("memory.project")
    project_mod.resolve_project_id = MagicMock(return_value="resolved-project")

    for name, mod in [
        ("memory", mem_pkg),
        ("memory.config", cfg_mod),
        ("memory.hooks_common", hooks_mod),
        ("memory.models", models_mod),
        ("memory.queue", queue_mod),
        ("memory.storage", storage_mod),
        ("memory.project", project_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _load_module(monkeypatch):
    """Inject mocks then load process_retry_queue.py fresh."""
    _inject_mocks(monkeypatch)
    monkeypatch.delitem(sys.modules, "process_retry_queue", raising=False)
    spec = importlib.util.spec_from_file_location("process_retry_queue", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    monkeypatch.delenv("AI_MEMORY_GROUP_ID", raising=False)


def _wire_queue_storage(mod, pending):
    """Point the loaded module's MemoryQueue/MemoryStorage at fakes.

    Returns (queue, storage) so tests can assert on dequeue/store_memory.
    """
    queue = MagicMock()
    queue.get_pending.return_value = pending
    storage = MagicMock()
    storage.store_memory.return_value = {"status": "stored", "memory_id": "m1"}
    mod.MemoryQueue = MagicMock(return_value=queue)
    mod.MemoryStorage = MagicMock(return_value=storage)
    return queue, storage


class TestGroupScopedDrain:
    """TD-713: --group-id scopes the drain; omitting it stays global."""

    def test_group_id_drains_only_that_group(self, monkeypatch):
        mod = _load_module(monkeypatch)
        pending = [
            _direct_entry("e1", "proj-a"),
            _direct_entry("e2", "proj-b"),
            _direct_entry("e3", "proj-a"),
        ]
        queue, storage = _wire_queue_storage(mod, pending)

        stats = mod.process_queue(group_id="proj-a")

        assert stats["processed"] == 2
        assert stats["success"] == 2
        stored_groups = [
            c.kwargs["group_id"] for c in storage.store_memory.call_args_list
        ]
        assert stored_groups == ["proj-a", "proj-a"]
        dequeued = [c.args[0] for c in queue.dequeue.call_args_list]
        assert dequeued == ["e1", "e3"]

    def test_omitted_group_id_drains_all_groups(self, monkeypatch):
        mod = _load_module(monkeypatch)
        pending = [
            _direct_entry("e1", "proj-a"),
            _direct_entry("e2", "proj-b"),
        ]
        _queue, storage = _wire_queue_storage(mod, pending)

        stats = mod.process_queue()  # default: global drain

        assert stats["processed"] == 2
        assert stats["success"] == 2
        assert storage.store_memory.call_count == 2

    def test_group_id_with_no_matches_processes_nothing(self, monkeypatch):
        mod = _load_module(monkeypatch)
        pending = [_direct_entry("e1", "proj-a")]
        queue, storage = _wire_queue_storage(mod, pending)

        stats = mod.process_queue(group_id="proj-zzz")

        assert stats["processed"] == 0
        storage.store_memory.assert_not_called()
        queue.dequeue.assert_not_called()


class TestExtractGroupId:
    """extract_group_id mirrors process_entry's per-format resolution."""

    def test_direct_format(self, monkeypatch):
        mod = _load_module(monkeypatch)
        entry = {"memory_data": {"content": "c", "group_id": "proj-a"}}
        assert mod.extract_group_id(entry) == "proj-a"

    def test_payload_format(self, monkeypatch):
        mod = _load_module(monkeypatch)
        entry = {"memory_data": {"payload": {"metadata": {"group_id": "proj-b"}}}}
        assert mod.extract_group_id(entry) == "proj-b"

    def test_hook_input_format_uses_resolver(self, monkeypatch):
        mod = _load_module(monkeypatch)
        entry = {"memory_data": {"hook_input": {"cwd": "/some/where"}}}
        # extract_group_id imports resolve_project_id from the injected module.
        sys.modules["memory.project"].resolve_project_id.return_value = "resolved-x"
        assert mod.extract_group_id(entry) == "resolved-x"

    def test_unknown_format_returns_none(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert mod.extract_group_id({"memory_data": {"mystery": 1}}) is None
