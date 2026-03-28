"""Unit tests for adapters/schema.py canonical event validation and utilities.

Tests cover acceptance criteria for Stories 1.1, 1.2, and 1.3.
"""

import os
from unittest.mock import patch

import pytest

from memory.adapters.schema import (
    VALID_HOOK_EVENTS,
    VALID_IDE_SOURCES,
    fork_to_background,
    normalize_claude_event,
    normalize_mcp_tool_name,
    resolve_cwd,
    resolve_session_id,
    validate_canonical_event,
)


def _valid_event(**overrides):
    """Build a minimal valid canonical event dict with optional overrides."""
    base = {
        "session_id": "test-session-123",
        "cwd": "/home/user/project",
        "hook_event_name": "PostToolUse",
        "ide_source": "claude",
        "tool_name": None,
        "tool_input": None,
        "tool_response": None,
        "transcript_path": None,
        "user_prompt": None,
        "trigger": None,
        "context_usage_percent": None,
        "context_tokens": None,
        "context_window_size": None,
        "is_background_agent": False,
    }
    base.update(overrides)
    return base


# --- Constants ---


class TestConstants:
    def test_valid_ide_sources(self):
        assert {"claude", "gemini", "cursor", "codex"} == VALID_IDE_SOURCES

    def test_valid_hook_events(self):
        expected = {
            "SessionStart",
            "PostToolUse",
            "PreToolUse",
            "PreCompact",
            "UserPromptSubmit",
            "SessionEnd",
            "Stop",
        }
        assert expected == VALID_HOOK_EVENTS


# --- Required fields ---


class TestRequiredFields:
    @pytest.mark.parametrize(
        "field", ["session_id", "cwd", "hook_event_name", "ide_source"]
    )
    def test_missing_required_field_raises(self, field):
        event = _valid_event()
        del event[field]
        with pytest.raises(
            ValueError, match=f"Missing or invalid required field: {field}"
        ):
            validate_canonical_event(event)

    @pytest.mark.parametrize(
        "field", ["session_id", "cwd", "hook_event_name", "ide_source"]
    )
    def test_non_str_required_field_raises(self, field):
        event = _valid_event(**{field: 123})
        with pytest.raises(
            ValueError, match=f"Missing or invalid required field: {field}"
        ):
            validate_canonical_event(event)

    def test_valid_event_passes(self):
        validate_canonical_event(_valid_event())


# --- ide_source validation ---


class TestIdeSource:
    @pytest.mark.parametrize("source", ["claude", "gemini", "cursor", "codex"])
    def test_valid_ide_source(self, source):
        validate_canonical_event(_valid_event(ide_source=source))

    def test_invalid_ide_source_raises(self):
        with pytest.raises(ValueError, match="Invalid ide_source"):
            validate_canonical_event(_valid_event(ide_source="vscode"))


# --- hook_event_name validation ---


class TestHookEventName:
    @pytest.mark.parametrize("event_name", VALID_HOOK_EVENTS)
    def test_valid_hook_event_names(self, event_name):
        overrides = {"hook_event_name": event_name}
        if event_name == "UserPromptSubmit":
            overrides["user_prompt"] = "test prompt"
        validate_canonical_event(_valid_event(**overrides))

    def test_invalid_hook_event_name_raises(self):
        with pytest.raises(ValueError, match="Invalid hook_event_name"):
            validate_canonical_event(_valid_event(hook_event_name="BeforeAgent"))


# --- Optional str | None fields ---


class TestOptionalStrOrNone:
    @pytest.mark.parametrize("field", ["tool_name", "transcript_path", "trigger"])
    def test_none_passes(self, field):
        validate_canonical_event(_valid_event(**{field: None}))

    @pytest.mark.parametrize("field", ["tool_name", "transcript_path", "trigger"])
    def test_str_passes(self, field):
        validate_canonical_event(_valid_event(**{field: "some_value"}))

    @pytest.mark.parametrize("field", ["tool_name", "transcript_path", "trigger"])
    def test_non_str_raises(self, field):
        with pytest.raises(ValueError, match=f"{field} must be str or None"):
            validate_canonical_event(_valid_event(**{field: 42}))


# --- tool_input (dict | None) ---


