"""Activity logging for BMAD Memory hooks.

Writes user-visible activity to a log file that can be monitored with:
    tail -f $BMAD_INSTALL_DIR/logs/activity.log

This provides reliable visibility into hook execution since STDERR
output from Claude Code hooks is not consistently displayed.

Icons:
    🧠 SessionStart - Memory retrieval
    📤 PreCompact - Session save
    📥 Capture - Implementation capture
    🔴 ErrorCapture - Error pattern
    💾 ManualSave - /save-memory
    🔍 SearchMemory - /search-memory
    📊 MemoryStatus - /memory-status
    🔧 PreToolUse - Tool about to execute
    📋 PostToolUse - Tool completed
    🎯 BestPractices - Best practices retrieval
    ⏹️ Stop - Claude finished
    🤖 SubagentStop - Subagent completed
    🔚 SessionEnd - Session ended
    💬 UserPrompt - User input
    🔔 Notification - System notification
    🔐 Permission - Permission request
    📄 FULL_CONTENT - Expandable content marker
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

# Log file location - use BMAD_INSTALL_DIR if available
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))
LOG_DIR = Path(INSTALL_DIR) / "logs"
ACTIVITY_LOG = LOG_DIR / "activity.log"

# Maximum log entries before rotation
MAX_LOG_ENTRIES = 500

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)


def rotate_log() -> None:
    """Rotate log file, keeping only the last MAX_LOG_ENTRIES lines.

    This prevents the log file from growing unbounded. Called automatically
    after each write operation.
    """
    try:
        if not ACTIVITY_LOG.exists():
            return

        # Read all lines
        with open(ACTIVITY_LOG, 'r') as f:
            lines = f.readlines()

        # If over limit, keep only last MAX_LOG_ENTRIES
        if len(lines) > MAX_LOG_ENTRIES:
            with open(ACTIVITY_LOG, 'w') as f:
                f.writelines(lines[-MAX_LOG_ENTRIES:])
    except Exception:
        # Never fail on rotation - graceful degradation
        pass


def log_activity(icon: str, message: str) -> None:
    """Write activity message to log file.

    Args:
        icon: Emoji icon (🧠, 📥, 📤, etc.)
        message: Activity message to log
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {icon} {message}\n"

        with open(ACTIVITY_LOG, "a") as f:
            f.write(line)

        # Rotate log if needed
        rotate_log()
    except Exception:
        # Never fail - this is just for user visibility
        pass


