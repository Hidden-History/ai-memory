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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Configure structured logging (Story 6.2)
from memory.logging_config import StructuredFormatter
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from memory.metrics import hook_duration_seconds
except ImportError:
    hook_duration_seconds = None


def validate_hook_input(data: Dict[str, Any]) -> Optional[str]:
    """Validate hook input against expected schema.

    AC 2.1.3: Input schema validation
    AC 2.1.1: Validate tool_name and tool_status

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    # Check required fields
    required_fields = ["tool_name", "tool_status", "tool_input", "cwd", "session_id"]
    for field in required_fields:
        if field not in data:
            return f"missing_required_field_{field}"

    # AC 2.1.1: Validate tool_name
    valid_tools = ["Edit", "Write", "NotebookEdit"]
    if data["tool_name"] not in valid_tools:
        return "invalid_tool_name"

    # AC 2.1.1: Validate tool_status == success
    if data["tool_status"] != "success":
        return "tool_not_successful"

    return None


def fork_to_background(hook_input: Dict[str, Any]) -> None:
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
        process = subprocess.Popen(
            [sys.executable, str(store_async_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Full detachment from parent
        )

        # Write input and close stdin (non-blocking)
        if process.stdin:
            process.stdin.write(input_json.encode('utf-8'))
            process.stdin.close()

        logger.info(
            "background_forked",
            extra={
                "tool_name": hook_input["tool_name"],
                "session_id": hook_input["session_id"]
            }
        )

    except Exception as e:
        # Non-blocking error - log and continue
        logger.error(
            "fork_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        # Don't raise - graceful degradation


def main() -> int:
    """PostToolUse hook entry point.

    Reads hook input from stdin, validates it, and forks to background.

    Returns:
        Exit code: 0 (success) or 1 (non-blocking error)
    """
    global hook_duration_seconds
    start_time = time.perf_counter()

    # Late import of metrics after sys.path is configured (Story 6.1, AC 6.1.3)
    try:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent.parent
        local_src = project_root / "src"
        if local_src.exists():
            sys.path.insert(0, str(local_src))
        from memory.metrics import hook_duration_seconds as _hook_metric
        hook_duration_seconds = _hook_metric
    except ImportError:
        logger.warning("metrics_module_unavailable")
        hook_duration_seconds = None

    try:
        # Read hook input from stdin (Claude Code convention)
        raw_input = sys.stdin.read()

        # AC 2.1.3: Handle malformed JSON (FR34)
        try:
            hook_input = json.loads(raw_input)
        except json.JSONDecodeError as e:
            logger.error(
                "malformed_json",
                extra={
                    "error": str(e),
                    "input_preview": raw_input[:100]
                }
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
                    "tool_status": hook_input.get("tool_status")
                }
            )
            return 0  # Non-blocking - graceful handling

        # AC 2.1.1: Fork to background for <500ms performance
        fork_to_background(hook_input)

        # Metrics: Record hook duration (Story 6.1, AC 6.1.3)
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="PostToolUse").observe(duration_seconds)

        # AC 2.1.1: Exit immediately after fork (NFR-P1)
        return 0

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "hook_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__
            }
        )

        # Metrics: Record hook duration even on error (Story 6.1, AC 6.1.3)
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="PostToolUse").observe(duration_seconds)

        return 1  # Non-blocking error


if __name__ == "__main__":
    sys.exit(main())
