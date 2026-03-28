"""Unit tests for Cursor IDE adapter normalize_cursor_event and adapter functions.

Tests cover acceptance criteria for Stories 4.1, 4.2, 4.3, 4.4, 4.5.
"""

import pathlib

import pytest
import yaml

from memory.adapters.schema import (
    normalize_cursor_event,
    validate_canonical_event,
)


class TestNormalizeCursorEvent:
    def test_session_start_basic(self):
        raw = {
            "session_id": "cursor-sess-001",
            "cwd": "/home/user/project",
        }
        event = normalize_cursor_event(raw, "sessionStart")
        assert event["session_id"] == "cursor-sess-001"
        assert event["cwd"] == "/home/user/project"
        assert event["hook_event_name"] == "SessionStart"
        assert event["ide_source"] == "cursor"
        assert event["tool_name"] is None
        assert event["is_background_agent"] is False
        validate_canonical_event(event)

    def test_session_start_workspace_roots_fallback(self):
        raw = {
            "session_id": "cursor-sess-002",
            "workspace_roots": ["/path/to/project"],
        }
        event = normalize_cursor_event(raw, "sessionStart")
        assert event["cwd"] == "/path/to/project"
        validate_canonical_event(event)

    def test_session_start_is_background_agent_true(self):
        raw = {
            "session_id": "cursor-sess-003",
            "cwd": "/project",
            "is_background_agent": True,
        }
        event = normalize_cursor_event(raw, "sessionStart")
        assert event["is_background_agent"] is True
        validate_canonical_event(event)

    def test_session_start_is_background_agent_false_default(self):
        raw = {"session_id": "s", "cwd": "/p"}
        event = normalize_cursor_event(raw, "sessionStart")
        assert event["is_background_agent"] is False

    def test_conversation_id_fallback_for_session_id(self):
        raw = {
            "conversation_id": "conv-abc-123",
            "cwd": "/project",
        }
        event = normalize_cursor_event(raw, "sessionStart")
        assert event["session_id"] == "conv-abc-123"

    def test_hook_name_mapping(self):
        cases = {
            "sessionStart": "SessionStart",
            "postToolUse": "PostToolUse",
            "preToolUse": "PreToolUse",
            "beforeSubmitPrompt": "UserPromptSubmit",
            "preCompact": "PreCompact",
            "stop": "Stop",
            "sessionEnd": "SessionEnd",
        }
        for cursor_name, canonical_name in cases.items():
            raw = {"session_id": "s", "cwd": "/p"}
            if cursor_name == "beforeSubmitPrompt":
                raw["prompt"] = "test prompt"
            event = normalize_cursor_event(raw, cursor_name)
            assert (
                event["hook_event_name"] == canonical_name
            ), f"{cursor_name} -> {canonical_name}"

    def test_tool_name_mapping(self):
        cases = {
            "Write": "Write",
            "Edit": "Edit",
            "Shell": "Bash",
            "Read": "Read",
            "Grep": "Grep",
            "Delete": "Delete",
            "NotebookEdit": "NotebookEdit",
        }
        for cursor_name, canonical_name in cases.items():
            raw = {"session_id": "s", "cwd": "/p", "tool_name": cursor_name}
            event = normalize_cursor_event(raw, "postToolUse")
            assert (
                event["tool_name"] == canonical_name
            ), f"{cursor_name} -> {canonical_name}"

    def test_mcp_tool_normalized(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "MCP:github_search",
        }
        event = normalize_cursor_event(raw, "postToolUse")
        assert event["tool_name"] == "mcp:unknown:github_search"

    def test_mcp_tool_normalized_database_query(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "MCP:database_query",
        }
        event = normalize_cursor_event(raw, "postToolUse")
        assert event["tool_name"] == "mcp:unknown:database_query"

    def test_tool_output_maps_to_tool_response(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "Shell",
            "tool_output": "command output here",
        }
        event = normalize_cursor_event(raw, "postToolUse")
        assert event["tool_response"] == "command output here"

    def test_tool_response_preferred_over_tool_output(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "Shell",
            "tool_response": "from tool_response",
            "tool_output": "from tool_output",
        }
        event = normalize_cursor_event(raw, "postToolUse")
        assert event["tool_response"] == "from tool_response"

    def test_before_submit_prompt_populates_user_prompt(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "prompt": "what authentication pattern do we use?",
        }
        event = normalize_cursor_event(raw, "beforeSubmitPrompt")
        assert event["hook_event_name"] == "UserPromptSubmit"
        assert event["user_prompt"] == "what authentication pattern do we use?"
        validate_canonical_event(event)

    def test_non_prompt_event_user_prompt_is_none(self):
        raw = {"session_id": "s", "cwd": "/p"}
        event = normalize_cursor_event(raw, "postToolUse")
        assert event["user_prompt"] is None

    def test_pre_compact_context_fields(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "context_usage_percent": 87.5,
            "context_tokens": 120000,
            "context_window_size": 140000,
        }
        event = normalize_cursor_event(raw, "preCompact")
        assert event["hook_event_name"] == "PreCompact"
        assert event["context_usage_percent"] == 87.5
        assert event["context_tokens"] == 120000
        assert event["context_window_size"] == 140000
        validate_canonical_event(event)

    def test_validate_passes_for_post_tool_use(self):
        raw = {
            "session_id": "cursor-sess-004",
            "cwd": "/project",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test.py"},
            "tool_output": "file written",
        }
        event = normalize_cursor_event(raw, "postToolUse")
        assert event["tool_name"] == "Write"
        validate_canonical_event(event)


