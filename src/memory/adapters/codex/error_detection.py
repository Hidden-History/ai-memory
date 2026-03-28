#!/usr/bin/env python3
"""Codex CLI PostToolUse(Bash) adapter — retrieves past error fixes.

Architecture: §2 Data Flow Retrieval Path (error path)
PRD: FR-402 (Bash error detection)

Fires when PostToolUse matches Bash and output contains error patterns.
Retrieves error_pattern memories and injects as additionalContext.
"""

import json
import logging
import os
import sys

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

logger = logging.getLogger("ai_memory.adapters.codex.error_detection")
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

EMPTY_OUTPUT = {"hookSpecificOutput": {"additionalContext": ""}}


def _output_json(data: dict) -> None:
    print(json.dumps(data))
    sys.stdout.flush()


def main() -> int:
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

        event = normalize_codex_event(raw, "PostToolUse")
        validate_canonical_event(event)
    except (ValueError, ImportError) as e:
        logger.warning("normalization_error", extra={"error": str(e)})
        _output_json(EMPTY_OUTPUT)
        return 0

    # Only process Bash tool errors
    if event["tool_name"] != "Bash":
        _output_json(EMPTY_OUTPUT)
        return 0

    tool_response = event.get("tool_response")
    if not tool_response:
        _output_json(EMPTY_OUTPUT)
        return 0

    # Check for error signatures in output
    output_text = (
        tool_response if isinstance(tool_response, str) else str(tool_response)
    )

    try:
        from memory.hooks_common import extract_error_signature

        error_sig = extract_error_signature(output_text)
        if not error_sig:
            _output_json(EMPTY_OUTPUT)
            return 0
    except ImportError:
        _output_json(EMPTY_OUTPUT)
        return 0

    try:
        from memory.config import COLLECTION_CODE_PATTERNS, MemoryConfig
        from memory.health import check_qdrant_health
        from memory.project import detect_project
        from memory.qdrant_client import get_qdrant_client
        from memory.search import MemorySearch

        config = MemoryConfig()
        client = get_qdrant_client(config)
        if not check_qdrant_health(client):
            _output_json(EMPTY_OUTPUT)
            return 0

        project_name = detect_project(event["cwd"])
        search_client = MemorySearch(config)
        results = search_client.search(
            query=error_sig,
            collection=COLLECTION_CODE_PATTERNS,
            group_id=project_name,
            limit=3,
            type_filter="error_pattern",
        )

        if not results:
            _output_json(EMPTY_OUTPUT)
            return 0

        from memory.injection import format_injection_output

        formatted = format_injection_output(results, tier=2)
        output = {"hookSpecificOutput": {"additionalContext": formatted or ""}}
        _output_json(output)
        return 0

    except Exception:
        logger.exception("retrieval_error")
        _output_json(EMPTY_OUTPUT)
        return 0


if __name__ == "__main__":
    sys.exit(main())
