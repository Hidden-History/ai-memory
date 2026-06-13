"""
Install tests for the AI-Memory agent-guidance rule file (TD-600).

The installer ships an AI-Memory-owned rule at $PROJECT_PATH/.claude/rules/ai-memory.md
(Claude Code auto-loads .claude/rules/*.md at session start). Two surfaces are covered:

  1. sync_installed_files() — repo .claude/rules/ flows to INSTALL_DIR/.claude/rules/
     (Layer 1: source-of-truth threading, runs on both fresh + Option-1 update).
  2. deploy_ai_memory_rules() — INSTALL_DIR copy flows to PROJECT_PATH/.claude/rules/ai-memory.md
     (Layer 2: own-file overwrite, zero clobber of user-authored files).

Core safety property: the install creates/overwrites ONLY ai-memory.md. It must NEVER
touch the user's CLAUDE.md, .claude/CLAUDE.md, CLAUDE.local.md, or any other
.claude/rules/*.md.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_REPO_RULE = Path(__file__).parent.parent / ".claude" / "rules" / "ai-memory.md"


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
    shutil.copy(
        _SCRIPTS_DIR / "_env_split_helpers.sh", tmp_path / "_env_split_helpers.sh"
    )
    return copy


def _run_deploy_rules(
    install_sh_copy: Path,
    install_dir: Path,
    project_dir: Path,
) -> subprocess.CompletedProcess:
    """Source install.sh (no-main copy) and call deploy_ai_memory_rules with mocked dirs."""
    bash_cmd = f"""
set -euo pipefail
export INSTALL_DIR="{install_dir}"
export PROJECT_PATH="{project_dir}"
source "{install_sh_copy}"
INSTALL_DIR="{install_dir}"
PROJECT_PATH="{project_dir}"
deploy_ai_memory_rules
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


@pytest.fixture
def install_and_project_dirs(tmp_path):
    """Mock INSTALL_DIR (carrying the shipped rule) + an empty PROJECT_PATH.

    The rule placed in INSTALL_DIR is the real repo file, so assertions about the
    shipped content (e.g. the wired repo URL) exercise the actual product artifact.
    """
    install_dir = tmp_path / "install_dir"
    project_dir = tmp_path / "project_dir"
    rules_src = install_dir / ".claude" / "rules"
    rules_src.mkdir(parents=True)
    shutil.copy(_REPO_RULE, rules_src / "ai-memory.md")
    project_dir.mkdir()
    return install_dir, project_dir


