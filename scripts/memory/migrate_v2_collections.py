#!/usr/bin/env python3
"""Memory System v2.0 Migration Script.

Migrates from v1.0 collection architecture to v2.0 typed collections.

Changes:
- OLD: implementations, best_practices, agent-memory
- NEW: code-patterns, conventions, discussions (with type field on all memories)

Migration Logic:
- implementations → code-patterns (type: implementation)
- best_practices → conventions (type: guideline)
- agent-memory → discussions (with type inference based on content)

Usage:
    python scripts/memory/migrate_v2_collections.py --dry-run
    python scripts/memory/migrate_v2_collections.py --create-only  # Just create collections
    python scripts/memory/migrate_v2_collections.py  # Full migration

Architecture Compliance:
- Python naming: snake_case functions, PascalCase classes
- Structured logging with extras dict
- Batch updates (100 per batch) for efficiency
- Graceful degradation: continue on individual point failures
- Exit 0 for success/partial, Exit 1 for critical errors

References:
- oversight/specs/MEMORY-SYSTEM-REDESIGN-v2.md Section 4-6
- src/memory/models.py (MemoryType enum)
- src/memory/config.py (COLLECTION_NAMES)
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project src to path for local imports
# CRITICAL: Check development location FIRST for testing unreleased changes
for path in [
    str(Path(__file__).parent.parent.parent / "src"),  # Development location (priority)
    os.path.expanduser("~/.ai-memory/src"),  # Installed location (fallback)
]:
    if os.path.exists(path):
        sys.path.insert(0, path)
        break

from qdrant_client.models import Distance, VectorParams

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    get_config,
)
from memory.qdrant_client import QdrantUnavailable, get_qdrant_client

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Old collections (v1.0)
OLD_COLLECTIONS = ["implementations", "best_practices", "agent-memory"]

# New collections (v2.0) - from config.py
NEW_COLLECTIONS = [
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
]

# Migration mapping: old_collection → (new_collection, default_type)
MIGRATION_MAP = {
    "implementations": (COLLECTION_CODE_PATTERNS, "implementation"),
    "best_practices": (COLLECTION_CONVENTIONS, "guideline"),
    "agent-memory": (COLLECTION_DISCUSSIONS, None),  # Type needs inference
}

# Batch size for updates
BATCH_SIZE = 100

# Vector config (must match existing collections)
VECTOR_SIZE = 768
DISTANCE_METRIC = Distance.COSINE


def infer_type_for_agent_memory(payload: Dict[str, Any]) -> str:
    """Infer type for agent-memory records based on content and existing fields.

    Logic (from MEMORY-SYSTEM-REDESIGN-v2.md Section 5.2):
    - Contains "DEC-" → decision
    - Contains "BLK-" → blocker
    - type=session_summary → session
    - Contains "prefer", "like" → preference
    - Otherwise → context

    Args:
        payload: Memory payload dict

    Returns:
        str: Inferred type (decision, session, blocker, preference, context)
    """
    content = payload.get("content", "")
    existing_type = payload.get("type", "")

    # Check for decision markers
    if re.search(r"\bDEC-\d+\b", content, re.IGNORECASE):
        return "decision"

    # Check for blocker markers
    if re.search(r"\bBLK-\d+\b", content, re.IGNORECASE):
        return "blocker"

    # Check existing type field (legacy)
    if existing_type == "session_summary":
        return "session"

    # Check for preference markers
    if re.search(r"\b(prefer|preference|like|dislike)\b", content, re.IGNORECASE):
        return "preference"

    # Default to context
    return "context"


def create_collection_if_not_exists(
    qdrant_client: Any,
    collection_name: str,
    vector_size: int = VECTOR_SIZE,
    distance: Distance = DISTANCE_METRIC,
) -> bool:
    """Create a Qdrant collection if it doesn't exist.

    Args:
        qdrant_client: Qdrant client instance
        collection_name: Name of collection to create
        vector_size: Vector dimensions (default 768)
        distance: Distance metric (default COSINE)

    Returns:
        bool: True if created, False if already exists
    """
    # Check if collection exists
    collections = qdrant_client.get_collections().collections
    existing_names = [c.name for c in collections]

    if collection_name in existing_names:
        logger.info("collection_exists", extra={"collection": collection_name})
        return False

    # Create collection
    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=distance),
    )

    logger.info(
        "collection_created",
        extra={
            "collection": collection_name,
            "vector_size": vector_size,
            "distance": distance.value,
        },
    )

    return True


def migrate_point(
    point: Any, target_collection: str, default_type: Optional[str] = None
) -> Dict[str, Any]:
    """Migrate a single point to the new schema.

    Adds `type` field to payload, preserving all other fields.

    Args:
        point: Qdrant point object
        target_collection: Target collection name
        default_type: Default type if not inferred (None for agent-memory)

    Returns:
        dict: Migrated point data with keys:
            - id: Point UUID
            - vector: Embedding vector
            - payload: Updated payload with type field
    """
    payload = dict(point.payload)
    point_id = str(point.id)

    # Determine type
    if "type" not in payload or payload.get("type") is None:
        if default_type:
            # Simple mapping (implementations → implementation, best_practices → guideline)
            payload["type"] = default_type
        else:
            # Infer for agent-memory
            payload["type"] = infer_type_for_agent_memory(payload)
    else:
        # Type exists - validate and possibly remap legacy types
        existing_type = payload["type"]
        # Legacy type remapping (session_summary → session, etc.)
        type_remapping = {
            "session_summary": "session",
            "best_practice": "guideline",
            "error_pattern": "error_fix",
        }
        payload["type"] = type_remapping.get(existing_type, existing_type)

    return {"id": point_id, "vector": point.vector, "payload": payload}


def migrate_collection(
    old_collection: str,
    new_collection: str,
    default_type: Optional[str],
    dry_run: bool = False,
    qdrant_client: Any = None,
) -> Dict[str, int]:
    """Migrate points from old collection to new collection.

    Args:
        old_collection: Source collection name (v1.0)
        new_collection: Target collection name (v2.0)
        default_type: Default type for migrated points (None = infer)
        dry_run: If True, show what would be done without applying
        qdrant_client: Qdrant client instance

    Returns:
        dict: Statistics with keys:
            - total: Total points in old collection
            - migrated: Points successfully migrated
            - failed: Points that failed to migrate
    """
    logger.info(
        "collection_migration_started",
        extra={
            "old_collection": old_collection,
            "new_collection": new_collection,
            "default_type": default_type,
            "dry_run": dry_run,
        },
    )

    stats = {"total": 0, "migrated": 0, "failed": 0}
    batch = []

    # Check if old collection exists
    collections = qdrant_client.get_collections().collections
    if old_collection not in [c.name for c in collections]:
        logger.warning("old_collection_not_found", extra={"collection": old_collection})
        return stats

    # Scroll through all points in old collection
    scroll_result = qdrant_client.scroll(
        collection_name=old_collection,
        limit=10000,
        with_payload=True,
        with_vectors=True,  # Need vectors for migration
    )

    points, next_page_offset = scroll_result

    while points:
        for point in points:
            stats["total"] += 1

            try:
                # Migrate point
                migrated_point = migrate_point(point, new_collection, default_type)

                if not dry_run:
                    batch.append(migrated_point)

                    # Apply batch when full
                    if len(batch) >= BATCH_SIZE:
                        try:
                            from qdrant_client.models import PointStruct

                            point_structs = [
                                PointStruct(
                                    id=p["id"], vector=p["vector"], payload=p["payload"]
                                )
                                for p in batch
                            ]
                            qdrant_client.upsert(
                                collection_name=new_collection, points=point_structs
                            )
                            stats["migrated"] += len(batch)
                            logger.info(
                                "batch_migrated",
                                extra={
                                    "old_collection": old_collection,
                                    "new_collection": new_collection,
                                    "batch_size": len(batch),
                                },
                            )
                        except Exception as e:
                            logger.error(
                                "batch_migration_failed",
                                extra={
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                    "batch_size": len(batch),
                                },
                            )
                            stats["failed"] += len(batch)

                        batch = []
                else:
                    # Dry run - just count
                    stats["migrated"] += 1

            except Exception as e:
                logger.error(
                    "point_migration_failed",
                    extra={
                        "point_id": str(point.id)[:8],
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                stats["failed"] += 1

        # Get next page
        if next_page_offset is None:
            break

        scroll_result = qdrant_client.scroll(
            collection_name=old_collection,
            offset=next_page_offset,
            limit=10000,
            with_payload=True,
            with_vectors=True,
        )
        points, next_page_offset = scroll_result

    # Apply remaining batch
    if batch and not dry_run:
        try:
            from qdrant_client.models import PointStruct

            point_structs = [
                PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                for p in batch
            ]
            qdrant_client.upsert(collection_name=new_collection, points=point_structs)
            stats["migrated"] += len(batch)
            logger.info(
                "final_batch_migrated",
                extra={
                    "old_collection": old_collection,
                    "new_collection": new_collection,
                    "batch_size": len(batch),
                },
            )
        except Exception as e:
            logger.error(
                "final_batch_migration_failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "batch_size": len(batch),
                },
            )
            stats["failed"] += len(batch)

    logger.info(
        "collection_migration_complete",
        extra={
            "old_collection": old_collection,
            "new_collection": new_collection,
            "stats": stats,
            "dry_run": dry_run,
        },
    )

    return stats


def main():
    """Main execution entry point.

    Exit Codes:
        0: Success (even if some points failed - they're logged)
        1: Critical error (Qdrant unavailable, invalid args)
    """
    parser = argparse.ArgumentParser(
        description="Migrate Memory System v1.0 → v2.0 collections",
        epilog="Exit 0: success/partial, Exit 1: critical error",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without applying them"
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Only create new collections, don't migrate data",
    )
    args = parser.parse_args()

    try:
        # Connect to Qdrant
        config = get_config()
        qdrant_client = get_qdrant_client(config)

        logger.info(
            "migration_started",
            extra={
                "dry_run": args.dry_run,
                "create_only": args.create_only,
                "batch_size": BATCH_SIZE,
            },
        )

        # Step 1: Create new collections
        sys.stdout.write("\n=== Creating v2.0 Collections ===\n")
        for collection_name in NEW_COLLECTIONS:
            created = create_collection_if_not_exists(
                qdrant_client,
                collection_name,
                vector_size=VECTOR_SIZE,
                distance=DISTANCE_METRIC,
            )
            status = "Created" if created else "Already exists"
            sys.stdout.write(f"  {collection_name}: {status}\n")

        if args.create_only:
            sys.stdout.write("\n✓ Collections created. Exiting (--create-only mode).\n")
            return

        # Step 2: Migrate data
        sys.stdout.write("\n=== Migrating Data ===\n")
        total_stats = {"total": 0, "migrated": 0, "failed": 0}

        for old_collection, (new_collection, default_type) in MIGRATION_MAP.items():
            sys.stdout.write(f"\nMigrating {old_collection} → {new_collection}\n")

            stats = migrate_collection(
                old_collection=old_collection,
                new_collection=new_collection,
                default_type=default_type,
                dry_run=args.dry_run,
                qdrant_client=qdrant_client,
            )

            # Accumulate stats
            for key in total_stats:
                total_stats[key] += stats[key]

            # Print progress
            sys.stdout.write(
                f"  Total points: {stats['total']}\n"
                f"  Migrated: {stats['migrated']}\n"
                f"  Failed: {stats['failed']}\n"
            )

        # Print summary
        sys.stdout.write(
            f"\n{'='*50}\n"
            f"Migration {'DRY RUN ' if args.dry_run else ''}Summary:\n"
            f"  Total points processed: {total_stats['total']}\n"
            f"  Migrated: {total_stats['migrated']}\n"
            f"  Failed: {total_stats['failed']}\n"
            f"{'='*50}\n"
        )

        if not args.dry_run and total_stats["failed"] == 0:
            sys.stdout.write("\n✓ Migration complete. Old collections preserved.\n")
            sys.stdout.write("  To remove old collections, use:\n")
            for old_coll in OLD_COLLECTIONS:
                sys.stdout.write(
                    f"    # qdrant_client.delete_collection('{old_coll}')\n"
                )

        logger.info(
            "migration_complete",
            extra={"total_stats": total_stats, "dry_run": args.dry_run},
        )

    except QdrantUnavailable as e:
        logger.error("qdrant_unavailable", extra={"error": str(e)})
        sys.stdout.write(f"\nERROR: Qdrant unavailable: {e}\n")
        sys.stdout.write("Please ensure Qdrant is running:\n")
        sys.stdout.write("  docker compose -f docker/docker-compose.yml up -d\n")
        sys.exit(1)

    except Exception as e:
        logger.exception(
            "migration_critical_error", extra={"error_type": type(e).__name__}
        )
        sys.stdout.write(f"\nCRITICAL ERROR: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
