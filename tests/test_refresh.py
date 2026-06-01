"""Tests for scripts/memory/refresh.py (Item 11 — aim-refresh externalization).

Hermetic: memory.* injected via sys.modules before spec-load.
AI_MEMORY_PROJECT_ID unset throughout.
Run: pytest tests/test_refresh.py -p no:shell-utilities
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "memory" / "refresh.py"


def _make_report(**kwargs):
    r = MagicMock()
    r.total_checked = kwargs.get("total_checked", 5)
    r.fresh_count = kwargs.get("fresh_count", 5)
    r.aging_count = kwargs.get("aging_count", 0)
    r.stale_count = kwargs.get("stale_count", 0)
    r.expired_count = kwargs.get("expired_count", 0)
    r.unknown_count = kwargs.get("unknown_count", 0)
    r.duration_seconds = kwargs.get("duration_seconds", 1.0)
    return r


def _make_config(*, freshness_enabled=True, github_sync_enabled=True):
    cfg = MagicMock()
    cfg.freshness_enabled = freshness_enabled
    cfg.github_sync_enabled = github_sync_enabled
    return cfg


def _load(monkeypatch, *, config=None, report=None):
    """Load refresh.py with all memory.* mocked via sys.modules."""
    if config is None:
        config = _make_config()
    if report is None:
        report = _make_report()

    monkeypatch.delitem(sys.modules, "refresh", raising=False)

    mem_pkg = types.ModuleType("memory")
    monkeypatch.setitem(sys.modules, "memory", mem_pkg)

    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.get_config = MagicMock(return_value=config)
    monkeypatch.setitem(sys.modules, "memory.config", cfg_mod)

    fresh_mod = types.ModuleType("memory.freshness")
    fresh_mod.run_freshness_scan = MagicMock(return_value=report)
    monkeypatch.setitem(sys.modules, "memory.freshness", fresh_mod)

    metrics_mod = types.ModuleType("memory.metrics_push")
    metrics_mod.push_skill_metrics_async = MagicMock()
    monkeypatch.setitem(sys.modules, "memory.metrics_push", metrics_mod)

    # trace_buffer absent → local try/except in main() silently no-ops
    monkeypatch.setitem(
        sys.modules, "memory.trace_buffer", types.ModuleType("memory.trace_buffer")
    )

    spec = importlib.util.spec_from_file_location("refresh", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDisabledGuard:
    def test_freshness_disabled_prints_message_exits_0(self, monkeypatch, capsys):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py"])
        mod = _load(monkeypatch, config=_make_config(freshness_enabled=False))
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "Freshness detection is disabled" in out
        assert "FRESHNESS_ENABLED=true" in out


class TestGithubSyncWarning:
    def test_sync_disabled_prints_warning_and_continues(self, monkeypatch, capsys):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py"])
        mod = _load(
            monkeypatch,
            config=_make_config(freshness_enabled=True, github_sync_enabled=False),
        )
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "GitHub sync is not enabled" in out
        assert "Memory Refresh Complete" in out


class TestTopicNotice:
    def test_topic_flag_prints_v21_notice_scan_still_runs(self, monkeypatch, capsys):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py", "--topic", "authentication"])
        mod = _load(monkeypatch)
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "v2.1 feature" in out
        assert "authentication" in out
        _, kwargs = mod.run_freshness_scan.call_args
        assert "topic" not in kwargs


class TestEmptyScan:
    def test_empty_result_prints_no_memories_metrics_empty(self, monkeypatch, capsys):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py"])
        mod = _load(
            monkeypatch,
            report=_make_report(
                total_checked=0,
                fresh_count=0,
                aging_count=0,
                stale_count=0,
                expired_count=0,
                unknown_count=0,
            ),
        )
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "No code-patterns memories" in out
        mod.push_skill_metrics_async.assert_called_once()
        assert mod.push_skill_metrics_async.call_args[0][1] == "empty"


class TestActionable:
    def test_actionable_prints_attention_message(self, monkeypatch, capsys):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py"])
        mod = _load(
            monkeypatch,
            report=_make_report(
                total_checked=10,
                fresh_count=5,
                aging_count=1,
                stale_count=2,
                expired_count=2,
                unknown_count=0,
            ),
        )
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "4 memories need attention" in out
        assert "/aim-freshness-report" in out


class TestAllFresh:
    def test_all_fresh_prints_no_action_message(self, monkeypatch, capsys):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py"])
        mod = _load(
            monkeypatch,
            report=_make_report(
                total_checked=5,
                fresh_count=5,
                aging_count=0,
                stale_count=0,
                expired_count=0,
                unknown_count=0,
            ),
        )
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "All memories are fresh" in out


class TestProjectArg:
    def test_project_positional_forwarded_as_group_id(self, monkeypatch):
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
        monkeypatch.setattr(sys, "argv", ["refresh.py", "my-project"])
        mod = _load(monkeypatch)
        mod.main()
        _, kwargs = mod.run_freshness_scan.call_args
        assert kwargs["group_id"] == "my-project"
