"""Canonical event schema, validation, and shared utilities for IDE adapters.

All IDE adapters normalize their native hook payloads into the canonical event
dict defined here. The validation function enforces the contract between any
adapter and the storage/retrieval pipeline.

Architecture reference: §2 Canonical Event Schema, §3 Data Architecture
PRD reference: FR-101, FR-102, FR-601, FR-602
"""

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

VALID_IDE_SOURCES = {"claude", "gemini", "cursor", "codex"}

VALID_HOOK_EVENTS = {
    "SessionStart",
    "PostToolUse",
    "PreToolUse",
    "PreCompact",
    "UserPromptSubmit",
    "SessionEnd",
    "Stop",
}


def validate_canonical_event(event: dict) -> None:
    """Validate canonical event dict. Raises ValueError on invalid input."""
    required = ["session_id", "cwd", "hook_event_name", "ide_source"]
    for field in required:
        if field not in event or not isinstance(event[field], str):
            raise ValueError(f"Missing or invalid required field: {field}")
    if event["ide_source"] not in VALID_IDE_SOURCES:
        raise ValueError(f"Invalid ide_source: {event['ide_source']}")
    if event["hook_event_name"] not in VALID_HOOK_EVENTS:
        raise ValueError(f"Invalid hook_event_name: {event['hook_event_name']}")

    # user_prompt: required non-empty str for UserPromptSubmit, must be None otherwise
    if event["hook_event_name"] == "UserPromptSubmit":
        up = event.get("user_prompt")
        if not isinstance(up, str) or not up:
            raise ValueError(
                "user_prompt must be a non-empty str for UserPromptSubmit events"
            )
    else:
        up = event.get("user_prompt")
        if up is not None:
            raise ValueError(
                f"user_prompt must be None for {event['hook_event_name']} events"
            )

    optional_str_or_none = ["tool_name", "transcript_path", "trigger"]
    for field in optional_str_or_none:
        if (
            field in event
            and event[field] is not None
            and not isinstance(event[field], str)
        ):
            raise ValueError(
                f"{field} must be str or None, got {type(event[field]).__name__}"
            )

    optional_dict_or_none = ["tool_input"]
    for field in optional_dict_or_none:
        if (
            field in event
            and event[field] is not None
            and not isinstance(event[field], dict)
        ):
            raise ValueError(
                f"{field} must be dict or None, got {type(event[field]).__name__}"
            )

    if "tool_response" in event:
        tr = event["tool_response"]
        if tr is not None and not isinstance(tr, (dict, str)):
            raise ValueError(
                f"tool_response must be dict, str, or None, got {type(tr).__name__}"
            )

    optional_float_or_none = ["context_usage_percent"]
    for field in optional_float_or_none:
        if (
            field in event
            and event[field] is not None
            and not isinstance(event[field], float)
        ):
            raise ValueError(
                f"{field} must be float or None, got {type(event[field]).__name__}"
            )

    optional_int_or_none = ["context_tokens", "context_window_size"]
    for field in optional_int_or_none:
        if (
            field in event
            and event[field] is not None
            and not isinstance(event[field], int)
        ):
            raise ValueError(
                f"{field} must be int or None, got {type(event[field]).__name__}"
            )

    if "is_background_agent" in event and not isinstance(
        event["is_background_agent"], bool
    ):
        raise ValueError(
            f"is_background_agent must be bool, got {type(event['is_background_agent']).__name__}"
        )


def normalize_mcp_tool_name(raw_name: str) -> str | None:
    """Normalize IDE-specific MCP tool names to canonical format.

    Gemini format: mcp_<server>_<tool> -> mcp:<server>:<tool>
    Cursor format: MCP:<name>          -> mcp:unknown:<name>

    Returns None if the name is not an MCP tool name.
    """
    gemini_match = re.match(r"^mcp_([^_]+)_(.+)$", raw_name)
    if gemini_match:
        server = gemini_match.group(1)
        tool = gemini_match.group(2)
        return f"mcp:{server}:{tool}"

    cursor_match = re.match(r"^MCP:(.+)$", raw_name)
    if cursor_match:
        tool = cursor_match.group(1)
        return f"mcp:unknown:{tool}"

    return None


def resolve_session_id(payload: dict) -> str:
    """Resolve session_id from IDE payload using fallback chain (FR-601)."""
    sid = payload.get("session_id")
    if sid and isinstance(sid, str) and sid.strip():
        return sid.strip()

    cid = payload.get("conversation_id")
    if cid and isinstance(cid, str) and cid.strip():
        return cid.strip()

    tp = payload.get("transcript_path")
    if tp and isinstance(tp, str) and tp.strip():
        return os.path.splitext(os.path.basename(tp))[0]

    cwd = payload.get("cwd", os.getcwd())
    ts = datetime.now(tz=timezone.utc).isoformat()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{cwd}:{ts}"))