class TestToolInput:
    def test_none_passes(self):
        validate_canonical_event(_valid_event(tool_input=None))

    def test_dict_passes(self):
        validate_canonical_event(_valid_event(tool_input={"file_path": "/test.py"}))

    def test_non_dict_raises(self):
        with pytest.raises(ValueError, match="tool_input must be dict or None"):
            validate_canonical_event(_valid_event(tool_input="not a dict"))


# --- tool_response (dict | str | None) ---


class TestToolResponse:
    def test_none_passes(self):
        validate_canonical_event(_valid_event(tool_response=None))

    def test_dict_passes(self):
        validate_canonical_event(_valid_event(tool_response={"exitCode": 0}))

    def test_str_passes(self):
        validate_canonical_event(_valid_event(tool_response="<result>ok</result>"))

    def test_non_dict_str_raises(self):
        with pytest.raises(
            ValueError, match="tool_response must be dict, str, or None"
        ):
            validate_canonical_event(_valid_event(tool_response=42))

    def test_list_raises(self):
        with pytest.raises(
            ValueError, match="tool_response must be dict, str, or None"
        ):
            validate_canonical_event(_valid_event(tool_response=["a", "b"]))


# --- user_prompt (asymmetric validation) ---


class TestUserPrompt:
    def test_user_prompt_submit_requires_non_empty_str(self):
        event = _valid_event(
            hook_event_name="UserPromptSubmit",
            user_prompt="how should I handle errors?",
        )
        validate_canonical_event(event)

    def test_user_prompt_submit_none_raises(self):
        event = _valid_event(
            hook_event_name="UserPromptSubmit",
            user_prompt=None,
        )
        with pytest.raises(ValueError, match="user_prompt must be a non-empty str"):
            validate_canonical_event(event)

    def test_user_prompt_submit_empty_str_raises(self):
        event = _valid_event(
            hook_event_name="UserPromptSubmit",
            user_prompt="",
        )
        with pytest.raises(ValueError, match="user_prompt must be a non-empty str"):
            validate_canonical_event(event)

    def test_user_prompt_submit_non_str_raises(self):
        event = _valid_event(
            hook_event_name="UserPromptSubmit",
            user_prompt=123,
        )
        with pytest.raises(ValueError, match="user_prompt must be a non-empty str"):
            validate_canonical_event(event)

    def test_non_user_prompt_submit_none_passes(self):
        validate_canonical_event(_valid_event(user_prompt=None))

    def test_non_user_prompt_submit_non_none_raises(self):
        with pytest.raises(
            ValueError, match="user_prompt must be None for PostToolUse"
        ):
            validate_canonical_event(_valid_event(user_prompt="should be none"))


# --- is_background_agent (bool) ---


class TestIsBackgroundAgent:
    def test_bool_true_passes(self):
        validate_canonical_event(_valid_event(is_background_agent=True))

    def test_bool_false_passes(self):
        validate_canonical_event(_valid_event(is_background_agent=False))

    def test_non_bool_raises(self):
        with pytest.raises(ValueError, match="is_background_agent must be bool"):
            validate_canonical_event(_valid_event(is_background_agent=1))

    def test_string_raises(self):
        with pytest.raises(ValueError, match="is_background_agent must be bool"):
            validate_canonical_event(_valid_event(is_background_agent="true"))


# --- context_usage_percent (float | None) ---


class TestContextUsagePercent:
    def test_none_passes(self):
        validate_canonical_event(_valid_event(context_usage_percent=None))

    def test_float_passes(self):
        validate_canonical_event(_valid_event(context_usage_percent=0.95))

    def test_int_raises(self):
        with pytest.raises(
            ValueError, match="context_usage_percent must be float or None"
        ):
            validate_canonical_event(_valid_event(context_usage_percent=95))


# --- context_tokens / context_window_size (int | None) ---


class TestContextInts:
    @pytest.mark.parametrize("field", ["context_tokens", "context_window_size"])
    def test_none_passes(self, field):
        validate_canonical_event(_valid_event(**{field: None}))

    @pytest.mark.parametrize("field", ["context_tokens", "context_window_size"])
    def test_int_passes(self, field):
        validate_canonical_event(_valid_event(**{field: 128000}))

    @pytest.mark.parametrize("field", ["context_tokens", "context_window_size"])
    def test_non_int_raises(self, field):
        with pytest.raises(ValueError, match=f"{field} must be int or None"):
            validate_canonical_event(_valid_event(**{field: "128000"}))

    @pytest.mark.parametrize("field", ["context_tokens", "context_window_size"])
    def test_float_raises(self, field):
        with pytest.raises(ValueError, match=f"{field} must be int or None"):
            validate_canonical_event(_valid_event(**{field: 128000.0}))


