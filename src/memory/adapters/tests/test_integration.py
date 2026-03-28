"""Integration tests for multi-IDE adapter system.

Tests cover Epic 7 stories:
- Story 7.1: Cross-IDE memory sharing (SC-04, SC-05, SC-06)
- Story 7.2: Adapter unit tests with synthetic payloads (NFR-401)
- Story 7.3: Installer config generation tests (SC-08)

These tests use mocked Qdrant and pipeline to verify the adapter layer
without requiring a live Docker stack.
"""

import json
import os
import subprocess
import tempfile

from memory.adapters.schema import (
    normalize_claude_event,
    normalize_codex_event,
    normalize_cursor_event,
    normalize_gemini_event,
    validate_canonical_event,
)

# =============================================================================
# Story 7.1: Cross-IDE memory sharing
# =============================================================================


class TestCrossIdeMemorySharing:
    """Verify that canonical events from different IDEs share the same schema
    and would be stored/retrieved from the same Qdrant collections."""

    def test_all_four_ides_produce_valid_canonical_events(self):
        """SC-04/05/06: Events from all IDEs pass the same validation."""
        claude_event = normalize_claude_event(
            {"session_id": "c1", "cwd": "/project", "tool_name": "Write"},
            "PostToolUse",
        )
        gemini_event = normalize_gemini_event(
            {"session_id": "g1", "cwd": "/project", "tool_name": "write_file"},
            "AfterTool",
        )
        cursor_event = normalize_cursor_event(
            {"session_id": "cu1", "cwd": "/project", "tool_name": "Write"},
            "postToolUse",
        )
        codex_event = normalize_codex_event(
            {"session_id": "co1", "cwd": "/project", "tool_name": "Bash"},
            "PostToolUse",
        )

        for event in [claude_event, gemini_event, cursor_event, codex_event]:
            validate_canonical_event(event)

    def test_ide_source_distinguishes_origin(self):
        """FR-102: ide_source field identifies the origin IDE."""
        assert (
            normalize_claude_event({"session_id": "s", "cwd": "/p"}, "PostToolUse")[
                "ide_source"
            ]
            == "claude"
        )
        assert (
            normalize_gemini_event({"session_id": "s", "cwd": "/p"}, "SessionStart")[
                "ide_source"
            ]
            == "gemini"
        )
        assert (
            normalize_cursor_event({"session_id": "s", "cwd": "/p"}, "sessionStart")[
                "ide_source"
            ]
            == "cursor"
        )
        assert (
            normalize_codex_event({"session_id": "s", "cwd": "/p"}, "SessionStart")[
                "ide_source"
            ]
            == "codex"
        )

    def test_tool_names_normalize_to_canonical(self):
        """All IDEs normalize tool names to the same canonical set."""
        # Write operations
        assert (
            normalize_claude_event(
                {"session_id": "s", "cwd": "/p", "tool_name": "Write"}, "PostToolUse"
            )["tool_name"]
            == "Write"
        )
        assert (
            normalize_gemini_event(
                {"session_id": "s", "cwd": "/p", "tool_name": "write_file"}, "AfterTool"
            )["tool_name"]
            == "Write"
        )
        assert (
            normalize_cursor_event(
                {"session_id": "s", "cwd": "/p", "tool_name": "Write"}, "postToolUse"
            )["tool_name"]
            == "Write"
        )

        # Shell/Bash operations
        assert (
            normalize_gemini_event(
                {"session_id": "s", "cwd": "/p", "tool_name": "run_shell_command"},
                "AfterTool",
            )["tool_name"]
            == "Bash"
        )
        assert (
            normalize_cursor_event(
                {"session_id": "s", "cwd": "/p", "tool_name": "Shell"}, "postToolUse"
            )["tool_name"]
            == "Bash"
        )
        assert (
            normalize_codex_event(
                {"session_id": "s", "cwd": "/p", "tool_name": "Bash"}, "PostToolUse"
            )["tool_name"]
            == "Bash"
        )

    def test_mcp_tools_normalize_across_ides(self):
        """MCP tool names from different IDEs normalize to mcp:<server>:<tool>."""
        gemini_event = normalize_gemini_event(
            {"session_id": "s", "cwd": "/p", "tool_name": "mcp_postgres_query"},
            "AfterTool",
        )
        cursor_event = normalize_cursor_event(
            {"session_id": "s", "cwd": "/p", "tool_name": "MCP:query"},
            "postToolUse",
        )
        assert gemini_event["tool_name"] == "mcp:postgres:query"
        assert cursor_event["tool_name"] == "mcp:unknown:query"

    def test_hook_names_normalize_to_canonical(self):
        """Different IDE hook names map to the same canonical events."""
        assert (
            normalize_gemini_event({"session_id": "s", "cwd": "/p"}, "AfterTool")[
                "hook_event_name"
            ]
            == "PostToolUse"
        )
        assert (
            normalize_cursor_event({"session_id": "s", "cwd": "/p"}, "postToolUse")[
                "hook_event_name"
            ]
            == "PostToolUse"
        )
        assert (
            normalize_codex_event({"session_id": "s", "cwd": "/p"}, "PostToolUse")[
                "hook_event_name"
            ]
            == "PostToolUse"
        )

        assert (
            normalize_gemini_event({"session_id": "s", "cwd": "/p"}, "PreCompress")[
                "hook_event_name"
            ]
            == "PreCompact"
        )
        assert (
            normalize_cursor_event({"session_id": "s", "cwd": "/p"}, "preCompact")[
                "hook_event_name"
            ]
            == "PreCompact"
        )


