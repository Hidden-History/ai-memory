"""Companion test for scripts/check_bmad_commands.sh (aim-agent-dispatch).

Verifies that every /bmad-* command referenced in the dispatch tables resolves
to an installed skill.

Design under test
-----------------
Fire-only-if-missing: SILENT (no stdout, no stderr, exit 0) when all referenced
commands resolve; fires loud on stderr listing only the unresolved ones (exit 1).

Graceful degrade: when NO bmad-* skills exist at the resolution root, BMAD is
not installed here -> report once on stderr and exit 0, rather than flag every
command as broken.

Placeholder handling: the "/bmad-agent-<name>" prose placeholder extracts as the
trailing-dash token "/bmad-agent-" and must be dropped, not flagged.

Output routing: all output is net-new -> stderr; stdout stays empty.

Exit codes under test: 0=all resolve or BMAD absent, 1=unresolved, 2=bad arg.

Harness: stdlib subprocess.run only.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HELPER = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory/pov/skills/aim-agent-dispatch/scripts/check_bmad_commands.sh"
)


@pytest.fixture(scope="session")
def helper() -> Path:
    """Resolved path to check_bmad_commands.sh; fails fast if missing."""
    assert HELPER.exists(), f"Helper not found: {HELPER}"
    return HELPER


def _base_env() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}


def _write_skill_md(base: Path, commands: str) -> Path:
    """Write a minimal SKILL.md whose table cell carries *commands* verbatim."""
    p = base / "SKILL.md"
    p.write_text(
        "# Dispatch\n\n"
        "| Phase | Agent | Workflow Command |\n"
        "|---|---|---|\n"
        f"| X | Y | {commands} |\n",
        encoding="utf-8",
    )
    return p


def _make_skills(base: Path, names: tuple[str, ...]) -> Path:
    """Create a skills dir with one subdir per skill name; return the dir."""
    d = base / "skills"
    d.mkdir(exist_ok=True)
    for n in names:
        (d / n).mkdir(exist_ok=True)
    return d


def _write_skill_frontmatter(skills_dir: Path, name: str, description: str) -> None:
    """Give an installed skill a SKILL.md carrying *description* in frontmatter."""
    (skills_dir / name).mkdir(exist_ok=True)
    (skills_dir / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _run(
    helper: Path,
    skill_md: Path,
    skills_dir: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(helper),
            "--skill-md",
            str(skill_md),
            "--skills-dir",
            str(skills_dir),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_base_env(),
    )


# ---------------------------------------------------------------------------
# All referenced commands resolve -> silent exit 0
# ---------------------------------------------------------------------------


def test_all_resolve_is_silent(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(tmp_path, "`/bmad-agent-dev`, `/bmad-code-review`")
    skills = _make_skills(tmp_path, ("bmad-agent-dev", "bmad-code-review"))
    r = _run(helper, skill_md, skills)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# An unresolved command fires loud; only the unresolved one is named
# ---------------------------------------------------------------------------


def test_unresolved_fires(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(tmp_path, "`/bmad-agent-dev`, `/bmad-nonexistent-skill`")
    # /bmad-nonexistent-skill has no installed skill dir; /bmad-agent-dev does.
    skills = _make_skills(tmp_path, ("bmad-agent-dev",))
    r = _run(helper, skill_md, skills)
    assert r.returncode == 1
    assert r.stdout == ""
    assert "/bmad-nonexistent-skill" in r.stderr
    assert "/bmad-agent-dev" not in r.stderr


# ---------------------------------------------------------------------------
# The "/bmad-agent-<name>" prose placeholder must not be flagged
# ---------------------------------------------------------------------------


def test_placeholder_not_flagged(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(
        tmp_path, "activate via `/bmad-agent-<name>`; DEV is `/bmad-agent-dev`"
    )
    skills = _make_skills(tmp_path, ("bmad-agent-dev",))
    r = _run(helper, skill_md, skills)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# A markdown link path containing a /bmad-*-shaped substring must not be
# treated as a referenced command (only backtick-delimited tokens count)
# ---------------------------------------------------------------------------


def test_link_path_not_flagged(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(
        tmp_path,
        "see [workflow](../workflows/bmad-dispatch/workflow.md); "
        "run `/bmad-agent-dev`",
    )
    skills = _make_skills(tmp_path, ("bmad-agent-dev",))
    r = _run(helper, skill_md, skills)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


# ---------------------------------------------------------------------------
# Graceful degrade: no bmad-* skills installed -> report once, exit 0
# ---------------------------------------------------------------------------


def test_bmad_not_installed_degrades(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(tmp_path, "`/bmad-agent-dev`")
    skills = _make_skills(tmp_path, ())  # empty skills dir, no bmad-* present
    r = _run(helper, skill_md, skills)
    assert r.returncode == 0
    assert r.stdout == ""
    assert "BMAD not installed" in r.stderr


# ---------------------------------------------------------------------------
# Arg / input errors -> exit 2, stderr, stdout empty
# ---------------------------------------------------------------------------


def test_unknown_arg_exits_two(helper: Path, tmp_path: Path) -> None:
    r = subprocess.run(
        ["bash", str(helper), "--bogus"],
        capture_output=True,
        text=True,
        check=False,
        env=_base_env(),
    )
    assert r.returncode == 2
    assert r.stdout == ""
    assert "Usage" in r.stderr


def test_missing_skill_md_exits_two(helper: Path, tmp_path: Path) -> None:
    skills = _make_skills(tmp_path, ("bmad-agent-dev",))
    r = _run(helper, tmp_path / "nope.md", skills)
    assert r.returncode == 2
    assert r.stdout == ""
    assert "not found" in r.stderr


# ---------------------------------------------------------------------------
# --check-deprecated: a shim RESOLVES, so only this mode can catch it (TD-971)
# ---------------------------------------------------------------------------


def test_deprecated_shim_ignored_without_flag(helper: Path, tmp_path: Path) -> None:
    """Default mode is resolution-only: a shim resolves, so it passes silently.

    This pins the exact gap that let TD-971 survive a green check.
    """
    skill_md = _write_skill_md(tmp_path, "`/bmad-create-prd`")
    skills = _make_skills(tmp_path, ())
    _write_skill_frontmatter(
        skills, "bmad-create-prd", "'DEPRECATED — consolidated into bmad-prd.'"
    )
    r = _run(helper, skill_md, skills)
    assert r.returncode == 0
    assert r.stderr == ""


def test_deprecated_shim_fires_with_flag(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(tmp_path, "`/bmad-create-prd`, `/bmad-agent-dev`")
    skills = _make_skills(tmp_path, ())
    _write_skill_frontmatter(
        skills, "bmad-create-prd", "'DEPRECATED — consolidated into bmad-prd.'"
    )
    _write_skill_frontmatter(skills, "bmad-agent-dev", "Senior software engineer.")
    r = _run(helper, skill_md, skills, "--check-deprecated")
    assert r.returncode == 1
    assert r.stdout == ""
    assert "/bmad-create-prd" in r.stderr
    assert "/bmad-agent-dev" not in r.stderr


def test_live_skill_is_silent_with_flag(helper: Path, tmp_path: Path) -> None:
    skill_md = _write_skill_md(tmp_path, "`/bmad-agent-dev`")
    skills = _make_skills(tmp_path, ())
    _write_skill_frontmatter(skills, "bmad-agent-dev", "Senior software engineer.")
    r = _run(helper, skill_md, skills, "--check-deprecated")
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_body_mention_of_deprecation_not_flagged(helper: Path, tmp_path: Path) -> None:
    """Only the frontmatter `description:` marks a shim; body prose does not.

    /bmad-create-story says "Performance improvements or deprecations" in its
    body and is NOT a shim — a body-wide grep would false-positive on it.
    """
    skill_md = _write_skill_md(tmp_path, "`/bmad-create-story`")
    skills = _make_skills(tmp_path, ())
    (skills / "bmad-create-story").mkdir(exist_ok=True)
    (skills / "bmad-create-story" / "SKILL.md").write_text(
        "---\nname: bmad-create-story\ndescription: Creates a story file.\n---\n\n"
        "# Create Story\n\n- Performance improvements or deprecations\n",
        encoding="utf-8",
    )
    r = _run(helper, skill_md, skills, "--check-deprecated")
    assert r.returncode == 0
    assert r.stderr == ""


def test_deprecated_flag_degrades_when_bmad_absent(
    helper: Path, tmp_path: Path
) -> None:
    """Graceful degrade still wins over the deprecation pass."""
    skill_md = _write_skill_md(tmp_path, "`/bmad-agent-dev`")
    skills = _make_skills(tmp_path, ())
    r = _run(helper, skill_md, skills, "--check-deprecated")
    assert r.returncode == 0
    assert "BMAD not installed" in r.stderr
