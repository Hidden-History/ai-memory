#!/usr/bin/env python3
"""Langfuse Stop Hook — Session-Level Tier 1 Tracing.

Captures Claude Code conversation transcripts as Langfuse traces.
Fires after every Claude Code response (Stop hook).

PLAN-008 / SPEC-022 §2
"""

import json
import logging
import os
import signal
import sys
import uuid
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    """Main entry point for Stop hook."""
    # Kill-switches — exit immediately if tracing disabled
    if os.environ.get("TRACE_TO_LANGFUSE", "false").lower() != "true":
        sys.exit(0)
    if os.environ.get("LANGFUSE_TRACE_SESSIONS", "true").lower() != "true":
        sys.exit(0)

    try:
        # Read transcript from stdin (Claude Code passes JSON)
        input_data = sys.stdin.read()
        if not input_data.strip():
            logger.debug("No input data — skipping trace")
            sys.exit(0)

        transcript = json.loads(input_data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse transcript: %s", e)
        sys.exit(0)  # Never block Claude Code

    try:
        # Add src to path for imports
        install_dir = os.environ.get("AI_MEMORY_INSTALL_DIR", "")
        if install_dir:
            sys.path.insert(0, os.path.join(install_dir, "src"))

        from langfuse import Langfuse

        from memory.langfuse_config import get_langfuse_client

        client = get_langfuse_client()
        if client is None:
            sys.exit(0)

        # Build trace metadata (SPEC-022 §2.3, §2.4)
        project_id = os.environ.get("AI_MEMORY_PROJECT_ID", "")
        trace_metadata = {
            "project_id": project_id,
            "source": "claude_code_stop_hook",
        }

        # Parzival session tagging (SPEC-022 §2.3)
        if os.environ.get("PARZIVAL_ENABLED", "false").lower() == "true":
            trace_metadata["agent_id"] = "parzival"

        # Extract session info from transcript
        session_id = transcript.get("session_id", str(uuid.uuid4()))
        messages = transcript.get("messages", transcript.get("turns", []))

        # Create trace with v3 API (SPEC-022 §2.6)
        trace_id = Langfuse.create_trace_id(seed=session_id)
        root_span = client.start_span(
            trace_context={"trace_id": trace_id},
            name="claude_code_session",
            metadata={
                **trace_metadata,
                "start_time": transcript.get(
                    "start_time", datetime.utcnow().isoformat()
                ),
                "end_time": transcript.get("end_time", datetime.utcnow().isoformat()),
                "turn_count": len(messages),
            },
        )
        root_span.update_trace(
            name="claude_code_session",
            session_id=session_id,
            metadata={**trace_metadata, "turn_count": len(messages)},
        )

        # Add child spans for each turn (SPEC-022 §2.6)
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            span_metadata = {"role": role}
            # Include token_count if available
            if "token_count" in msg:
                span_metadata["token_count"] = msg["token_count"]

            turn_span = client.start_span(
                trace_context={"trace_id": trace_id, "parent_span_id": root_span.id},
                name=f"turn_{i}",
                metadata=span_metadata,
                input=content[:500] if isinstance(content, str) else str(content)[:500],
            )
            turn_span.end()

        root_span.end()

        # Synchronous flush — acceptable for Stop hook (SPEC-022 §2.1)
        # 2-second timeout per SPEC-022 §8 risk mitigation
        try:

            def _flush_timeout_handler(signum, frame):
                raise TimeoutError("Langfuse flush exceeded 2s timeout")

            old_handler = signal.signal(signal.SIGALRM, _flush_timeout_handler)
            signal.alarm(2)
            try:
                client.flush()
            except TimeoutError:
                logger.warning("Langfuse flush timed out after 2s — traces may be lost")
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except AttributeError:
            # SIGALRM not available on Windows — flush without timeout
            client.flush()

        logger.debug(
            "Langfuse trace created: session=%s, turns=%d", session_id, len(messages)
        )

    except Exception as e:
        # CRITICAL: Never block Claude Code (SPEC-022 AC-11)
        logger.warning("Langfuse stop hook error (non-blocking): %s", e)

    sys.exit(0)


if __name__ == "__main__":
    main()
