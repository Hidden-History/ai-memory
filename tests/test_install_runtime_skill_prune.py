"""Install test: sync_installed_files prunes retired managed skills from the runtime staging dir.

Root cause (TD-741): sync_installed_files copies .claude/skills with an additive
`cp -r`, so a retired managed skill (e.g. aim-bmad-dispatch, dropped at v2.4.0)
that vanished from source lingers in the runtime staging dir (INSTALL_DIR/.claude/skills/)
and re-propagates to every project. sync_installed_files now prunes managed-prefix
skills (aim-*/parzival-save-*) that are absent from source, while leaving non-managed
skills (bmad-*, etc. — installed separately) untouched.

These tests exercise the real sync_installed_files (install.sh sourced minus the final
`main "$@"` line) against a mocked src/dst pair, and assert:

  - a retired aim-* skill present in dst but absent from src is REMOVED.
  - a legit aim-* skill present in both src and dst is KEPT.
  - a non-managed bmad-* skill present in dst but absent from src is KEPT.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"


def _skill_dir(skills_root: Path, name: str) -> Path:
    """Create a minimal skill directory with a SKILL.md under skills_root/<name>/."""
    d = skills_root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill.\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return d


def _scaffold_src(src: Path, skill_names: list[str]) -> None:
    """Create the minimal source tree sync_installed_files requires to run.

    The function hard-fails (exit 1) on the mandatory src/memory, scripts, and
    .claude/hooks copies if their globs are empty, so each needs at least one file.
    Optional dirs are [[ -d ]]-guarded and can be omitted.
    """
    (src / "src" / "memory").mkdir(parents=True)
    (src / "src" / "memory" / "__init__.py").write_text("", encoding="utf-8")
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "placeholder.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (src / ".claude" / "hooks").mkdir(parents=True)
    (src / ".claude" / "hooks" / "placeholder.py").write_text("", encoding="utf-8")

    src_skills = src / ".claude" / "skills"
    src_skills.mkdir(parents=True)
    for name in skill_names:
        _skill_dir(src_skills, name)


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


def _sync(install_sh: Path, src: Path, dst: Path):
    bash_cmd = f"""
set -euo pipefail
source "{install_sh}"
sync_installed_files "{src}" "{dst}"
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


class TestRuntimeSkillPrune:
    def test_retired_managed_skill_pruned_legit_and_nonmanaged_kept(
        self, install_sh_no_main, tmp_path
    ):
        src = tmp_path / "src"
        dst = tmp_path / "dst"

        # Source ships the legit aim-foo only (aim-bmad-dispatch was retired from source).
        _scaffold_src(src, ["aim-foo"])

        # Dest (runtime staging) carries the legit aim-foo, the retired
        # aim-bmad-dispatch ghost, and a non-managed bmad-x skill.
        dst_skills = dst / ".claude" / "skills"
        _skill_dir(dst_skills, "aim-foo")
        _skill_dir(dst_skills, "aim-bmad-dispatch")
        _skill_dir(dst_skills, "bmad-x")

        res = _sync(install_sh_no_main, src, dst)
        assert res.returncode == 0, f"sync failed: {res.stderr}"

        # Retired managed skill removed.
        assert not (
            dst_skills / "aim-bmad-dispatch"
        ).exists(), "retired aim-bmad-dispatch must be pruned from the staging dir"
        # Legit managed skill (present in source) kept.
        assert (dst_skills / "aim-foo").exists(), "legit aim-foo must be kept"
        # Non-managed skill (absent from source) never touched.
        assert (
            dst_skills / "bmad-x"
        ).exists(), "non-managed bmad-x must never be pruned"

    def test_retired_parzival_save_skill_pruned(self, install_sh_no_main, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"

        # Source has no parzival-save-* skills.
        _scaffold_src(src, ["aim-foo"])

        # Dest carries a retired parzival-save-* ghost alongside the legit aim-foo.
        dst_skills = dst / ".claude" / "skills"
        _skill_dir(dst_skills, "aim-foo")
        _skill_dir(dst_skills, "parzival-save-legacy")

        res = _sync(install_sh_no_main, src, dst)
        assert res.returncode == 0, f"sync failed: {res.stderr}"

        assert not (
            dst_skills / "parzival-save-legacy"
        ).exists(), "retired parzival-save-* skill must be pruned"
        assert (dst_skills / "aim-foo").exists()
