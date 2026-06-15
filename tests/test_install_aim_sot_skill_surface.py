"""Install test: aim-sot is surfaced as a discoverable .claude/skills/ shim.

Root cause (Finding #7 / DEC-PM336-A2): aim-sot ships under _ai-memory/skills/ with
no full .claude/skills/ copy, so an installed project could not discover it as a
Claude skill. deploy_ai_memory_skills now generates a thin discovery shim for
aim-* skills that live under _ai-memory/skills/ but lack a full copy.

These tests exercise the real deploy_ai_memory_skills (install.sh sourced minus the
final `main "$@"` line) against a mocked INSTALL_DIR, and assert:

  - aim-sot appears in the target .claude/skills/ as a thin shim (LOAD -> canonical).
  - a sibling that already has a full copy (aim-search) keeps its full copy, unshimmed.
  - parzival-save-* are NOT surfaced: oversight-internal Parzival skills, correctly
    absent from an end-user project's .claude/skills/ (the project has no Parzival).
  - re-install is idempotent (single aim-sot shim; parzival-save-* stays absent).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"


def _skill_md(name: str, description: str, *, tools: str | None = None) -> str:
    """Minimal but realistic SKILL.md with frontmatter + a level-1 heading + body."""
    lines = ["---", f"name: {name}", f"description: {description}"]
    if tools:
        lines.append(f"allowed-tools: {tools}")
    lines += ["---", "", f"# {name} — heading", "", "Canonical skill body content.", ""]
    return "\n".join(lines)


@pytest.fixture
def install_sh_no_main(tmp_path) -> Path:
    """Copy install.sh minus final 'main "$@"' line into tmp_path for safe sourcing."""
    content = _INSTALL_SH.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    assert lines[-1].strip() == 'main "$@"', (
        f"Expected last line 'main \"$@\"', got: {lines[-1]!r}. "
        "If install.sh structure changed, update this fixture."
    )
    copy = tmp_path / "install.sh"
    copy.write_text("".join(lines[:-1]), encoding="utf-8")
    copy.chmod(0o755)
    # install.sh sources _env_split_helpers.sh from its own dir at load time.
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


@pytest.fixture
def install_dir(tmp_path) -> Path:
    """Mock INSTALL_DIR.

    - .claude/skills/aim-search/ : a full skill (deployed verbatim).
    - _ai-memory/skills/aim-sot/ : engine-home skill, no full copy -> shimmed.
    - _ai-memory/skills/aim-search/ : already has a full copy -> NOT shimmed.
    - _ai-memory/skills/parzival-save-handoff/ : oversight-internal -> NOT surfaced.
    """
    d = tmp_path / "install_dir"

    claude_search = d / ".claude" / "skills" / "aim-search"
    claude_search.mkdir(parents=True)
    (claude_search / "SKILL.md").write_text(
        _skill_md("aim-search", "Search memory."), encoding="utf-8"
    )

    aim_mem = d / "_ai-memory" / "skills"
    (aim_mem / "aim-sot").mkdir(parents=True)
    (aim_mem / "aim-sot" / "SKILL.md").write_text(
        _skill_md(
            "aim-sot",
            "Track the source-of-truth for each part of the user's own project.",
            tools="Bash, Read",
        ),
        encoding="utf-8",
    )
    (aim_mem / "aim-search").mkdir(parents=True)
    (aim_mem / "aim-search" / "SKILL.md").write_text(
        _skill_md("aim-search", "Search memory."), encoding="utf-8"
    )
    (aim_mem / "parzival-save-handoff").mkdir(parents=True)
    (aim_mem / "parzival-save-handoff" / "SKILL.md").write_text(
        _skill_md("parzival-save-handoff", "Save Parzival session handoff to Qdrant."),
        encoding="utf-8",
    )
    return d


def _deploy(install_sh: Path, project: Path, install: Path):
    bash_cmd = f"""
set -euo pipefail
source "{install_sh}"
PROJECT_PATH="{project}"
INSTALL_DIR="{install}"
deploy_ai_memory_skills
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


class TestAimSotSkillSurface:
    def test_aim_sot_surfaced_as_shim(self, install_sh_no_main, install_dir, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()

        res = _deploy(install_sh_no_main, project, install_dir)
        assert res.returncode == 0, f"deploy failed: {res.stderr}"

        skills = project / ".claude" / "skills"

        # aim-sot present as a thin shim pointing at the canonical engine home.
        sot = skills / "aim-sot" / "SKILL.md"
        assert sot.exists(), "aim-sot must be surfaced in .claude/skills/"
        sot_text = sot.read_text(encoding="utf-8")
        assert (
            "**LOAD**: Read and follow `_ai-memory/skills/aim-sot/SKILL.md`" in sot_text
        )
        assert "name: aim-sot" in sot_text  # frontmatter carried for indexing
        assert "allowed-tools: Bash, Read" in sot_text

        # aim-search already had a full copy -> remains the full skill, not a shim.
        search = skills / "aim-search" / "SKILL.md"
        assert search.exists()
        search_text = search.read_text(encoding="utf-8")
        assert "**LOAD**" not in search_text, "full-copy skill must not be shimmed"
        assert "Canonical skill body content." in search_text

    def test_parzival_internal_skills_not_surfaced(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()

        res = _deploy(install_sh_no_main, project, install_dir)
        assert res.returncode == 0, f"deploy failed: {res.stderr}"

        # Oversight-internal Parzival skills must NOT leak into an end-user project.
        assert not (project / ".claude" / "skills" / "parzival-save-handoff").exists()

    def test_idempotent_on_reinstall(self, install_sh_no_main, install_dir, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()

        first = _deploy(install_sh_no_main, project, install_dir)
        assert first.returncode == 0, f"first deploy failed: {first.stderr}"
        second = _deploy(install_sh_no_main, project, install_dir)
        assert second.returncode == 0, f"second deploy failed: {second.stderr}"

        sot = project / ".claude" / "skills" / "aim-sot" / "SKILL.md"
        assert sot.exists()
        # Exactly one LOAD line — re-install neither duplicates nor corrupts the shim.
        assert sot.read_text(encoding="utf-8").count("**LOAD**") == 1
        assert not (project / ".claude" / "skills" / "parzival-save-handoff").exists()
