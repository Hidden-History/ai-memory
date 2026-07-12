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
    """A queue entry in the direct (content) payload format.

    Self-contained per BP-180: carries a persisted group_id AND source_hook so
    the fixed drain reads scope/provenance from the entry (never re-resolves).
    """
    return {
        "id": entry_id,
        "retry_count": 0,
        "max_retries": 3,
        "memory_data": {
            "content": "x" * 50,
            "type": "implementation",
            "group_id": group_id,
            "source_hook": "manual",
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

    # Import real extraction/filters BEFORE replacing the memory package so they
    # land in sys.modules and survive the fake package being installed.
    # Both modules have no memory.* deps; safe to import from the real stack.
    import importlib as _importlib

    _real_extraction = _importlib.import_module("memory.extraction")
    _real_filters = _importlib.import_module("memory.filters")

    for name, mod in [
        ("memory", mem_pkg),
        ("memory.config", cfg_mod),
        ("memory.hooks_common", hooks_mod),
        ("memory.models", models_mod),
        ("memory.queue", queue_mod),
        ("memory.storage", storage_mod),
        ("memory.project", project_mod),
        ("memory.extraction", _real_extraction),
        ("memory.filters", _real_filters),
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

    def test_hook_input_format_reads_persisted_group_id(self, monkeypatch):
        """BP-180/BUG-522: hook_input group is read from the persisted field,
        NEVER re-resolved from the stored cwd at drain time."""
        mod = _load_module(monkeypatch)
        entry = {
            "memory_data": {
                "group_id": "persisted-x",
                "hook_input": {"cwd": "/some/where"},
            }
        }
        # A drain-time resolver call would be the BUG-522 regression — spy proves none.
        sys.modules["memory.project"].resolve_project_id.reset_mock()
        assert mod.extract_group_id(entry) == "persisted-x"
        sys.modules["memory.project"].resolve_project_id.assert_not_called()

    def test_hook_input_without_persisted_group_id_returns_none(self, monkeypatch):
        """A legacy hook_input entry lacking a persisted group_id yields None
        (poison → DLQ), instead of a drain-time cwd re-resolution."""
        mod = _load_module(monkeypatch)
        entry = {"memory_data": {"hook_input": {"cwd": "/some/where"}}}
        assert mod.extract_group_id(entry) is None

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
            "source_hook": "manual",
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
                "source_hook": "manual",
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


class TestL5RecoverableForms:
    """L5: the two capture hooks now enqueue drainable forms on a Qdrant outage.

    store_async wraps the raw event as {"hook_input": ...} (drains via format-2);
    error_store_async enqueues a direct {"content", "type", "group_id",
    "session_id"} record (drains via format-1). The raw flat event each hook used
    to enqueue is still "Unknown payload format" — proving why the wrap was
    necessary.
    """

    def test_store_async_hook_input_wrapper_drains_via_format2(self, monkeypatch):
        """A {"hook_input": <PostToolUse event>} entry stores the extracted content.

        BP-180/BUG-522: group_id is read from the entry's persisted field, not
        re-resolved from the stored cwd at drain time.
        """
        mod = _load_module(monkeypatch)
        sys.modules["memory.project"].resolve_project_id.reset_mock()
        storage = MagicMock()
        storage.store_memory.return_value = {"status": "stored", "memory_id": "m1"}

        entry = {
            "id": "h1",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "group_id": "persisted-project",
                "hook_input": {
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": "foo.py",
                        "new_string": "def hello():\n    return 1\n",
                    },
                    "session_id": "sess-1",
                    "cwd": "/repo",
                },
            },
        }

        ok, msg = mod.process_entry(entry, storage, dry_run=False)

        assert ok, msg
        kwargs = storage.store_memory.call_args.kwargs
        # TD-728: content must be enriched by extract_patterns, not stored raw
        from memory.extraction import extract_patterns

        expected_content = extract_patterns("def hello():\n    return 1\n", "foo.py")[
            "content"
        ]
        assert kwargs["content"] == expected_content
        assert kwargs["group_id"] == "persisted-project"
        assert kwargs["memory_type"] == "implementation"
        assert kwargs["session_id"] == "sess-1"
        # No drain-time cwd re-resolution (the BUG-522 regression).
        sys.modules["memory.project"].resolve_project_id.assert_not_called()

    def test_error_store_direct_payload_drains_via_format1(self, monkeypatch):
        """A direct error-store payload stores its content/type/group_id/session_id."""
        mod = _load_module(monkeypatch)
        storage = MagicMock()
        storage.store_memory.return_value = {"status": "stored", "memory_id": "m2"}

        entry = {
            "id": "e1",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "content": "[error_pattern]\nCommand: pytest\nError: boom",
                "type": "error_pattern",
                "group_id": "myorg-myrepo",
                "session_id": "sess-2",
                "source_hook": "manual",
            },
        }

        ok, msg = mod.process_entry(entry, storage, dry_run=False)

        assert ok, msg
        kwargs = storage.store_memory.call_args.kwargs
        assert kwargs["content"].startswith("[error_pattern]")
        assert kwargs["group_id"] == "myorg-myrepo"
        assert kwargs["memory_type"] == "error_pattern"
        assert kwargs["session_id"] == "sess-2"

    def test_raw_flat_event_is_unknown_format(self, monkeypatch):
        """The raw flat event the hooks used to enqueue is undrainable (Unknown format)."""
        mod = _load_module(monkeypatch)
        storage = MagicMock()

        ok, msg = mod.process_entry(_unknown_format_entry("flat-1"), storage, False)

        assert ok is False
        assert "Unknown payload format" in msg
        storage.store_memory.assert_not_called()


