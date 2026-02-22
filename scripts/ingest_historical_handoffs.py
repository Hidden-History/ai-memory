#!/usr/bin/env python3
"""Ingest historical SESSION_HANDOFF_*.md files into Qdrant agent memory.

One-time ingestion of existing oversight/session-logs/SESSION_HANDOFF_*.md files
into Qdrant as agent_handoff memories. Gives Parzival access to 57+ session
histories via semantic search.

Script is idempotent — duplicate detection via content_hash prevents re-ingestion
on subsequent runs.

Usage:
    python scripts/ingest_historical_handoffs.py
    python scripts/ingest_historical_handoffs.py --dry-run
    python scripts/ingest_historical_handoffs.py --oversight-dir /path/to/oversight
    python scripts/ingest_historical_handoffs.py --group-id dev-ai-memory

Reference: SPEC-018 Release Engineering
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import get_config
from memory.storage import MemoryStorage

# ANSI color codes (match other scripts in this project)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def discover_handoffs(oversight_dir: Path) -> list[dict]:
    """Find all SESSION_HANDOFF_*.md files and extract metadata.

    Args:
        oversight_dir: Path to the oversight/ directory.

    Returns:
        List of dicts with keys: path, date, pm_number, content, filename.
        Sorted by filename (chronological order).
    """
    session_logs = oversight_dir / "session-logs"
    if not session_logs.exists():
        print(f"{YELLOW}Warning: {session_logs} not found{RESET}")
        return []

    files = sorted(session_logs.glob("SESSION_HANDOFF_*.md"))
    handoffs = []

    for f in files:
        # Extract date from filename: SESSION_HANDOFF_YYYY-MM-DD[_suffix].md
        match = re.search(r"SESSION_HANDOFF_(\d{4}-\d{2}-\d{2})", f.name)
        if match:
            date_str = match.group(1)
        else:
            date_str = None
            print(f"  {YELLOW}Warning: Could not parse date from {f.name}{RESET}")

        content = f.read_text(encoding="utf-8")

        # Extract PM number from content header (first 500 chars)
        pm_match = re.search(r"\*\*Session\*\*:\s*PM\s*#(\d+)", content[:500])
        pm_number = int(pm_match.group(1)) if pm_match else None

        handoffs.append(
            {
                "path": f,
                "date": date_str,
                "pm_number": pm_number,
                "content": content,
                "filename": f.name,
            }
        )

    return handoffs


def ingest_handoffs(
    handoffs: list[dict],
    group_id: str,
    dry_run: bool = False,
) -> dict:
    """Store handoff files into Qdrant via store_agent_memory().

    Args:
        handoffs: List of handoff dicts from discover_handoffs().
        group_id: Project group ID for Qdrant payload filtering.
        dry_run: If True, print what would be stored without storing.

    Returns:
        Stats dict with keys: total, stored, skipped, errors.
    """
    stats = {"total": len(handoffs), "stored": 0, "skipped": 0, "errors": 0}

    if dry_run:
        for h in handoffs:
            pm_label = f" (PM #{h['pm_number']})" if h["pm_number"] else ""
            date_label = f" [{h['date']}]" if h["date"] else ""
            print(
                f"  DRY RUN: Would ingest {h['filename']}"
                f"{date_label}{pm_label}"
                f" ({len(h['content'])} chars)"
            )
            stats["stored"] += 1
        return stats

    config = get_config()
    storage = MemoryStorage(config)

    for h in handoffs:
        try:
            # Build metadata, filtering out None values
            raw_metadata = {
                "stored_at": f"{h['date']}T12:00:00Z" if h["date"] else None,
                "source_file": str(h["path"]),
                "session_date": h["date"],
                "pm_number": h.get("pm_number") or h["pm_number"],
            }
            metadata = {k: v for k, v in raw_metadata.items() if v is not None}
            result = storage.store_agent_memory(
                content=h["content"],
                memory_type="agent_handoff",
                agent_id="parzival",
                group_id=group_id,
                metadata=metadata,
            )

            status = result.get("status", "unknown")

            if status == "stored":
                stats["stored"] += 1
                pm_label = f" (PM #{h['pm_number']})" if h["pm_number"] else ""
                print(f"  {GREEN}Stored:{RESET} {h['filename']}{pm_label}")
            elif status == "duplicate":
                stats["skipped"] += 1
                print(f"  {YELLOW}Skipped (duplicate):{RESET} {h['filename']}")
            else:
                stats["errors"] += 1
                print(f"  {YELLOW}Warning:{RESET} {h['filename']} → {status}")

        except Exception as e:
            stats["errors"] += 1
            print(f"  {RED}Error:{RESET} {h['filename']} → {e}")

    return stats


def main():
    """Main entry point for historical handoff ingestion."""
    parser = argparse.ArgumentParser(
        description="Ingest historical SESSION_HANDOFF_*.md files into Qdrant"
    )
    parser.add_argument(
        "--oversight-dir",
        type=Path,
        default=None,
        help=(
            "Path to oversight/ directory "
            "(default: $AI_MEMORY_PROJECT_DIR/oversight or ./oversight)"
        ),
    )
    parser.add_argument(
        "--group-id",
        default=None,
        help="Project group_id (default: basename of current working directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be ingested without storing anything",
    )
    args = parser.parse_args()

    # Resolve oversight directory
    oversight_dir = args.oversight_dir
    if oversight_dir is None:
        project_dir = os.environ.get("AI_MEMORY_PROJECT_DIR", os.getcwd())
        oversight_dir = Path(project_dir) / "oversight"

    # Resolve group_id
    group_id = args.group_id or Path(os.getcwd()).name

    print(f"Oversight dir: {oversight_dir}")
    print(f"Group ID:      {group_id}")
    if args.dry_run:
        print(f"{YELLOW}Mode: DRY RUN (nothing will be stored){RESET}")
    print()

    # Discover handoff files
    handoffs = discover_handoffs(oversight_dir)
    print(f"Found {len(handoffs)} handoff file(s)")

    if not handoffs:
        print("Nothing to ingest.")
        return

    print()

    # Ingest
    stats = ingest_handoffs(handoffs, group_id, dry_run=args.dry_run)

    # Summary
    print(f"\n{'DRY RUN ' if args.dry_run else ''}Ingestion complete:")
    print(f"  Total:   {stats['total']}")
    print(f"  {GREEN}Stored:  {stats['stored']}{RESET}")
    print(f"  {YELLOW}Skipped: {stats['skipped']} (duplicates){RESET}")
    if stats["errors"]:
        print(f"  {RED}Errors:  {stats['errors']}{RESET}")
    else:
        print(f"  Errors:  {stats['errors']}")

    if args.dry_run:
        print(f"\n{YELLOW}Re-run without --dry-run to store.{RESET}")


if __name__ == "__main__":
    main()
