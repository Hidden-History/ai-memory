"""Companion test for scripts/lib/preflight_agent_teams.sh.

The Agent Teams prerequisite guard for parallel-team dispatch. Enforces the
prerequisites already documented as prose in:
  _ai-memory/pov/constraints/global/GC-19-spawn-agents-as-teammates.md:21
  aim-model-dispatch/workflows/claude-native/workflow.md (Prerequisites)

Design under test
-----------------
Fire-only-if-missing: SILENT on the happy path (no stdout, no stderr), fires
loud with remediation on stderr only when a prerequisite is missing.

Checks:
  1. env CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS == "1"  (hard requirement)
  2. teammateMode is a team mode: unset (default "auto"), "auto", or "tmux".
     Fires only on an explicit non-team mode ("in-process").

Output routing (TASK-071-wide rule): no inline equivalent exists, so all output
is net-new -> stderr; stdout stays empty in every case.

Exit codes under test: 0=ok (silent), 1=prerequisite missing, 2=bad arg.

Harness: stdlib subprocess.run only (no pytest-shell-utilities).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory/pov/skills/aim-model-dispatch/scripts/lib"
)


@pytest.fixture(scope="session")
def helper() -> Path:
    """Resolved path to preflight_agent_teams.sh; fails fast if missing."""
    p = SCRIPTS_DIR / "preflight_agent_teams.sh"
    assert p.exists(), f"Helper not found: {p}"
    return p


def _base_env(teams_flag: str | None) -> dict[str, str]:
    """Deterministic env; sets the Agent Teams flag only when given.

    HOME points nowhere meaningful so the default settings-resolution chain
    finds no user settings file unless a test supplies one via --settings.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "HOME": "/nonexistent",
    }
    if teams_flag is not None:
        env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = teams_flag
    return env


def _write_settings(base: Path, teammate_mode: str | None) -> Path:
    """Write a .claude/settings.json in *base*; omit teammateMode when None."""
    payload: dict[str, str] = {}
    if teammate_mode is not None:
        payload["teammateMode"] = teammate_mode
    p = base / "settings.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _run(
    helper: Path,
    *args: str,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(helper), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
        env=env,
    )


# ---------------------------------------------------------------------------
# Happy path: prerequisites satisfied -> exit 0, fully silent
# ---------------------------------------------------------------------------

_OK_MODES = [
    pytest.param(None, id="mode-unset-default-auto"),
    pytest.param("auto", id="mode-auto"),
    pytest.param("tmux", id="mode-tmux"),
]


@pytest.mark.parametrize("teammate_mode", _OK_MODES)
def test_satisfied_is_silent(
    helper: Path, tmp_path: Path, teammate_mode: str | None
) -> None:
    """Flag=1 and a team mode -> exit 0 with no stdout and no stderr."""
    settings = _write_settings(tmp_path, teammate_mode)
    r = _run(
        helper,
        "--settings",
        str(settings),
        cwd=tmp_path,
        env=_base_env("1"),
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# Missing flag -> fires loud on stderr, stdout empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("teams_flag", [None, "0", "true"])
def test_flag_missing_fires(
    helper: Path, tmp_path: Path, teams_flag: str | None
) -> None:
    """Flag absent or not exactly "1" -> exit 1; remediation names the var."""
    settings = _write_settings(tmp_path, "tmux")
    r = _run(
        helper,
        "--settings",
        str(settings),
        cwd=tmp_path,
        env=_base_env(teams_flag),
    )
    assert r.returncode == 1
    assert r.stdout == ""
    assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in r.stderr


# ---------------------------------------------------------------------------
# Non-team teammateMode -> fires loud on stderr, stdout empty
# ---------------------------------------------------------------------------


def test_in_process_mode_fires(helper: Path, tmp_path: Path) -> None:
    """teammateMode "in-process" -> exit 1; remediation names teammateMode."""
    settings = _write_settings(tmp_path, "in-process")
    r = _run(
        helper,
        "--settings",
        str(settings),
        cwd=tmp_path,
        env=_base_env("1"),
    )
    assert r.returncode == 1
    assert r.stdout == ""
    assert "teammateMode" in r.stderr


def test_both_missing_reports_both(helper: Path, tmp_path: Path) -> None:
    """Flag missing AND non-team mode -> exit 1; both remediations on stderr."""
    settings = _write_settings(tmp_path, "in-process")
    r = _run(
        helper,
        "--settings",
        str(settings),
        cwd=tmp_path,
        env=_base_env(None),
    )
    assert r.returncode == 1
    assert r.stdout == ""
    assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in r.stderr
    assert "teammateMode" in r.stderr


# ---------------------------------------------------------------------------
# Arg errors: net-new output -> stderr; stdout empty; exit 2
# ---------------------------------------------------------------------------


def test_unknown_flag_exits_two(helper: Path, tmp_path: Path) -> None:
    """Unknown flag -> exit 2; usage on stderr; stdout empty."""
    r = _run(helper, "--bogus", cwd=tmp_path, env=_base_env("1"))
    assert r.returncode == 2
    assert r.stdout == ""
    assert "Usage" in r.stderr


def test_settings_requires_argument(helper: Path, tmp_path: Path) -> None:
    """--settings with no value -> exit 2; usage on stderr; stdout empty."""
    r = _run(helper, "--settings", cwd=tmp_path, env=_base_env("1"))
    assert r.returncode == 2
    assert r.stdout == ""
    assert "Usage" in r.stderr