# =============================================================================
# Story 1.2: normalize_mcp_tool_name()
# =============================================================================


class TestNormalizeMcpToolName:
    def test_gemini_format(self):
        assert normalize_mcp_tool_name("mcp_postgres_query") == "mcp:postgres:query"

    def test_gemini_format_slack(self):
        assert normalize_mcp_tool_name("mcp_slack_send") == "mcp:slack:send"

    def test_cursor_format_with_server(self):
        assert (
            normalize_mcp_tool_name("MCP:postgres_query")
            == "mcp:unknown:postgres_query"
        )

    def test_cursor_format_simple(self):
        assert normalize_mcp_tool_name("MCP:query") == "mcp:unknown:query"

    def test_non_mcp_returns_none(self):
        assert normalize_mcp_tool_name("Write") is None

    def test_non_mcp_edit_returns_none(self):
        assert normalize_mcp_tool_name("Edit") is None

    def test_non_mcp_bash_returns_none(self):
        assert normalize_mcp_tool_name("Bash") is None

    def test_gemini_multi_underscore_tool(self):
        assert (
            normalize_mcp_tool_name("mcp_github_create_issue")
            == "mcp:github:create_issue"
        )


# =============================================================================
# Story 1.3: resolve_session_id() and resolve_cwd()
# =============================================================================


class TestResolveSessionId:
    def test_priority_1_native_session_id(self):
        payload = {"session_id": "abc-123"}
        assert resolve_session_id(payload) == "abc-123"

    def test_priority_1_strips_whitespace(self):
        payload = {"session_id": "  abc-123  "}
        assert resolve_session_id(payload) == "abc-123"

    def test_priority_2_conversation_id(self):
        payload = {"conversation_id": "conv-456"}
        assert resolve_session_id(payload) == "conv-456"

    def test_priority_2_skips_empty_session_id(self):
        payload = {"session_id": "", "conversation_id": "conv-456"}
        assert resolve_session_id(payload) == "conv-456"

    def test_priority_3_transcript_path(self):
        payload = {"transcript_path": "/home/user/.claude/projects/abc123.jsonl"}
        assert resolve_session_id(payload) == "abc123"

    def test_priority_3_strips_extension(self):
        payload = {"transcript_path": "/path/to/session-xyz.jsonl"}
        assert resolve_session_id(payload) == "session-xyz"

    def test_priority_4_uuid_fallback(self):
        payload = {"cwd": "/home/user/project"}
        result = resolve_session_id(payload)
        # Should be a valid UUID string
        import uuid

        uuid.UUID(result)  # Raises ValueError if invalid

    def test_priority_4_uses_getcwd_when_no_cwd(self):
        payload = {}
        result = resolve_session_id(payload)
        import uuid

        uuid.UUID(result)  # Should still produce valid UUID


class TestResolveCwd:
    def test_priority_1_native_cwd(self):
        payload = {"cwd": "/home/user/project"}
        assert resolve_cwd(payload, "gemini") == "/home/user/project"

    def test_priority_1_strips_whitespace(self):
        payload = {"cwd": "  /home/user/project  "}
        assert resolve_cwd(payload, "cursor") == "/home/user/project"

    def test_priority_2_cursor_workspace_roots(self):
        payload = {"workspace_roots": ["/home/user/project"]}
        assert resolve_cwd(payload, "cursor") == "/home/user/project"

    def test_priority_2_cursor_skips_empty_cwd(self):
        payload = {"cwd": "", "workspace_roots": ["/home/user/project"]}
        assert resolve_cwd(payload, "cursor") == "/home/user/project"

    def test_priority_2_not_used_for_gemini(self):
        payload = {"workspace_roots": ["/home/user/project"]}
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("os.getcwd", return_value="/fallback"),
        ):
            assert resolve_cwd(payload, "gemini") == "/fallback"

    def test_priority_3_cursor_project_dir_env(self):
        payload = {}
        with patch.dict(os.environ, {"CURSOR_PROJECT_DIR": "/env/cursor/project"}):
            assert resolve_cwd(payload, "cursor") == "/env/cursor/project"

    def test_priority_3_gemini_cwd_env(self):
        payload = {}
        with patch.dict(os.environ, {"GEMINI_CWD": "/env/gemini/project"}):
            assert resolve_cwd(payload, "gemini") == "/env/gemini/project"

    def test_priority_3_not_used_for_codex(self):
        payload = {}
        with (
            patch.dict(os.environ, {"GEMINI_CWD": "/should/not/use"}, clear=True),
            patch("os.getcwd", return_value="/fallback"),
        ):
            assert resolve_cwd(payload, "codex") == "/fallback"

    def test_priority_4_os_getcwd_fallback(self):
        payload = {}
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("os.getcwd", return_value="/fallback/cwd"),
        ):
            assert resolve_cwd(payload, "claude") == "/fallback/cwd"

    def test_priority_4_codex_falls_through_to_getcwd(self):
        payload = {}
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("os.getcwd", return_value="/codex/fallback"),
        ):
            assert resolve_cwd(payload, "codex") == "/codex/fallback"


