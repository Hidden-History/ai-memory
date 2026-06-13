"""Install tests for multi-CLI agent-guidance delivery (TD-600 / BP-172).

The installer already ships AI-Memory guidance to Claude (.claude/rules/ai-memory.md).
This covers the other three CLIs, each in that CLI's own always-on convention:

  - Gemini  → AI-Memory-owned AI-MEMORY.md at project root + appended to
              context.fileName in .gemini/settings.json (never drops GEMINI.md
              or user entries; never writes the user's GEMINI.md).
  - Cursor  → owned .cursor/rules/ai-memory.mdc with `alwaysApply: true`
              (never touches other .mdc / .cursorrules / AGENTS.md).
  - Codex   → managed marker-block inside root AGENTS.md (insert/replace;
              byte-preserved outside markers; backup + atomic write).

Each function is exercised by sourcing install.sh (minus `main "$@"`) and calling
the real write_<cli>_config with a mocked INSTALL_DIR carrying the shipped
template files.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
_INSTALL_SH = _SCRIPTS_DIR / "install.sh"
_TEMPLATES = _REPO / "src" / "memory" / "adapters" / "templates"


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


@pytest.fixture
def install_dir(tmp_path) -> Path:
    """Mock INSTALL_DIR carrying the real shipped templates + merge_agents_md.py."""
    d = tmp_path / "install_dir"
    # Templates (real shipped guidance source files).
    shutil.copytree(_TEMPLATES, d / "src" / "memory" / "adapters" / "templates")
    # Codex managed-block splice script.
    (d / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        _SCRIPTS_DIR / "merge_agents_md.py", d / "scripts" / "merge_agents_md.py"
    )
    return d


def _call(install_sh: Path, func: str, project: Path, install: Path, force="false"):
    bash_cmd = f"""
set -euo pipefail
source "{install_sh}"
{func} "{project}" "{install}" "test-project" "{force}"
"""
    return subprocess.run(["bash", "-c", bash_cmd], capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #
class TestGeminiGuidance:
    def test_owned_file_and_context_registered(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        guidance = project / "AI-MEMORY.md"
        assert guidance.exists()
        assert (
            guidance.read_bytes()
            == (_TEMPLATES / "gemini" / "ai-memory.md").read_bytes()
        )

        settings = json.loads((project / ".gemini" / "settings.json").read_text())
        names = settings["context"]["fileName"]
        # Default GEMINI.md preserved (so implicit loading isn't lost) + ours added.
        assert names == ["GEMINI.md", "AI-MEMORY.md"]

    def test_zero_clobber_user_gemini_md_and_custom_context(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        user_gemini = project / "GEMINI.md"
        user_gemini.write_text("# My Gemini rules\nKeep me.\n", encoding="utf-8")
        # Pre-existing user settings with a custom context.fileName (no AI-Memory marker).
        (project / ".gemini" / "settings.json").write_text(
            json.dumps({"context": {"fileName": ["GEMINI.md", "custom.md"]}}),
            encoding="utf-8",
        )
        before = user_gemini.read_bytes()

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        # User's GEMINI.md never written.
        assert user_gemini.read_bytes() == before
        # Custom entry preserved; AI-MEMORY.md appended; no duplication.
        names = json.loads((project / ".gemini" / "settings.json").read_text())[
            "context"
        ]["fileName"]
        assert names == ["GEMINI.md", "custom.md", "AI-MEMORY.md"]

    def test_idempotent_no_duplicate_context_entry(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        # Force a re-write (marker now present) — must not duplicate AI-MEMORY.md.
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            force="true",
        )
        assert result.returncode == 0, result.stderr
        names = json.loads((project / ".gemini" / "settings.json").read_text())[
            "context"
        ]["fileName"]
        assert names.count("AI-MEMORY.md") == 1

    def test_update_path_deploys_guidance_without_force(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """No-force re-install over an existing ai-memory hook config still deploys
        the guidance file and registers context.fileName (regression for the
        hook-config early-return that previously gated guidance deploy)."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        # Simulate an existing ai-memory settings.json (hook config already present).
        existing_settings = {
            "env": {"AI_MEMORY_INSTALL_DIR": "/old/path"},
            "hooks": {},
            "context": {"fileName": ["GEMINI.md"]},
        }
        (project / ".gemini" / "settings.json").write_text(
            json.dumps(existing_settings), encoding="utf-8"
        )

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        # Guidance file deployed even though the hook config was skipped.
        guidance = project / "AI-MEMORY.md"
        assert guidance.exists()
        assert (
            guidance.read_bytes()
            == (_TEMPLATES / "gemini" / "ai-memory.md").read_bytes()
        )
        # context.fileName registration happened.
        names = json.loads((project / ".gemini" / "settings.json").read_text())[
            "context"
        ]["fileName"]
        assert "AI-MEMORY.md" in names
        # Existing entry preserved.
        assert "GEMINI.md" in names


