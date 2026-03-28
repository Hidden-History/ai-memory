#!/usr/bin/env python3
"""Cursor IDE preCompact adapter — saves session summary before context compression.

Architecture: §2 Data Flow Capture Path (session summary)
PRD: FR-303

Cursor preCompact maps to canonical PreCompact. Captures session summary
to discussions collection before Cursor compresses context.
Preserves context_usage_percent, context_tokens, and context_window_size.
No stdout output — fire-and-forget.
"""

import json
import logging
import os
import sys

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

logger = logging.getLogger("ai_memory.adapters.cursor.pre_compact")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def main() -> int:
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
            normalize_cursor_event,
            validate_canonical_event,
        )

        event = normalize_cursor_event(raw, "preCompact")
        validate_canonical_event(event)
    except (ValueError, ImportError) as e:
        logger.warning("normalization_error", extra={"error": str(e)})
        return 0

    try:
        pipeline_script = os.path.join(
            INSTALL_DIR, ".claude", "hooks", "scripts", "store_async.py"
        )
        fork_to_background(event, pipeline_script)
        logger.info(
            "pre_compact_complete",
            extra={
                "trigger": event.get("trigger"),
                "context_usage_percent": event.get("context_usage_percent"),
                "ide_source": "cursor",
            },
        )
        return 0
    except Exception:
        logger.exception("fork_error")
        return 0


if __name__ == "__main__":
    sys.exit(main())
