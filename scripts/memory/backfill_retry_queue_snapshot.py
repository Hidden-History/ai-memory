#!/usr/bin/env python3
"""Backfill preserved retry-queue snapshot entries under their persisted scope.

One-off migration for the PM #386 snapshot (BUG-521 / BUG-522). Re-stores each
recoverable entry from the preserved ``pending_queue.jsonl`` / ``retry_queue_dlq.jsonl``
through the SAME fixed drain path (``process_retry_queue.process_entry``) so the
result is identical to what the fixed daemon would produce.

Scope resolution (BP-180):
- Entries that already carry a persisted ``group_id`` are re-stored under it,
  untouched.
- Legacy ``hook_input`` entries (captured before the persist fix) carry only a
  ``cwd``. This backfill re-derives their ``group_id`` from that persisted cwd
  ONCE, OFFLINE, and stamps it onto the entry before draining. This deliberate,
  reviewable, one-time re-derivation is the BP-180 legacy carve-out — it is NOT
  the drain-time cwd re-resolution BUG-522 forbids (the daemon never does this).
- Entries with neither a persisted group_id nor a resolvable cwd, and non-memory
  records (e.g. raw command/output dicts in the DLQ), are reported as skipped —
  never stored under a catch-all.

SAFETY (W-02): the default is ``--dry-run`` (no Qdrant writes). Storing for real
requires the explicit ``--execute`` flag, which is a Will-gated database write and
MUST NOT be run without his go-ahead. Dry-run prints exactly what would be stored,
per group, with zero Qdrant calls.

Usage:
    # Dry run (default, safe): show what WOULD be re-stored, per group
    python scripts/memory/backfill_retry_queue_snapshot.py --snapshot-dir <dir>

    # Execute (W-02 — requires Will's go-ahead; do NOT run otherwise)
    python scripts/memory/backfill_retry_queue_snapshot.py --snapshot-dir <dir> --execute

Reference: BP-180, BUG-521, BUG-522, PM #386.
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

# Setup Python path (mirrors process_retry_queue.py)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from process_retry_queue import process_entry  # noqa: E402

_SNAPSHOT_FILES = ("pending_queue.jsonl", "retry_queue_dlq.jsonl")


def _stamp_legacy_scope(entry: dict) -> tuple[dict, str | None]:
    """Ensure *entry*'s memory_data carries a persisted group_id + source_hook.

    Returns (entry, reason_skipped). reason_skipped is None when the entry is
    ready to drain; otherwise a short human-readable reason.

    For legacy ``hook_input`` entries that lack a persisted group_id, resolves it
    ONCE offline from the persisted cwd (BP-180 legacy carve-out). Entries that
    are not a recognised memory record, or whose scope cannot be resolved, are
    left for the caller to report as skipped.
    """
    memory_data = entry.get("memory_data", {})
    if not isinstance(memory_data, dict):
        return entry, "non-memory record (memory_data is not a dict)"

    # Legacy hook_input: re-derive group_id from the persisted cwd, offline.
    if "hook_input" in memory_data and not memory_data.get("group_id"):
        from memory.project import resolve_project_id

        hook_input = memory_data["hook_input"]
        cwd = hook_input.get("cwd")
        if not cwd:
            return entry, "hook_input entry has no cwd to resolve scope from"
        try:
            group_id = resolve_project_id(cwd)
        except ValueError as exc:
            return entry, f"cwd '{cwd}' not resolvable offline ({exc})"
        # Stamp resolved scope + provenance so the fixed drain path reads them.
        memory_data["group_id"] = group_id
        memory_data.setdefault(
            "source_hook", hook_input.get("hook_event_name") or "PostToolUse"
        )
        memory_data.setdefault("session_id", hook_input.get("session_id", "manual"))
        return entry, None

    # Direct/content or hook_input entry that already carries a persisted
    # group_id but is missing a valid source_hook (the BUG-521 legacy defect).
    # BP-180 legacy carve-out: backfill a VALID 'manual' source_hook (never the
    # invalid 'retry') — and only for entries whose group_id is present.
    if memory_data.get("group_id"):
        if not memory_data.get("source_hook"):
            memory_data["source_hook"] = "manual"
        return entry, None

    # Payload-wrapper with a persisted group_id in its metadata.
    if "payload" in memory_data:
        meta = memory_data["payload"].get("metadata", {})
        if meta.get("group_id"):
            if not meta.get("source_hook"):
                meta["source_hook"] = "manual"
            return entry, None
        return entry, "payload entry has no persisted group_id in metadata"

    return entry, "not a recognised memory record (no group_id / hook_input / payload)"


def backfill(snapshot_dir: Path, dry_run: bool, limit: int | None) -> dict:
    """Backfill snapshot entries. Returns a stats dict."""
    # storage is only constructed for a real execute; dry-run makes no Qdrant calls.
    storage = None
    if not dry_run:
        from memory.storage import MemoryStorage

        storage = MemoryStorage()

    stats = {
        "read": 0,
        "stored": 0,
        "duplicate": 0,
        "filtered": 0,
        "skipped": 0,
        "failed": 0,
        "by_group": Counter(),
        "skip_reasons": Counter(),
    }

    processed = 0
    for filename in _SNAPSHOT_FILES:
        path = snapshot_dir / filename
        if not path.exists():
            print(f"  (snapshot file not found, skipping: {path})")
            continue

        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if limit is not None and processed >= limit:
                    break
                stats["read"] += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    stats["skipped"] += 1
                    stats["skip_reasons"]["corrupt JSON line"] += 1
                    continue

                entry, skip_reason = _stamp_legacy_scope(entry)
                if skip_reason is not None:
                    stats["skipped"] += 1
                    stats["skip_reasons"][skip_reason] += 1
                    continue

                processed += 1
                group_id = entry["memory_data"].get("group_id") or (
                    entry["memory_data"]
                    .get("payload", {})
                    .get("metadata", {})
                    .get("group_id")
                )
                success, message = process_entry(entry, storage, dry_run=dry_run)
                if success:
                    lowered = message.lower()
                    if lowered.startswith("filtered") or "skipping" in lowered:
                        stats["filtered"] += 1
                    elif "duplicate" in lowered:
                        stats["duplicate"] += 1
                    else:
                        stats["stored"] += 1
                        stats["by_group"][group_id] += 1
                    print(f"  [{group_id}] {message}")
                else:
                    stats["failed"] += 1
                    stats["skip_reasons"][message] += 1
                    print(f"  [SKIP {group_id}] {message}")

    return stats


def main() -> int:
    default_snapshot = (
        "/mnt/e/projects/dev-ai-memory/oversight/tasks/pm386-lane-c/"
        "queue-snapshot-2026-07-09"
    )
    parser = argparse.ArgumentParser(
        description="Backfill preserved retry-queue snapshot entries (BUG-521/522)."
    )
    parser.add_argument(
        "--snapshot-dir",
        default=default_snapshot,
        help=f"Directory holding the snapshot .jsonl files (default: {default_snapshot})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Actually store to Qdrant. W-02: a Will-gated database write — do NOT "
            "run without his explicit go-ahead. Omit for a safe dry run (default)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max recoverable entries to process (default: all)",
    )
    args = parser.parse_args()

    dry_run = not args.execute
    snapshot_dir = Path(args.snapshot_dir)

    mode = (
        "DRY RUN (no Qdrant writes)"
        if dry_run
        else "EXECUTE (W-02 — writing to Qdrant)"
    )
    print(f"Retry-queue snapshot backfill — {mode}")
    print(f"Snapshot dir: {snapshot_dir}\n")

    if not snapshot_dir.exists():
        print(f"ERROR: snapshot dir does not exist: {snapshot_dir}")
        return 1

    stats = backfill(snapshot_dir, dry_run=dry_run, limit=args.limit)

    print("\nSummary:")
    print(f"  Entries read:        {stats['read']}")
    verb = "Would store" if dry_run else "Stored"
    print(f"  {verb}:         {stats['stored']}")
    print(f"  Duplicate (skip):    {stats['duplicate']}")
    print(f"  Filtered (live-path parity): {stats['filtered']}")
    print(f"  Skipped (unrecoverable):     {stats['skipped']}")
    print(f"  Failed:              {stats['failed']}")

    if stats["by_group"]:
        print(f"\n  {verb} by group:")
        for group, count in sorted(stats["by_group"].items()):
            print(f"    {group}: {count}")

    if stats["skip_reasons"]:
        print("\n  Skip/failure reasons:")
        for reason, count in stats["skip_reasons"].most_common():
            print(f"    {count}x {reason}")

    if dry_run:
        print(
            "\nDry run complete — nothing was written. To execute (W-02, "
            "Will-gated), re-run with --execute."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
