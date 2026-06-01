#!/usr/bin/env python3
# scripts/memory/github_sync_runner.py
"""GitHub sync runner: /aim-github-sync (full/incremental modes).

Externalizes the inline Python block from aim-github-sync/SKILL.md.
Behavior-preserving: identical stdout and exit semantics as the inline form.

Usage (via run-with-env.sh):
    run-with-env.sh github_sync_runner.py               # incremental (default)
    run-with-env.sh github_sync_runner.py --full        # full sync
    run-with-env.sh github_sync_runner.py --incremental # incremental sync

Exit codes:
  0 — sync completed
  1 — bad args
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

_install_dir = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(_install_dir, "src"))

from memory.connectors.github.sync import GitHubSyncEngine  # noqa: E402


def main() -> int:
    """Entry point for /aim-github-sync skill (full/incremental modes)."""
    parser = argparse.ArgumentParser(description="GitHub sync runner")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--full", action="store_true", help="Full sync (all data)")
    mode_group.add_argument(
        "--incremental", action="store_true", help="Incremental sync (default)"
    )

    args = parser.parse_args()
    mode = "full" if args.full else "incremental"

    engine = GitHubSyncEngine()
    result = asyncio.run(engine.sync(mode=mode))
    print(
        f"Synced {result.total_synced} items "
        f"({result.items_skipped} skipped, {result.errors} errors) "
        f"in {result.duration_seconds:.1f}s"
    )
    d = result.to_dict()
    for k, v in d.items():
        if v and k != "total_synced":
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
