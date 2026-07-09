"""Hermetic tests for scripts/memory/backfill_retry_queue_snapshot.py (WI-4).

Verifies the one-off snapshot backfill (BUG-521 / BUG-522):
  - hook_input entries lacking a persisted group_id are re-scoped OFFLINE from
    their persisted cwd (the BP-180 legacy carve-out — deliberate, not the
    forbidden drain-time re-resolution).
  - direct/payload entries with a persisted group_id but missing source_hook get
    a VALID 'manual' source_hook (never 'retry').
  - non-memory records and unresolvable entries are skipped, never stored under a
    catch-all.
  - dry-run makes ZERO Qdrant calls.

Mocks the memory.* stack at the import boundary (same approach as
test_process_retry_queue.py); never touches the live Qdrant.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "memory" / "backfill_retry_queue_snapshot.py"


def _inject_mocks(monkeypatch):
    """Inject fake memory.* modules so the script imports without the real stack."""
    mem_pkg = types.ModuleType("memory")

    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.COLLECTION_CODE_PATTERNS = "code-patterns"
    cfg_mod.COLLECTION_CONVENTIONS = "conventions"
    cfg_mod.COLLECTION_DISCUSSIONS = "discussions"

    hooks_mod = types.ModuleType("memory.hooks_common")
    hooks_mod.setup_hook_logging = MagicMock(
        return_value=logging.getLogger("test_backfill")
    )

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
    project_mod.resolve_project_id = MagicMock(return_value="resolved-from-cwd")

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
    _inject_mocks(monkeypatch)
    monkeypatch.delitem(sys.modules, "process_retry_queue", raising=False)
    monkeypatch.delitem(sys.modules, "backfill_retry_queue_snapshot", raising=False)
    spec = importlib.util.spec_from_file_location(
        "backfill_retry_queue_snapshot", _SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)


class TestStampLegacyScope:
    def test_hook_input_without_group_id_resolves_from_cwd(self, monkeypatch):
        mod = _load_module(monkeypatch)
        sys.modules["memory.project"].resolve_project_id.return_value = "proj-from-cwd"
        entry = {"memory_data": {"hook_input": {"cwd": "/x/proj", "session_id": "s"}}}
        out, reason = mod._stamp_legacy_scope(entry)
        assert reason is None
        assert out["memory_data"]["group_id"] == "proj-from-cwd"
        assert out["memory_data"]["source_hook"]  # a valid hook stamped

    def test_hook_input_unresolvable_cwd_is_skipped(self, monkeypatch):
        mod = _load_module(monkeypatch)
        sys.modules["memory.project"].resolve_project_id.side_effect = ValueError(
            "project detection failed"
        )
        entry = {"memory_data": {"hook_input": {"cwd": "/nope"}}}
        _out, reason = mod._stamp_legacy_scope(entry)
        assert reason is not None
        assert "not resolvable" in reason

    def test_direct_with_group_id_gets_manual_source_hook(self, monkeypatch):
        mod = _load_module(monkeypatch)
        entry = {
            "memory_data": {
                "content": "x" * 40,
                "group_id": "g",
                "type": "implementation",
            }
        }
        out, reason = mod._stamp_legacy_scope(entry)
        assert reason is None
        # BP-180: valid 'manual', never 'retry'
        assert out["memory_data"]["source_hook"] == "manual"

    def test_direct_without_group_id_is_skipped(self, monkeypatch):
        mod = _load_module(monkeypatch)
        entry = {"memory_data": {"content": "x" * 40, "type": "implementation"}}
        _out, reason = mod._stamp_legacy_scope(entry)
        assert reason is not None

    def test_non_memory_record_is_skipped(self, monkeypatch):
        mod = _load_module(monkeypatch)
        entry = {"memory_data": {"command": "ls", "exit_code": 0, "output": "x"}}
        _out, reason = mod._stamp_legacy_scope(entry)
        assert reason is not None


class TestBackfillDryRun:
    def _write_snapshot(self, tmp_path, pending, dlq):
        (tmp_path / "pending_queue.jsonl").write_text(
            "\n".join(json.dumps(e) for e in pending) + "\n"
        )
        (tmp_path / "retry_queue_dlq.jsonl").write_text(
            "\n".join(json.dumps(e) for e in dlq) + "\n"
        )

    def test_dry_run_tallies_and_makes_no_storage_calls(self, monkeypatch, tmp_path):
        mod = _load_module(monkeypatch)
        sys.modules["memory.project"].resolve_project_id.return_value = "resolved-proj"

        pending = [
            # hook_input, no persisted group_id → resolved offline from cwd
            {
                "id": "p1",
                "memory_data": {
                    "hook_input": {
                        "tool_name": "Write",
                        "tool_input": {
                            "file_path": "a.py",
                            "content": "def f():\n    return compute_value()\n",
                        },
                        "session_id": "s1",
                        "cwd": "/repo/proj",
                    }
                },
            },
        ]
        dlq = [
            # direct with group_id, missing source_hook → recoverable ('manual')
            {
                "id": "d1",
                "memory_data": {
                    "content": "[error_pattern] boom happened during test run",
                    "type": "error_pattern",
                    "group_id": "myproj",
                },
            },
            # non-memory raw command record → skipped
            {"id": "d2", "memory_data": {"command": "ls", "exit_code": 0}},
        ]
        self._write_snapshot(tmp_path, pending, dlq)

        stats = mod.backfill(tmp_path, dry_run=True, limit=None)

        assert stats["read"] == 3
        assert stats["stored"] == 2  # p1 (resolved) + d1 (manual source_hook)
        assert stats["failed"] == 0
        assert stats["skipped"] == 1  # d2 non-memory
        # Storage must never be constructed/called in dry-run.
        sys.modules["memory.storage"].MemoryStorage.assert_not_called()
        assert stats["by_group"]["resolved-proj"] == 1
        assert stats["by_group"]["myproj"] == 1
