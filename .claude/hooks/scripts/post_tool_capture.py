#!/usr/bin/env python3
"""PostToolUse Hook - Capture implementation patterns after Edit/Write.

AC 2.1.1: Hook Infrastructure with Modern Python Patterns
AC 2.1.3: Hook Input Schema Validation
AC 2.1.4: Performance Requirements (<500ms)

Exit Codes:
- 0: Success (normal completion)
- 1: Non-blocking error (Claude continues, graceful degradation)

Performance: Must complete in <500ms (NFR-P1)
Pattern: Fork to background using subprocess.Popen + start_new_session=True

Sources:
- Python 3.14 fork deprecation: https://iifx.dev/en/articles/460266762/
- Asyncio subprocess patterns: https://docs.python.org/3/library/asyncio-subprocess.html
"""

import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add src to path for imports
# Use INSTALL_DIR to find installed module (fixes path calculation bug)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Configure structured logging (Story 6.2)
from memory.logging_config import StructuredFormatter

handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import push metrics for Pushgateway (TECH-DEBT-142)
try:
    from memory.metrics_push import track_hook_duration
    from memory.project import detect_project
    from memory.trace_buffer import emit_trace_event  # SPEC-021
except ImportError:
    track_hook_duration = None
    detect_project = None
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000  # Max chars for Langfuse input/output fields


