#!/usr/bin/env python3
"""Migrate GitHub data from discussions to dedicated github collection (PLAN-010).

v2.0.9 migration script. Idempotent — safe to run multiple times.

Steps:
1. Create github collection if it does not exist (768-dim, cosine, int8 quant)
2. Migrate all github_* points from discussions → github collection
3. Purge false-positive error_fix entries from code-patterns
4. Log migration to .audit/migration-log.json

Usage:
    python scripts/migrate_v209_github_collection.py
    python scripts/migrate_v209_github_collection.py --dry-run
    python scripts/migrate_v209_github_collection.py --skip-backup
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    HnswConfigDiff,
    KeywordIndexParams,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    TextIndexParams,
    TokenizerType,
    VectorParams,
)

from memory.config import get_config
from memory.qdrant_client import get_qdrant_client

# Configuration
SCRIPT_DIR = Path(__file__).resolve().parent
INSTALL_DIR = Path.home() / ".ai-memory"
BATCH_SIZE = 100

# GitHub types to migrate from discussions → github
GITHUB_TYPES = [
    "github_code_blob",
    "github_issue",
    "github_issue_comment",
    "github_pr",
    "github_pr_diff",
    "github_pr_review",
    "github_commit",
    "github_ci_result",
    "github_release",
]

# Patterns that indicate a REAL error (not a false positive)
ERROR_INDICATORS = re.compile(
    r"(Traceback|Exception|Error:|FAILED|exit\s+code|raise\s+\w+|"
    r"errno|fatal:|panic:|segfault|core\s+dump|"
    r"permission\s+denied|command\s+not\s+found|no\s+such\s+file)",
    re.IGNORECASE,
)

# Patterns indicating error_message is CODE/CONFIG content being displayed,
# not a real runtime error. These override ERROR_INDICATORS matches.
# Example: `except Exception:` in source code is not an actual exception.
CODE_CONTENT_PATTERNS = re.compile(
    r"(^\s*except\s+\w+|"  # Python exception handler syntax
    r"\w+_(?:failed|error|failure)(?:\W|$)|"  # snake_case identifier (metric name)
    r'"(?:failed|error|failure)"|'  # Quoted string literal in code
    r'(?:Error|error):\s*""\s*$)',  # Empty error field (Last Error: "")
    re.IGNORECASE | re.MULTILINE,
)

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"


# ─── Step 1: Create github collection ───────────────────────────────────────


def create_github_collection(client, dry_run: bool) -> bool:
    """Create the github collection with proper schema if it does not exist.

    Returns:
        True if collection exists (created or already present), False on error.
    """
    if client.collection_exists("github"):
        print(
            f"  {YELLOW}!{RESET} github collection already exists (skipping creation)"
        )
        return True

    if dry_run:
        print(f"  {GRAY}[DRY RUN] Would create github collection{RESET}")
        return True

    try:
        vector_config = VectorParams(size=768, distance=Distance.COSINE)

        hnsw_config = HnswConfigDiff(
            m=16,
            ef_construct=100,
            full_scan_threshold=10000,
            on_disk=True,
        )

        quantization_config = ScalarQuantization(
            scalar=ScalarQuantizationConfig(
                type=ScalarType.INT8,
                quantile=0.99,
                always_ram=True,
            )
        )

        client.create_collection(
            collection_name="github",
            vectors_config=vector_config,
            hnsw_config=hnsw_config,
            quantization_config=quantization_config,
        )

        # Standard indexes (same as all collections)
        standard_indexes = [
            ("group_id", KeywordIndexParams(type="keyword", is_tenant=True)),
            ("type", PayloadSchemaType.KEYWORD),
            ("source_hook", PayloadSchemaType.KEYWORD),
            ("content_hash", KeywordIndexParams(type="keyword")),
            (
                "content",
                TextIndexParams(
                    type="text",
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=20,
                ),
            ),
            ("timestamp", PayloadSchemaType.DATETIME),
            ("decay_score", PayloadSchemaType.FLOAT),
            ("freshness_status", PayloadSchemaType.KEYWORD),
            ("source_authority", PayloadSchemaType.FLOAT),
            ("is_current", PayloadSchemaType.BOOL),
            ("version", PayloadSchemaType.INTEGER),
        ]

        for field_name, schema_type in standard_indexes:
            client.create_payload_index(
                collection_name="github",
                field_name=field_name,
                field_schema=schema_type,
            )

        # GitHub-specific indexes
        github_indexes = [
            ("source", KeywordIndexParams(type="keyword", is_tenant=True)),
            ("github_id", PayloadSchemaType.INTEGER),
            ("file_path", PayloadSchemaType.KEYWORD),
            ("sha", PayloadSchemaType.KEYWORD),
            ("state", PayloadSchemaType.KEYWORD),
            ("last_synced", PayloadSchemaType.DATETIME),
            ("update_batch_id", PayloadSchemaType.KEYWORD),
        ]

        for field_name, schema_type in github_indexes:
            client.create_payload_index(
                collection_name="github",
                field_name=field_name,
                field_schema=schema_type,
            )

        total_indexes = len(standard_indexes) + len(github_indexes)
        print(
            f"  {GREEN}✓{RESET} Created github collection with {total_indexes} indexes"
        )
        return True

    except Exception as e:
        print(f"  {RED}✗ Failed to create github collection: {e}{RESET}")
        return False


# ─── Step 2: Migrate GitHub data from discussions → github ──────────────────


def migrate_github_data(client, dry_run: bool) -> dict:
    """Move all github_* points from discussions to the github collection.

    Returns:
        Stats dict: scrolled, migrated, skipped, deleted.
    """
    stats = {"scrolled": 0, "migrated": 0, "skipped": 0, "deleted": 0}

    github_filter = Filter(
        must=[
            FieldCondition(
                key="type",
                match=MatchAny(any=GITHUB_TYPES),
            )
        ]
    )

    # Check if there's anything to migrate
    if not client.collection_exists("discussions"):
        print(
            f"  {YELLOW}!{RESET} discussions collection not found — skipping migration"
        )
        return stats

    # Count github points in discussions
    discussions_info = client.count(
        collection_name="discussions",
        count_filter=github_filter,
        exact=True,
    )
    source_count = discussions_info.count

    if source_count == 0:
        print(
            f"  {YELLOW}!{RESET} No github_* points in discussions — already migrated"
        )
        return stats

    print(f"  Found {source_count} github_* points in discussions to migrate")

    # Scroll all github points with vectors
    batch_points = []
    offset = None

    while True:
        scroll_kwargs = {
            "collection_name": "discussions",
            "scroll_filter": github_filter,
            "limit": BATCH_SIZE,
            "with_payload": True,
            "with_vectors": True,
        }
        if offset is not None:
            scroll_kwargs["offset"] = offset

        points, next_offset = client.scroll(**scroll_kwargs)

        if not points:
            break

        for point in points:
            stats["scrolled"] += 1

            if dry_run:
                stats["migrated"] += 1
                continue

            batch_points.append(
                PointStruct(
                    id=point.id,
                    vector=point.vector,
                    payload=point.payload,
                )
            )

            # Upsert in batches
            if len(batch_points) >= BATCH_SIZE:
                client.upsert(
                    collection_name="github",
                    points=batch_points,
                )
                stats["migrated"] += len(batch_points)
                batch_points = []

        if next_offset is None:
            break
        offset = next_offset

    # Flush remaining batch
    if batch_points and not dry_run:
        client.upsert(
            collection_name="github",
            points=batch_points,
        )
        stats["migrated"] += len(batch_points)

    # Verify count before deleting
    if not dry_run and stats["migrated"] > 0:
        github_info = client.count(
            collection_name="github",
            count_filter=github_filter,
            exact=True,
        )
        target_count = github_info.count

        if target_count < source_count:
            print(
                f"  {RED}✗ Count mismatch: source={source_count}, "
                f"target={target_count} — aborting deletion{RESET}"
            )
            return stats

        # Bulk delete from discussions
        client.delete(
            collection_name="discussions",
            points_selector=FilterSelector(filter=github_filter),
        )
        stats["deleted"] = source_count
        print(
            f"  {GREEN}✓{RESET} Migrated {stats['migrated']} points, "
            f"deleted {stats['deleted']} from discussions"
        )
    elif dry_run:
        print(
            f"  {GRAY}[DRY RUN] Would migrate {stats['migrated']} points "
            f"and delete from discussions{RESET}"
        )
    else:
        print(f"  {YELLOW}!{RESET} No points migrated — nothing to delete")

    return stats


# ─── Step 3: Purge false error_fix from code-patterns ───────────────────────


def purge_false_errors(client, dry_run: bool) -> dict:
    """Remove false-positive error_fix entries from code-patterns.

    A false positive is an error_fix point whose error_message field
    looks like a file path listing without real error indicators
    (Traceback, Exception, Error:, FAILED, etc.).

    Returns:
        Stats dict: scanned, purged, kept.
    """
    stats = {"scanned": 0, "purged": 0, "kept": 0}

    if not client.collection_exists("code-patterns"):
        print(f"  {YELLOW}!{RESET} code-patterns collection not found — skipping purge")
        return stats

    error_filter = Filter(
        must=[
            FieldCondition(
                key="type",
                match=MatchValue(value="error_fix"),
            )
        ]
    )

    # Count error_fix points
    count_result = client.count(
        collection_name="code-patterns",
        count_filter=error_filter,
        exact=True,
    )

    if count_result.count == 0:
        print(
            f"  {YELLOW}!{RESET} No error_fix points in code-patterns — nothing to purge"
        )
        return stats

    print(f"  Found {count_result.count} error_fix points to evaluate")

    false_positive_ids = []
    offset = None

    while True:
        scroll_kwargs = {
            "collection_name": "code-patterns",
            "scroll_filter": error_filter,
            "limit": BATCH_SIZE,
            "with_payload": True,
            "with_vectors": False,
        }
        if offset is not None:
            scroll_kwargs["offset"] = offset

        points, next_offset = client.scroll(**scroll_kwargs)

        if not points:
            break

        for point in points:
            stats["scanned"] += 1
            payload = point.payload or {}

            # BUG FIX: Check error_message ONLY, not content.
            # The content field always contains "Error: <msg>" as a format
            # label (from error_store_async.py line 114), which matches
            # ERROR_INDICATORS and defeats false-positive detection entirely.
            error_message = payload.get("error_message", "")
            exit_code = payload.get("exit_code")

            # Non-zero exit code is strong evidence of a real error
            if exit_code is not None and exit_code != 0:
                stats["kept"] += 1
                continue

            if _is_false_positive_error(error_message):
                false_positive_ids.append(point.id)
                stats["purged"] += 1
            else:
                stats["kept"] += 1

        if next_offset is None:
            break
        offset = next_offset

    # Delete false positives
    if false_positive_ids and not dry_run:
        # Delete in batches
        for i in range(0, len(false_positive_ids), BATCH_SIZE):
            batch = false_positive_ids[i : i + BATCH_SIZE]
            client.delete(
                collection_name="code-patterns",
                points_selector=batch,
            )
        print(
            f"  {GREEN}✓{RESET} Purged {stats['purged']} false positives, "
            f"kept {stats['kept']} real errors"
        )
    elif dry_run and false_positive_ids:
        print(
            f"  {GRAY}[DRY RUN] Would purge {stats['purged']} false positives, "
            f"keep {stats['kept']} real errors{RESET}"
        )
    else:
        print(
            f"  {GREEN}✓{RESET} No false positives found — all {stats['kept']} are real"
        )

    # After purge, rename remaining error_fix → error_pattern (BUG-200)
    # These are real error captures that have the old type name.
    # The error_store_async.py fix (line 417) now stores new captures as
    # error_pattern, but existing entries need this rename for consistency.
    rename_filter = Filter(
        must=[
            FieldCondition(
                key="type",
                match=MatchValue(value="error_fix"),
            )
        ]
    )
    rename_result = client.scroll(
        collection_name="code-patterns",
        scroll_filter=rename_filter,
        limit=1000,
        with_payload=False,
        with_vectors=False,
    )
    rename_ids = [p.id for p in rename_result[0]]
    stats["renamed"] = len(rename_ids)

    if rename_ids and not dry_run:
        for pid in rename_ids:
            client.set_payload(
                collection_name="code-patterns",
                payload={"type": "error_pattern"},
                points=[pid],
            )
        print(f"  {GREEN}✓{RESET} Renamed {len(rename_ids)} error_fix → error_pattern")
    elif dry_run and rename_ids:
        print(
            f"  {GRAY}[DRY RUN] Would rename {len(rename_ids)} "
            f"error_fix → error_pattern{RESET}"
        )
    else:
        print(f"  {GREEN}✓{RESET} No error_fix entries to rename")

    return stats


def _is_false_positive_error(text: str) -> bool:
    """Determine if error_fix error_message is a false positive.

    Logic:
    1. Empty text → false positive
    2. Matches ERROR_INDICATORS → check for code-content override → real if not code
    3. No error indicators → false positive (no evidence of a real error)

    Returns:
        True if the text is a false positive (should be deleted).
    """
    if not text or not text.strip():
        return True

    # If the text contains real error indicators, check for code-content override
    if ERROR_INDICATORS.search(text):
        # Code/config content that happens to contain error keywords
        # (e.g., "except Exception:" in source code) is not a real error
        if CODE_CONTENT_PATTERNS.search(text):
            return True
        return False

    # No error indicators at all → false positive
    return True


# ─── Step 4: Audit log ──────────────────────────────────────────────────────


def log_migration(
    migration_stats: dict,
    purge_stats: dict,
    collection_created: bool,
    duration_seconds: float,
    dry_run: bool,
) -> None:
    """Append migration entry to .audit/migration-log.json."""
    audit_dir = INSTALL_DIR / ".audit"

    if dry_run:
        print(
            f"  {GRAY}[DRY RUN] Would log migration to "
            f"{audit_dir / 'migration-log.json'}{RESET}"
        )
        return

    audit_dir.mkdir(parents=True, exist_ok=True)
    log_path = audit_dir / "migration-log.json"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "migration": "v2.0.9-github-collection",
        "plan": "PLAN-010",
        "github_collection_created": collection_created,
        "points_migrated": migration_stats.get("migrated", 0),
        "points_deleted_from_discussions": migration_stats.get("deleted", 0),
        "false_errors_purged": purge_stats.get("purged", 0),
        "real_errors_kept": purge_stats.get("kept", 0),
        "duration_seconds": round(duration_seconds, 2),
        "dry_run": dry_run,
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"  {GREEN}✓{RESET} Migration logged to {log_path}")
    except Exception as e:
        print(f"  {YELLOW}!{RESET} Could not write audit log: {e}")


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Migrate GitHub data to dedicated collection (PLAN-010, v2.0.9)",
        epilog="Exit 0: success, Exit 1: critical error",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would change without mutating any data",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip pre-migration backup (not recommended)",
    )
    args = parser.parse_args()

    start_time = time.monotonic()

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print("  PLAN-010 Migration: GitHub Collection (v2.0.9)  [DRY RUN]")
    else:
        print("  PLAN-010 Migration: GitHub Collection (v2.0.9)")
    print(f"{'=' * 60}\n")

    # Connect to Qdrant
    try:
        config = get_config()

        # Warn if shell QDRANT_API_KEY overrides .env value (common 401 cause)
        shell_key = os.environ.get("QDRANT_API_KEY")
        if shell_key:
            env_file = INSTALL_DIR / "docker" / ".env"
            dotenv_key = None
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("QDRANT_API_KEY="):
                        dotenv_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if dotenv_key and shell_key != dotenv_key:
                print(
                    f"{YELLOW}WARNING: Shell env QDRANT_API_KEY (len={len(shell_key)}) "
                    f"overrides .env value (len={len(dotenv_key)}){RESET}"
                )
                print("  pydantic-settings priority: shell env > .env file")
                print("  If you get 401 errors, fix with:")
                print("    unset QDRANT_API_KEY")
                print("  or sync to container key:")
                print(
                    '    export QDRANT_API_KEY="$(docker exec ai-memory-qdrant '
                    'env | grep QDRANT__SERVICE__API_KEY | cut -d= -f2)"'
                )
                print()

        client = get_qdrant_client(config)
    except Exception as e:
        print(f"{RED}✗ Cannot connect to Qdrant: {e}{RESET}")
        print("  Ensure Qdrant is running:")
        print("    docker compose -f docker/docker-compose.yml up -d")
        sys.exit(1)

    # Step 1: Pre-migration backup
    if not args.skip_backup and not args.dry_run:
        print("Step 1/4: Pre-migration backup")
        backup_script = SCRIPT_DIR / "backup_qdrant.py"
        if backup_script.exists():
            import subprocess

            try:
                result = subprocess.run(
                    [sys.executable, str(backup_script)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    print(f"  {GREEN}✓{RESET} Backup complete")
                else:
                    print(f"  {RED}✗ Backup failed (exit {result.returncode}){RESET}")
                    print("  Use --skip-backup to proceed without backup")
                    sys.exit(1)
            except subprocess.TimeoutExpired:
                print(f"  {RED}✗ Backup timed out{RESET}")
                sys.exit(1)
        else:
            print(f"  {YELLOW}!{RESET} backup_qdrant.py not found — skipping")
    elif args.dry_run:
        print(f"Step 1/4: {GRAY}Skipping backup (dry-run mode){RESET}")
    else:
        print(f"Step 1/4: {YELLOW}Skipping backup (--skip-backup){RESET}")

    # Step 2: Create github collection
    print("\nStep 2/4: Create github collection")
    collection_created = create_github_collection(client, args.dry_run)
    if not collection_created:
        print(f"\n{RED}✗ Failed to create github collection — aborting{RESET}")
        sys.exit(1)

    # Step 3: Migrate github data
    print("\nStep 3/4: Migrate GitHub data (discussions → github)")
    migration_stats = migrate_github_data(client, args.dry_run)

    # Step 4: Purge false errors
    print("\nStep 4/4: Purge false-positive error_fix from code-patterns")
    purge_stats = purge_false_errors(client, args.dry_run)

    # Audit log
    duration = time.monotonic() - start_time
    print("\nWriting audit log...")
    log_migration(
        migration_stats=migration_stats,
        purge_stats=purge_stats,
        collection_created=collection_created,
        duration_seconds=duration,
        dry_run=args.dry_run,
    )

    # Summary
    print(f"\n{'=' * 60}")
    if args.dry_run:
        print(f"  {YELLOW}DRY RUN complete — no data was mutated{RESET}")
    else:
        print(f"  {GREEN}✓ PLAN-010 migration complete{RESET}")
    print()
    print(f"  GitHub collection  : {'created' if collection_created else 'FAILED'}")
    print(f"  Points migrated    : {migration_stats.get('migrated', 0)}")
    print(f"  Deleted from disc. : {migration_stats.get('deleted', 0)}")
    print(f"  False errors purged: {purge_stats.get('purged', 0)}")
    print(f"  Errors renamed     : {purge_stats.get('renamed', 0)}")
    print(f"  Real errors kept   : {purge_stats.get('kept', 0)}")
    print(f"  Duration           : {duration:.1f}s")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
