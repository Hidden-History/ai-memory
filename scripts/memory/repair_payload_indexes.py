#!/usr/bin/env python3
# ruff: noqa: E402
"""Non-destructive payload-index repair (BUG-530 / PLAN-036 P4 / issue #337).

Applies the canonical payload-index set (``memory.qdrant_client.
canonical_payload_indexes``) to EXISTING Qdrant collections, for installs
already broken by the #337 defect (a collection-recreate path that silently
dropped indexes, degrading ``get_recent()``/hook retrieval with no operator
signal). Reuses ``memory.qdrant_client.ensure_payload_indexes``, which calls
``create_payload_index`` — idempotent, so this NEVER recreates, deletes, or
rewrites collection data. Mirrors the workaround GitHub issue #337's reporter
used manually (``create_payload_index`` with ``wait=True``).

Usage:
    python scripts/memory/repair_payload_indexes.py [--dry-run] [--verbose]
        [--collection NAME ...]

Exit codes:
    0 - every target collection SUCCESS (indexes confirmed present, point
        count unchanged) or, under --dry-run, every target inspected cleanly
    1 - any target collection failed: a create error propagated, canonical
        fields were still missing after the read-back poll budget, the
        read-back was inconclusive (index state unknown — never reported as
        success), the collection does not exist, or the point count moved
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import COLLECTION_JIRA_DATA, COLLECTION_NAMES, get_config
from memory.qdrant_client import (
    canonical_payload_indexes,
    ensure_payload_indexes,
    get_qdrant_client,
)

EXIT_SUCCESS = 0
EXIT_ERROR = 1

KNOWN_COLLECTIONS = [*COLLECTION_NAMES, COLLECTION_JIRA_DATA]

# The exact message ensure_payload_indexes() logs (never raises) when the
# read-back verify-GET itself could not be completed. It returns the same
# field-name list for SUCCESS and this outcome, so watching for the log
# record is the only way to tell them apart without editing the helper
# (out of scope for P4 — PLAN-036 §2a routes that to P5/TD-880 item 1).
_VERIFY_INCONCLUSIVE_MESSAGE = "payload_indexes_verify_inconclusive"

_OUTCOME_LABELS = {
    "success": "indexes ensured, canonical fields confirmed present",
    "dry_run": "would ensure indexes (dry run — no changes made)",
    "create_error": "index creation failed",
    "definitive_absent": "canonical fields still missing after the read-back "
    "poll budget — repair did NOT work",
    "transient_inconclusive": "index state unverified (read-back could not "
    "confirm) — NOT reported as success",
    "not_found": "collection does not exist",
}
_FAILURE_OUTCOMES = {
    "create_error",
    "definitive_absent",
    "transient_inconclusive",
    "not_found",
}


class _InconclusiveWatcher(logging.Handler):
    """Detects the payload_indexes_verify_inconclusive log record."""

    def __init__(self) -> None:
        super().__init__()
        self.triggered = False

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == _VERIFY_INCONCLUSIVE_MESSAGE:
            self.triggered = True


def select_collections(available: list[str], requested: list[str] | None) -> list[str]:
    """Resolve the collections to repair.

    Args:
        available: Collections that actually exist on the target Qdrant
            instance.
        requested: ``--collection`` values, or ``None``/empty for "all known
            AI Memory collections present on the instance".

    Returns:
        Collection names to repair, in a stable order.
    """
    if requested:
        return list(requested)
    known = set(KNOWN_COLLECTIONS)
    return sorted(name for name in available if name in known)


def repair_collection(client, collection_name: str, dry_run: bool) -> dict[str, object]:
    """Repair one collection's payload indexes non-destructively.

    Returns a result dict with keys: collection, outcome, point_count_before,
    point_count_after, added_fields, error.
    """
    canonical = canonical_payload_indexes(collection_name)

    try:
        before_count = client.count(collection_name, exact=True).count
    except Exception as e:
        return {
            "collection": collection_name,
            "outcome": "not_found",
            "point_count_before": None,
            "point_count_after": None,
            "added_fields": [],
            "error": str(e),
        }

    # Best-effort only: a transient failure here must NOT short-circuit the
    # repair attempt below — ensure_payload_indexes() has its own read-back
    # loop that is the actual source of truth for TRANSIENT-INCONCLUSIVE.
    try:
        live_schema = set(client.get_collection(collection_name).payload_schema or {})
        missing_before = sorted(set(canonical) - live_schema)
    except Exception:
        missing_before = []

    if dry_run:
        return {
            "collection": collection_name,
            "outcome": "dry_run",
            "point_count_before": before_count,
            "point_count_after": before_count,
            "added_fields": missing_before,
            "error": None,
        }

    watcher = _InconclusiveWatcher()
    storage_logger = logging.getLogger("ai_memory.storage")
    storage_logger.addHandler(watcher)
    try:
        ensure_payload_indexes(client, collection_name)
    except Exception as e:
        after_count = client.count(collection_name, exact=True).count
        outcome = "definitive_absent" if isinstance(e, RuntimeError) else "create_error"
        return {
            "collection": collection_name,
            "outcome": outcome,
            "point_count_before": before_count,
            "point_count_after": after_count,
            "added_fields": missing_before,
            "error": str(e),
        }
    finally:
        storage_logger.removeHandler(watcher)

    after_count = client.count(collection_name, exact=True).count
    outcome = "transient_inconclusive" if watcher.triggered else "success"
    return {
        "collection": collection_name,
        "outcome": outcome,
        "point_count_before": before_count,
        "point_count_after": after_count,
        "added_fields": missing_before,
        "error": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Non-destructively repair missing Qdrant payload indexes"
    )
    parser.add_argument(
        "--collection",
        action="append",
        dest="collections",
        help="Repair only this collection (repeatable). Default: every known "
        "AI Memory collection present on the target Qdrant instance.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be repaired without creating any index",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detail even for collections needing no repair",
    )
    return parser.parse_args()


def report_result(result: dict[str, object], verbose: bool) -> None:
    outcome = str(result["outcome"])
    marker = "✓" if outcome in ("success", "dry_run") else "✗"
    print(f"{marker} {result['collection']}: {_OUTCOME_LABELS[outcome]}")
    if outcome != "not_found":
        print(
            f"    points: {result['point_count_before']} -> "
            f"{result['point_count_after']}"
        )
    added_fields = result["added_fields"]
    if added_fields:
        print(f"    fields added: {', '.join(added_fields)}")
    elif verbose:
        print("    fields added: none (already canonical)")
    if result["error"]:
        print(f"    error: {result['error']}")


def main() -> int:
    args = parse_args()
    config = get_config()
    client = get_qdrant_client(config)

    print("=== AI Memory Payload Index Repair ===")
    if args.dry_run:
        print("[DRY RUN MODE]")

    available = {c.name for c in client.get_collections().collections}
    targets = select_collections(sorted(available), args.collections)

    if not targets:
        print("\nNo target collections found. Nothing to repair.")
        return EXIT_SUCCESS

    print(f"\nTarget collections: {', '.join(targets)}\n")

    exit_code = EXIT_SUCCESS
    for name in targets:
        result = repair_collection(client, name, args.dry_run)
        report_result(result, args.verbose)

        if result["outcome"] in _FAILURE_OUTCOMES:
            exit_code = EXIT_ERROR
        elif result["point_count_before"] != result["point_count_after"]:
            # Point-count invariant outranks the index outcome (PLAN-036 §2a):
            # non-destructive by definition, so a moved count is a hard
            # failure even when the schema looks right.
            print(
                f"    ✗ POINT COUNT CHANGED "
                f"({result['point_count_before']} -> "
                f"{result['point_count_after']}) — treating as a hard failure"
            )
            exit_code = EXIT_ERROR

    print()
    if exit_code == EXIT_SUCCESS:
        print(
            "✓ Repair complete. All target collections carry the canonical index set."
        )
    else:
        print("✗ Repair incomplete. See per-collection detail above.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