def _log_to_activity(message: str) -> None:
    """Log to activity file for Streamlit visibility.

    Activity log provides user-visible feedback about memory operations.
    Located at $AI_MEMORY_INSTALL_DIR/logs/activity.log

    Args:
        message: Message to log (can be multi-line)
    """
    log_dir = Path(INSTALL_DIR) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "activity.log"
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    # Escape newlines for single-line output (Streamlit parses line-by-line)
    safe_message = message.replace("\n", "\\n")
    try:
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {safe_message}\n")
    except Exception:
        pass  # Graceful degradation


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the file

    Returns:
        Language name (e.g., "python", "typescript", "javascript")
    """
    ext = Path(file_path).suffix.lower()
    language_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "react",
        ".tsx": "react-typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".cs": "csharp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".sql": "sql",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".html": "html",
        ".css": "css",
        ".md": "markdown",
    }
    return language_map.get(ext, "unknown")


def validate_hook_input(data: dict[str, Any]) -> str | None:
    """Validate hook input against expected schema.

    AC 2.1.3: Input schema validation
    AC 2.1.1: Validate tool_name and tool_response.success

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid

    Claude Code PostToolUse payload schema:
        - session_id: Unique session identifier
        - cwd: Current working directory
        - tool_name: Name of the tool (Edit, Write, etc.)
        - tool_input: Input parameters for the tool
        - tool_response: Response object with success boolean
    """
    # Check required fields (per Claude Code hook schema)
    # Note: session_id removed - it's for audit trail only, not required for tenant isolation (BUG-058)
    required_fields = ["tool_name", "tool_input", "cwd"]
    for field in required_fields:
        if field not in data:
            return f"missing_required_field_{field}"

    # AC 2.1.1: Validate tool_name (TECH-DEBT-097: safe .get() access)
    valid_tools = ["Edit", "Write", "NotebookEdit"]
    if data.get("tool_name", "") not in valid_tools:
        return "invalid_tool_name"

    # AC 2.1.1: Validate tool completed successfully
    # Claude Code doesn't send "success: true" - presence of filePath indicates success
    tool_response = data.get("tool_response", {})
    if not isinstance(tool_response, dict):
        return "invalid_tool_response_format"

    # Success is indicated by presence of filePath (for Write/Edit) or content in response
    # Error responses would have "error" field or be a string message
    if "error" in tool_response:
        return "tool_had_error"
    if not tool_response.get("filePath") and not tool_response.get("content"):
        return "tool_response_missing_result"

    return None


def fork_to_background(hook_input: dict[str, Any], trace_id: str | None = None) -> None:
    """Fork storage operation to background process.

    AC 2.1.1: Modern Python fork pattern using subprocess.Popen
    AC 2.1.4: Must return immediately for <500ms performance

    Uses subprocess.Popen with start_new_session=True for full detachment.
    This avoids Python 3.14+ fork() deprecation with active event loops.

    Args:
        hook_input: Validated hook input to pass to background script

    Raises:
        No exceptions - logs errors and continues
    """
    try:
        # Path to background storage script
        script_dir = Path(__file__).parent
        store_async_script = script_dir / "store_async.py"

        # Serialize hook input for background process
        input_json = json.dumps(hook_input)

        # Fork to background using subprocess.Popen + start_new_session=True
        # This is Python 3.14+ compliant (avoids fork with active event loops)
        # SPEC-021: Propagate trace_id to store-async subprocess
        subprocess_env = os.environ.copy()
        if trace_id:
            subprocess_env["LANGFUSE_TRACE_ID"] = trace_id

        process = subprocess.Popen(
            [sys.executable, str(store_async_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Full detachment from parent
            env=subprocess_env,
        )

        # Write input and close stdin (non-blocking)
        if process.stdin:
            process.stdin.write(input_json.encode("utf-8"))
            process.stdin.close()

        logger.info(
            "background_forked",
            extra={
                "tool_name": hook_input.get("tool_name", "unknown"),
                "session_id": hook_input.get("session_id", "unknown"),
            },
        )

    except Exception as e:
        # Non-blocking error - log and continue
        logger.error(
            "fork_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )
        # Don't raise - graceful degradation


def main() -> int:
    """PostToolUse hook entry point.

    Reads hook input from stdin, validates it, and forks to background.

    Returns:
        Exit code: 0 (success) or 1 (non-blocking error)
    """
    import contextlib

    # TECH-DEBT-142: Late import of push metrics after sys.path is configured
    track_hook_duration_func = None
    detect_project_func = None
    try:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent.parent
        local_src = project_root / "src"
        if local_src.exists():
            sys.path.insert(0, str(local_src))
        from memory.metrics_push import track_hook_duration
        from memory.project import detect_project

        track_hook_duration_func = track_hook_duration
        detect_project_func = detect_project
    except ImportError:
        logger.warning("metrics_push_module_unavailable")

    # Detect project for metrics
    project = detect_project_func(os.getcwd()) if detect_project_func else "unknown"

    # HIGH-1 FIX: Use proper with statement to ensure __exit__() on all paths
    cm = (
        track_hook_duration_func("PostToolUse", project=project)
        if track_hook_duration_func
        else contextlib.nullcontext()
    )

    with cm:
        try:
            # Read hook input from stdin (Claude Code convention)
            raw_input = sys.stdin.read()

            # AC 2.1.3: Handle malformed JSON (FR34)
            try:
                hook_input = json.loads(raw_input)
            except json.JSONDecodeError as e:
                logger.error(
                    "malformed_json",
                    extra={"error": str(e), "input_preview": raw_input[:100]},
                )
                return 0  # Non-blocking - Claude continues

            # AC 2.1.3: Validate schema
            validation_error = validate_hook_input(hook_input)
            if validation_error:
                logger.info(
                    "validation_failed",
                    extra={
                        "reason": validation_error,
                        "tool_name": hook_input.get("tool_name"),
                        "tool_status": hook_input.get("tool_status"),
                    },
                )
                return 0  # Non-blocking - graceful handling

            # TECH-DEBT-010: Extract content and log to activity before fork
            tool_name = hook_input.get("tool_name", "")
            tool_input = hook_input.get("tool_input", {})
            tool_response = hook_input.get("tool_response", {})

            # Extract file path (F3: tool-specific path extraction)
            if tool_name == "NotebookEdit":
                file_path = tool_input.get("notebook_path", "")
            else:
                file_path = tool_response.get("filePath") or tool_input.get(
                    "file_path", ""
                )

            # Extract content based on tool type
            content = ""
            if tool_name == "Edit":
                content = tool_input.get("new_string", "")
            elif tool_name == "Write":
                content = tool_input.get("content", "")
            elif tool_name == "NotebookEdit":
                content = tool_input.get("new_source", "")

            # Log full content with metadata if we have both file path and content
            if file_path and content:
                language = detect_language(file_path)
                content_lines = len(content.split("\n"))

                # Build multi-line activity log entry
                log_message = "📥 PostToolUse captured implementation:\n"
                log_message += f"  File: {file_path}\n"
                log_message += f"  Tool: {tool_name} | Language: {language}\n"
                log_message += f"  Lines: {content_lines}\n"
                log_message += "  Content:\n"

                # F1: Limit to first 100 lines to prevent disk exhaustion
                MAX_LINES = 100
                for line in content.split("\n")[:MAX_LINES]:
                    log_message += f"    {line}\n"

                if content_lines > MAX_LINES:
                    log_message += (
                        f"    ... [TRUNCATED: {content_lines - MAX_LINES} more lines]\n"
                    )

                _log_to_activity(log_message)

            # SPEC-021: Generate trace_id for pipeline trace linking
            trace_id = None
            if emit_trace_event:
                trace_id = uuid.uuid4().hex
                capture_start = datetime.now(tz=timezone.utc)
                cwd_path = hook_input.get("cwd", os.getcwd())
                try:
                    emit_trace_event(
                        event_type="1_capture",
                        data={
                            "input": content[:TRACE_CONTENT_MAX] if content else "",
                            "output": f"Captured {len(content) if content else 0} chars from post_tool hook",
                            "metadata": {
                                "hook_type": "post_tool",
                                "source": tool_name,
                                "raw_length": len(content) if content else 0,
                                "content_length": len(content) if content else 0,
                                "content_extracted": bool(content),
                            },
                        },
                        trace_id=trace_id,
                        session_id=hook_input.get("session_id"),
                        project_id=(
                            detect_project_func(cwd_path)
                            if detect_project_func
                            else None
                        ),
                        start_time=capture_start,
                        end_time=datetime.now(tz=timezone.utc),
                    )
                except Exception:
                    pass  # Never crash the hook for tracing

            # AC 2.1.1: Fork to background for <500ms performance
            fork_to_background(hook_input, trace_id)

            # User notification via JSON systemMessage (visible in Claude Code UI per issue #4084)
            file_path = hook_input.get("tool_response", {}).get("filePath", "")
            file_name = file_path.split("/")[-1] if file_path else "file"
            tool_name = hook_input.get("tool_name", "Edit")
            message = f"📥 AI Memory: Capturing {file_name} (via {tool_name})"
            print(json.dumps({"systemMessage": message}))
            sys.stdout.flush()  # Ensure output is flushed before exit

            # Activity log handled by _log_to_activity() above (TECH-DEBT-010)
            # Old log_capture() call removed - full content logging now in place

            # AC 2.1.1: Exit immediately after fork (NFR-P1)
            # HIGH-1 FIX: Context manager automatically calls __exit__() on return
            return 0

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(
                "hook_failed", extra={"error": str(e), "error_type": type(e).__name__}
            )

            # HIGH-1 FIX: Context manager automatically calls __exit__() on exception
            return 1  # Non-blocking error


if __name__ == "__main__":
    sys.exit(main())