# --------------------------------------------------------------------------- #
# Cursor
# --------------------------------------------------------------------------- #
class TestCursorGuidance:
    def test_owned_mdc_with_always_apply(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(install_sh_no_main, "write_cursor_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        mdc = project / ".cursor" / "rules" / "ai-memory.mdc"
        assert mdc.exists()
        text = mdc.read_text(encoding="utf-8")
        assert text.startswith("---")
        assert "alwaysApply: true" in text
        assert "search-memory" in text

    def test_zero_clobber_other_cursor_files(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        rules = project / ".cursor" / "rules"
        rules.mkdir(parents=True)
        user_rule = rules / "my.mdc"
        user_rule.write_text("---\nalwaysApply: false\n---\nMine.\n", encoding="utf-8")
        cursorrules = project / ".cursorrules"
        cursorrules.write_text("legacy user rules\n", encoding="utf-8")
        agents = project / "AGENTS.md"
        agents.write_text("# user agents\n", encoding="utf-8")
        before = {p: p.read_bytes() for p in (user_rule, cursorrules, agents)}

        result = _call(install_sh_no_main, "write_cursor_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        for p, original in before.items():
            assert p.read_bytes() == original, f"{p} was modified"
        assert (rules / "ai-memory.mdc").exists()
        assert sorted(p.name for p in rules.iterdir()) == ["ai-memory.mdc", "my.mdc"]

    def test_idempotent_single_file(self, install_sh_no_main, install_dir, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        _call(install_sh_no_main, "write_cursor_config", project, install_dir)
        first = (project / ".cursor" / "rules" / "ai-memory.mdc").read_bytes()
        result = _call(
            install_sh_no_main,
            "write_cursor_config",
            project,
            install_dir,
            force="true",
        )
        assert result.returncode == 0, result.stderr
        rules = project / ".cursor" / "rules"
        assert [p.name for p in rules.iterdir()] == ["ai-memory.mdc"]
        assert (rules / "ai-memory.mdc").read_bytes() == first

    def test_update_path_deploys_guidance_without_force(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """No-force re-install over an existing ai-memory hook config still deploys
        the .mdc guidance rule (regression for the early-return gate)."""
        project = tmp_path / "proj"
        hooks_dir = project / ".cursor"
        hooks_dir.mkdir(parents=True)
        # Simulate an existing ai-memory hooks.json.
        (hooks_dir / "hooks.json").write_text(
            json.dumps({"AI_MEMORY_INSTALL_DIR": "/old"}), encoding="utf-8"
        )

        result = _call(install_sh_no_main, "write_cursor_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        mdc = project / ".cursor" / "rules" / "ai-memory.mdc"
        assert mdc.exists()
        assert "alwaysApply: true" in mdc.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Codex
# --------------------------------------------------------------------------- #
class TestCodexGuidance:
    def test_managed_block_in_agents_md(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(install_sh_no_main, "write_codex_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        agents = project / "AGENTS.md"
        assert agents.exists()
        text = agents.read_text(encoding="utf-8")
        assert "<!-- BEGIN AI-MEMORY -->" in text
        assert "<!-- END AI-MEMORY -->" in text
        assert "search-memory" in text

    def test_zero_clobber_existing_agents_md(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        agents = project / "AGENTS.md"
        user_text = "# My AGENTS\n\nUser-authored guidance. Do not clobber.\n"
        agents.write_text(user_text, encoding="utf-8")

        result = _call(install_sh_no_main, "write_codex_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        out = agents.read_text(encoding="utf-8")
        # User content preserved byte-for-byte as a prefix; block appended after.
        assert out.startswith(user_text)
        assert "<!-- BEGIN AI-MEMORY -->" in out
        # Backup of the original was created.
        backups = list(project.glob("AGENTS.md.backup.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == user_text

    def test_idempotent_block_replaced_not_stacked(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        project = tmp_path / "proj"
        project.mkdir()
        agents = project / "AGENTS.md"
        agents.write_text("# My AGENTS\n\nKeep me.\n", encoding="utf-8")
        _call(install_sh_no_main, "write_codex_config", project, install_dir)
        first = agents.read_text(encoding="utf-8")
        result = _call(
            install_sh_no_main, "write_codex_config", project, install_dir, force="true"
        )
        assert result.returncode == 0, result.stderr
        second = agents.read_text(encoding="utf-8")
        assert first == second
        assert second.count("<!-- BEGIN AI-MEMORY -->") == 1

    def test_update_path_deploys_guidance_without_force(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """No-force re-install over an existing ai-memory hook config still deploys
        the AGENTS.md guidance block (regression for the early-return gate)."""
        project = tmp_path / "proj"
        hooks_dir = project / ".codex"
        hooks_dir.mkdir(parents=True)
        # Simulate an existing ai-memory hooks.json.
        (hooks_dir / "hooks.json").write_text(
            json.dumps({"AI_MEMORY_INSTALL_DIR": "/old"}), encoding="utf-8"
        )

        result = _call(install_sh_no_main, "write_codex_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        agents = project / "AGENTS.md"
        assert agents.exists()
        text = agents.read_text(encoding="utf-8")
        assert "<!-- BEGIN AI-MEMORY -->" in text
        assert "search-memory" in text
