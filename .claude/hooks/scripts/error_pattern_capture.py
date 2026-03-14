#!/usr/bin/env python3
"""PostToolUse Hook - Capture error patterns from failed Bash commands.

Triggered by: PostToolUse with matcher "Bash"

Requirements:
- Parse tool_output JSON from Claude Code hook
- Detect error indicators (exit code != 0, error strings)
- Extract error context (command, error message, stack trace)
- Store to implementations collection with type="error_pattern"
- Use fork pattern for non-blocking storage
- Include file:line references if present
- Exit 0 immediately after forking

Exit Codes:
- 0: Always (hooks must never block Claude — §1.2 Principle 4)

Performance: Must complete in <500ms (NFR-P1)
Pattern: Fork to background using subprocess.Popen + start_new_session=True
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4, §7.7
# SDK VERSION: V3 ONLY. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.activity_log import log_error_capture

# Configure structured logging
from memory.logging_config import StructuredFormatter

handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# TECH-DEBT-142: Import push metrics for Pushgateway
try:
    from memory.metrics_push import track_hook_duration
    from memory.project import detect_project
    from memory.trace_buffer import emit_trace_event  # SPEC-021
except ImportError:
    track_hook_duration = None
    detect_project = None
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000  # Max chars for Langfuse input/output fields


def extract_command_prefix(command: str) -> str:
    """Extract first token of command as prefix.

    Args:
        command: Full command string (e.g., "pip install foo")

    Returns:
        First token (e.g., "pip")
    """
    parts = command.strip().split()
    return parts[0] if parts else "unknown"


def extract_exception_type(output: str) -> str:
    """Extract exception/error type from output.

    Looks for Python exception patterns (e.g., "ModuleNotFoundError:"),
    shell errors, and generic error types.

    Args:
        output: Error output text

    Returns:
        Exception type string (e.g., "ModuleNotFoundError")
    """
    # Python exception pattern: ExceptionName: message
    match = re.search(r"(\w+Error|\w+Exception|\w+Warning):", output)
    if match:
        return match.group(1)

    # Shell error patterns
    if "command not found" in output.lower():
        return "CommandNotFound"
    if "permission denied" in output.lower():
        return "PermissionDenied"
    if "no such file or directory" in output.lower():
        return "FileNotFoundError"
    if "segmentation fault" in output.lower():
        return "SegmentationFault"
    if "syntax error" in output.lower():
        return "SyntaxError"

    return "UnknownError"


def compute_error_group_id(
    command_prefix: str, exception_type: str, session_id: str
) -> str:
    """Compute error_group_id: SHA-256(command_prefix + exception_type + session_id), first 16 hex chars.

    Args:
        command_prefix: First token of the command
        exception_type: Extracted exception type
        session_id: Current session ID

    Returns:
        First 16 hex chars of SHA-256 hash
    """
    key = f"{command_prefix}:{exception_type}:{session_id}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def detect_bash_fix(hook_input: dict[str, Any]) -> None:
    """Detect if a successful Bash command resolves a prior error.

    After error capture, check if current Bash SUCCESS resolves a prior error
    by matching command_prefix + exit code 0.

    Args:
        hook_input: Validated hook input
    """
    try:
        tool_response = hook_input.get("tool_response", {})
        exit_code = tool_response.get("exitCode")

        # Only check successful commands
        if exit_code is not None and exit_code != 0:
            return
        if exit_code is None:
            return

        command = hook_input.get("tool_input", {}).get("command", "")
        if not command:
            return

        session_id = hook_input.get("session_id", "")
        if not session_id:
            return

        from memory.injection import InjectionSessionState

        state = InjectionSessionState.load(session_id)
        if not state.error_state:
            return

        current_prefix = extract_command_prefix(command)

        # Find matching active errors by command_prefix
        matched_errors = []
        for eid, edata in state.error_state.items():
            if eid.startswith("_"):
                continue
            stored_prefix = edata.get("command_prefix", "")
            if stored_prefix and stored_prefix == current_prefix:
                matched_errors.append((eid, edata))

        if not matched_errors:
            return

        # Create fix entries for matched errors
        for error_group_id, error_data in matched_errors:
            turn_diff = state.turn_count - error_data.get("turn_number", 0)

            # Resolution confidence scoring per §C4b
            if turn_diff <= 3:
                confidence = 0.5  # Same prefix but different context (Bash)
            elif turn_diff <= 10:
                confidence = 0.4
            else:
                confidence = 0.3

            _fork_fix_to_background(
                session_id=session_id,
                error_group_id=error_group_id,
                error_data=error_data,
                fix_content=f"Bash fix: {command}",
                resolution_confidence=confidence,
                fix_source="bash_success",
                cwd=hook_input.get("cwd", ""),
                turn_count=state.turn_count,
            )

        # Remove resolved errors from session state
        for eid, _ in matched_errors:
            state.error_state.pop(eid, None)
        state.save()

    except Exception as e:
        logger.warning("bash_fix_detection_failed", extra={"error": str(e)})


def _fork_fix_to_background(
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
        fix_source: Source of fix detection ("edit", "write", "bash_success")
        cwd: Working directory
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

        # Langfuse trace for fix capture
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
                            "file_overlap": fix_source != "bash_success",
                            "fix_source": fix_source,
                        },
                    },
                    trace_id=hashlib.md5(error_group_id.encode()).hexdigest()[:32],
                    session_id=session_id,
                    tags=["capture", "error_detection"],
                )
            except Exception:
                pass

        # Prometheus metric
        try:
            from memory.metrics import error_fix_captures_total
            from memory.project import detect_project

            project = detect_project(cwd) if cwd else "unknown"
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


def detect_error_indicators(output: str, exit_code: int | None) -> bool:
    """Detect if output contains error indicators.

    PLAN-010 (P10-7): Rewritten to avoid false positives from filenames
    containing 'error' in directory listings (find, ls, glob output).

    Args:
        output: Tool output text
        exit_code: Command exit code (None if not available)

    Returns:
        True if error detected, False otherwise
    """
    # Exit code check (most reliable indicator)
    if exit_code is not None and exit_code != 0:
        return True

    # Skip if output looks like a directory listing (find/ls/glob output)
    # These commonly contain filenames with "error" in the name
    lines = output.strip().split("\n")
    if lines and all(
        re.match(r"^[\s]*[/.]?[\w./-]+\.\w+\s*$", line.strip())
        for line in lines[:20]
        if line.strip()
    ):
        return False

    # Actual error patterns — structured error indicators, NOT bare keywords
    # Checked FIRST so real errors are never masked by conversational filter
    error_patterns = [
        r"Traceback \(most recent call last\)",
        r"(?:^|\s)(?:Error|Exception|Fatal|FATAL):\s",
        r"(?:^|\s)(?:error|FAILED|panic)\[?\s*[\d:]",
        r"command not found",
        r"permission denied",
        r"no such file or directory",
        r"segmentation fault",
        r"core dumped",
        r"syntax error",
        r"exit code [1-9]",
        r"FAILED\s",
        r"npm ERR!",
        r"ModuleNotFoundError:",
        r"ImportError:",
        r"TypeError:",
        r"ValueError:",
        r"KeyError:",
        r"AttributeError:",
        r"RuntimeError:",
        r"FileNotFoundError:",
        r"ConnectionError:",
        r"TimeoutError:",
    ]

    output_text = output
    has_structural_error = False
    for pattern in error_patterns:
        if re.search(pattern, output_text, re.IGNORECASE | re.MULTILINE):
            has_structural_error = True
            break

    # If structural error found, it's a real error regardless of conversational text
    if has_structural_error:
        return True

    # TD-260: Skip conversational content when no structural error AND no non-zero exit code
    # Prevents false positives from agent responses mentioning "error" conversationally
    # Applied AFTER structural error check to avoid masking real errors
    if exit_code is None or exit_code == 0:
        first_lines = "\n".join(lines[:5]).lower()
        conversational_phrases = [
            "i fixed",
            "i resolved",
            "the error was",
            "no errors",
            "error handling",
            "error-free",
            "without error",
            "has been fixed",
            "has been resolved",
            "was resolved",
            "successfully",
            "works correctly",
            "no issues",
            "error is gone",
            "errors were fixed",
            "fixed the error",
            "resolved the error",
            "error has been",
            "handled the error",
        ]
        if any(phrase in first_lines for phrase in conversational_phrases):
            return False

    return False


def extract_file_line_references(output: str) -> list[dict[str, Any]]:
    """Extract file:line references from error output.

    Common patterns:
    - file.py:42
    - /path/to/file.py:42
    - file.py:42:10 (with column)
    - File "file.py", line 42
    - at file.py:42

    Args:
        output: Error output text

    Returns:
        List of dicts with 'file', 'line', and optional 'column' keys
    """
    references = []

    # Pattern 1: file.py:42 or file.py:42:10
    pattern1 = r"([a-zA-Z0-9_./\-]+\.py):(\d+)(?::(\d+))?"
    for match in re.finditer(pattern1, output):
        ref = {"file": match.group(1), "line": int(match.group(2))}
        if match.group(3):
            ref["column"] = int(match.group(3))
        references.append(ref)

    # Pattern 2: File "file.py", line 42
    pattern2 = r'File "([^"]+)", line (\d+)'
    for match in re.finditer(pattern2, output):
        references.append({"file": match.group(1), "line": int(match.group(2))})

    # Pattern 3: at file.py:42
    pattern3 = r"at ([a-zA-Z0-9_./\-]+\.py):(\d+)"
    for match in re.finditer(pattern3, output):
        references.append({"file": match.group(1), "line": int(match.group(2))})

    return references


def extract_stack_trace(output: str) -> str | None:
    """Extract stack trace from error output.

    Args:
        output: Error output text

    Returns:
        Stack trace string if found, None otherwise
    """
    # Python traceback pattern
    if "Traceback (most recent call last):" in output:
        lines = output.split("\n")
        trace_lines = []
        in_trace = False

        for line in lines:
            if "Traceback (most recent call last):" in line:
                in_trace = True
                trace_lines.append(line)
            elif in_trace:
                trace_lines.append(line)
                # Stop at first non-indented line after traceback
                if line and not line.startswith((" ", "\t")):
                    break

        if trace_lines:
            return "\n".join(trace_lines)

    # Generic stack trace pattern (multiple "at" lines)
    at_lines = [line for line in output.split("\n") if re.match(r"\s*at\s+", line)]
    if len(at_lines) >= 2:
        return "\n".join(at_lines)

    return None


def extract_error_message(output: str) -> str:
    """Extract concise error message from output.

    Args:
        output: Error output text

    Returns:
        Extracted error message
    """
    lines = output.strip().split("\n")

    # Look for lines containing error keywords
    error_keywords = ["error", "exception", "failed", "failure", "fatal"]

    for line in lines:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in error_keywords):
            # Return first error line, truncated if too long
            return line.strip()[:200]

    # Fallback: return last non-empty line (often the error)
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:200]

    return "Error detected in command output"


def validate_hook_input(data: dict[str, Any]) -> str | None:
    """Validate hook input for Bash tool.

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    # Check required fields
    required_fields = ["tool_name", "tool_input", "tool_response", "cwd", "session_id"]
    for field in required_fields:
        if field not in data:
            return f"missing_required_field_{field}"

    # Validate tool_name is Bash
    if data["tool_name"] != "Bash":
        return "not_bash_tool"

    # Validate tool_response structure
    tool_response = data.get("tool_response", {})
    if not isinstance(tool_response, dict):
        return "invalid_tool_response_format"

    return None