def resolve_cwd(payload: dict, ide_source: str) -> str:
    """Resolve cwd from IDE payload using fallback chain (FR-602)."""
    cwd = payload.get("cwd")
    if cwd and isinstance(cwd, str) and cwd.strip():
        return cwd.strip()

    if ide_source == "cursor":
        roots = payload.get("workspace_roots", [])
        if roots and isinstance(roots[0], str):
            return roots[0]
        cursor_dir = os.environ.get("CURSOR_PROJECT_DIR")
        if cursor_dir:
            return cursor_dir

    if ide_source == "gemini":
        gemini_cwd = os.environ.get("GEMINI_CWD")
        if gemini_cwd:
            return gemini_cwd

    return os.getcwd()


def normalize_claude_event(raw: dict, hook_event_name: str) -> dict:
    """Normalize Claude Code native stdin to canonical event schema.

    Claude Code stdin already contains most canonical fields natively.
    This normalizer standardizes naming and adds ide_source.
    """
    tool_name = raw.get("tool_name")
    mcp_name = normalize_mcp_tool_name(tool_name) if tool_name else None

    return {
        "session_id": resolve_session_id(raw),
        "cwd": resolve_cwd(raw, "claude"),
        "hook_event_name": hook_event_name,
        "tool_name": mcp_name or tool_name,
        "tool_input": raw.get("tool_input"),
        "tool_response": raw.get("tool_response"),
        "transcript_path": raw.get("transcript_path"),
        "user_prompt": (
            raw.get("prompt") if hook_event_name == "UserPromptSubmit" else None
        ),
        "ide_source": "claude",
        "trigger": raw.get("trigger"),
        "is_background_agent": False,
    }


# Gemini hook-to-canonical name mapping
_GEMINI_HOOK_MAP = {
    "SessionStart": "SessionStart",
    "AfterTool": "PostToolUse",
    "BeforeTool": "PreToolUse",
    "BeforeAgent": "UserPromptSubmit",
    "PreCompress": "PreCompact",
    "SessionEnd": "SessionEnd",
}

# Gemini tool name → canonical tool name mapping
_GEMINI_TOOL_MAP = {
    "edit_file": "Edit",
    "write_file": "Write",
    "create_file": "Write",
    "run_shell_command": "Bash",
}


def normalize_gemini_event(raw: dict, native_hook_name: str) -> dict:
    """Normalize Gemini CLI native stdin to canonical event schema.

    Gemini uses different hook names (AfterTool vs PostToolUse) and tool names
    (edit_file vs Edit). This normalizer maps both to canonical values.
    """
    canonical_hook = _GEMINI_HOOK_MAP.get(native_hook_name, native_hook_name)

    raw_tool_name = raw.get("tool_name")
    if raw_tool_name:
        mcp_name = normalize_mcp_tool_name(raw_tool_name)
        tool_name = mcp_name or _GEMINI_TOOL_MAP.get(raw_tool_name, raw_tool_name)
    else:
        tool_name = None

    tool_response = raw.get("tool_response")
    if isinstance(tool_response, dict):
        tool_response = tool_response.get("llmContent", tool_response)

    return {
        "session_id": resolve_session_id(raw),
        "cwd": resolve_cwd(raw, "gemini"),
        "hook_event_name": canonical_hook,
        "tool_name": tool_name,
        "tool_input": raw.get("tool_input"),
        "tool_response": tool_response,
        "transcript_path": raw.get("transcript_path"),
        "user_prompt": (
            raw.get("prompt") if canonical_hook == "UserPromptSubmit" else None
        ),
        "ide_source": "gemini",
        "trigger": raw.get("trigger"),
        "is_background_agent": raw.get("is_background_agent", False),
    }


# Cursor hook-to-canonical name mapping
_CURSOR_HOOK_MAP = {
    "sessionStart": "SessionStart",
    "postToolUse": "PostToolUse",
    "preToolUse": "PreToolUse",
    "beforeSubmitPrompt": "UserPromptSubmit",
    "preCompact": "PreCompact",
    "stop": "Stop",
    "sessionEnd": "SessionEnd",
}

