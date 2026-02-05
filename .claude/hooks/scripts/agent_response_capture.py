#!/usr/bin/env python3
"""Stop Hook - Capture agent responses for turn-by-turn memory.

Memory System V2.0 - Section 10: Turn-by-Turn Conversation Capture

This hook fires when Claude finishes responding to the user.
Stores agent responses to discussions collection for conversation continuity.

Exit Codes:
- 0: Success (normal completion)
- 1: Non-blocking error (Claude continues, graceful degradation)

Performance: <500ms (non-blocking)
Pattern: Read transcript, extract last assistant message, fork to background

Input Schema:
{
    "session_id": "abc-123-def",
    "transcript_path": "~/.claude/projects/.../xxx.jsonl"
}
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Maximum response size to prevent memory issues in background process (100KB)
MAX_RESPONSE_SIZE = 100 * 1024

# Add src to path for imports (must be inline before importing from memory)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# CR-3.3: Use consolidated logging and transcript reading
from memory.hooks_common import read_transcript, setup_hook_logging

logger = setup_hook_logging()

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import hook_duration_seconds
    from memory.storage import detect_project
except ImportError:
    hook_duration_seconds = None
    detect_project = None


def validate_hook_input(data: dict[str, Any]) -> str | None:
    """Validate hook input against expected schema.

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    required_fields = ["session_id", "transcript_path"]
    for field in required_fields:
        if field not in data:
            return f"missing_required_field_{field}"

    return None


# CR-3.3: read_transcript() moved to hooks_common.py


def extract_last_assistant_message(
    entries: list[dict[str, Any]], max_retries: int = 5, retry_delay: float = 0.1
) -> str | None:
    """Extract the last assistant message from transcript with retry for timing issues.

    Args:
        entries: List of transcript entries
        max_retries: Number of retries if content is empty (default 5)
        retry_delay: Delay between retries in seconds (default 0.1)

    Returns:
        Last assistant message text, or None if not found

    Note:
        Returns full content without truncation - embeddings can handle large text.
        Includes retry logic for Stop hook timing issue (content may not be written yet).
    """
    for attempt in range(max_retries + 1):
        # Reverse iterate to find last assistant message
        for entry in reversed(entries):
            if entry.get("type") == "assistant":
                message = entry.get("message", {})
                content = message.get("content", [])

                # Check if content is populated
                if content:
                    # Extract text from content array
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if text:
                                text_parts.append(text)

                    if text_parts:
                        return "\n".join(text_parts)
                else:
                    # Content empty - timing issue
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        # Note: entries list won't update, need to re-read transcript
                        # This is handled in main() - we need to re-read there
                        return "RETRY_NEEDED"  # Signal to main() to re-read
                    else:
                        return None

        # No assistant entry at all
        return None

    return None


def fork_to_background(
    hook_input: dict[str, Any], response_text: str, turn_number: int
) -> None:
    """Fork storage operation to background process.

    Args:
        hook_input: Validated hook input
        response_text: Assistant's response text to store
        turn_number: Turn number extracted from transcript

    Raises:
        No exceptions - logs errors and continues
    """
    try:
        # Path to background storage script
        script_dir = Path(__file__).parent
        store_script = script_dir / "agent_response_store_async.py"

        # Build data for background process
        # BUG-003 FIX: Use .get() pattern for safe session_id access
        store_data = {
            "session_id": hook_input.get("session_id", "unknown"),
            "response_text": response_text,
            "turn_number": turn_number,
        }

        # Serialize data for background process
        input_json = json.dumps(store_data)

        # Fork to background using subprocess.Popen + start_new_session=True
        process = subprocess.Popen(
            [sys.executable, str(store_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Full detachment from parent
        )

        # Write input and close stdin (non-blocking, CRITICAL FIX: error handling)
        try:
            if process.stdin:
                process.stdin.write(input_json.encode("utf-8"))
                process.stdin.close()
        except (BrokenPipeError, OSError) as e:
            logger.error(
                "stdin_write_failed",
                extra={"error": str(e), "error_type": type(e).__name__},
            )

        logger.info(
            "background_forked",
            extra={
                "hook_type": "Stop",
                "session_id": hook_input.get("session_id", "unknown"),
                "turn_number": turn_number,
                "response_length": len(response_text),
            },
        )

    except Exception as e:
        # Non-blocking error - log and continue
        logger.error(
            "fork_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )


def main() -> int:
    """Stop hook entry point.

    Returns:
        Exit code: 0 (success) or 1 (non-blocking error)
    """
    start_time = time.perf_counter()

    try:
        # Read hook input from stdin
        raw_input = sys.stdin.read()

        # Handle malformed JSON
        try:
            hook_input = json.loads(raw_input)
        except json.JSONDecodeError as e:
            logger.error(
                "malformed_json",
                extra={"error": str(e), "input_preview": raw_input[:100]},
            )
            return 0  # Non-blocking - Claude continues

        # Validate schema
        validation_error = validate_hook_input(hook_input)
        if validation_error:
            logger.info(
                "validation_failed",
                extra={
                    "reason": validation_error,
                    "session_id": hook_input.get("session_id"),
                },
            )
            return 0  # Non-blocking - graceful handling

        # Read transcript
        transcript_path = hook_input["transcript_path"]
        transcript_entries = read_transcript(transcript_path)

        if not transcript_entries:
            logger.info(
                "no_transcript_skipping",
                extra={"session_id": hook_input.get("session_id")},
            )
            return 0

        # Extract last assistant message with retry for timing issues
        # CRITICAL FIX: Reduced from 20/0.25s (5s) to 2/0.05s (100ms max) per CR-3.2
        max_retries = 2
        retry_delay = 0.05
        response_text = None

        for attempt in range(max_retries + 1):
            response_text = extract_last_assistant_message(transcript_entries)

            if response_text == "RETRY_NEEDED":
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    transcript_entries = read_transcript(transcript_path)
                    continue
                else:
                    response_text = None
                    break
            else:
                break

        if not response_text:
            logger.info(
                "no_assistant_message_found",
                extra={
                    "session_id": hook_input.get("session_id"),
                    "attempts": max_retries + 1,
                },
            )
            return 0

        # Count turns (HIGH FIX: count only assistant messages for agent turn number)
        # Current response is already included in transcript_entries
        assistant_count = sum(
            1 for e in transcript_entries if e.get("type") == "assistant"
        )
        # Validate turn number (Fix #3: bounds checking prevents corruption)
        turn_number = max(1, min(assistant_count, 10000))  # Bounds: 1 to 10000

        # Truncate large responses to prevent memory issues in background process
        if len(response_text) > MAX_RESPONSE_SIZE:
            logger.warning(
                "response_text_truncated",
                extra={
                    "original_size": len(response_text),
                    "max_size": MAX_RESPONSE_SIZE,
                    "session_id": hook_input.get("session_id"),
                },
            )
            response_text = response_text[:MAX_RESPONSE_SIZE] + "\n... [truncated]"

        # Fork to background
        fork_to_background(hook_input, response_text, turn_number)

        # Metrics: Record hook duration
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            project = detect_project(os.getcwd()) if detect_project else "unknown"
            hook_duration_seconds.labels(
                hook_type="Stop", status="success", project=project
            ).observe(duration_seconds)

        # Exit immediately after fork
        return 0

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "hook_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )

        # Metrics: Record hook duration even on error
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            project = detect_project(os.getcwd()) if detect_project else "unknown"
            hook_duration_seconds.labels(
                hook_type="Stop", status="error", project=project
            ).observe(duration_seconds)

        return 1  # Non-blocking error


if __name__ == "__main__":
    sys.exit(main())
