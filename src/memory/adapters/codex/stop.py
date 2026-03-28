#!/usr/bin/env python3
"""Codex CLI Stop adapter — saves session summary at session end.

Architecture: §2 Data Flow Capture Path (session summary)
PRD: FR-405

Codex Stop event fires at session end. Captures session summary
synchronously to discussions collection. Runs synchronously (not
fire-and-forget) because latency at session end does not block the user.
No stdout output.
"""

import json
import logging
import os
import sys

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

logger = logging.getLogger("ai_memory.adapters.codex.stop")
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
            normalize_codex_event,
            validate_canonical_event,
        )

        event = normalize_codex_event(raw, "Stop")
        validate_canonical_event(event)
    except (ValueError, ImportError) as e:
        logger.warning("normalization_error", extra={"error": str(e)})
        return 0

    try:
        from memory.config import MemoryConfig
        from memory.health import check_qdrant_health
        from memory.qdrant_client import get_qdrant_client

        config = MemoryConfig()
        client = get_qdrant_client(config)

        if not check_qdrant_health(client):
            logger.warning("qdrant_unavailable")
            return 0

        # Run synchronously via background pipeline script (blocking call)
        import subprocess

        pipeline_script = os.path.join(
            INSTALL_DIR, ".claude", "hooks", "scripts", "agent_response_store_async.py"
        )

        subprocess_env = os.environ.copy()
        sid = event.get("session_id", "")
        if sid:
            subprocess_env["CLAUDE_SESSION_ID"] = sid

        proc = subprocess.run(
            [sys.executable, pipeline_script],
            input=json.dumps(event).encode("utf-8"),
            capture_output=True,
            env=subprocess_env,
            timeout=30,
        )

        logger.info(
            "stop_complete",
            extra={
                "session_id": event.get("session_id"),
                "ide_source": "codex",
                "returncode": proc.returncode,
            },
        )
        return 0

    except Exception:
        logger.exception("stop_error")
        return 0


if __name__ == "__main__":
    sys.exit(main())