def _write_full_content(content_lines: list[str]) -> None:
    """Write full content block with FULL_CONTENT marker."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_content = "\\n".join(content_lines)
    try:
        with open(ACTIVITY_LOG, "a") as f:
            f.write(f"[{timestamp}] 📄 FULL_CONTENT:{full_content}\n")
    except Exception:
        pass


# Session Lifecycle
def log_session_start(project: str, trigger: str, memories: list[dict], duration_ms: float) -> None:
    """Log SessionStart with full memory content."""
    log_activity("🧠", f"SessionStart ({trigger}): Loaded {len(memories)} memories for {project} [{duration_ms:.0f}ms]")

    if memories:
        content_lines = []
        for i, mem in enumerate(memories, 1):
            score = mem.get('score', 0)
            mem_type = mem.get('type', 'memory')
            created = mem.get('created_at', 'unknown')[:10]  # Date only
            content = mem.get('content', '')

            content_lines.append(f"  [{i}] {mem_type} ({score:.0%}) {created}:")
            for line in content.split('\n'):
                content_lines.append(f"    {line}")
            content_lines.append("")

        _write_full_content(content_lines)


def log_conversation_context_injection(
    project: str,
    trigger: str,
    message_count: int,
    summary_count: int,
    duration_ms: float,
    context_preview: str = ""
) -> None:
    """Log V2.0 conversation context injection.

    Args:
        project: Project name
        trigger: Trigger type (compact, resume)
        message_count: Number of user/agent messages injected
        summary_count: Number of session summaries injected
        duration_ms: Duration of retrieval
        context_preview: Optional preview of context (first 200 chars)
    """
    total = message_count + summary_count
    log_activity("🧠", f"SessionStart ({trigger}): Injected {total} items ({summary_count} summaries, {message_count} messages) for {project} [{duration_ms:.0f}ms]")

    if context_preview:
        content_lines = [f"  Context:"]
        for line in context_preview.split('\n'):
            content_lines.append(f"    {line}")
        _write_full_content(content_lines)


def log_session_end(project: str, reason: str, duration_ms: float) -> None:
    """Log SessionEnd event."""
    log_activity("🔚", f"SessionEnd ({reason}): Session ended for {project} [{duration_ms:.0f}ms]")


def log_stop(project: str, stop_hook_active: bool) -> None:
    """Log Stop event (Claude finished responding)."""
    status = "hook active" if stop_hook_active else "normal"
    log_activity("⏹️", f"Stop: Claude finished responding ({status})")


def log_subagent_stop(agent_id: str, project: str) -> None:
    """Log SubagentStop event."""
    log_activity("🤖", f"SubagentStop: Agent {agent_id[:8]} completed")


# Tool Operations
def log_pre_tool_use(tool_name: str, tool_input: dict, project: str) -> None:
    """Log PreToolUse event with tool input."""
    # Summary based on tool type
    if tool_name == "Bash":
        cmd = tool_input.get('command', '')
        summary = f"$ {cmd}"
    elif tool_name in ["Read", "Write", "Edit"]:
        path = tool_input.get('file_path', '')
        summary = path
    elif tool_name == "Glob":
        pattern = tool_input.get('pattern', '')
        summary = f"pattern: {pattern}"
    elif tool_name == "Grep":
        pattern = tool_input.get('pattern', '')
        summary = f"search: {pattern}"
    elif tool_name == "Task":
        desc = tool_input.get('description', '')
        summary = f"task: {desc}"
    else:
        summary = str(tool_input)

    log_activity("🔧", f"PreToolUse {tool_name}: {summary}")


def log_post_tool_use(tool_name: str, tool_input: dict, tool_response: dict, project: str, duration_ms: float = 0) -> None:
    """Log PostToolUse event with result."""
    success = tool_response.get('success', True) if isinstance(tool_response, dict) else True
    status = "✓" if success else "✗"

    # Summary based on tool type
    if tool_name == "Bash":
        exit_code = tool_response.get('exitCode', 0) if isinstance(tool_response, dict) else 0
        # Use stdout/stderr fields (Claude Code format)
        stdout = tool_response.get('stdout', '') if isinstance(tool_response, dict) else ""
        stderr = tool_response.get('stderr', '') if isinstance(tool_response, dict) else ""
        output = stderr if stderr else stdout
        summary = f"exit:{exit_code} {output}"
    elif tool_name in ["Write", "Edit"]:
        path = tool_response.get('filePath', '') if isinstance(tool_response, dict) else ""
        summary = path
    elif tool_name == "Read":
        path = tool_input.get('file_path', '')
        summary = path
    else:
        summary = str(tool_response) if tool_response else "completed"

    log_activity("📋", f"PostToolUse {tool_name} {status}: {summary} [{duration_ms:.0f}ms]")


# Memory Operations
def log_precompact(project: str, session_id: str, content: str, metadata: dict, duration_ms: float) -> None:
    """Log PreCompact session save with full content."""
    tools = metadata.get('tools_used', [])
    tools_str = ', '.join(tools[:5]) if tools else 'None'
    files_count = metadata.get('files_modified', 0)

    log_activity("📤", f"PreCompact: Saved session for {project} [{duration_ms:.0f}ms]")

    content_lines = [
        f"  Session: {session_id[:12]}",
        f"  Tools: {tools_str}",
        f"  Files Modified: {files_count}",
        f"  Content:",
    ]
    for line in content.split('\n'):
        content_lines.append(f"    {line}")

    _write_full_content(content_lines)


def log_manual_save(project: str, description: str, success: bool) -> None:
    """Log /save-memory command."""
    status = "saved" if success else "queued"
    desc = f' - "{description[:40]}"' if description else ""
    log_activity("💾", f"ManualSave: Memory {status} for {project}{desc}")


def log_memory_search(project: str, query: str, results_count: int, duration_ms: float, results: list[dict] = None) -> None:
    """Log /search-memory command with results."""
    log_activity("🔍", f"SearchMemory: {results_count} results for \"{query}\" [{duration_ms:.0f}ms]")

    if results:
        content_lines = []
        for i, r in enumerate(results, 1):
            score = r.get('score', 0)
            content = r.get('content', '')
            content_lines.append(f"  [{i}] ({score:.0%}) {content}")

        _write_full_content(content_lines)


def log_memory_status(project: str, collections: dict) -> None:
    """Log /memory-status command."""
    discussions = collections.get('discussions', 0)
    code_patterns = collections.get('code-patterns', 0)
    conventions = collections.get('conventions', 0)
    log_activity("📊", f"MemoryStatus: {project} - disc:{discussions} code:{code_patterns} conv:{conventions}")


def log_implementation_capture(file_path: str, tool_name: str, language: str, content: str, lines: int) -> None:
    """Log PostToolUse implementation capture with full content."""
    filename = file_path.split('/')[-1] if '/' in file_path else file_path
    log_activity("📥", f"Capture: {filename} ({tool_name}, {language}, {lines} lines)")

    content_lines = [
        f"  File: {file_path}",
        f"  Tool: {tool_name} | Language: {language}",
        f"  Content ({lines} lines):",
    ]
    # No truncation - show full content for Streamlit dropdown
    for line in content.split('\n'):
        content_lines.append(f"    {line}")

    _write_full_content(content_lines)


def log_error_capture(command: str, error_msg: str, exit_code: int, output: str = None) -> None:
    """Log error pattern capture with full context."""
    log_activity("🔴", f"ErrorCapture: {error_msg} (exit {exit_code})")

    content_lines = [
        f"  Command: {command}",
        f"  Exit Code: {exit_code}",
        f"  Error: {error_msg}",
    ]
    if output:
        content_lines.append("  Output:")
        for line in output.split('\n'):
            content_lines.append(f"    {line}")

    _write_full_content(content_lines)


def log_error_context_retrieval(file_path: str, language: str, results: list[dict], duration_ms: float) -> None:
    """Log PreToolUse error context retrieval."""
    log_activity("🔧", f"ErrorContext: {len(results)} code-patterns for {file_path} [{duration_ms:.0f}ms]")

    if results:
        content_lines = []
        for i, impl in enumerate(results, 1):
            score = impl.get('score', 0)
            content = impl.get('content', '')
            content_lines.append(f"  [{i}] ({score:.0%}) {content}")

        _write_full_content(content_lines)


def log_best_practices_retrieval(file_path: str, component: str, results: list[dict], duration_ms: float) -> None:
    """Log best practices retrieval (explicit mode)."""
    log_activity("🎯", f"BestPractices: {len(results)} for {component} [{duration_ms:.0f}ms]")


# User Interaction
def log_user_prompt(prompt: str) -> None:
    """Log UserPromptSubmit event with full content."""
    log_activity("💬", f"UserPrompt: {prompt}")

    # Write full content for expansion
    content_lines = [
        "  Content:",
    ]
    for line in prompt.split('\n'):
        content_lines.append(f"    {line}")

    _write_full_content(content_lines)


def log_notification(notification_type: str, message: str) -> None:
    """Log Notification event."""
    log_activity("🔔", f"Notification ({notification_type}): {message}")


def log_permission_request(tool_name: str, decision: str) -> None:
    """Log PermissionRequest event."""
    log_activity("🔐", f"Permission {tool_name}: {decision}")


# Legacy functions for backwards compatibility
def log_retrieval(project: str, count: int, duration_ms: float, previews: list[str] = None) -> None:
    """Legacy function - use log_session_start instead."""
    if count > 0:
        log_activity("🧠", f"Loaded {count} memories for {project} [{duration_ms:.0f}ms]")
    else:
        log_activity("🧠", f"No memories found for {project} [{duration_ms:.0f}ms]")


def log_capture(filename: str, memory_type: str = "implementation") -> None:
    """Legacy function - use log_implementation_capture instead."""
    log_activity("📥", f"Capturing {filename} ({memory_type})")


def log_error(hook: str, error: str) -> None:
    """Log hook error.

    Args:
        hook: Hook name (SessionStart, PostToolUse, Stop)
        error: Error message
    """
    log_activity("⚠️", f"{hook}: {error}")