# Cursor tool name → canonical tool name mapping
_CURSOR_TOOL_MAP = {
    "Write": "Write",
    "Edit": "Edit",
    "Shell": "Bash",
    "Read": "Read",
    "Grep": "Grep",
    "Delete": "Delete",
    "NotebookEdit": "NotebookEdit",
}


def normalize_cursor_event(raw: dict, native_hook_name: str) -> dict:
    """Normalize Cursor IDE native stdin to canonical event schema.

    Cursor uses camelCase hook names (sessionStart, postToolUse) and
    tool names (Shell instead of Bash). Cursor-specific fields:
    - is_background_agent: skip retrieval when True
    - conversation_id: fallback for session_id
    - workspace_roots: fallback for cwd
    - tool_output: maps to canonical tool_response
    - MCP tools: prefix "MCP:<name>" normalized via normalize_mcp_tool_name
    """
    canonical_hook = _CURSOR_HOOK_MAP.get(native_hook_name, native_hook_name)

    raw_tool_name = raw.get("tool_name")
    if raw_tool_name:
        mcp_name = normalize_mcp_tool_name(raw_tool_name)
        tool_name = mcp_name or _CURSOR_TOOL_MAP.get(raw_tool_name, raw_tool_name)
    else:
        tool_name = None

    # Cursor uses tool_output (not tool_response) in postToolUse payload
    tool_response = raw.get("tool_response") or raw.get("tool_output")

    return {
        "session_id": resolve_session_id(raw),
        "cwd": resolve_cwd(raw, "cursor"),
        "hook_event_name": canonical_hook,
        "tool_name": tool_name,
        "tool_input": raw.get("tool_input"),
        "tool_response": tool_response,
        "transcript_path": raw.get("transcript_path"),
        "user_prompt": (
            raw.get("prompt") if canonical_hook == "UserPromptSubmit" else None
        ),
        "ide_source": "cursor",
        "trigger": raw.get("trigger"),
        "is_background_agent": raw.get("is_background_agent", False),
        "context_usage_percent": raw.get("context_usage_percent"),
        "context_tokens": raw.get("context_tokens"),
        "context_window_size": raw.get("context_window_size"),
    }


# Codex hook-to-canonical name mapping (Codex uses canonical names natively)
_CODEX_HOOK_MAP = {
    "SessionStart": "SessionStart",
    "PostToolUse": "PostToolUse",
    "UserPromptSubmit": "UserPromptSubmit",
    "Stop": "Stop",
}

# Codex tool name → canonical tool name mapping (Bash-only for PostToolUse)
_CODEX_TOOL_MAP = {
    "Bash": "Bash",
}


def normalize_codex_event(raw: dict, hook_event_name: str) -> dict:
    """Normalize Codex CLI native stdin to canonical event schema.

    Codex uses canonical hook names natively (SessionStart, PostToolUse, etc.).
    PostToolUse is Bash-only — no Write/Edit hooks in Codex.
    - user_prompt: populated from raw.get("prompt") for UserPromptSubmit
    - No is_background_agent support (defaults False)
    - turn_id field available but not required
    """
    canonical_hook = _CODEX_HOOK_MAP.get(hook_event_name, hook_event_name)

    raw_tool_name = raw.get("tool_name")
    if raw_tool_name:
        tool_name = _CODEX_TOOL_MAP.get(raw_tool_name, raw_tool_name)
    else:
        tool_name = None

    return {
        "session_id": resolve_session_id(raw),
        "cwd": resolve_cwd(raw, "codex"),
        "hook_event_name": canonical_hook,
        "tool_name": tool_name,
        "tool_input": raw.get("tool_input"),
        "tool_response": raw.get("tool_response"),
        "transcript_path": raw.get("transcript_path"),
        "user_prompt": (
            raw.get("prompt") if canonical_hook == "UserPromptSubmit" else None
        ),
        "ide_source": "codex",
        "trigger": raw.get("trigger"),
        "is_background_agent": False,
    }


def fork_to_background(canonical_event: dict, pipeline_script_path: str) -> None:
    """Fork storage to background. Adapter exits immediately after this call.

    Spawns the pipeline script as a detached subprocess, passes the canonical
    event JSON to its stdin, and returns without waiting. The subprocess
    inherits the current environment plus CLAUDE_SESSION_ID.
    """
    subprocess_env = os.environ.copy()
    sid = canonical_event.get("session_id", "")
    if sid:
        subprocess_env["CLAUDE_SESSION_ID"] = sid

    process = subprocess.Popen(
        [sys.executable, pipeline_script_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=subprocess_env,
    )
    if process.stdin:
        process.stdin.write(json.dumps(canonical_event).encode("utf-8"))
        process.stdin.close()
