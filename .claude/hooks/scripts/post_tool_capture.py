#!/usr/bin/env python3
"""PostToolUse Hook - Capture implementation patterns after Edit/Write.

AC 2.1.1: Hook Infrastructure with Modern Python Patterns
AC 2.1.3: Hook Input Schema Validation
AC 2.1.4: Performance Requirements (<500ms)

Exit Codes:
- 0: Always (hooks must never block Claude — §1.2 Principle 4)

Performance: Must complete in <500ms (NFR-P1)
Pattern: Fork to background using subprocess.Popen + start_new_session=True

Sources:
- Python 3.14 fork deprecation: https://iifx.dev/en/articles/460266762/
- Asyncio subprocess patterns: https://docs.python.org/3/library/asyncio-subprocess.html
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4, §7.7
# SDK VERSION: V3 ONLY. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import hashlib
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
    # F9 FIX: tool_response may be a string (e.g. "<result>...</result>") or a dict with
    # no filePath — Claude Code does not always include filePath in tool_response.
    # The file path is reliably available in tool_input.file_path, so we no longer
    # require filePath in tool_response to accept the hook event.
    tool_response = data.get("tool_response", {})
    if isinstance(tool_response, dict) and "error" in tool_response:
        return "tool_had_error"

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
        # SPEC-021: Propagate trace_id + session_id (TD-241) to store-async subprocess
        subprocess_env = os.environ.copy()
        if trace_id:
            subprocess_env["LANGFUSE_TRACE_ID"] = trace_id
        # TD-241: Propagate CLAUDE_SESSION_ID so store_async library calls get session_id
        # via env fallback even if explicit param is unavailable.
        _sid = hook_input.get("session_id", "")
        if _sid:
            subprocess_env["CLAUDE_SESSION_ID"] = _sid

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


def detect_edit_write_fix(hook_input: dict[str, Any]) -> None:
    """Detect if a successful Edit/Write resolves a prior error (§C4b).

    After existing fork_to_background(), check if the tool operation fixes an active error.

    Fix detection conditions:
    a) Successful Edit to file with active error → fix detected
    b) Successful Write creating file referenced in error (FileNotFoundError) → fix detected

    Args:
        hook_input: Validated hook input
    """
    try:
        tool_name = hook_input.get("tool_name", "")
        if tool_name not in ("Edit", "Write"):
            return

        session_id = hook_input.get("session_id", "")
        if not session_id:
            return

        # Check for tool success — if tool_response has "error", it failed
        tool_response = hook_input.get("tool_response", {})
        if isinstance(tool_response, dict) and "error" in tool_response:
            return

        from memory.injection import InjectionSessionState

        state = InjectionSessionState.load(session_id)
        if not state.error_state:
            return

        # Get the file being edited/written
        tool_input = hook_input.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            # Try tool_response for filePath
            if isinstance(tool_response, dict):
                file_path = tool_response.get("filePath", "")
        if not file_path:
            return

        # Normalize file path for comparison
        file_name = Path(file_path).name

        matched_errors = []
        for eid, edata in state.error_state.items():
            if eid.startswith("_"):
                continue
            error_file = edata.get("file_path", "")
            error_exception = edata.get("exception_type", "")

            if tool_name == "Edit":
                # Edit to same file as error → fix
                if error_file and (
                    error_file == file_path
                    or Path(error_file).name == file_name
                    or file_path.endswith(error_file)
                    or error_file.endswith(file_name)
                ):
                    matched_errors.append((eid, edata, True))  # same_file=True

            elif tool_name == "Write":
                # §C4b: Write fix ONLY for FileNotFoundError (creating missing file)
                if error_exception == "FileNotFoundError" and (
                    error_file == file_path
                    or Path(error_file).name == file_name
                    or file_path.endswith(error_file)
                ):
                    matched_errors.append((eid, edata, True))

        if not matched_errors:
            return

        # Get fix content for embedding
        if tool_name == "Edit":
            fix_content = tool_input.get("new_string", "")[:1000]
        elif tool_name == "Write":
            fix_content = tool_input.get("content", "")[:1000]
        else:
            fix_content = ""

        cwd = hook_input.get("cwd", "")

        for error_group_id, error_data, same_file in matched_errors:
            turn_diff = state.turn_count - error_data.get("turn_number", 0)

            # Resolution confidence scoring per §C4b
            if same_file and turn_diff <= 3:
                confidence = 0.9
            elif same_file and turn_diff <= 10:
                confidence = 0.7
            elif not same_file and turn_diff <= 3:
                confidence = 0.5
            elif not same_file and turn_diff <= 10:
                confidence = 0.4
            else:
                confidence = 0.3

            _fork_fix_to_background_from_post_tool(
                session_id=session_id,
                error_group_id=error_group_id,
                error_data=error_data,
                fix_content=f"{tool_name} fix ({file_path}):\n{fix_content}",
                resolution_confidence=confidence,
                fix_source=tool_name.lower(),
                cwd=cwd,
                turn_count=state.turn_count,
            )

        # Remove resolved errors from session state
        for eid, _, _ in matched_errors:
            state.error_state.pop(eid, None)
        state.save()

    except Exception as e:
        # Never block Claude for fix detection failures
        try:
            logger.warning("fix_detection_failed", extra={"error": str(e)})
        except Exception:
            pass


def _fork_fix_to_background_from_post_tool(
    session_id: str,
    error_group_id: str,
    error_data: dict,
    fix_content: str,
    resolution_confidence: float,
    fix_source: str,
    cwd: str,
    turn_count: int = 0,
) -> None:
    """Fork fix storage to background process (reuses error_store_async.py).

    Args:
        session_id: Session identifier
        error_group_id: Error group ID linking fix to error
        error_data: Original error data from session state
        fix_content: Content describing the fix
        resolution_confidence: Confidence score (0-1)
        fix_source: Source of fix detection ("edit", "write")
        cwd: Working directory
        turn_count: Current session turn count for delta calculation
    """
    try:
        script_dir = Path(__file__).parent
        error_store_script = script_dir / "error_store_async.py"

        fix_context = {
            "command": f"fix:{fix_source}",
            "error_message": f"Fix for {error_data.get('exception_type', 'unknown')}",
            "output": fix_content[:1000],
            "exit_code": 0,
            "file_references": [],
            "stack_trace": None,
            "cwd": cwd,
            "session_id": session_id,
            # Fix-specific fields passed through to store_async
            "_is_fix": True,
            "_error_group_id": error_group_id,
            "_resolution_confidence": resolution_confidence,
            "_fix_source": fix_source,
            "_original_error": error_data,
        }

        input_json = json.dumps(fix_context)

        subprocess_env = os.environ.copy()
        if session_id:
            subprocess_env["CLAUDE_SESSION_ID"] = session_id

        process = subprocess.Popen(
            [sys.executable, str(error_store_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=subprocess_env,
        )

        if process.stdin:
            process.stdin.write(input_json.encode("utf-8"))
            process.stdin.close()

        # Langfuse trace for fix capture (§8.3)
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="error_fix_capture",
                    data={
                        "input": fix_content[:TRACE_CONTENT_MAX],
                        "output": f"Fix captured: group={error_group_id}, confidence={resolution_confidence}",
                        "metadata": {
                            "error_group_id": error_group_id,
                            "resolution_confidence": resolution_confidence,
                            "turns_since_error": turn_count
                            - error_data.get("turn_number", 0),
                            "file_overlap": fix_source in ("edit", "write"),
                            "fix_source": fix_source,
                        },
                    },
                    trace_id=uuid.uuid4().hex,
                    session_id=session_id,
                    tags=["capture", "trigger"],
                )
            except Exception:
                pass

        # Prometheus metric
        try:
            from memory.metrics import error_fix_captures_total
            from memory.project import detect_project as _dp

            project = _dp(cwd) if cwd else "unknown"
            error_fix_captures_total.labels(project=project).inc()
        except Exception:
            pass

        logger.info(
            "error_fix_forked",
            extra={
                "error_group_id": error_group_id,
                "resolution_confidence": resolution_confidence,
                "fix_source": fix_source,
            },
        )

    except Exception as e:
        logger.warning("fork_fix_failed", extra={"error": str(e)})


def main() -> int:
    """PostToolUse hook entry point.

    Reads hook input from stdin, validates it, and forks to background.

    Returns:
        Exit code: 0 always (§1.2 Principle 4: hooks never block Claude)
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

            # TD-241: Set CLAUDE_SESSION_ID in this process so library calls pick it up via env fallback
            _session_id = hook_input.get("session_id", "")
            if _session_id:
                os.environ["CLAUDE_SESSION_ID"] = _session_id

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
                                "agent_name": os.environ.get(
                                    "CLAUDE_AGENT_NAME", "main"
                                ),
                                "agent_role": os.environ.get(
                                    "CLAUDE_AGENT_ROLE", "user"
                                ),
                            },
                        },
                        trace_id=trace_id,
                        session_id=hook_input.get("session_id"),
                        project_id=(
                            detect_project_func(cwd_path)
                            if detect_project_func
                            else None
                        ),
                        tags=["capture", "trigger"],
                        start_time=capture_start,
                        end_time=datetime.now(tz=timezone.utc),
                    )
                except Exception:
                    pass  # Never crash the hook for tracing

            # AC 2.1.1: Fork to background for <500ms performance
            fork_to_background(hook_input, trace_id)

            # WP-6 §6.3: After existing capture fork, detect if this Edit/Write fixes an active error
            detect_edit_write_fix(hook_input)

            # User notification via JSON systemMessage (visible in Claude Code UI per issue #4084)
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
            return 0  # Hooks must always exit 0 (§1.2 Principle 4)


if __name__ == "__main__":
    sys.exit(main())
