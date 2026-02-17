#!/usr/bin/env python3
"""Migrate AI Memory from v2.0.5 to v2.0.6.

Implements SPEC-018 Release Engineering migration:
- Freshness bootstrap: adds decay_score, freshness_status, source_authority,
  is_current, version fields to all existing vectors
- Creates agent_id index on discussions collection
- Appends PARZIVAL_* config vars to .env
- Updates hooks via merge_settings.py
- Logs migration to .audit/migration-log.json

Usage:
    python scripts/migrate_v205_to_v206.py
    python scripts/migrate_v205_to_v206.py --dry-run
    python scripts/migrate_v205_to_v206.py --skip-backup
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client.models import KeywordIndexParams

from memory.config import get_config
from memory.qdrant_client import get_qdrant_client

# Configuration
SCRIPT_DIR = Path(__file__).resolve().parent
INSTALL_DIR = Path(
    os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
)
COLLECTIONS = ["code-patterns", "conventions", "discussions", "jira-data"]
BATCH_SIZE = 100

# Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"

# AD-5 half-life overrides (days) per memory type
TYPE_OVERRIDES = {
    "github_ci_result": 7,
    "agent_task": 14,
    "github_code_blob": 14,
    "github_commit": 14,
    "conversation": 21,
    "session_summary": 21,
    "github_issue": 30,
    "github_pr": 30,
    "jira_issue": 30,
    "agent_memory": 30,
    "guideline": 60,
    "rule": 60,
    "architecture_decision": 90,
    "agent_handoff": 180,
    "agent_insight": 180,
}
DEFAULT_HALF_LIFE = 30


# ─── Helper functions ─────────────────────────────────────────────────────────


def compute_decay_score(stored_at: str, half_life_days: int) -> float:
    """AD-5 formula: 0.5^(age_days / half_life_days)."""
    try:
        stored = datetime.fromisoformat(stored_at.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - stored).total_seconds() / 86400
        return math.pow(0.5, age_days / half_life_days)
    except (ValueError, TypeError):
        return 0.5


def get_source_authority(memory_type: str) -> float:
    """Return source authority score based on memory type."""
    human_types = {"rule", "guideline", "architecture_decision", "decision"}
    agent_types = {"agent_handoff", "agent_memory", "agent_insight", "agent_task"}
    if memory_type in human_types:
        return 1.0
    elif memory_type in agent_types:
        return 0.6
    else:
        return 0.4


# ─── Step 1: Version detection ────────────────────────────────────────────────


def detect_version(client) -> str:
    """Detect current data version by inspecting payload fields.

    Returns:
        "empty"  – collection has no points
        "v2.0.6" – freshness fields already present in ALL sampled points
        "v2.0.5" – pre-migration data (any point missing freshness fields)
    """
    points, _ = client.scroll(
        collection_name="code-patterns",
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    if not points:
        return "empty"

    # Check ALL sampled points — partial migration returns "v2.0.5"
    for point in points:
        payload = point.payload or {}
        if "decay_score" not in payload or "freshness_status" not in payload:
            return "v2.0.5"

    return "v2.0.6"


# ─── Step 2: Auto-backup ──────────────────────────────────────────────────────


def auto_backup() -> bool:
    """Run backup_qdrant.py via subprocess before migration.

    Returns:
        True on success, False on failure.
    """
    backup_script = SCRIPT_DIR / "backup_qdrant.py"
    print("  Running pre-migration backup...")
    try:
        result = subprocess.run(
            [sys.executable, str(backup_script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"    {GREEN}✓{RESET} Backup complete")
            return True
        else:
            print(f"    {RED}✗ Backup failed (exit {result.returncode}){RESET}")
            if result.stderr:
                print(f"    {GRAY}{result.stderr.strip()}{RESET}")
            return False
    except subprocess.TimeoutExpired:
        print(f"    {RED}✗ Backup timed out after 120s{RESET}")
        return False
    except Exception as e:
        print(f"    {RED}✗ Backup error: {e}{RESET}")
        return False


# ─── Step 3: Freshness bootstrap ─────────────────────────────────────────────


def build_freshness_payload(payload: dict) -> dict:
    """Compute the 5 new freshness fields for a given point payload."""
    memory_type = payload.get("type", "")
    stored_at = payload.get("stored_at") or payload.get("timestamp", "")
    half_life = TYPE_OVERRIDES.get(memory_type, DEFAULT_HALF_LIFE)

    return {
        "decay_score": compute_decay_score(stored_at, half_life),
        "freshness_status": "unverified",
        "source_authority": get_source_authority(memory_type),
        "is_current": True,
        "version": 1,
    }


def migrate_collection_freshness(client, collection: str, dry_run: bool) -> dict:
    """Add freshness fields to all vectors in a collection.

    Returns stats dict: total, updated, skipped, failed.
    """
    stats = {"total": 0, "updated": 0, "skipped": 0, "failed": 0}

    offset = None
    while True:
        scroll_kwargs = dict(
            collection_name=collection,
            limit=BATCH_SIZE,
            with_payload=True,
            with_vectors=False,
        )
        if offset is not None:
            scroll_kwargs["offset"] = offset

        points, next_offset = client.scroll(**scroll_kwargs)

        if not points:
            break

        for point in points:
            stats["total"] += 1
            payload = point.payload or {}

            # Idempotency check: skip if already migrated
            if "decay_score" in payload and "freshness_status" in payload:
                stats["skipped"] += 1
                continue

            new_fields = build_freshness_payload(payload)

            if dry_run:
                stats["updated"] += 1
            else:
                try:
                    client.set_payload(
                        collection_name=collection,
                        payload=new_fields,
                        points=[point.id],
                    )
                    stats["updated"] += 1
                except Exception as e:
                    print(f"    {YELLOW}! Failed point {str(point.id)[:8]}: {e}{RESET}")
                    stats["failed"] += 1

        if next_offset is None:
            break
        offset = next_offset

    return stats


def run_freshness_bootstrap(client, dry_run: bool) -> tuple[int, list]:
    """Run freshness bootstrap across all collections.

    Returns:
        (total_vectors_migrated, collections_processed)
    """
    total_migrated = 0
    collections_processed = []

    for collection in COLLECTIONS:
        print(f"  Migrating {collection}...")
        stats = migrate_collection_freshness(client, collection, dry_run)
        collections_processed.append(collection)
        total_migrated += stats["updated"]

        dry_tag = " [DRY RUN]" if dry_run else ""
        print(
            f"    {GREEN}✓{RESET} {stats['total']} points: "
            f"{stats['updated']} updated, {stats['skipped']} skipped, "
            f"{stats['failed']} failed{dry_tag}"
        )

    return total_migrated, collections_processed


# ─── Step 4: agent_id index on discussions ───────────────────────────────────


def create_agent_id_index(client, dry_run: bool) -> bool:
    """Create agent_id keyword index on discussions collection.

    Returns:
        True if index was created (or already existed), False on error.
    """
    if dry_run:
        print(f"  {GRAY}[DRY RUN] Would create agent_id index on discussions{RESET}")
        return True

    try:
        client.create_payload_index(
            collection_name="discussions",
            field_name="agent_id",
            field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
        )
        print(f"  {GREEN}✓{RESET} Created agent_id index on discussions")
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "already exists" in err_str or "conflict" in err_str:
            print(f"  {YELLOW}!{RESET} agent_id index on discussions already exists")
            return True
        print(f"  {RED}✗ Failed to create agent_id index: {e}{RESET}")
        return False


# ─── Step 5: Append config vars to .env ──────────────────────────────────────

PARZIVAL_VARS = [
    ("PARZIVAL_ENABLED", "false"),
    ("PARZIVAL_USER_NAME", "Developer"),
    ("PARZIVAL_LANGUAGE", "English"),
    ("PARZIVAL_DOC_LANGUAGE", "English"),
    ("PARZIVAL_OVERSIGHT_FOLDER", "oversight"),
    ("PARZIVAL_HANDOFF_RETENTION", "10"),
]


def update_env_file(dry_run: bool) -> bool:
    """Append PARZIVAL_* vars to install_dir/.env if not already present.

    Returns:
        True on success.
    """
    env_path = INSTALL_DIR / ".env"

    if dry_run:
        print(f"  {GRAY}[DRY RUN] Would update {env_path}{RESET}")
        for key, _ in PARZIVAL_VARS:
            print(f"    {GRAY}+ {key}{RESET}")
        return True

    # Read existing content (or empty if not found)
    existing = ""
    if env_path.exists():
        existing = env_path.read_text()

    additions = []
    for key, default in PARZIVAL_VARS:
        if not re.search(rf"^{re.escape(key)}=", existing, re.MULTILINE):
            additions.append(f"{key}={default}")
    lines_to_append = additions

    if not lines_to_append:
        print(f"  {YELLOW}!{RESET} .env already has all PARZIVAL_* vars")
        return True

    try:
        with open(env_path, "a") as f:
            f.write("\n# v2.0.6 freshness bootstrap\n")
            for line in lines_to_append:
                f.write(line + "\n")
        print(f"  {GREEN}✓{RESET} Appended {len(lines_to_append)} vars to {env_path}")
        return True
    except Exception as e:
        print(f"  {RED}✗ Failed to update .env: {e}{RESET}")
        return False


# ─── Step 6: Update hooks via merge_settings.py ──────────────────────────────


def update_hooks(dry_run: bool) -> bool:
    """Call merge_settings.py via subprocess if it exists.

    Returns:
        True on success or if script not found.
    """
    merge_script = SCRIPT_DIR / "merge_settings.py"

    if not merge_script.exists():
        print(f"  {YELLOW}!{RESET} merge_settings.py not found, skipping hooks update")
        return True

    if dry_run:
        print(f"  {GRAY}[DRY RUN] Would run merge_settings.py{RESET}")
        return True

    try:
        result = subprocess.run(
            [sys.executable, str(merge_script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  {GREEN}✓{RESET} Hooks updated via merge_settings.py")
            return True
        else:
            print(
                f"  {YELLOW}!{RESET} merge_settings.py exited {result.returncode} "
                f"(non-critical)"
            )
            return True
    except subprocess.TimeoutExpired:
        print(f"  {YELLOW}!{RESET} merge_settings.py timed out (non-critical)")
        return True
    except Exception as e:
        print(f"  {YELLOW}!{RESET} merge_settings.py error: {e} (non-critical)")
        return True


# ─── Step 7: Audit log ────────────────────────────────────────────────────────


def log_migration(
    vectors_migrated: int,
    collections_processed: list,
    duration_seconds: float,
    agent_id_index_created: bool,
    dry_run: bool,
) -> None:
    """Append migration entry to .audit/migration-log.json."""
    audit_dir = INSTALL_DIR / ".audit"

    if dry_run:
        print(
            f"  {GRAY}[DRY RUN] Would log migration to {audit_dir / 'migration-log.json'}{RESET}"
        )
        return

    audit_dir.mkdir(parents=True, exist_ok=True)
    log_path = audit_dir / "migration-log.json"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "from_version": "v2.0.5",
        "to_version": "v2.0.6",
        "vectors_migrated": vectors_migrated,
        "collections_processed": collections_processed,
        "duration_seconds": round(duration_seconds, 2),
        "agent_id_index_created": agent_id_index_created,
        "dry_run": dry_run,
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"  {GREEN}✓{RESET} Migration logged to {log_path}")
    except Exception as e:
        print(f"  {YELLOW}!{RESET} Could not write audit log: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Migrate AI Memory v2.0.5 → v2.0.6",
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

    print(f"\n{'='*60}")
    if args.dry_run:
        print("  AI Memory Migration v2.0.5 → v2.0.6  [DRY RUN]")
    else:
        print("  AI Memory Migration v2.0.5 → v2.0.6")
    print(f"{'='*60}\n")

    # Connect to Qdrant
    try:
        config = get_config()
        client = get_qdrant_client(config)
    except Exception as e:
        print(f"{RED}✗ Cannot connect to Qdrant: {e}{RESET}")
        print("  Ensure Qdrant is running:")
        print("    docker compose -f docker/docker-compose.yml up -d")
        sys.exit(1)

    # Step 1: Detect version
    print("Detecting current version...")
    version = detect_version(client)
    print(f"  Detected: {version}")

    if version == "v2.0.6":
        print(f"\n{GREEN}✓ Already at v2.0.6 — nothing to do.{RESET}\n")
        sys.exit(0)

    if version == "empty":
        print(
            f"\n{YELLOW}! Collections are empty — applying schema migration only.{RESET}\n"
        )

    # Step 2: Backup
    if not args.skip_backup and not args.dry_run:
        print("\nStep 1/6: Pre-migration backup")
        backup_ok = auto_backup()
        if not backup_ok:
            print(f"{RED}Error: Pre-migration backup failed. Aborting.{RESET}")
            print("  Use --skip-backup to proceed without backup (not recommended)")
            sys.exit(1)
    elif args.dry_run:
        print(f"{YELLOW}Skipping backup (dry-run mode){RESET}")
    else:
        print(f"\n{YELLOW}! Skipping backup (--skip-backup){RESET}")

    # Step 3: Freshness bootstrap
    print("\nStep 2/6: Freshness bootstrap")
    total_migrated, collections_processed = run_freshness_bootstrap(
        client, args.dry_run
    )

    # Step 4: Create agent_id index
    print("\nStep 3/6: Create agent_id index on discussions")
    index_created = create_agent_id_index(client, args.dry_run)

    # Step 5: Update .env
    print("\nStep 4/6: Update .env config")
    update_env_file(args.dry_run)

    # Step 6: Update hooks
    print("\nStep 5/6: Update hooks")
    update_hooks(args.dry_run)

    # Step 7: Audit log
    print("\nStep 6/6: Write audit log")
    duration = time.monotonic() - start_time
    log_migration(
        vectors_migrated=total_migrated,
        collections_processed=collections_processed,
        duration_seconds=duration,
        agent_id_index_created=index_created,
        dry_run=args.dry_run,
    )

    # Summary
    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"  {YELLOW}DRY RUN complete — no data was mutated{RESET}")
    else:
        print(f"  {GREEN}✓ Migration complete{RESET}")
    print()
    print(f"  Vectors migrated : {total_migrated}")
    print(f"  Collections      : {', '.join(collections_processed)}")
    print(f"  Duration         : {duration:.1f}s")
    print(f"  index created    : {index_created}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
