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


class TestIsPermanentFailure:
    """_is_permanent_failure marks Unknown payload format as non-retryable."""

    def test_unknown_payload_format_is_permanent(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert (
            mod._is_permanent_failure("Unknown payload format: ['tool_name']") is True
        )

    def test_transient_error_is_not_permanent(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert (
            mod._is_permanent_failure("Storage error: ConnectionRefusedError: ...")
            is False
        )

    def test_empty_message_is_not_permanent(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert mod._is_permanent_failure("") is False


def _unknown_format_entry(entry_id: str) -> dict:
    """A queue entry whose memory_data has no recognised key — Unknown payload format."""
    return {
        "id": entry_id,
        "retry_count": 0,
        "max_retries": 3,
        "memory_data": {
            "tool_name": "Edit",
            "tool_input": {"file_path": "x.py"},
            "session_id": "s1",
            "cwd": "/tmp",
        },
    }


def _exhausted_entry(entry_id: str, group_id: str) -> dict:
    """A direct-format entry that has exhausted its retry budget."""
    return {
        "id": entry_id,
        "retry_count": 2,  # retry_count >= max_retries - 1 (2 >= 2)
        "max_retries": 3,
        "memory_data": {
            "content": "x" * 50,
            "type": "implementation",
            "group_id": group_id,
        },
    }


class TestDeadLetterQueue:
    """Entries dead-letter immediately on Unknown payload format; or on retry exhaustion."""

    def test_unknown_payload_format_dead_lettered_immediately(
        self, monkeypatch, tmp_path
    ):
        """An entry with no recognised payload key is moved to DLQ on first attempt."""
        mod = _load_module(monkeypatch)
        dlq_path = tmp_path / "dlq.jsonl"
        monkeypatch.setattr(mod, "DLQ_FILE", dlq_path)

        entry = _unknown_format_entry("dlq-test-1")
        queue, _storage = _wire_queue_storage(mod, [entry])

        stats = mod.process_queue()

        # Entry must be dead-lettered, not retried
        assert stats["moved_to_dlq"] == 1
        assert stats["failed"] == 1
        queue.dequeue.assert_called_once_with("dlq-test-1")
        queue.mark_failed.assert_not_called()

        # DLQ file must contain the entry
        assert dlq_path.exists()
        dlq_lines = dlq_path.read_text().strip().splitlines()
        assert len(dlq_lines) == 1
        dlq_entry = __import__("json").loads(dlq_lines[0])
        assert dlq_entry["id"] == "dlq-test-1"
        assert "moved_to_dlq_at" in dlq_entry

    def test_exhausted_entry_dead_lettered_on_last_retry(self, monkeypatch, tmp_path):
        """An entry at retry_count == max_retries-1 is moved to DLQ after failure."""
        mod = _load_module(monkeypatch)
        dlq_path = tmp_path / "dlq.jsonl"
        monkeypatch.setattr(mod, "DLQ_FILE", dlq_path)

        entry = _exhausted_entry("dlq-test-2", "proj-a")
        # storage.store_memory raises to force a failure
        queue, storage = _wire_queue_storage(mod, [entry])
        storage.store_memory.return_value = {"status": "error"}

        # process_entry returns (False, ...) via the "Unknown status" branch
        # — good enough to trigger the exhaustion path
        stats = mod.process_queue()

        assert stats["moved_to_dlq"] == 1
        queue.dequeue.assert_called_once_with("dlq-test-2")
        queue.mark_failed.assert_not_called()

    def test_happy_path_entry_not_dead_lettered(self, monkeypatch, tmp_path):
        """A valid entry that stores successfully is dequeued — never touches DLQ."""
        mod = _load_module(monkeypatch)
        dlq_path = tmp_path / "dlq.jsonl"
        monkeypatch.setattr(mod, "DLQ_FILE", dlq_path)

        entry = _direct_entry("happy-1", "proj-a")
        queue, storage = _wire_queue_storage(mod, [entry])
        storage.store_memory.return_value = {"status": "stored", "memory_id": "m1"}

        stats = mod.process_queue()

        assert stats["success"] == 1
        assert stats["moved_to_dlq"] == 0
        queue.dequeue.assert_called_once_with("happy-1")
        queue.mark_failed.assert_not_called()
        assert not dlq_path.exists()

    def test_transient_failure_increments_retry_not_dlq(self, monkeypatch, tmp_path):
        """A transient failure on a non-exhausted entry increments retry_count, not DLQ."""
        mod = _load_module(monkeypatch)
        dlq_path = tmp_path / "dlq.jsonl"
        monkeypatch.setattr(mod, "DLQ_FILE", dlq_path)

        # retry_count=0 (first attempt), failure will be transient (storage returns error)
        entry = {
            "id": "transient-1",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "content": "x" * 50,
                "type": "implementation",
                "group_id": "g",
            },
        }
        queue, storage = _wire_queue_storage(mod, [entry])
        storage.store_memory.return_value = {
            "status": "error"
        }  # not stored, not "stored"

        stats = mod.process_queue()

        assert stats["moved_to_dlq"] == 0
        queue.mark_failed.assert_called_once_with("transient-1")
        queue.dequeue.assert_not_called()
        assert not dlq_path.exists()