class TestCursorSkillTemplates:
    """Tests for Cursor SKILL.md template files (Story 4.5)."""

    TEMPLATES_BASE = pathlib.Path(__file__).parent.parent / "templates" / "cursor"

    @pytest.mark.parametrize(
        "skill_name", ["search-memory", "memory-status", "save-memory"]
    )
    def test_skill_file_exists(self, skill_name):
        skill_path = self.TEMPLATES_BASE / skill_name / "SKILL.md"
        assert skill_path.exists(), f"SKILL.md missing for {skill_name}"

    @pytest.mark.parametrize(
        "skill_name", ["search-memory", "memory-status", "save-memory"]
    )
    def test_skill_frontmatter_has_name_and_description(self, skill_name):
        skill_path = self.TEMPLATES_BASE / skill_name / "SKILL.md"
        content = skill_path.read_text()

        # Extract YAML frontmatter between --- delimiters
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"No valid YAML frontmatter in {skill_name}/SKILL.md"
        frontmatter = yaml.safe_load(parts[1])

        assert (
            "name" in frontmatter
        ), f"Missing 'name' in {skill_name}/SKILL.md frontmatter"
        assert (
            "description" in frontmatter
        ), f"Missing 'description' in {skill_name}/SKILL.md frontmatter"
        assert frontmatter["name"], f"'name' is empty in {skill_name}/SKILL.md"
        assert frontmatter[
            "description"
        ], f"'description' is empty in {skill_name}/SKILL.md"

    @pytest.mark.parametrize(
        "skill_name", ["search-memory", "memory-status", "save-memory"]
    )
    def test_skill_allowed_tools_is_bash(self, skill_name):
        skill_path = self.TEMPLATES_BASE / skill_name / "SKILL.md"
        content = skill_path.read_text()
        parts = content.split("---", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert (
            frontmatter.get("allowed-tools") == "Bash"
        ), f"allowed-tools must be 'Bash' in {skill_name}/SKILL.md"

    def test_search_memory_references_install_dir(self):
        skill_path = self.TEMPLATES_BASE / "search-memory" / "SKILL.md"
        content = skill_path.read_text()
        assert "$AI_MEMORY_INSTALL_DIR" in content