def extract_error_context(hook_input: dict[str, Any]) -> dict[str, Any] | None:
    """Extract error context from Bash tool output.

    Args:
        hook_input: Validated hook input

    Returns:
        Error context dict if error detected, None otherwise
    """
    tool_input = hook_input.get("tool_input", {})
    tool_response = hook_input.get("tool_response", {})

    # Get command and output
    # Claude Code sends stdout/stderr separately, not combined "output"
    command = tool_input.get("command", "")
    stdout = tool_response.get("stdout", "")
    stderr = tool_response.get("stderr", "")
    output = stderr if stderr else stdout  # Prefer stderr for errors
    exit_code = tool_response.get(
        "exitCode"
    )  # May not be present in newer Claude Code versions

    # Detect if this is an error
    if not detect_error_indicators(output, exit_code):
        return None

    # Extract error details
    file_references = extract_file_line_references(output)
    stack_trace = extract_stack_trace(output)
    error_message = extract_error_message(output)

    # Compute error_group_id (§C4)
    session_id = hook_input.get("session_id", "")
    command_prefix = extract_command_prefix(command)
    exception_type = extract_exception_type(output)
    error_group_id = compute_error_group_id(command_prefix, exception_type, session_id)

    # Primary file from references
    primary_file = file_references[0]["file"] if file_references else "unknown"

    # Build error context
    context = {
        "command": command,
        "exit_code": exit_code,
        "error_message": error_message,
        "output": output[:1000],  # Truncate long output
        "file_references": file_references,
        "stack_trace": stack_trace,
        "cwd": hook_input.get("cwd", ""),
        "session_id": session_id,
        # WP-6: Error-fix linkage fields
        "command_prefix": command_prefix,
        "exception_type": exception_type,
        "error_group_id": error_group_id,
    }

    return context


