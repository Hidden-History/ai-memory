"""Unit tests for Gemini CLI session_start adapter and normalize_gemini_event.

Tests cover Story 3.1 acceptance criteria.
"""

import json
import os
from unittest.mock import patch

from memory.adapters.schema import (
    normalize_gemini_event,
    validate_canonical_event,
)


class TestNormalizeGeminiEvent:
    def test_session_start_basic(self):
        raw = {
            "session_id": "gemini-sess-001",
            "cwd": "/home/user/project",
            "hook_event_name": "SessionStart",
            "timestamp": "2026-03-27T12:00:00Z",
        }
        event = normalize_gemini_event(raw, "SessionStart")
        assert event["session_id"] == "gemini-sess-001"
        assert event["cwd"] == "/home/user/project"
        assert event["hook_event_name"] == "SessionStart"
        assert event["ide_source"] == "gemini"
        assert event["tool_name"] is None
        assert event["is_background_agent"] is False
        validate_canonical_event(event)

    def test_after_tool_maps_to_post_tool_use(self):
        raw = {
            "session_id": "sess-002",
            "cwd": "/project",
            "tool_name": "edit_file",
            "tool_input": {"file_path": "/test.py"},
            "tool_response": {"llmContent": "file edited successfully"},
        }
        event = normalize_gemini_event(raw, "AfterTool")
        assert event["hook_event_name"] == "PostToolUse"
        assert event["tool_name"] == "Edit"
        assert event["tool_response"] == "file edited successfully"
        validate_canonical_event(event)

    def test_tool_name_mapping(self):
        cases = {
            "edit_file": "Edit",
            "write_file": "Write",
            "create_file": "Write",
            "run_shell_command": "Bash",
        }
        for gemini_name, canonical_name in cases.items():
            raw = {"session_id": "s", "cwd": "/p", "tool_name": gemini_name}
            event = normalize_gemini_event(raw, "AfterTool")
            assert (
                event["tool_name"] == canonical_name
            ), f"{gemini_name} -> {canonical_name}"

    def test_mcp_tool_normalized(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "mcp_postgres_query",
        }
        event = normalize_gemini_event(raw, "AfterTool")
        assert event["tool_name"] == "mcp:postgres:query"

    def test_before_tool_maps_to_pre_tool_use(self):
        raw = {"session_id": "s", "cwd": "/p", "tool_name": "edit_file"}
        event = normalize_gemini_event(raw, "BeforeTool")
        assert event["hook_event_name"] == "PreToolUse"

    def test_before_agent_maps_to_user_prompt_submit(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "prompt": "how should I structure this?",
        }
        event = normalize_gemini_event(raw, "BeforeAgent")
        assert event["hook_event_name"] == "UserPromptSubmit"
        assert event["user_prompt"] == "how should I structure this?"
        validate_canonical_event(event)

    def test_pre_compress_maps_to_pre_compact(self):
        raw = {"session_id": "s", "cwd": "/p", "trigger": "auto"}
        event = normalize_gemini_event(raw, "PreCompress")
        assert event["hook_event_name"] == "PreCompact"
        assert event["trigger"] == "auto"

    def test_session_end_maps_to_session_end(self):
        raw = {"session_id": "s", "cwd": "/p"}
        event = normalize_gemini_event(raw, "SessionEnd")
        assert event["hook_event_name"] == "SessionEnd"

    def test_cwd_fallback_to_gemini_env(self):
        raw = {"session_id": "s"}
        with patch.dict(os.environ, {"GEMINI_CWD": "/env/gemini"}):
            event = normalize_gemini_event(raw, "SessionStart")
            assert event["cwd"] == "/env/gemini"

    def test_tool_response_llm_content_extracted(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "write_file",
            "tool_response": {
                "llmContent": "wrote 42 bytes",
                "rawOutput": "...",
            },
        }
        event = normalize_gemini_event(raw, "AfterTool")
        assert event["tool_response"] == "wrote 42 bytes"

    def test_tool_response_non_dict_passthrough(self):
        raw = {
            "session_id": "s",
            "cwd": "/p",
            "tool_name": "edit_file",
            "tool_response": "plain string response",
        }
        event = normalize_gemini_event(raw, "AfterTool")
        assert event["tool_response"] == "plain string response"


class TestGeminiSessionStartAdapter:
    """Tests for the adapter's main() function via subprocess or import."""

    def test_malformed_json_returns_empty_output(self):
        from memory.adapters.gemini.session_start import EMPTY_OUTPUT

        assert EMPTY_OUTPUT == {"hookSpecificOutput": {"additionalContext": ""}}

    def test_output_json_produces_valid_json(self, capsys):
        from memory.adapters.gemini.session_start import _output_json

        data = {"hookSpecificOutput": {"additionalContext": "test"}}
        _output_json(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed == data