class TestDeployAgentGuidanceRule:
    def test_rule_deployed_with_shipped_content(
        self, install_sh_no_main, install_and_project_dirs
    ):
        install_dir, project_dir = install_and_project_dirs
        result = _run_deploy_rules(install_sh_no_main, install_dir, project_dir)
        assert (
            result.returncode == 0
        ), f"deploy_ai_memory_rules failed:\n{result.stderr}"
        deployed = project_dir / ".claude" / "rules" / "ai-memory.md"
        assert deployed.exists()
        # Byte-identical to the shipped repo source.
        assert deployed.read_bytes() == _REPO_RULE.read_bytes()

    def test_repo_url_wired(self, install_sh_no_main, install_and_project_dirs):
        install_dir, project_dir = install_and_project_dirs
        _run_deploy_rules(install_sh_no_main, install_dir, project_dir)
        content = (project_dir / ".claude" / "rules" / "ai-memory.md").read_text()
        assert "https://github.com/Hidden-History/ai-memory/issues" in content

    def test_rules_dir_created_when_absent(
        self, install_sh_no_main, install_and_project_dirs
    ):
        install_dir, project_dir = install_and_project_dirs
        # project_dir has no .claude/ at all
        assert not (project_dir / ".claude" / "rules").exists()
        result = _run_deploy_rules(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, result.stderr
        assert (project_dir / ".claude" / "rules" / "ai-memory.md").exists()

    def test_idempotent_single_file_identical_content(
        self, install_sh_no_main, install_and_project_dirs
    ):
        install_dir, project_dir = install_and_project_dirs
        _run_deploy_rules(install_sh_no_main, install_dir, project_dir)
        first = (project_dir / ".claude" / "rules" / "ai-memory.md").read_bytes()
        # Second run — own-file overwrite, no duplication/append.
        result = _run_deploy_rules(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, result.stderr
        rules_dir = project_dir / ".claude" / "rules"
        assert [p.name for p in rules_dir.iterdir()] == ["ai-memory.md"]
        assert (rules_dir / "ai-memory.md").read_bytes() == first

    def test_zero_clobber_user_files_untouched(
        self, install_sh_no_main, install_and_project_dirs
    ):
        install_dir, project_dir = install_and_project_dirs

        # Pre-existing user-authored files that must NEVER be touched.
        user_claude_md = project_dir / "CLAUDE.md"
        user_claude_md.write_text(
            "# My project rules\nDo not touch.\n", encoding="utf-8"
        )
        dot_claude_md = project_dir / ".claude" / "CLAUDE.md"
        dot_claude_md.parent.mkdir(parents=True, exist_ok=True)
        dot_claude_md.write_text("# dot-claude CLAUDE\n", encoding="utf-8")
        claude_local = project_dir / "CLAUDE.local.md"
        claude_local.write_text("# local overrides\n", encoding="utf-8")
        user_rule = project_dir / ".claude" / "rules" / "my-rule.md"
        user_rule.parent.mkdir(parents=True, exist_ok=True)
        user_rule.write_text("# My own rule\nKeep me verbatim.\n", encoding="utf-8")

        before = {
            p: p.read_bytes()
            for p in (user_claude_md, dot_claude_md, claude_local, user_rule)
        }

        result = _run_deploy_rules(install_sh_no_main, install_dir, project_dir)
        assert result.returncode == 0, result.stderr

        # Every user file is byte-unchanged.
        for p, original in before.items():
            assert p.read_bytes() == original, f"{p} was modified by install"

        # Only ai-memory.md was added alongside the user's rule.
        assert (project_dir / ".claude" / "rules" / "ai-memory.md").exists()
        assert sorted(
            p.name for p in (project_dir / ".claude" / "rules").iterdir()
        ) == ["ai-memory.md", "my-rule.md"]


class TestSyncInstalledFilesThreadsRules:
    """Layer 1: repo .claude/rules/ is synced into INSTALL_DIR/.claude/rules/ on both
    fresh install (copy_files) and Option-1 update (update_shared_scripts), via the
    shared sync_installed_files() function."""

    def test_rules_synced_to_install_dir(self, install_sh_no_main, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        # Minimal source tree required by sync_installed_files().
        (src_dir / "src" / "memory").mkdir(parents=True)
        (src_dir / "src" / "memory" / "__init__.py").write_text("", encoding="utf-8")
        (src_dir / "scripts").mkdir(parents=True)
        (src_dir / "scripts" / "noop.py").write_text("", encoding="utf-8")
        (src_dir / ".claude" / "hooks").mkdir(parents=True)
        (src_dir / ".claude" / "hooks" / "placeholder").write_text("", encoding="utf-8")
        rules_src = src_dir / ".claude" / "rules"
        rules_src.mkdir(parents=True)
        shutil.copy(_REPO_RULE, rules_src / "ai-memory.md")

        bash_cmd = f"""
set -euo pipefail
source "{install_sh_no_main}"
sync_installed_files "{src_dir}" "{dst_dir}"
"""
        result = subprocess.run(
            ["bash", "-c", bash_cmd], capture_output=True, text=True
        )
        assert result.returncode == 0, f"sync_installed_files failed:\n{result.stderr}"
        synced = dst_dir / ".claude" / "rules" / "ai-memory.md"
        assert synced.exists()
        assert synced.read_bytes() == _REPO_RULE.read_bytes()
