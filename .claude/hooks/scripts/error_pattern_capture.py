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
- 0: Success (normal completion)
- 1: Non-blocking error (Claude continues, graceful degradation)

Performance: Must complete in <500ms (NFR-P1)
Pattern: Fork to background using subprocess.Popen + start_new_session=True
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
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
    from memory.storage import detect_project
except ImportError:
    track_hook_duration = None
    detect_project = None


def detect_error_indicators(output: str, exit_code: int | None) -> bool:
    """Detect if output contains error indicators.

    Args:
        output: Tool output text
        exit_code: Command exit code (None if not available)

    Returns:
        True if error detected, False otherwise
    """
    # Exit code check (most reliable)
    if exit_code is not None and exit_code != 0:
        return True

    # Common error patterns (case-insensitive)
    error_patterns = [
        r"\berror\b",
        r"\bfailed\b",
        r"\bfailure\b",
        r"\bexception\b",
        r"\btraceback\b",
        r"\bfatal\b",
        r"\bpanic\b",
        r"\bwarning\b",
        r"\bcannot\b",
        r"\bunable to\b",
        r"\bpermission denied\b",
        r"\bno such file\b",
        r"\bcommand not found\b",
        r"\bsyntax error\b",
        r"\bsegmentation fault\b",
        r"\bcore dumped\b",
    ]

    output_lower = output.lower()
    for pattern in error_patterns:
        if re.search(pattern, output_lower):
            return True

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

    # Build error context
    context = {
        "command": command,
        "exit_code": exit_code,
        "error_message": error_message,
        "output": output[:1000],  # Truncate long output
        "file_references": file_references,
        "stack_trace": stack_trace,
        "cwd": hook_input.get("cwd", ""),
        "session_id": hook_input.get("session_id", ""),
    }

    return context


def fork_to_background(error_context: dict[str, Any]) -> None:
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

        # Fork to background
        process = subprocess.Popen(
            [sys.executable, str(error_store_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
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
        Exit code: 0 (success) or 1 (non-blocking error)
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
        from memory.storage import detect_project

        track_hook_duration_func = track_hook_duration
        detect_project_func = detect_project
    except ImportError:
        logger.warning("metrics_push_module_unavailable")

    # Detect project for metrics
    project = detect_project_func(os.getcwd()) if detect_project_func else "unknown"

    # HIGH-2 FIX: Use proper with statement to ensure __exit__() on all paths
    cm = track_hook_duration_func("PostToolUse_Error", project=project) if track_hook_duration_func else contextlib.nullcontext()

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
                # No error detected - normal completion
                return 0

            # Fork to background
            fork_to_background(error_context)

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
            return 1  # Non-blocking error


if __name__ == "__main__":
    sys.exit(main())
