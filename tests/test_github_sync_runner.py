"""Tests for scripts/memory/github_sync_runner.py (TASK-071 Item 13).

Hermetic: memory.* injected via sys.modules before spec load.
Uses importlib.util.spec_from_file_location per CI convention (testpaths=["tests"]).
AI_MEMORY_PROJECT_ID must be unset in the test environment.

Run: pytest tests/test_github_sync_runner.py -p no:shell-utilities
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "memory"
    / "github_sync_runner.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_result(
    issues_synced: int = 2,
    comments_synced: int = 1,
    prs_synced: int = 1,
    reviews_synced: int = 0,
    diffs_synced: int = 0,
    commits_synced: int = 1,
    ci_results_synced: int = 0,
    items_skipped: int = 1,
    errors: int = 0,
    duration_seconds: float = 2.3,
) -> MagicMock:
    """Build a mock SyncResult whose shape mirrors SyncResult from sync.py."""
    total_synced = (
        issues_synced
        + comments_synced
        + prs_synced
        + reviews_synced
        + diffs_synced
        + commits_synced
        + ci_results_synced
    )
    result = MagicMock()
    result.total_synced = total_synced
    result.items_skipped = items_skipped
    result.errors = errors
    result.duration_seconds = duration_seconds
    result.to_dict.return_value = {
        "issues_synced": issues_synced,
        "comments_synced": comments_synced,
        "prs_synced": prs_synced,
        "reviews_synced": reviews_synced,
        "diffs_synced": diffs_synced,
        "commits_synced": commits_synced,
        "ci_results_synced": ci_results_synced,
        "items_skipped": items_skipped,
        "errors": errors,
        "total_synced": total_synced,
        "duration_seconds": round(duration_seconds, 2),
    }
    return result


def _make_engine_class(result: MagicMock) -> MagicMock:
    """Return a GitHubSyncEngine class mock whose instance.sync() returns result."""
    engine_instance = MagicMock()
    engine_instance.sync = AsyncMock(return_value=result)
    engine_class = MagicMock(return_value=engine_instance)
    return engine_class


def _build_sys_modules(engine_class: MagicMock) -> dict:
    """Return fake memory.* module stubs keyed by module name."""
    sync_mod = MagicMock(name="memory.connectors.github.sync")
    sync_mod.GitHubSyncEngine = engine_class
    return {
        "memory": MagicMock(name="memory"),
        "memory.connectors": MagicMock(name="memory.connectors"),
        "memory.connectors.github": MagicMock(name="memory.connectors.github"),
        "memory.connectors.github.sync": sync_mod,
    }


def _load_module(monkeypatch: pytest.MonkeyPatch, engine_class: MagicMock):
    """Inject mocks then load github_sync_runner.py fresh via spec_from_file_location."""
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    monkeypatch.delitem(sys.modules, "github_sync_runner", raising=False)

    mocks = _build_sys_modules(engine_class)
    for name, mod in mocks.items():
        monkeypatch.setitem(sys.modules, name, mod)

    spec = importlib.util.spec_from_file_location("github_sync_runner", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# T1: mode selection — sync() called with correct mode
# ---------------------------------------------------------------------------


class TestModeSelection:
    """sync() is called with the mode that matches the CLI flag."""

    def test_no_args_defaults_to_incremental(self, monkeypatch: pytest.MonkeyPatch):
        result = _make_sync_result()
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        rc = mod.main()

        assert rc == 0
        engine_class.return_value.sync.assert_awaited_once_with(mode="incremental")

    def test_explicit_incremental_flag(self, monkeypatch: pytest.MonkeyPatch):
        result = _make_sync_result()
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py", "--incremental"])

        rc = mod.main()

        assert rc == 0
        engine_class.return_value.sync.assert_awaited_once_with(mode="incremental")

    def test_full_flag_passes_full_mode(self, monkeypatch: pytest.MonkeyPatch):
        result = _make_sync_result()
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py", "--full"])

        rc = mod.main()

        assert rc == 0
        engine_class.return_value.sync.assert_awaited_once_with(mode="full")

    def test_engine_constructed_with_no_args(self, monkeypatch: pytest.MonkeyPatch):
        """GitHubSyncEngine() called with no positional or keyword args (matching inline)."""
        result = _make_sync_result()
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        engine_class.assert_called_once_with()


# ---------------------------------------------------------------------------
# T2: stdout — exact parity with inline block's first line
# ---------------------------------------------------------------------------


class TestStdoutFirstLine:
    """First output line matches inline: 'Synced N items (X skipped, Y errors) in Zs'."""

    def test_incremental_first_line(self, monkeypatch: pytest.MonkeyPatch, capsys):
        result = _make_sync_result(
            issues_synced=2,
            prs_synced=1,
            commits_synced=1,
            items_skipped=1,
            errors=0,
            duration_seconds=2.3,
        )
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line == "Synced 5 items (1 skipped, 0 errors) in 2.3s"

    def test_full_first_line(self, monkeypatch: pytest.MonkeyPatch, capsys):
        result = _make_sync_result(
            issues_synced=10,
            comments_synced=5,
            prs_synced=3,
            reviews_synced=2,
            diffs_synced=1,
            commits_synced=5,
            ci_results_synced=2,
            items_skipped=3,
            errors=1,
            duration_seconds=10.0,
        )
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py", "--full"])

        mod.main()

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line == "Synced 28 items (3 skipped, 1 errors) in 10.0s"

    def test_duration_formatted_one_decimal(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        """:.1f formatting — 1.567 → '1.6s', not '1.57s'."""
        result = _make_sync_result(duration_seconds=1.567)
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.endswith("in 1.6s")

    def test_zero_synced_zero_skipped(self, monkeypatch: pytest.MonkeyPatch, capsys):
        result = _make_sync_result(
            issues_synced=0,
            comments_synced=0,
            prs_synced=0,
            reviews_synced=0,
            diffs_synced=0,
            commits_synced=0,
            ci_results_synced=0,
            items_skipped=0,
            errors=0,
            duration_seconds=0.5,
        )
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line == "Synced 0 items (0 skipped, 0 errors) in 0.5s"


# ---------------------------------------------------------------------------
# T3: to_dict() dump — non-empty, non-total_synced keys printed with "  k: v"
# ---------------------------------------------------------------------------


class TestToDictDump:
    """Per-key dump from result.to_dict(): truthy values, total_synced excluded."""

    def test_nonzero_keys_printed_with_indent(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        result = _make_sync_result(
            issues_synced=2,
            prs_synced=1,
            comments_synced=0,
            reviews_synced=0,
            diffs_synced=0,
            commits_synced=0,
            ci_results_synced=0,
            items_skipped=0,
            errors=0,
            duration_seconds=1.0,
        )
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        lines = capsys.readouterr().out.splitlines()
        assert "  issues_synced: 2" in lines
        assert "  prs_synced: 1" in lines
        assert "  duration_seconds: 1.0" in lines

    def test_zero_value_keys_excluded(self, monkeypatch: pytest.MonkeyPatch, capsys):
        result = _make_sync_result(
            issues_synced=1,
            comments_synced=0,
            prs_synced=0,
            reviews_synced=0,
            diffs_synced=0,
            commits_synced=0,
            ci_results_synced=0,
            items_skipped=0,
            errors=0,
            duration_seconds=0.5,
        )
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        out = capsys.readouterr().out
        assert "comments_synced" not in out
        assert "prs_synced" not in out
        assert "reviews_synced" not in out

    def test_total_synced_always_excluded(
        self, monkeypatch: pytest.MonkeyPatch, capsys
    ):
        result = _make_sync_result(issues_synced=5)
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        out = capsys.readouterr().out
        assert "total_synced" not in out

    def test_errors_printed_when_nonzero(self, monkeypatch: pytest.MonkeyPatch, capsys):
        result = _make_sync_result(errors=3)
        engine_class = _make_engine_class(result)
        mod = _load_module(monkeypatch, engine_class)
        monkeypatch.setattr(sys, "argv", ["github_sync_runner.py"])

        mod.main()

        lines = capsys.readouterr().out.splitlines()
        assert "  errors: 3" in lines