class TestFormatTwoTypeCoercion:
    """TD-728: format-2 (hook_input) recovery uses live-path content + type reconstruction.

    Before this fix the format-2 branch hardcoded memory_type="implementation" AND
    collection=COLLECTION_CODE_PATTERNS AND stored the raw code_content instead of the
    enriched content produced by extract_patterns().  Every bullet below verifies a
    field the live store_async.py path would produce for the same hook_input.
    """

    def test_write_tool_field_level_fidelity(self, monkeypatch):
        """Write tool: stored content == extract_patterns enriched, type == implementation,
        collection derived from type (not hardcoded)."""
        mod = _load_module(monkeypatch)
        storage = MagicMock()
        storage.store_memory.return_value = {"status": "stored", "memory_id": "m-td728"}

        code = (
            "async def fetch_user(user_id: int):\n"
            "    db = await get_db()\n"
            "    return await db.get(user_id)\n"
        )
        entry = {
            "id": "td728-write",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "group_id": "proj-td728",
                "hook_input": {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "api/users.py", "content": code},
                    "session_id": "sess-td728",
                    "cwd": "/myproject",
                },
            },
        }

        ok, msg = mod.process_entry(entry, storage)
        assert ok, msg

        from memory.extraction import extract_patterns

        expected_content = extract_patterns(code, "api/users.py")["content"]
        expected_collection = _COL_CODE  # get_collection_for_type("implementation")

        call_kw = storage.store_memory.call_args.kwargs
        assert (
            call_kw["content"] == expected_content
        ), "content must be enriched via extract_patterns, not stored raw"
        assert call_kw["memory_type"] == "implementation"
        assert call_kw["collection"] == expected_collection
        assert call_kw["group_id"] == "proj-td728"
        assert call_kw["session_id"] == "sess-td728"

    def test_edit_tool_field_level_fidelity(self, monkeypatch):
        """Edit tool: enriched content + correct collection via get_collection_for_type."""
        mod = _load_module(monkeypatch)
        storage = MagicMock()
        storage.store_memory.return_value = {"status": "stored", "memory_id": "m-edit"}

        new_string = (
            "def process(data: dict) -> dict:\n"
            "    return {k: v for k, v in data.items() if v is not None}\n"
        )
        entry = {
            "id": "td728-edit",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "group_id": "proj-edit",
                "hook_input": {
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": "core/transform.py",
                        "new_string": new_string,
                    },
                    "session_id": "sess-edit",
                    "cwd": "/myproject",
                },
            },
        }

        ok, msg = mod.process_entry(entry, storage)
        assert ok, msg

        from memory.extraction import extract_patterns

        expected_content = extract_patterns(new_string, "core/transform.py")["content"]
        call_kw = storage.store_memory.call_args.kwargs
        assert call_kw["content"] == expected_content
        assert call_kw["memory_type"] == "implementation"
        assert call_kw["collection"] == _COL_CODE

    def test_non_implementation_format3_not_coerced_to_code_patterns(self, monkeypatch):
        """Non-implementation: format-3 decision type lands in discussions, not code-patterns.

        Proves the coercion is gone — a queued decision entry must not end up in the
        code-patterns collection that the old format-2 hardcode would have forced it into.
        """
        mod = _load_module(monkeypatch)
        storage = MagicMock()
        storage.store_memory.return_value = {"status": "stored", "memory_id": "m-dec"}

        entry = {
            "id": "td728-decision",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "content": "Adopted event-driven architecture for the notification service.",
                "type": "decision",
                "group_id": "proj-arch",
                "session_id": "sess-arch",
                "source_hook": "manual",
                "file_path": "",
            },
        }

        ok, msg = mod.process_entry(entry, storage)
        assert ok, msg

        call_kw = storage.store_memory.call_args.kwargs
        # decision → COLLECTION_DISCUSSIONS, must NOT be COLLECTION_CODE_PATTERNS
        assert (
            call_kw["collection"] == _COL_DISC
        ), f"decision type must land in {_COL_DISC!r}, got {call_kw['collection']!r}"
        assert call_kw["memory_type"] == "decision"
        assert call_kw["group_id"] == "proj-arch"


