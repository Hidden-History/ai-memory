"""Unit tests for Codex CLI adapter normalize_codex_event and adapter functions.

Tests cover acceptance criteria for Stories 5.1, 5.2, 5.2a, 5.3, 5.4, 5.5.
"""

import pathlib

import pytest
import yaml

from memory.adapters.schema import (
    normalize_codex_event,
    validate_canonical_event,
)


class TestNormalizeCodexEvent:
    def test_session_start_basic(self):
        raw = {
            "session_id": "codex-sess-001",
            "cwd": "/home/user/project",
        }
        event = normalize_codex_event(raw, "SessionStart")
        assert event["session_id"] == "codex-sess-001"
        assert event["cwd"] == "/home/user/project"
        assert event["hook_event_name"] == "SessionStart"
        assert event["ide_source"] == "codex"
        assert event["tool_name"] is None
        assert event["is_background_agent"] is False
        validate_canonical_event(event)

    def test_hook_name_mapping(self):
        cases = {
            "SessionStart": "SessionStart",
            "PostToolUse": "PostToolUse",
            "UserPromptSubmit": "UserPromptSubmit",
            "Stop": "Stop",
        }
        for codex_name, canonical_name in cases.items():
            raw = {"session_id": "s", "cwd": "/p"}
            if codex_name == "UserPromptSubmit":
                raw["prompt"] = "test prompt"
            event = normalize_codex_event(raw, codex_name)
            assert event["hook_event_name"] == canonical_name, (
                f"{codex_name} -> {canonical_name}"
            )

    def test_bash_tool_mapping(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "Bash",
        }
        event = normalize_codex_event(raw, "PostToolUse")
        assert event["tool_name"] == "Bash"
        validate_canonical_event(event)

    def test_user_prompt_submit_populates_user_prompt(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "prompt": "what authentication pattern do we use?",
        }
        event = normalize_codex_event(raw, "UserPromptSubmit")
        assert event["hook_event_name"] == "UserPromptSubmit"
        assert event["user_prompt"] == "what authentication pattern do we use?"
        validate_canonical_event(event)

    def test_non_prompt_event_user_prompt_is_none(self):
        raw = {"session_id": "s", "cwd": "/p"}
        event = normalize_codex_event(raw, "SessionStart")
        assert event["user_prompt"] is None

    def test_is_background_agent_always_false(self):
        raw = {"session_id": "s", "cwd": "/p"}
        event = normalize_codex_event(raw, "SessionStart")
        assert event["is_background_agent"] is False

    def test_session_id_fallback_transcript_path(self):
        raw = {
            "cwd": "/project",
            "transcript_path": "/home/user/.codex/sessions/abc123.json",
        }
        event = normalize_codex_event(raw, "SessionStart")
        assert event["session_id"] == "abc123"

    def test_stop_event_normalizes(self):
        raw = {
            "session_id": "codex-sess-stop",
            "cwd": "/project",
        }
        event = normalize_codex_event(raw, "Stop")
        assert event["hook_event_name"] == "Stop"
        assert event["ide_source"] == "codex"
        validate_canonical_event(event)

    def test_post_tool_use_bash_with_tool_response(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "Bash",
            "tool_input": {"cmd": "npm test"},
            "tool_response": "FAIL: 3 tests failed",
        }
        event = normalize_codex_event(raw, "PostToolUse")
        assert event["tool_name"] == "Bash"
        assert event["tool_response"] == "FAIL: 3 tests failed"
        assert event["tool_input"] == {"cmd": "npm test"}
        validate_canonical_event(event)

    def test_unknown_tool_name_passthrough(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "UnknownTool",
        }
        event = normalize_codex_event(raw, "PostToolUse")
        # Unknown tools pass through as-is (not None)
        assert event["tool_name"] == "UnknownTool"

    def test_turn_id_field_available_but_not_required(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "turn_id": "turn-abc-123",
        }
        # turn_id is not in canonical schema but should not raise
        event = normalize_codex_event(raw, "SessionStart")
        validate_canonical_event(event)

    def test_validate_passes_for_session_start(self):
        raw = {
            "session_id": "codex-sess-valid",
            "cwd": "/project",
        }
        event = normalize_codex_event(raw, "SessionStart")
        validate_canonical_event(event)

    def test_validate_passes_for_stop(self):
        raw = {
            "session_id": "codex-sess-stop",
            "cwd": "/project",
        }
        event = normalize_codex_event(raw, "Stop")
        validate_canonical_event(event)


class TestCodexSkillTemplates:
    """Tests for Codex SKILL.md template files (Story 5.5)."""

    TEMPLATES_BASE = pathlib.Path(__file__).parent.parent / "templates" / "codex"

    @pytest.mark.parametrize("skill_name", ["search-memory", "memory-status"])
    def test_skill_file_exists(self, skill_name):
        skill_path = self.TEMPLATES_BASE / skill_name / "SKILL.md"
        assert skill_path.exists(), f"SKILL.md missing for {skill_name}"

    @pytest.mark.parametrize("skill_name", ["search-memory", "memory-status"])
    def test_skill_frontmatter_has_name_and_description(self, skill_name):
        skill_path = self.TEMPLATES_BASE / skill_name / "SKILL.md"
        content = skill_path.read_text()

        parts = content.split("---", 2)
        assert len(parts) >= 3, f"No valid YAML frontmatter in {skill_name}/SKILL.md"
        frontmatter = yaml.safe_load(parts[1])

        assert "name" in frontmatter, (
            f"Missing 'name' in {skill_name}/SKILL.md frontmatter"
        )
        assert "description" in frontmatter, (
            f"Missing 'description' in {skill_name}/SKILL.md frontmatter"
        )
        assert frontmatter["name"], f"'name' is empty in {skill_name}/SKILL.md"
        assert frontmatter["description"], (
            f"'description' is empty in {skill_name}/SKILL.md"
        )

    @pytest.mark.parametrize("skill_name", ["search-memory", "memory-status"])
    def test_skill_allowed_tools_is_shell(self, skill_name):
        skill_path = self.TEMPLATES_BASE / skill_name / "SKILL.md"
        content = skill_path.read_text()
        parts = content.split("---", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter.get("allowed-tools") == "shell", (
            f"allowed-tools must be 'shell' in {skill_name}/SKILL.md"
        )

    def test_search_memory_references_install_dir(self):
        skill_path = self.TEMPLATES_BASE / "search-memory" / "SKILL.md"
        content = skill_path.read_text()
        assert "$AI_MEMORY_INSTALL_DIR" in content
