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

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from memory.config import get_config
from memory.metrics_push import push_skill_metrics_async
from memory.parzival_state import disabled_message, resolve_cause
from memory.storage import MemoryStorage

from parzival_save_common import (
    bound_handoff_content,
    emit_trace,
    store_with_metrics,
)

TRACE_CONTENT_MAX = 10000  # Path A emit_trace_event content cap (V4; no other value)


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
        # D4 F-1: bound the injectable vector; the full file stays on disk.
        return bound_handoff_content(
            file_path.read_text(encoding="utf-8"), source_path=str(file_path)
        )

    content = " ".join(args.content).strip()
    if not content:
        print("Error: No content provided. Pass text or --file <path>.")
        raise SystemExit(1)
    return bound_handoff_content(content)


def main() -> int:
    start_time = time.perf_counter()
    config = get_config()

    if not config.parzival_enabled:
        print(disabled_message(resolve_cause(config)))
        return 0

    args = parse_args()
    content = load_content(args)

    # PLAN-028 P1B / W-09 (DEC-PM302-D1): store_agent_memory requires explicit
    # group_id. BUG-314: resolve through the one shared resolver (env-first ->
    # cwd/git -> fail-loud); on detection failure print friendly error.
    from memory.project import resolve_project_id

    try:
        group_id = resolve_project_id(os.getcwd())
    except ValueError as _proj_e:
        print(f"Warning: Failed to resolve project scope: {_proj_e}")
        print("Set AI_MEMORY_PROJECT_ID and rerun. Closeout continues.")
        push_skill_metrics_async(
            "parzival-save-handoff", "error", time.perf_counter() - start_time
        )
        return 0

    storage = MemoryStorage(config)
    try:
        result = store_with_metrics(
            storage=storage,
            content=content,
            memory_type="agent_handoff",
            group_id=group_id,
            agent_id="parzival",
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
        # D4 F-2: auto-supersede the prior handoff for this agent + project so
        # bootstrap injects only the newest one (read filter excludes the rest).
        storage.supersede_prior_agent_memories(
            group_id=group_id,
            agent_id="parzival",
            memory_type="agent_handoff",
            exclude_memory_id=result.get("memory_id"),
        )
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

    emit_trace(
        session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        data={
            "input": "Skill: parzival-save-handoff"[:TRACE_CONTENT_MAX],
            "output": "Result: completed"[:TRACE_CONTENT_MAX],
            "metadata": {"skill_name": "parzival-save-handoff"},
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
