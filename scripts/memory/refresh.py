#!/usr/bin/env python3
# scripts/memory/refresh.py
"""Memory refresh skill: /aim-refresh

Externalizes the inline Python program from aim-refresh/SKILL.md.
Manually re-evaluates freshness for code-patterns memories. Reuses the
freshness scan pipeline from SPEC-013 with optional scope filters.

Usage:
    run-with-env.sh refresh.py                          # Scan all
    run-with-env.sh refresh.py --topic "authentication" # Semantic filter (v2.1)
    run-with-env.sh refresh.py my-project               # Limit to project
"""

from __future__ import annotations

import argparse
import os
import sys
import time

_INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(_INSTALL_DIR, "src"))

from memory.config import get_config
from memory.freshness import run_freshness_scan
from memory.metrics_push import push_skill_metrics_async


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh memory freshness")
    parser.add_argument("project", nargs="?", help="Project group_id filter")
    parser.add_argument("--topic", help="Semantic topic filter (future)")
    args = parser.parse_args()

    start_time = time.perf_counter()
    config = get_config()

    if not config.freshness_enabled:
        print("Freshness detection is disabled. Set FRESHNESS_ENABLED=true to enable.")
        return 0

    if not config.github_sync_enabled:
        print(
            "Warning: GitHub sync is not enabled. Freshness scan will "
            "use existing ground truth data if available."
        )

    if args.topic:
        print(
            f"Note: Topic-based refresh (--topic '{args.topic}') is a "
            f"v2.1 feature. Running full scan with project filter instead."
        )

    # Run freshness scan with scope filters
    report = run_freshness_scan(
        config=config,
        group_id=args.project,
        cwd=os.getcwd(),
    )

    if report.total_checked == 0:
        print("No code-patterns memories with file_path found.")
        push_skill_metrics_async(
            "memory-refresh", "empty", time.perf_counter() - start_time
        )
        return 0

    print("## Memory Refresh Complete")
    print("")
    print(
        f"Scanned **{report.total_checked}** memories in {report.duration_seconds:.1f}s"
    )
    print("")
    print("| Tier | Count |")
    print("|------|-------|")
    print(f"| Fresh | {report.fresh_count} |")
    print(f"| Aging | {report.aging_count} |")
    print(f"| Stale | {report.stale_count} |")
    print(f"| Expired | {report.expired_count} |")
    print(f"| Unknown | {report.unknown_count} |")

    actionable = report.stale_count + report.expired_count
    if actionable > 0:
        print("")
        print(
            f"**{actionable} memories need attention.** Run `/aim-freshness-report` for details."
        )
    else:
        print("")
        print("All memories are fresh. No action needed.")

    push_skill_metrics_async(
        "memory-refresh", "success", time.perf_counter() - start_time
    )

    # Skill tracing (PLAN-014 G-06)
    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": "Skill: aim-refresh"[:10000],
                "output": "Result: completed"[:10000],
                "metadata": {"skill_name": "aim-refresh"},
            },
            session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            tags=["skill"],
        )
    except Exception:
        pass  # Tracing failures never break skill execution

    return 0


if __name__ == "__main__":
    sys.exit(main())
