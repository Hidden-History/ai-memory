---
name: parzival-save-decision
description: "Save a Parzival session decision to Qdrant for cross-session memory and L2 retrieval"
allowed-tools: Bash
---

```python
"""Save Parzival decision to Qdrant: /parzival-save-decision

Called by parzival-closeout step-04 once per DEC entry logged in this session's
PMxxx-D# block in decision-log.md. Stores the decision content to Qdrant
discussions collection with type=decision, agent_id=parzival.

Closes the TD-519 / F-002 gap: bootstrap L2 retrieval
(memory_type=["decision"]) was permanently empty because decisions were
canonical-stored in decision-log.md but never emitted to Qdrant.

Storage contract: WHOLE, 1 vector, no chunking, no thresholds, no truncation
(Chunking-Strategy-V2 §3.3 + §7). Per-DEC SHA-256 content_hash dedup makes
re-emit idempotent.

Usage:
    /parzival-save-decision --dec-id PM285-D2 --content "Decision: ..." --pm-number 285
    /parzival-save-decision --dec-id PM285-D3 --content "..." --rationale "..." --pm-number 285
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

_install_dir = os.path.expanduser("~/.ai-memory")
sys.path.insert(0, os.path.join(_install_dir, "src"))

from memory.config import get_config
from memory.storage import MemoryStorage
from memory.metrics_push import push_skill_metrics_async

# Strips a leading "DEC-XXX-D#:" prefix from the first line of a DEC body
# when computing decision_summary. Case-insensitive; matches only the
# DEC-prefix shape so URLs and prose qualifiers stay intact.
_DEC_PREFIX_RE = re.compile(r"^DEC-[A-Z0-9_-]+:\s*", re.IGNORECASE)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save Parzival decision to Qdrant")
    parser.add_argument("--dec-id", required=True, help="Decision ID, e.g., PM285-D1")
    parser.add_argument("--content", required=True, help="Full DEC body (Decision + Rationale)")
    parser.add_argument("--rationale", required=False, default=None, help="Optional separate rationale text")
    parser.add_argument("--session-id", required=False, default=None, help="Auto-detected from CLAUDE_SESSION_ID env when omitted")
    parser.add_argument("--pm-number", required=False, type=int, default=None, help="PM number, e.g., 285")
    return parser.parse_args()


def main():
    start_time = time.perf_counter()
    config = get_config()

    if not config.parzival_enabled:
        print("Parzival is not enabled. Set PARZIVAL_ENABLED=true in .env.")
        return

    args = _parse_args()
    session_id = args.session_id or os.environ.get("CLAUDE_SESSION_ID", "unknown")
    # Strip leading "DEC-XXX-D#:" prefix WHEN PRESENT; dec_id payload field
    # already carries the ID. Regex matches only the DEC-prefix shape,
    # leaving multi-colon legitimate content intact.
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
    except Exception as e:
        print(f"Warning: Failed to save decision {args.dec_id} to Qdrant: {e}")
        print("Closeout continues — decision-log.md is the primary record.")
        push_skill_metrics_async("parzival-save-decision", "error", time.perf_counter() - start_time)
        return

    status = result.get("status", "unknown")
    if status == "stored":
        print(f"Decision {args.dec_id} saved to Qdrant (id: {result.get('memory_id', 'unknown')[:8]}...)")
    elif status == "duplicate":
        print(f"Decision {args.dec_id} already exists in Qdrant (duplicate detected).")
    else:
        print(f"Decision {args.dec_id} storage result: {status}")

    metric_status = "success" if status in ("stored", "duplicate") else "error"
    push_skill_metrics_async("parzival-save-decision", metric_status, time.perf_counter() - start_time)

    # Skill tracing (PLAN-014 G-06)
    try:
        from memory.trace_buffer import emit_trace_event
        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": f"Skill: parzival-save-decision"[:10000],
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
        pass  # Tracing failures never break skill execution


if __name__ == "__main__":
    main()
```
