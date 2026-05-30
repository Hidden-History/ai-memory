#!/usr/bin/env python3
"""Save a Parzival insight to AI Memory.

Canonical runtime for the /parzival-save-insight skill. This script is intended
to be executed through scripts/memory/run-with-env.sh so it always uses the
ai-memory virtualenv plus the expected local service defaults.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.metrics_push import push_skill_metrics_async
from memory.storage import MemoryStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save Parzival insight to Qdrant")
    parser.add_argument("insight", nargs="+", help="Insight text to store")
    return parser.parse_args()


def main() -> int:
    start_time = time.perf_counter()
    config = get_config()

    if not config.parzival_enabled:
        print("Parzival is not enabled. Set PARZIVAL_ENABLED=true in .env.")
        return 1

    args = parse_args()
    insight = " ".join(args.insight).strip()

    # PLAN-028 P1B / W-09 (DEC-PM302-D1): store_agent_memory requires explicit
    # group_id. BUG-314: resolve through the one shared resolver (env-first ->
    # cwd/git -> fail-loud); on detection failure print friendly error.
    from memory.project import resolve_project_id

    try:
        group_id = resolve_project_id(os.getcwd())
    except ValueError as _proj_e:
        print(f"Failed to resolve project scope: {_proj_e}")
        print("Set AI_MEMORY_PROJECT_ID and rerun.")
        push_skill_metrics_async(
            "parzival-save-insight", "error", time.perf_counter() - start_time
        )
        return 1

    storage = MemoryStorage(config)
    try:
        result = storage.store_agent_memory(
            content=insight,
            memory_type="agent_insight",
            agent_id="parzival",
            cwd=os.getcwd(),
            group_id=group_id,
        )
    except Exception as exc:
        print(f"Failed to save insight: {exc}")
        push_skill_metrics_async(
            "parzival-save-insight", "error", time.perf_counter() - start_time
        )
        return 1

    status = result.get("status", "unknown")
    if status == "stored":
        print(
            f"Insight saved to Qdrant (id: {result.get('memory_id', 'unknown')[:8]}...)"
        )
    elif status == "duplicate":
        print("Insight already exists in Qdrant (duplicate detected).")
    else:
        print(f"Insight storage result: {status}")

    metric_status = "success" if status in ("stored", "duplicate") else "error"
    push_skill_metrics_async(
        "parzival-save-insight", metric_status, time.perf_counter() - start_time
    )

    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": "Skill: parzival-save-insight"[:10000],
                "output": "Result: completed"[:10000],
                "metadata": {"skill_name": "parzival-save-insight"},
            },
            session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            tags=["skill"],
        )
    except Exception:
        pass

    return 0 if status in ("stored", "duplicate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
