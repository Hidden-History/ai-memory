#!/usr/bin/env python3
"""UserPromptSubmit Hook - Capture user messages for turn-by-turn memory.

Memory System V2.0 - Section 10: Turn-by-Turn Conversation Capture

This hook fires when the user submits a message to Claude Code.
Stores user prompts to discussions collection for conversation continuity.

Exit Codes:
- 0: Success (normal completion)
- 1: Non-blocking error (Claude continues, graceful degradation)

Performance: Must complete in <50ms (NFR-P1)
Pattern: Fork to background using subprocess.Popen + start_new_session=True

Input Schema:
{
    "session_id": "abc-123-def",
    "prompt": "The user's message text",
    "transcript_path": "~/.claude/projects/.../xxx.jsonl"
}
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Configure structured logging
from memory.logging_config import StructuredFormatter

handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation
try:
    from memory.metrics import hook_duration_seconds
except ImportError:
    hook_duration_seconds = None

# Maximum content length for user prompts (prevents payload bloat)
# V2.0 Fix: Truncate extremely long prompts to avoid Qdrant payload issues
MAX_CONTENT_LENGTH = 10000  # Embeddings handle large text well


def validate_hook_input(data: Dict[str, Any]) -> Optional[str]:
    """Validate hook input against expected schema.

    Args:
        data: Parsed JSON input from Claude Code

    Returns:
        Error message if validation fails, None if valid
    """
    required_fields = ["session_id", "prompt", "transcript_path"]
    for field in required_fields:
        if field not in data:
            return f"missing_required_field_{field}"

    # Validate prompt is non-empty
    if not data.get("prompt", "").strip():
        return "empty_prompt"

    return None


def count_turns_from_transcript(transcript_path: str) -> int:
    """Count number of messages in transcript for turn_number.

    Args:
        transcript_path: Path to .jsonl transcript file

    Returns:
        Number of messages in transcript
    """
    try:
        expanded_path = os.path.expanduser(transcript_path)
        if not os.path.exists(expanded_path):
            return 0

        count = 0
        with open(expanded_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    except Exception:
        return 0


def fork_to_background(hook_input: Dict[str, Any], turn_number: int) -> None:
    """Fork storage operation to background process.

    Args:
        hook_input: Validated hook input to pass to background script
        turn_number: Turn number extracted from transcript

    Raises:
        No exceptions - logs errors and continues
    """
    try:
        # Path to background storage script
        script_dir = Path(__file__).parent
        store_script = script_dir / "user_prompt_store_async.py"

        # Truncate long prompts before storage (Fix #12)
        prompt = hook_input.get("prompt", "")
        if len(prompt) > MAX_CONTENT_LENGTH:
            hook_input["prompt"] = (
                prompt[:MAX_CONTENT_LENGTH]
                + f"... [truncated from {len(prompt)} chars]"
            )
            logger.info(
                "prompt_truncated",
                extra={
                    "original_length": len(prompt),
                    "truncated_length": MAX_CONTENT_LENGTH,
                    "session_id": hook_input.get("session_id"),
                },
            )

        # Add turn_number to hook_input
        hook_input["turn_number"] = turn_number

        # Serialize hook input for background process
        input_json = json.dumps(hook_input)

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
                "hook_type": "UserPromptSubmit",
                "session_id": hook_input["session_id"],
                "turn_number": turn_number,
            },
        )

    except Exception as e:
        # Non-blocking error - log and continue
        logger.error(
            "fork_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )


def main() -> int:
    """UserPromptSubmit hook entry point.

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

        # Extract turn number from transcript (HIGH FIX: +1 for current message)
        transcript_path = hook_input.get("transcript_path", "")
        # Current message is NEXT turn, not current count
        raw_count = count_turns_from_transcript(transcript_path)
        # Validate turn number (Fix #3: bounds checking prevents corruption)
        turn_number = max(1, min(raw_count + 1, 10000))  # Bounds: 1 to 10000

        # Fork to background immediately for <50ms performance
        fork_to_background(hook_input, turn_number)

        # Metrics: Record hook duration
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="UserPromptSubmit").observe(
                duration_seconds
            )

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
            hook_duration_seconds.labels(hook_type="UserPromptSubmit").observe(
                duration_seconds
            )

        return 1  # Non-blocking error


if __name__ == "__main__":
    sys.exit(main())