# =============================================================================
# Story 1.4: normalize_claude_event() and fork_to_background()
# =============================================================================


class TestNormalizeClaudeEvent:
    def test_basic_post_tool_use(self):
        raw = {
            "session_id": "sess-123",
            "cwd": "/home/user/project",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test.py", "content": "print('hi')"},
            "tool_response": {"filePath": "/test.py"},
        }
        event = normalize_claude_event(raw, "PostToolUse")
        assert event["session_id"] == "sess-123"
        assert event["cwd"] == "/home/user/project"
        assert event["hook_event_name"] == "PostToolUse"
        assert event["tool_name"] == "Write"
        assert event["ide_source"] == "claude"
        assert event["user_prompt"] is None
        assert event["is_background_agent"] is False

    def test_mcp_tool_name_normalized(self):
        raw = {
            "session_id": "sess-123",
            "cwd": "/project",
            "tool_name": "mcp_postgres_query",
        }
        event = normalize_claude_event(raw, "PostToolUse")
        assert event["tool_name"] == "mcp:postgres:query"

    def test_non_mcp_tool_name_passed_through(self):
        raw = {"session_id": "sess-123", "cwd": "/project", "tool_name": "Edit"}
        event = normalize_claude_event(raw, "PostToolUse")
        assert event["tool_name"] == "Edit"

    def test_session_start(self):
        raw = {"session_id": "sess-456", "cwd": "/project", "source": "resume"}
        event = normalize_claude_event(raw, "SessionStart")
        assert event["hook_event_name"] == "SessionStart"
        assert event["tool_name"] is None

    def test_user_prompt_submit(self):
        raw = {
            "session_id": "sess-789",
            "cwd": "/project",
            "prompt": "how should I handle errors?",
        }
        event = normalize_claude_event(raw, "UserPromptSubmit")
        assert event["user_prompt"] == "how should I handle errors?"

    def test_pre_compact_trigger(self):
        raw = {
            "session_id": "sess-abc",
            "cwd": "/project",
            "trigger": "auto",
        }
        event = normalize_claude_event(raw, "PreCompact")
        assert event["trigger"] == "auto"

    def test_validates_after_normalization(self):
        raw = {"session_id": "sess-123", "cwd": "/project"}
        event = normalize_claude_event(raw, "PostToolUse")
        validate_canonical_event(event)


class TestForkToBackground:
    def test_spawns_subprocess_and_passes_json(self):
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "import sys, json\n"
                "data = json.loads(sys.stdin.read())\n"
                "assert data['ide_source'] == 'claude'\n"
                "assert data['session_id'] == 'test-sess'\n"
            )
            script_path = f.name

        try:
            event = _valid_event(session_id="test-sess")
            fork_to_background(event, script_path)
            # No exception means spawn succeeded
        finally:
            os.unlink(script_path)

    def test_does_not_use_shell_true(self):
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.stdin = None
            event = _valid_event(session_id="test-sess")
            fork_to_background(event, "/fake/script.py")
            call_kwargs = mock_popen.call_args
            assert call_kwargs.kwargs.get("shell") is not True
            assert "start_new_session" in call_kwargs.kwargs
            assert call_kwargs.kwargs["start_new_session"] is True

    def test_sets_claude_session_id_env(self):
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.stdin = None
            event = _valid_event(session_id="my-session-id")
            fork_to_background(event, "/fake/script.py")
            call_kwargs = mock_popen.call_args
            env = call_kwargs.kwargs.get("env", {})
            assert env.get("CLAUDE_SESSION_ID") == "my-session-id"