def fork_to_background(
    error_context: dict[str, Any], trace_id: str | None = None
) -> None:
    """Fork error storage to background process.

    Args:
        error_context: Error context to store
    """
    try:
        # Path to background storage script
        script_dir = Path(__file__).parent
        error_store_script = script_dir / "error_store_async.py"

        # Serialize error context
        input_json = json.dumps(error_context)

        # SPEC-021: Propagate trace_id + session_id (TD-241) to store-async subprocess
        subprocess_env = os.environ.copy()
        if trace_id:
            subprocess_env["LANGFUSE_TRACE_ID"] = trace_id
        # TD-241: Propagate CLAUDE_SESSION_ID so store_async library calls get session_id
        # via env fallback even if explicit param is unavailable.
        _sid = error_context.get("session_id", "")
        if _sid:
            subprocess_env["CLAUDE_SESSION_ID"] = _sid

        # Fork to background
        process = subprocess.Popen(
            [sys.executable, str(error_store_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=subprocess_env,
        )

        # Write input and close stdin
        if process.stdin:
            process.stdin.write(input_json.encode("utf-8"))
            process.stdin.close()

        logger.info(
            "error_pattern_forked",
            extra={
                "command": error_context.get("command", "")[:50],
                "session_id": error_context.get("session_id", "unknown"),
            },
        )

    except Exception as e:
        logger.error(
            "fork_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )


def main() -> int:
    """PostToolUse hook entry point for error pattern capture.

    Returns:
        Exit code: 0 always (§1.2 Principle 4: hooks never block Claude)
    """
    import contextlib

    # TECH-DEBT-142: Late import of push metrics
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

    # HIGH-2 FIX: Use proper with statement to ensure __exit__() on all paths
    cm = (
        track_hook_duration_func("PostToolUse_Error", project=project)
        if track_hook_duration_func
        else contextlib.nullcontext()
    )

    with cm:
        try:
            # Read hook input from stdin
            raw_input = sys.stdin.read()

            # Parse JSON
            try:
                hook_input = json.loads(raw_input)
            except json.JSONDecodeError as e:
                logger.error(
                    "malformed_json",
                    extra={"error": str(e), "input_preview": raw_input[:100]},
                )
                return 0  # Non-blocking

            # Validate schema
            validation_error = validate_hook_input(hook_input)
            if validation_error:
                logger.info(
                    "validation_failed",
                    extra={
                        "reason": validation_error,
                        "tool_name": hook_input.get("tool_name"),
                    },
                )
                return 0  # Non-blocking

            # Extract error context
            error_context = extract_error_context(hook_input)

            if error_context is None:
                # No error detected - check if this successful command resolves a prior error (§C4b)
                detect_bash_fix(hook_input)
                return 0

            # TD-241: Set CLAUDE_SESSION_ID in this process so library calls pick it up via env fallback
            _session_id = hook_input.get("session_id", "")
            if _session_id:
                os.environ["CLAUDE_SESSION_ID"] = _session_id

            # WP-6: Track error in session state for fix detection linkage
            _egid = error_context.get("error_group_id", "")
            _efile = (
                error_context["file_references"][0]["file"]
                if error_context.get("file_references")
                else "unknown"
            )
            if _egid and _session_id:
                # Also store command_prefix in session state for Bash fix matching
                try:
                    from memory.injection import InjectionSessionState

                    _state = InjectionSessionState.load(_session_id)
                    if _state.error_state is None:
                        _state.error_state = {}
                    _state.error_state[_egid] = {
                        "error_group_id": _egid,
                        "file_path": _efile,
                        "turn_number": _state.turn_count,
                        "exception_type": error_context.get(
                            "exception_type", "UnknownError"
                        ),
                        "command_prefix": error_context.get(
                            "command_prefix", "unknown"
                        ),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    _state.save()
                except Exception as e:
                    logger.warning(
                        "error_state_tracking_failed", extra={"error": str(e)}
                    )

            # SPEC-021: Generate trace_id for pipeline trace linking
            trace_id = None
            if emit_trace_event:
                trace_id = uuid.uuid4().hex
                capture_start = datetime.now(tz=timezone.utc)
                cwd = hook_input.get("cwd", os.getcwd())
                try:
                    _error_output = error_context.get("output", "")
                    _error_cmd = error_context.get("command", "")
                    _error_content = (
                        f"$ {_error_cmd}\n{_error_output}"
                        if _error_cmd
                        else _error_output
                    )
                    emit_trace_event(
                        event_type="1_capture",
                        data={
                            "input": _error_content[:TRACE_CONTENT_MAX],
                            "output": f"Captured {len(_error_output)} chars from error_pattern hook",
                            "metadata": {
                                "hook_type": "error_pattern",
                                "source": "bash_tool_output",
                                "raw_length": len(_error_output),
                                "content_length": len(_error_output),
                                "content_extracted": True,
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
                            detect_project_func(cwd) if detect_project_func else None
                        ),
                        tags=["capture", "error_detection"],
                        start_time=capture_start,
                        end_time=datetime.now(tz=timezone.utc),
                    )
                except Exception:
                    pass  # Never crash the hook for tracing

                # WP-6 §8.3: Emit error_capture Langfuse trace
                try:
                    emit_trace_event(
                        event_type="error_capture",
                        data={
                            "input": _error_content[:TRACE_CONTENT_MAX],
                            "output": f"Error captured: group={_egid}",
                            "metadata": {
                                "error_group_id": _egid,
                                "exception_type": error_context.get(
                                    "exception_type", ""
                                ),
                                "file_path": _efile,
                                "command_prefix": error_context.get(
                                    "command_prefix", ""
                                ),
                            },
                        },
                        trace_id=trace_id,
                        session_id=hook_input.get("session_id"),
                        project_id=(
                            detect_project_func(cwd) if detect_project_func else None
                        ),
                        tags=["capture", "error_detection"],
                    )
                except Exception:
                    pass

            # Fork to background
            fork_to_background(error_context, trace_id)

            # User notification via JSON systemMessage (visible in Claude Code UI per issue #4084)
            error_msg = error_context.get("error_message", "Unknown error")
            message = f"🔴 AI Memory: Captured error pattern: {error_msg}"
            print(json.dumps({"systemMessage": message}))
            sys.stdout.flush()  # Ensure output is flushed before exit

            # Activity log with proper error icon (no truncation)
            log_error_capture(
                command=error_context.get("command", ""),
                error_msg=error_msg,
                exit_code=error_context.get("exit_code", -1),
                output=error_context.get("output", ""),
            )

            # HIGH-2 FIX: Context manager automatically calls __exit__() on return
            return 0

        except Exception as e:
            logger.error(
                "hook_failed", extra={"error": str(e), "error_type": type(e).__name__}
            )

            # HIGH-2 FIX: Context manager automatically calls __exit__() on exception
            return 0  # Hooks must always exit 0 (§1.2 Principle 4)


if __name__ == "__main__":
    sys.exit(main())
