"""Tests for scripts/memory/freshness_report.py (Item 9 externalization).

Hermetic: all memory.* injected via sys.modules before spec load.
Uses importlib.util.spec_from_file_location per CI convention (testpaths=["tests"]).
AI_MEMORY_PROJECT_ID must be unset in the test environment.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent / "scripts" / "memory" / "freshness_report.py"
)


def _make_mocks() -> dict:
    """Build sys.modules stubs for all memory.* dependencies."""
    return {
        "memory": MagicMock(name="memory"),
        "memory.config": MagicMock(name="memory.config"),
        "memory.freshness": MagicMock(name="memory.freshness"),
        "memory.metrics_push": MagicMock(name="memory.metrics_push"),
        "memory.trace_buffer": MagicMock(name="memory.trace_buffer"),
    }


@pytest.fixture()
def loaded(monkeypatch):
    """Load freshness_report module with memory.* stubbed; keep stubs active for test."""
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["freshness_report.py"])
    mocks = _make_mocks()
    with patch.dict(sys.modules, mocks):
        spec = importlib.util.spec_from_file_location("freshness_report", SCRIPT_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod, mocks


def _make_config(freshness_enabled=True, github_sync_enabled=True):
    cfg = MagicMock()
    cfg.freshness_enabled = freshness_enabled
    cfg.github_sync_enabled = github_sync_enabled
    return cfg


def _make_report(
    total_checked=5,
    fresh=3,
    aging=1,
    stale=0,
    expired=0,
    unknown=1,
    results=None,
):
    rpt = MagicMock()
    rpt.total_checked = total_checked
    rpt.duration_seconds = 1.2
    rpt.fresh_count = fresh
    rpt.aging_count = aging
    rpt.stale_count = stale
    rpt.expired_count = expired
    rpt.unknown_count = unknown
    rpt.results = results if results is not None else []
    return rpt


# ---------------------------------------------------------------------------
# T1: freshness_enabled=False — exit 0, disabled message on stdout
# ---------------------------------------------------------------------------


def test_freshness_disabled(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config(
        freshness_enabled=False
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "Freshness detection is disabled" in out
    assert "FRESHNESS_ENABLED=true" in out
    mocks["memory.freshness"].run_freshness_scan.assert_not_called()


# ---------------------------------------------------------------------------
# T2: github_sync_enabled=False — exit 0, GitHub message on stdout
# ---------------------------------------------------------------------------


def test_github_sync_disabled(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config(
        github_sync_enabled=False
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "GitHub sync is not enabled" in out
    assert "GITHUB_SYNC_ENABLED=true" in out
    mocks["memory.freshness"].run_freshness_scan.assert_not_called()


# ---------------------------------------------------------------------------
# T3: total_checked == 0 — exit 0, no-memories message on stdout
# ---------------------------------------------------------------------------


def test_no_memories_found(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=0, fresh=0, aging=0
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "No code-patterns memories" in out
    assert "file_path" in out


# ---------------------------------------------------------------------------
# T4: happy path — exit 0, ## Freshness Report header, tier counts in Summary
# ---------------------------------------------------------------------------


def test_happy_path_all_fresh(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=4, fresh=3, aging=1, stale=0, expired=0, unknown=0, results=[]
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "## Freshness Report" in out
    assert "### Summary" in out
    assert "| Fresh | 3 |" in out
    assert "| Aging | 1 |" in out
    assert "| Stale | 0 |" in out
    assert "| Expired | 0 |" in out
    assert "Scanned **4** code-patterns memories" in out


# ---------------------------------------------------------------------------
# T5: actionable items present — sorted expired→stale→aging in output
# ---------------------------------------------------------------------------


def test_actionable_sort_order(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()

    tier = mocks["memory.freshness"].FreshnessTier

    def _result(status, path):
        r = MagicMock()
        r.status = status
        r.file_path = path
        r.memory_type = "code-pattern"
        r.commit_count = 5
        r.reason = "test reason"
        return r

    results = [
        _result(tier.AGING, "aging.py"),
        _result(tier.EXPIRED, "expired.py"),
        _result(tier.STALE, "stale.py"),
    ]
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=3,
        fresh=0,
        aging=1,
        stale=1,
        expired=1,
        unknown=0,
        results=results,
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "### Actionable Memories" in out
    assert out.index("expired.py") < out.index("stale.py") < out.index("aging.py")


# ---------------------------------------------------------------------------
# T6: no actionable items (all fresh/unknown) — Actionable Memories absent
# ---------------------------------------------------------------------------


def test_no_actionable_items(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()

    tier = mocks["memory.freshness"].FreshnessTier

    def _result(status, path):
        r = MagicMock()
        r.status = status
        r.file_path = path
        r.memory_type = "code-pattern"
        r.commit_count = 0
        r.reason = "ok"
        return r

    results = [
        _result(tier.FRESH, "fresh.py"),
        _result(tier.UNKNOWN, "unknown.py"),
    ]
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=2,
        fresh=1,
        aging=0,
        stale=0,
        expired=0,
        unknown=1,
        results=results,
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "### Actionable Memories" not in out


# ---------------------------------------------------------------------------
# T7: Recommended Actions — expired only, correct bullet present
# ---------------------------------------------------------------------------


def test_recommended_actions_expired_only(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=2, fresh=0, aging=0, stale=0, expired=2, unknown=0, results=[]
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "2 expired" in out
    assert "re-capturing" in out


# ---------------------------------------------------------------------------
# T8: Recommended Actions — all fresh, "No action needed" line present
# ---------------------------------------------------------------------------


def test_recommended_actions_all_fresh(loaded, capsys):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=3, fresh=3, aging=0, stale=0, expired=0, unknown=0, results=[]
    )

    rc = mod.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert "No action needed" in out


# ---------------------------------------------------------------------------
# T9: group_id positional passed through to run_freshness_scan
# ---------------------------------------------------------------------------


def test_group_id_passed_to_scan(loaded):
    mod, mocks = loaded
    mocks["memory.config"].get_config.return_value = _make_config()
    mocks["memory.freshness"].run_freshness_scan.return_value = _make_report(
        total_checked=1, results=[]
    )

    with patch.object(sys, "argv", ["freshness_report.py", "my-project"]):
        mod.main()

    mocks["memory.freshness"].run_freshness_scan.assert_called_once()
    call_kwargs = mocks["memory.freshness"].run_freshness_scan.call_args
    assert call_kwargs.kwargs.get("group_id") == "my-project"
