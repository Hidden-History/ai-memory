#!/usr/bin/env python3
"""Codex CLI UserPromptSubmit adapter — per-turn context injection.

Architecture: §2 Data Flow Retrieval Path
PRD: FR-404

Fires on every UserPromptSubmit event. Queries Qdrant for semantically
relevant memories and returns them as additionalContext.
Must complete within 2000ms and never block the user turn.

Codex stdout contract: JSON only. No plain text. All logging to stderr.
Output: {"hookSpecificOutput": {"additionalContext": "<markdown>"}}
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

logger = logging.getLogger("ai_memory.adapters.codex.context_injection")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

EMPTY_OUTPUT = {"hookSpecificOutput": {"additionalContext": ""}}


def _output_json(data: dict) -> None:
    """Write JSON to stdout and flush. Codex requires JSON-only stdout."""
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
            normalize_codex_event,
            validate_canonical_event,
        )

        event = normalize_codex_event(raw, "UserPromptSubmit")
        validate_canonical_event(event)
    except (ValueError, ImportError) as e:
        logger.warning("normalization_error", extra={"error": str(e)})
        _output_json(EMPTY_OUTPUT)
        return 0

    user_prompt = event.get("user_prompt")
    if not user_prompt:
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

        results = search_client.search(
            query=user_prompt,
            group_id=project_name,
            limit=5,
        )

        if not results:
            _output_json(EMPTY_OUTPUT)
            return 0

        from memory.injection import format_injection_output

        formatted = format_injection_output(results, tier=2)

        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        logger.info(
            "context_injection_complete",
            extra={
                "results": len(results),
                "elapsed_ms": elapsed_ms,
                "ide_source": "codex",
                "project": project_name,
            },
        )

        output = {"hookSpecificOutput": {"additionalContext": formatted or ""}}
        _output_json(output)
        return 0

    except Exception:
        logger.exception("retrieval_error")
        _output_json(EMPTY_OUTPUT)
        return 0


if __name__ == "__main__":
    sys.exit(main())
