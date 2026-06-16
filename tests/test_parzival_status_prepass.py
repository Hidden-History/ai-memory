"""Unit tests for parzival-status-prepass.py consumer regressions (v2.7.0 Lane A).

Covers two consumer fixes against the keep-compat heartbeat schema:
  - last_session_summary read from an INLINE-quoted scalar (the form the seed
    + close steps actually write), with the block form still accepted.
  - active_plan_file re-sourced from the heartbeat's live_record pointer
    (the dropped notes field made the old notes-scan permanently None).
"""

import importlib.util
from pathlib import Path

import pytest

# Hyphenated filename — load via importlib.
_SCRIPT = (
    Path(__file__).parent.parent
    / "_ai-memory"
    / "pov"
    / "scripts"
    / "parzival-status-prepass.py"
)
_spec = importlib.util.spec_from_file_location("parzival_status_prepass", _SCRIPT)
prepass = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepass)


# --- last_session_summary: inline-quoted scalar (MEDIUM #1) ------------------


def _write_status(tmp_path, body):
    status = tmp_path / "project-status.md"
    status.write_text(body, encoding="utf-8")
    return status


def test_last_session_summary_inline_quoted(tmp_path):
    """Inline double-quoted scalar (the seed schema form) is read."""
    status = _write_status(
        tmp_path,
        "---\nclass: heartbeat\n---\n```yaml\n"
        "current_phase: execution\n"
        'last_session_summary: "2026-06-16 PM#42 shipped Lane A seeds"\n'
        "open_issues: 0\n```\n",
    )
    result = prepass.parse_project_status(status)
    assert result["last_session_summary"] == "2026-06-16 PM#42 shipped Lane A seeds"


def test_last_session_summary_block_form_still_works(tmp_path):
    """Block scalar form remains supported for robustness."""
    status = _write_status(
        tmp_path,
        "---\nclass: heartbeat\n---\n"
        "last_session_summary: |\n"
        "  line one\n"
        "  line two\n"
        "open_issues: 0\n",
    )
    result = prepass.parse_project_status(status)
    assert result["last_session_summary"] == "line one\nline two"


def test_last_session_summary_absent_is_none(tmp_path):
    status = _write_status(
        tmp_path, "---\nclass: heartbeat\n---\ncurrent_phase: execution\n"
    )
    result = prepass.parse_project_status(status)
    assert result["last_session_summary"] is None


# --- active_plan_file: live_record -> SWI scan (MEDIUM #2) -------------------


def test_active_plan_file_from_live_record(tmp_path):
    """active_plan_file is re-sourced via live_record -> live index PLAN scan."""
    swi = tmp_path / "oversight" / "SESSION_WORK_INDEX.md"
    swi.parent.mkdir(parents=True)
    swi.write_text(
        "# Session Work Index\n"
        "Older work referenced PLAN-001-foundation.md\n"
        "Active plan: PLAN-014-injection.md\n",
        encoding="utf-8",
    )
    status = _write_status(
        tmp_path,
        "---\nclass: heartbeat\n---\n"
        "live_record: oversight/SESSION_WORK_INDEX.md\n"
        "open_issues: 0\n",
    )
    result = prepass.parse_project_status(status)
    # Last (most-recent) PLAN ref wins.
    assert result["active_plan_file"] == "PLAN-014-injection.md"


def test_active_plan_file_none_when_live_record_missing(tmp_path):
    """No live_record pointer -> active_plan_file is None (graceful)."""
    status = _write_status(
        tmp_path,
        "---\nclass: heartbeat\n---\ncurrent_phase: execution\nopen_issues: 0\n",
    )
    result = prepass.parse_project_status(status)
    assert result["active_plan_file"] is None


def test_active_plan_file_none_when_live_record_unreadable(tmp_path):
    """live_record points at a missing file -> active_plan_file is None."""
    status = _write_status(
        tmp_path,
        "---\nclass: heartbeat\n---\n" "live_record: oversight/SESSION_WORK_INDEX.md\n",
    )
    result = prepass.parse_project_status(status)
    assert result["active_plan_file"] is None


def test_active_plan_file_none_when_no_plan_ref(tmp_path):
    """live_record resolves but holds no PLAN ref -> None."""
    swi = tmp_path / "oversight" / "SESSION_WORK_INDEX.md"
    swi.parent.mkdir(parents=True)
    swi.write_text("# Session Work Index\nNo plans here.\n", encoding="utf-8")
    status = _write_status(
        tmp_path,
        "---\nclass: heartbeat\n---\n" "live_record: oversight/SESSION_WORK_INDEX.md\n",
    )
    result = prepass.parse_project_status(status)
    assert result["active_plan_file"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
