#!/usr/bin/env python3
"""Cursor IDE sessionStart adapter — retrieves memories and injects as additional_context.

Architecture: §2 Data Flow Retrieval Path
PRD: FR-301, FR-601, FR-602, FR-603

Cursor stdout contract: JSON only. No plain text. All logging to stderr.
Output: {"additional_context": "<markdown>"}
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

logger = logging.getLogger("ai_memory.adapters.cursor.session_start")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

EMPTY_OUTPUT = {"additional_context": ""}


def _output_json(data: dict) -> None:
    """Write JSON to stdout and flush. Cursor requires JSON-only stdout."""
    print(json.dumps(data))
    sys.stdout.flush()


def main() -> int:
    start_ms = time.perf_counter()

    try:
        raw_input = sys.stdin.read()
    except Exception:
        logger.exception("stdin_read_error")
        _output_json(EMPTY_OUTPUT)
        return 0

    try:
        raw = json.loads(raw_input)
    except (json.JSONDecodeError, TypeError):
        logger.warning("malformed_json_input")
        _output_json(EMPTY_OUTPUT)
        return 0

    try:
        from memory.adapters.schema import (
            normalize_cursor_event,
            validate_canonical_event,
        )

        event = normalize_cursor_event(raw, "sessionStart")
        validate_canonical_event(event)
    except (ValueError, ImportError) as e:
        logger.warning("normalization_error", extra={"error": str(e)})
        _output_json(EMPTY_OUTPUT)
        return 0

    # Skip retrieval for background agents
    if event.get("is_background_agent"):
        logger.debug("skip_background_agent")
        _output_json(EMPTY_OUTPUT)
        return 0

    try:
        from memory.config import MemoryConfig
        from memory.health import check_qdrant_health
        from memory.project import detect_project
        from memory.qdrant_client import get_qdrant_client
        from memory.search import MemorySearch

        config = MemoryConfig()
        client = get_qdrant_client(config)

        if not check_qdrant_health(client):
            logger.warning("qdrant_unavailable")
            _output_json(EMPTY_OUTPUT)
            return 0

        project_name = detect_project(event["cwd"])
        search_client = MemorySearch(config)

        from memory.injection import (
            format_injection_output,
            retrieve_bootstrap_context,
            select_results_greedy,
        )

        results = retrieve_bootstrap_context(search_client, project_name, config)
        selected, tokens_used = select_results_greedy(
            results, config.bootstrap_token_budget
        )
        formatted = format_injection_output(selected, tier=1)

        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        logger.info(
            "session_start_complete",
            extra={
                "results": len(selected),
                "tokens": tokens_used,
                "elapsed_ms": elapsed_ms,
                "ide_source": "cursor",
                "project": project_name,
            },
        )

        output = {"additional_context": formatted or ""}
        _output_json(output)
        return 0

    except Exception:
        logger.exception("retrieval_error")
        _output_json(EMPTY_OUTPUT)
        return 0


if __name__ == "__main__":
    sys.exit(main())
