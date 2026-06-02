"""Hermetic tests for scripts/memory/purge_collections.py.

Tests:
  (a) dry-run output: mocked scroll -> stdout contains expected collection counts
  (b) safety gate: absence of --confirm -> client.delete never called
  (c) confirm path: --confirm -> client.delete called against mock, not project Qdrant

Run: pytest tests/test_purge_collections.py -p no:shell-utilities
     AI_MEMORY_PROJECT_ID must be unset (enforced by _isolate_env fixture).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "memory" / "purge_collections.py"

# Collection name constants — must match what the mock config exposes.
_COL_CODE = "code-patterns"
_COL_CONV = "conventions"
_COL_DISC = "discussions"
_COL_JIRA = "jira-data"
_ALL_COLS = [_COL_CODE, _COL_CONV, _COL_DISC, _COL_JIRA]


def _make_point(pid, mtype="best_practice", ts="2020-01-01T00:00:00+00:00"):
    p = MagicMock()
    p.id = pid
    p.payload = {"type": mtype, "timestamp": ts}
    return p


def _inject_mocks(monkeypatch, mock_client):
    """Inject fake memory.* and qdrant_client modules into sys.modules."""
    mem_pkg = types.ModuleType("memory")

    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.COLLECTION_CODE_PATTERNS = _COL_CODE
    cfg_mod.COLLECTION_CONVENTIONS = _COL_CONV
    cfg_mod.COLLECTION_DISCUSSIONS = _COL_DISC
    cfg_mod.COLLECTION_JIRA_DATA = _COL_JIRA
    cfg_mod.get_config = MagicMock(return_value=MagicMock())

    qdrant_cli_mod = types.ModuleType("memory.qdrant_client")
    qdrant_cli_mod.get_qdrant_client = MagicMock(return_value=mock_client)

    metrics_mod = types.ModuleType("memory.metrics_push")
    metrics_mod.push_skill_metrics_async = MagicMock()

    trace_mod = types.ModuleType("memory.trace_buffer")
    trace_mod.emit_trace_event = MagicMock()

    qc_pkg = types.ModuleType("qdrant_client")
    qc_models = types.ModuleType("qdrant_client.models")

    class _FC:
        def __init__(self, **kw):
            pass

    class _Filter:
        def __init__(self, **kw):
            pass

    class _MV:
        def __init__(self, **kw):
            pass

    class _Range:
        def __init__(self, **kw):
            pass

    qc_models.FieldCondition = _FC
    qc_models.Filter = _Filter
    qc_models.MatchValue = _MV
    qc_models.Range = _Range

    for name, mod in [
        ("memory", mem_pkg),
        ("memory.config", cfg_mod),
        ("memory.qdrant_client", qdrant_cli_mod),
        ("memory.metrics_push", metrics_mod),
        ("memory.trace_buffer", trace_mod),
        ("qdrant_client", qc_pkg),
        ("qdrant_client.models", qc_models),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _load_module(monkeypatch, mock_client):
    """Inject mocks then load purge_collections.py fresh."""
    _inject_mocks(monkeypatch, mock_client)
    monkeypatch.delitem(sys.modules, "purge_collections", raising=False)
    spec = importlib.util.spec_from_file_location("purge_collections", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    monkeypatch.delenv("AI_MEMORY_GROUP_ID", raising=False)


class TestDryRunCounts:
    """(a) dry-run produces expected counts vs mocked Qdrant."""

    def test_stdout_contains_collection_and_count(self, monkeypatch, capsys):
        mock_client = MagicMock()

        def _scroll(**kw):
            if kw.get("collection_name") == _COL_CODE:
                return ([_make_point(1), _make_point(2), _make_point(3)], None)
            return ([], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys, "argv", ["purge_collections.py", "--older-than", "30d"]
        )

        rc = mod.main()

        assert rc == 0
        out = capsys.readouterr().out
        assert _COL_CODE in out
        assert "3 memories" in out
        assert "would be purged" in out

    def test_total_count_is_sum_across_collections(self, monkeypatch, capsys):
        mock_client = MagicMock()

        def _scroll(**kw):
            cn = kw.get("collection_name")
            if cn == _COL_CODE:
                return ([_make_point(1), _make_point(2)], None)
            if cn == _COL_CONV:
                return ([_make_point(3)], None)
            return ([], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys, "argv", ["purge_collections.py", "--older-than", "30d"]
        )

        rc = mod.main()

        assert rc == 0
        assert "**Total**: 3 memories would be purged" in capsys.readouterr().out

    def test_empty_result_prints_none_found(self, monkeypatch, capsys):
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys, "argv", ["purge_collections.py", "--older-than", "30d"]
        )

        rc = mod.main()

        assert rc == 0
        assert "No memories found" in capsys.readouterr().out


class TestSafetyGate:
    """(b) safety guard — live purge refused without explicit --confirm."""

    def test_no_confirm_never_calls_delete(self, monkeypatch):
        mock_client = MagicMock()

        def _scroll(**kw):
            return ([_make_point(10), _make_point(11)], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(sys, "argv", ["purge_collections.py", "--older-than", "7d"])

        rc = mod.main()

        assert rc == 0
        mock_client.delete.assert_not_called()

    def test_no_confirm_shows_rerun_hint(self, monkeypatch, capsys):
        mock_client = MagicMock()

        def _scroll(**kw):
            return ([_make_point(1)], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys, "argv", ["purge_collections.py", "--older-than", "30d"]
        )

        mod.main()

        assert "--confirm" in capsys.readouterr().out

    def test_invalid_duration_returns_exit1(self, monkeypatch, capsys):
        mock_client = MagicMock()

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys, "argv", ["purge_collections.py", "--older-than", "bad"]
        )

        rc = mod.main()

        assert rc == 1
        assert "Error" in capsys.readouterr().out

    def test_unknown_collection_returns_exit1(self, monkeypatch, capsys):
        mock_client = MagicMock()

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "purge_collections.py",
                "--older-than",
                "30d",
                "--collection",
                "nonexistent",
            ],
        )

        rc = mod.main()

        assert rc == 1
        assert "Error" in capsys.readouterr().out


class TestConfirmPath:
    """(c) destructive path tested against mocked collection only — never project Qdrant."""

    def test_confirm_calls_delete_with_correct_ids(self, monkeypatch, tmp_path):
        mock_client = MagicMock()

        def _scroll(**kw):
            if kw.get("collection_name") == _COL_CODE:
                return ([_make_point(101), _make_point(102)], None)
            return ([], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys,
            "argv",
            ["purge_collections.py", "--older-than", "30d", "--confirm"],
        )
        monkeypatch.chdir(tmp_path)

        rc = mod.main()

        assert rc == 0
        mock_client.delete.assert_called_once_with(
            collection_name=_COL_CODE,
            points_selector=[101, 102],
        )

    def test_confirm_prints_purge_summary(self, monkeypatch, capsys, tmp_path):
        mock_client = MagicMock()

        def _scroll(**kw):
            if kw.get("collection_name") == _COL_CODE:
                return ([_make_point(1), _make_point(2), _make_point(3)], None)
            return ([], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys,
            "argv",
            ["purge_collections.py", "--older-than", "30d", "--confirm"],
        )
        monkeypatch.chdir(tmp_path)

        mod.main()

        out = capsys.readouterr().out
        assert "Memory Purge Complete" in out
        assert "3" in out
        assert "purge-log.jsonl" in out

    def test_confirm_writes_audit_log(self, monkeypatch, tmp_path):
        mock_client = MagicMock()

        def _scroll(**kw):
            if kw.get("collection_name") == _COL_CONV:
                return ([_make_point(5)], None)
            return ([], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys,
            "argv",
            ["purge_collections.py", "--older-than", "30d", "--confirm"],
        )
        monkeypatch.chdir(tmp_path)

        mod.main()

        log_path = tmp_path / ".audit" / "logs" / "purge-log.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text())
        assert entry["deleted"][_COL_CONV] == 1

    def test_confirm_batches_large_result(self, monkeypatch, tmp_path):
        """execute_purge deletes in batches of 100 — verify delete called twice for 150 pts."""
        mock_client = MagicMock()

        def _scroll(**kw):
            if kw.get("collection_name") == _COL_CODE:
                return ([_make_point(i) for i in range(150)], None)
            return ([], None)

        mock_client.scroll.side_effect = _scroll

        mod = _load_module(monkeypatch, mock_client)
        monkeypatch.setattr(
            sys,
            "argv",
            ["purge_collections.py", "--older-than", "30d", "--confirm"],
        )
        monkeypatch.chdir(tmp_path)

        rc = mod.main()

        assert rc == 0
        assert mock_client.delete.call_count == 2
