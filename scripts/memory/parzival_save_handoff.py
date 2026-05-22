#!/usr/bin/env python3
"""Save a Parzival handoff to AI Memory.

Canonical runtime for the /parzival-save-handoff skill. This script is intended
to be executed through scripts/memory/run-with-env.sh so it always uses the
ai-memory virtualenv plus the expected local service defaults.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
from memory.metrics_push import push_skill_metrics_async
from memory.storage import MemoryStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save Parzival handoff to Qdrant")
    parser.add_argument("content", nargs="*", help="Inline handoff content")
    parser.add_argument("--file", dest="file_path", help="Path to handoff file")
    return parser.parse_args()


def load_content(args: argparse.Namespace) -> str:
    if args.file_path:
        file_path = Path(args.file_path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            print(f"Error: File not found: {file_path}")
            raise SystemExit(1)
        return file_path.read_text(encoding="utf-8")

    content = " ".join(args.content).strip()
    if not content:
        print("Error: No content provided. Pass text or --file <path>.")
        raise SystemExit(1)
    return content


def main() -> int:
    start_time = time.perf_counter()
    config = get_config()

    if not config.parzival_enabled:
        print("Parzival is not enabled. Set PARZIVAL_ENABLED=true in .env.")
        return 0

    args = parse_args()
    content = load_content(args)

    # PLAN-028 P1B / W-09 (DEC-PM302-D1): store_agent_memory requires explicit
    # group_id. Resolve env-first; on detection failure print friendly error.
    from memory.project import detect_project as _detect_project

    group_id = os.environ.get("AI_MEMORY_PROJECT_ID") or ""
    if not group_id.strip():
        try:
            group_id = _detect_project(os.getcwd())
        except ValueError as _proj_e:
            print(f"Warning: Failed to resolve project scope: {_proj_e}")
            print("Set AI_MEMORY_PROJECT_ID and rerun. Closeout continues.")
            push_skill_metrics_async(
                "parzival-save-handoff", "error", time.perf_counter() - start_time
            )
            return 0

    storage = MemoryStorage(config)
    try:
        result = storage.store_agent_memory(
            content=content,
            memory_type="agent_handoff",
            agent_id="parzival",
            cwd=os.getcwd(),
            group_id=group_id,
        )
    except Exception as exc:
        print(f"Warning: Failed to save handoff to Qdrant: {exc}")
        print("Closeout continues — file write is the primary record.")
        push_skill_metrics_async(
            "parzival-save-handoff", "error", time.perf_counter() - start_time
        )
        return 0

    status = result.get("status", "unknown")
    if status == "stored":
        print(
            f"Handoff saved to Qdrant (id: {result.get('memory_id', 'unknown')[:8]}...)"
        )
    elif status == "duplicate":
        print("Handoff already exists in Qdrant (duplicate detected).")
    else:
        print(f"Handoff storage result: {status}")

    metric_status = "success" if status in ("stored", "duplicate") else "error"
    push_skill_metrics_async(
        "parzival-save-handoff", metric_status, time.perf_counter() - start_time
    )

    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": "Skill: parzival-save-handoff"[:10000],
                "output": "Result: completed"[:10000],
                "metadata": {"skill_name": "parzival-save-handoff"},
            },
            session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            tags=["skill"],
        )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
