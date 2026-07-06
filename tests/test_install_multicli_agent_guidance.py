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

    def test_zero_clobber_user_top_level_keys(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635: a pre-existing settings.json with user top-level keys (theme,
        mcpServers, ...) survives install byte-equivalent except the AI-Memory-owned
        keys (env, hooks, context); a timestamped backup is written first."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        user_settings = {
            "theme": "GitHub",
            "mcpServers": {"my-server": {"command": "node", "args": ["srv.js"]}},
            "model": {"name": "gemini-2.5-pro"},
            "env": {"MY_CUSTOM_VAR": "keep-me", "LOG_LEVEL": "DEBUG"},
        }
        (project / ".gemini" / "settings.json").write_text(
            json.dumps(user_settings), encoding="utf-8"
        )

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        after = json.loads((project / ".gemini" / "settings.json").read_text())
        # User top-level keys survive byte-equivalent (compare everything except
        # the AI-Memory-owned keys the installer sets/updates).
        owned = {"env", "hooks", "context"}
        before_rest = {k: v for k, v in user_settings.items() if k not in owned}
        after_rest = {k: v for k, v in after.items() if k not in owned}
        assert after_rest == before_rest
        # AI-Memory-owned keys are set.
        assert after["env"]["AI_MEMORY_INSTALL_DIR"] == str(install_dir)
        assert after["env"]["AI_MEMORY_PROJECT_ID"] == "test-project"
        assert "SessionStart" in after["hooks"]
        assert "AI-MEMORY.md" in after["context"]["fileName"]
        # User env entries preserved (custom var kept; user LOG_LEVEL not overwritten).
        assert after["env"]["MY_CUSTOM_VAR"] == "keep-me"
        assert after["env"]["LOG_LEVEL"] == "DEBUG"
        # Timestamped backup written before the atomic rewrite.
        assert list((project / ".gemini").glob("settings.json.backup.*"))

    def test_reinstall_idempotent_settings_byte_equivalent(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635: a forced re-install produces byte-identical settings.json."""
        project = tmp_path / "proj"
        project.mkdir()
        _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        first = (project / ".gemini" / "settings.json").read_bytes()
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            force="true",
        )
        assert result.returncode == 0, result.stderr
        second = (project / ".gemini" / "settings.json").read_bytes()
        assert second == first

    def test_malformed_json_no_crash_and_backup_is_pristine(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635: malformed settings.json must NOT abort the installer, and the
        timestamped backup must preserve the ORIGINAL (pristine) content so the
        user's keys are recoverable."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        # Invalid JSON (trailing comma) that still textually carries user keys.
        malformed = '{"theme": "Dracula", "mcpServers": {"srv": {"command": "node"}},}'
        settings.write_text(malformed, encoding="utf-8")
        original = settings.read_bytes()

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        # Installer does not crash on malformed input.
        assert result.returncode == 0, result.stderr
        # settings.json was rewritten to a valid AI-Memory config.
        rewritten = json.loads(settings.read_text())
        assert "AI-MEMORY.md" in rewritten["context"]["fileName"]
        # A pristine backup preserves the ORIGINAL content byte-for-byte, so the
        # user's theme/mcpServers remain recoverable.
        backups = list((project / ".gemini").glob("settings.json.backup.*"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == original
        assert "theme" in backups[0].read_text()
        assert "mcpServers" in backups[0].read_text()

    def test_top_level_non_dict_json_no_crash(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635: a top-level non-dict JSON document (e.g. an array) must not raise
        under set -euo pipefail — it degrades to a safe default."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        settings.write_text("[1, 2, 3]", encoding="utf-8")
        original = settings.read_bytes()

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr
        rewritten = json.loads(settings.read_text())
        assert isinstance(rewritten, dict)
        assert "AI-MEMORY.md" in rewritten["context"]["fileName"]
        # Original array preserved in the pristine backup.
        backups = list((project / ".gemini").glob("settings.json.backup.*"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == original

    def test_context_present_but_non_dict_no_crash(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635: a `context` key whose value is not a dict must not raise; it
        degrades to the default fileName registration."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        settings.write_text(
            json.dumps({"theme": "Solarized", "context": 5}), encoding="utf-8"
        )

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr
        rewritten = json.loads(settings.read_text())
        # User top-level key preserved; context.fileName registered with defaults.
        assert rewritten["theme"] == "Solarized"
        assert rewritten["context"]["fileName"] == ["GEMINI.md", "AI-MEMORY.md"]

    def test_reinstall_idempotent_from_user_file(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635: re-install starting FROM a pre-existing user file (not an empty
        project) is byte-equivalent and the user's top-level keys survive."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        settings.write_text(
            json.dumps({"theme": "GitHub", "mcpServers": {"s": {"command": "x"}}}),
            encoding="utf-8",
        )

        _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        first = settings.read_bytes()
        # Forced re-install must reproduce byte-identical settings.json.
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            force="true",
        )
        assert result.returncode == 0, result.stderr
        second = settings.read_bytes()
        assert second == first
        after = json.loads(second)
        assert after["theme"] == "GitHub"
        assert after["mcpServers"] == {"s": {"command": "x"}}

    def test_deep_merge_preserves_user_authored_hook(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """TD-635 fix ②: a user-authored Gemini hook survives the install — hooks are
        deep-merged (list-append + dedupe-by-command), not wholesale-replaced."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "matcher": "custom",
                                "hooks": [
                                    {"type": "command", "command": "echo user-hook"}
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr
        hooks = json.loads(settings.read_text())["hooks"]
        commands = json.dumps(hooks)
        # User hook preserved.
        assert "echo user-hook" in commands
        # AI-Memory hook appended alongside it (not replacing it).
        assert "gemini/session_start.py" in commands

    def test_all_after_tool_matchers_present_after_clean_install(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """All three AfterTool wrappers survive a clean install. Regression guard:
        the 'edit_file|write_file|create_file' and 'mcp_.*' wrappers share the
        after_tool_capture.py command, so command-only dedupe silently dropped the
        mcp_.* wrapper (Gemini stopped capturing memory on MCP tool calls)."""
        project = tmp_path / "proj"
        project.mkdir()
        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        after_tool = json.loads((project / ".gemini" / "settings.json").read_text())[
            "hooks"
        ]["AfterTool"]
        matchers = [w["matcher"] for w in after_tool]
        assert "edit_file|write_file|create_file" in matchers
        assert "run_shell_command" in matchers
        assert "mcp_.*" in matchers
        # Byte-idempotent on a forced reinstall (dedupe keeps all three, no dupes).
        result = _call(
            install_sh_no_main,
            "write_gemini_config",
            project,
            install_dir,
            force="true",
        )
        assert result.returncode == 0, result.stderr
        after_tool_2 = json.loads((project / ".gemini" / "settings.json").read_text())[
            "hooks"
        ]["AfterTool"]
        assert [w["matcher"] for w in after_tool_2] == matchers

    def test_register_only_leaves_env_and_hooks_untouched(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """Skip-path (existing ai-memory hooks, no force): register context.fileName
        ONLY — env and hooks content is left exactly as the user has it."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        existing = {
            "theme": "Nord",
            "env": {
                "AI_MEMORY_INSTALL_DIR": "/old/install",
                "AI_MEMORY_PROJECT_ID": "old-proj",
                "CUSTOM": "keep-me",
            },
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "custom",
                        "hooks": [{"type": "command", "command": "echo mine"}],
                    }
                ]
            },
            "context": {"fileName": ["GEMINI.md"]},
        }
        settings.write_text(json.dumps(existing), encoding="utf-8")

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr

        after = json.loads(settings.read_text())
        # env + hooks content untouched (no AI-Memory injection, old values kept).
        assert after["env"] == existing["env"]
        assert after["hooks"] == existing["hooks"]
        assert after["theme"] == "Nord"
        # Only context.fileName was updated.
        assert after["context"]["fileName"] == ["GEMINI.md", "AI-MEMORY.md"]

    def test_register_only_repeat_is_noop_with_no_new_backup(
        self, install_sh_no_main, install_dir, tmp_path
    ):
        """A second skip-path call once AI-MEMORY.md is already registered is a true
        no-op: the file is byte-identical and no new backup is written."""
        project = tmp_path / "proj"
        (project / ".gemini").mkdir(parents=True)
        settings = project / ".gemini" / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "env": {"AI_MEMORY_INSTALL_DIR": "/old"},
                    "hooks": {},
                    "context": {"fileName": ["GEMINI.md", "AI-MEMORY.md"]},
                }
            ),
            encoding="utf-8",
        )
        before = settings.read_bytes()

        result = _call(install_sh_no_main, "write_gemini_config", project, install_dir)
        assert result.returncode == 0, result.stderr
        # No write happened (already registered) → byte-identical, zero backups.
        assert settings.read_bytes() == before
        assert list((project / ".gemini").glob("settings.json.backup.*")) == []


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
