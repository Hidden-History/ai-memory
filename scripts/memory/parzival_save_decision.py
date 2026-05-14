#!/usr/bin/env python3
"""Save a Parzival session decision to AI Memory.

Canonical runtime for the /parzival-save-decision skill. This script is intended
to be executed through scripts/memory/run-with-env.sh so it always uses the
ai-memory virtualenv plus the expected local service defaults.

TD-519 (F-002): closes the long-standing gap where decisions were canonical-stored
in `oversight/tracking/decision-log.md` but never made it into Qdrant. Bootstrap
L2 retrieval (`memory_type=["decision"]`) was permanently empty as a result. Per
locked design D-1..D-7 in TECH-DEBT-519, decisions emit at session closeout via
per-DEC invocation of this script, mirroring /parzival-save-handoff and
/parzival-save-insight precedents.

Storage contract: WHOLE, 1 vector, no chunking, no thresholds, no truncation
(Chunking-Strategy-V2 §3.3 + §7). Per-DEC SHA-256 content_hash dedup makes
re-emit idempotent — see deduplication.py compute_content_hash.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

# Strips a leading ``DEC-XXX-D#:`` prefix from the first line of a DEC body
# when computing decision_summary. Case-insensitive; tolerates underscores
# in the ID for any hypothetical legacy DEC IDs that include them. Non-DEC
# content (e.g., URLs containing colons, prose with leading qualifiers) is
# left intact — the regex only matches the DEC-prefix shape, not any
# colon-prefix shape.
_DEC_PREFIX_RE = re.compile(r"^DEC-[A-Z0-9_-]+:\s*", re.IGNORECASE)

INSTALL_DIR = os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.metrics_push import push_skill_metrics_async
from memory.storage import MemoryStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save Parzival decision to Qdrant")
    parser.add_argument(
        "--dec-id",
        required=True,
        help="Decision ID, e.g., PM285-D1",
    )
    parser.add_argument(
        "--content",
        required=True,
        help="Full DEC body (Decision + Rationale)",
    )
    parser.add_argument(
        "--rationale",
        required=False,
        default=None,
        help="Optional separate rationale text (preserved in metadata)",
    )
    parser.add_argument(
        "--session-id",
        required=False,
        default=None,
        help="Session ID; auto-detected from CLAUDE_SESSION_ID env when omitted",
    )
    parser.add_argument(
        "--pm-number",
        required=False,
        type=int,
        default=None,
        help="PM number, e.g., 285",
    )
    return parser.parse_args()


def main() -> int:
    start_time = time.perf_counter()
    config = get_config()

    if not config.parzival_enabled:
        print("Parzival is not enabled. Set PARZIVAL_ENABLED=true in .env.")
        return 0

    args = parse_args()

    session_id = args.session_id or os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # First line of the DEC body acts as a quick-scan summary; cap defensively.
    # Strip leading "DEC-XXX-D#:" prefix WHEN PRESENT — the dec_id payload
    # field already carries the ID, so the summary stores the meaningful
    # suffix only. The regex matches only the DEC-prefix shape, leaving
    # multi-colon legitimate content (URLs, prose qualifiers like "Decision:"
    # or "Important note:") intact.
    first_line = args.content.split("\n")[0]
    decision_summary = _DEC_PREFIX_RE.sub("", first_line).strip()[:200]

    metadata = {
        "dec_id": args.dec_id,
        "pm_number": args.pm_number,
        "decision_summary": decision_summary,
        "rationale_text": args.rationale,
    }

    storage = MemoryStorage(config)
    try:
        result = storage.store_agent_memory(
            content=args.content,
            memory_type="decision",
            agent_id="parzival",
            session_id=session_id,
            cwd=os.getcwd(),
            metadata=metadata,
        )
    except Exception as exc:
        # Mirror handoff precedent: closeout continues — file write is the
        # primary record. NEVER crash session-close on a per-DEC failure.
        print(f"Warning: Failed to save decision {args.dec_id} to Qdrant: {exc}")
        print("Closeout continues — decision-log.md is the primary record.")
        push_skill_metrics_async(
            "parzival-save-decision", "error", time.perf_counter() - start_time
        )
        return 0

    status = result.get("status", "unknown")
    if status == "stored":
        print(
            f"Decision {args.dec_id} saved to Qdrant "
            f"(id: {result.get('memory_id', 'unknown')[:8]}...)"
        )
    elif status == "duplicate":
        print(
            f"Decision {args.dec_id} already exists in Qdrant (duplicate detected)."
        )
    else:
        print(f"Decision {args.dec_id} storage result: {status}")

    metric_status = "success" if status in ("stored", "duplicate") else "error"
    push_skill_metrics_async(
        "parzival-save-decision", metric_status, time.perf_counter() - start_time
    )

    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": "Skill: parzival-save-decision"[:10000],
                "output": f"Result: {status}"[:10000],
                "metadata": {
                    "skill_name": "parzival-save-decision",
                    "dec_id": args.dec_id,
                    "pm_number": args.pm_number,
                },
            },
            session_id=session_id,
            tags=["skill", "decision"],
        )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