class TestDrainLock:
    """The shared drain lock makes the in-stack daemon and an on-session-start
    drain mutually exclusive (never drain concurrently)."""

    def test_second_acquire_is_nonblocking_false(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        monkeypatch.setattr(mod, "DRAIN_LOCK_FILE", tmp_path / "retry_drain.lock")

        with mod.drain_lock() as first:
            assert first is True
            # A second acquisition while the first is held returns False (NB).
            with mod.drain_lock() as second:
                assert second is False

        # Once released, the lock can be acquired again.
        with mod.drain_lock() as third:
            assert third is True


class TestDrainScopeFidelity:
    """BUG-522 regression: the drain scopes each entry by its PERSISTED group_id
    and NEVER re-derives scope from a stored cwd at drain time.

    The autouse _isolate_env fixture guarantees AI_MEMORY_PROJECT_ID is unset —
    the exact contextless-cron environment where the old drain fail-louded.
    """

    def test_drains_under_persisted_group_id_without_cwd_redetect(self, monkeypatch):
        """Persisted group_id wins; resolve_project_id is never called even though
        the entry carries a stored cwd that does not resolve here."""
        mod = _load_module(monkeypatch)

        # Any drain-time resolve_project_id() call blows up — mirroring the
        # contextless cron that could not resolve the producer's workspace (the
        # very failure that made Fix B recover ≈0). If the drain calls it, the
        # test fails loudly.
        def _boom(*args, **kwargs):
            raise ValueError(
                "project detection failed — drain must not re-resolve at drain time"
            )

        sys.modules["memory.project"].resolve_project_id.side_effect = _boom

        entry = {
            "id": "scope-1",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "group_id": "proj-A",  # captured under proj-A
                "hook_input": {
                    "tool_name": "Write",
                    "tool_input": {
                        "file_path": "svc/app.py",
                        "content": "def run():\n    return compute()\n",
                    },
                    "session_id": "s-scope",
                    # cwd belongs to a different, unresolvable workspace — ignored.
                    "cwd": "/mnt/e/projects/some-other-unresolvable-project",
                },
            },
        }
        queue, storage = _wire_queue_storage(mod, [entry])

        stats = mod.process_queue()  # global drain, AI_MEMORY_PROJECT_ID unset

        assert stats["success"] == 1, stats
        kwargs = storage.store_memory.call_args.kwargs
        assert kwargs["group_id"] == "proj-A"  # persisted, NOT cwd-derived
        sys.modules["memory.project"].resolve_project_id.assert_not_called()
        queue.dequeue.assert_called_once_with("scope-1")

    def test_missing_source_hook_is_poison_never_stored_under_default(
        self, monkeypatch, tmp_path
    ):
        """BUG-521: an entry without persisted source_hook is dead-lettered, never
        stored with a synthesized 'retry' source_hook."""
        mod = _load_module(monkeypatch)
        dlq = tmp_path / "dlq.jsonl"
        monkeypatch.setattr(mod, "DLQ_FILE", dlq)

        entry = {
            "id": "poison-hook",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "content": "x" * 50,
                "type": "implementation",
                "group_id": "g",
                # no source_hook
            },
        }
        queue, storage = _wire_queue_storage(mod, [entry])

        stats = mod.process_queue()

        assert stats["moved_to_dlq"] == 1
        storage.store_memory.assert_not_called()
        queue.dequeue.assert_called_once_with("poison-hook")
        queue.mark_failed.assert_not_called()

    def test_missing_group_id_never_stored_under_catch_all(self, monkeypatch, tmp_path):
        """BUG-522/PM #380: an entry without persisted group_id is dead-lettered,
        never stored under an 'unknown' catch-all group."""
        mod = _load_module(monkeypatch)
        dlq = tmp_path / "dlq.jsonl"
        monkeypatch.setattr(mod, "DLQ_FILE", dlq)

        entry = {
            "id": "poison-grp",
            "retry_count": 0,
            "max_retries": 3,
            "memory_data": {
                "content": "x" * 50,
                "type": "implementation",
                "source_hook": "manual",
                # no group_id
            },
        }
        queue, storage = _wire_queue_storage(mod, [entry])

        stats = mod.process_queue()

        assert stats["moved_to_dlq"] == 1
        storage.store_memory.assert_not_called()
        queue.dequeue.assert_called_once_with("poison-grp")
        queue.mark_failed.assert_not_called()
