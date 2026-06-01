#!/usr/bin/env python3
# scripts/memory/freshness_report.py
"""Freshness report: scan code-patterns for stale memories against GitHub data.

Externalizes the inline Python block from aim-freshness-report SKILL.md.
Behavior-preserving: same args, output, and exit-code semantics as inline.

Usage:
    scripts/memory/run-with-env.sh freshness_report.py             # Scan all projects
    scripts/memory/run-with-env.sh freshness_report.py my-project  # Scan specific project
"""

from __future__ import annotations

import argparse
import os
import sys
import time

_install_dir = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(_install_dir, "src"))

from memory.config import get_config
from memory.freshness import FreshnessReport, FreshnessTier, run_freshness_scan
from memory.metrics_push import push_skill_metrics_async


def format_freshness_report(report: FreshnessReport) -> str:
    """Format FreshnessReport as markdown table for skill output."""
    lines: list[str] = []

    # Header
    lines.append("## Freshness Report")
    lines.append("")
    lines.append(
        f"Scanned **{report.total_checked}** code-patterns memories "
        f"in {report.duration_seconds:.1f}s"
    )
    lines.append("")

    # Summary counts
    lines.append("### Summary")
    lines.append("")
    lines.append("| Tier | Count | Description |")
    lines.append("|------|-------|-------------|")
    lines.append(
        f"| Fresh | {report.fresh_count} | " f"Content matches, low commit activity |"
    )
    lines.append(
        f"| Aging | {report.aging_count} | " f"Some commit activity since stored |"
    )
    lines.append(
        f"| Stale | {report.stale_count} | "
        f"Significant commit activity since stored |"
    )
    lines.append(
        f"| Expired | {report.expired_count} | "
        f"High commit activity or content changed |"
    )
    lines.append(
        f"| Unknown | {report.unknown_count} | " f"No GitHub code blob data available |"
    )

    # Detailed results (non-fresh only)
    actionable = [
        r
        for r in report.results
        if r.status not in (FreshnessTier.FRESH, FreshnessTier.UNKNOWN)
    ]
    if actionable:
        # Sort: expired first, then stale, then aging
        tier_order = {
            FreshnessTier.EXPIRED: 0,
            FreshnessTier.STALE: 1,
            FreshnessTier.AGING: 2,
        }
        actionable.sort(key=lambda r: tier_order.get(r.status, 99))

        lines.append("")
        lines.append("### Actionable Memories")
        lines.append("")
        lines.append("| File | Type | Status | Commits | Reason |")
        lines.append("|------|------|--------|---------|--------|")
        for r in actionable:
            lines.append(
                f"| `{r.file_path}` | {r.memory_type} | "
                f"**{r.status}** | {r.commit_count} | {r.reason} |"
            )

    # Recommended actions
    lines.append("")
    lines.append("### Recommended Actions")
    lines.append("")
    if report.expired_count > 0:
        lines.append(
            f"- **{report.expired_count} expired**: Source files have "
            f"changed. Consider re-capturing these patterns with "
            f"`/aim-save` or wait for automatic recapture on next "
            f"code interaction."
        )
    if report.stale_count > 0:
        lines.append(
            f"- **{report.stale_count} stale**: Significant commit "
            f"activity. Review these memories for accuracy."
        )
    if report.aging_count > 0:
        lines.append(
            f"- **{report.aging_count} aging**: Some activity. "
            f"Monitor but no action needed yet."
        )
    if report.expired_count == 0 and report.stale_count == 0:
        lines.append("- All memories are fresh or aging. No action needed.")

    if report.unknown_count > 0:
        lines.append(
            f"- **{report.unknown_count} unknown**: No GitHub code "
            f"blob data. Ensure GitHub sync is enabled and has "
            f"completed at least one full sync."
        )

    return "\n".join(lines)


def main() -> int:
    """Entry point for freshness report script."""
    parser = argparse.ArgumentParser(
        description="Scan code-patterns for stale memories against GitHub data",
    )
    parser.add_argument(
        "group_id",
        nargs="?",
        default=None,
        metavar="GROUP_ID",
        help="Project group ID to scan (default: all projects)",
    )
    args = parser.parse_args()

    start_time = time.perf_counter()
    config = get_config()

    if not config.freshness_enabled:
        print(
            "Freshness detection is disabled. " "Set FRESHNESS_ENABLED=true to enable."
        )
        return 0

    if not config.github_sync_enabled:
        print(
            "GitHub sync is not enabled. Freshness detection requires "
            "GitHub code blob data. Set GITHUB_SYNC_ENABLED=true and "
            "configure GITHUB_TOKEN and GITHUB_REPO."
        )
        return 0

    report = run_freshness_scan(config=config, group_id=args.group_id, cwd=os.getcwd())

    if report.total_checked == 0:
        print(
            "No code-patterns memories with file_path found. "
            "Ensure GitHub sync has completed and code-patterns "
            "contain file_path metadata."
        )
        return 0

    output = format_freshness_report(report)
    print(output)

    # Push skill metrics
    duration = time.perf_counter() - start_time
    status = "success" if report.total_checked > 0 else "empty"
    push_skill_metrics_async("freshness-report", status, duration)

    # Skill tracing (PLAN-014 G-06)
    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data={
                "input": "Skill: aim-freshness-report"[:10000],
                "output": "Result: completed"[:10000],
                "metadata": {"skill_name": "aim-freshness-report"},
            },
            session_id=os.environ.get("CLAUDE_SESSION_ID", "unknown"),
            tags=["skill"],
        )
    except Exception:
        pass  # Tracing failures never break skill execution

    return 0


if __name__ == "__main__":
    sys.exit(main())