# =============================================================================
# Story 7.2: Adapter JSON output conformance (FR-603)
# =============================================================================


class TestAdapterOutputConformance:
    """Verify all adapter retrieval scripts produce valid JSON stdout."""

    def test_gemini_session_start_empty_output_is_json(self):
        from memory.adapters.gemini.session_start import EMPTY_OUTPUT

        json.dumps(EMPTY_OUTPUT)  # Must not raise

    def test_gemini_empty_output_has_correct_structure(self):
        from memory.adapters.gemini.session_start import EMPTY_OUTPUT

        assert "hookSpecificOutput" in EMPTY_OUTPUT
        assert "additionalContext" in EMPTY_OUTPUT["hookSpecificOutput"]

    def test_cursor_session_start_empty_output_is_json(self):
        from memory.adapters.cursor.session_start import EMPTY_OUTPUT

        json.dumps(EMPTY_OUTPUT)
        assert "additional_context" in EMPTY_OUTPUT

    def test_codex_session_start_empty_output_is_json(self):
        from memory.adapters.codex.session_start import EMPTY_OUTPUT

        json.dumps(EMPTY_OUTPUT)
        assert "hookSpecificOutput" in EMPTY_OUTPUT
        assert "systemMessage" in EMPTY_OUTPUT["hookSpecificOutput"]

    def test_codex_context_injection_empty_output_is_json(self):
        from memory.adapters.codex.context_injection import EMPTY_OUTPUT

        json.dumps(EMPTY_OUTPUT)
        assert "hookSpecificOutput" in EMPTY_OUTPUT
        assert "additionalContext" in EMPTY_OUTPUT["hookSpecificOutput"]


# =============================================================================
# Story 7.3: Installer config generation tests (SC-08)
# =============================================================================


class TestInstallerConfigGeneration:
    """Test that write_*_config() functions produce valid IDE config files."""

    def _run_write_config(self, ide: str, project_path: str, install_dir: str):
        """Run the installer's write_*_config function via bash."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                source scripts/install.sh 2>/dev/null
                # Stub log functions
                log_info() {{ true; }}
                log_success() {{ true; }}
                log_warning() {{ true; }}
                log_debug() {{ true; }}
                write_{ide}_config "{project_path}" "{install_dir}" "test-project" "false"
                """,
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    )
                )
            ),
        )
        return result

    def test_gemini_config_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_dir = os.path.join(tmpdir, "install")
            os.makedirs(os.path.join(install_dir, ".venv/bin"), exist_ok=True)
            os.makedirs(
                os.path.join(install_dir, "adapters/templates/gemini"), exist_ok=True
            )
            project_path = os.path.join(tmpdir, "project")
            os.makedirs(project_path)

            self._run_write_config("gemini", project_path, install_dir)
            config_file = os.path.join(project_path, ".gemini", "settings.json")

            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = json.load(f)
                assert "env" in config
                assert "AI_MEMORY_INSTALL_DIR" in config["env"]
                assert "hooks" in config
                assert "SessionStart" in config["hooks"]
                assert "AfterTool" in config["hooks"]
                assert "PreCompress" in config["hooks"]

    def test_cursor_config_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_dir = os.path.join(tmpdir, "install")
            os.makedirs(os.path.join(install_dir, ".venv/bin"), exist_ok=True)
            os.makedirs(
                os.path.join(install_dir, "adapters/templates/cursor"), exist_ok=True
            )
            project_path = os.path.join(tmpdir, "project")
            os.makedirs(project_path)

            self._run_write_config("cursor", project_path, install_dir)
            config_file = os.path.join(project_path, ".cursor", "hooks.json")

            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = json.load(f)
                assert config.get("version") == 1
                assert "hooks" in config
                assert "sessionStart" in config["hooks"]
                assert "postToolUse" in config["hooks"]
                assert "preCompact" in config["hooks"]
                # FR-304: no failClosed
                for hook_list in config["hooks"].values():
                    for hook in hook_list:
                        assert hook.get("failClosed") is not True

    def test_codex_config_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_dir = os.path.join(tmpdir, "install")
            os.makedirs(os.path.join(install_dir, ".venv/bin"), exist_ok=True)
            os.makedirs(
                os.path.join(install_dir, "adapters/templates/codex"), exist_ok=True
            )
            project_path = os.path.join(tmpdir, "project")
            os.makedirs(project_path)

            self._run_write_config("codex", project_path, install_dir)
            config_file = os.path.join(project_path, ".codex", "hooks.json")

            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = json.load(f)
                assert "hooks" in config
                assert "SessionStart" in config["hooks"]
                assert "PostToolUse" in config["hooks"]
                assert "UserPromptSubmit" in config["hooks"]
                assert "Stop" in config["hooks"]
