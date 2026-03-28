#!/usr/bin/env python3
"""Gemini CLI AfterTool adapter — captures code patterns from file edits and MCP tools.

Architecture: §2 Data Flow Capture Path
PRD: FR-202, FR-208

Gemini AfterTool fires after file writes, edits, shell commands, and MCP tools.
This adapter normalizes the payload and forks to the background pipeline.
No stdout output — fire-and-forget.
"""

import json
import logging
import os
import sys
import time

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

logger = logging.getLogger("ai_memory.adapters.gemini.after_tool_capture")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def main() -> int:
    start_ms = time.perf_counter()

    try:
        raw_input = sys.stdin.read()
    except Exception:
        logger.exception("stdin_read_error")
        return 0

    try:
        raw = json.loads(raw_input)
    except (json.JSONDecodeError, TypeError):
        logger.warning("malformed_json_input")
        return 0

    try:
        from memory.adapters.schema import (
            fork_to_background,
            normalize_gemini_event,
            validate_canonical_event,
        )

        event = normalize_gemini_event(raw, "AfterTool")
        validate_canonical_event(event)
    except (ValueError, ImportError) as e:
        logger.warning("normalization_error", extra={"error": str(e)})
        return 0

    # Skip unsupported tool types
    if event["tool_name"] is None:
        logger.debug("skip_no_tool_name")
        return 0

    try:
        pipeline_script = os.path.join(
            INSTALL_DIR, ".claude", "hooks", "scripts", "store_async.py"
        )
        fork_to_background(event, pipeline_script)

        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        logger.info(
            "after_tool_capture_complete",
            extra={
                "tool_name": event["tool_name"],
                "elapsed_ms": elapsed_ms,
                "ide_source": "gemini",
            },
        )
        return 0

    except Exception:
        logger.exception("fork_error")
        return 0


if __name__ == "__main__":
    sys.exit(main())
