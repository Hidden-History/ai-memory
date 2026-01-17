#!/usr/bin/env python3
"""One-time migration script to add new fields to existing memories.

Adds agent, component, story_id, and importance fields to existing memories
in Qdrant collections with smart inference and batch processing.

This script implements DEC-018 (BMAD Agent Enrichment) by backfilling
the new optional fields to existing memories.

Usage:
    python scripts/memory/migrate_add_fields.py --dry-run
    python scripts/memory/migrate_add_fields.py --collection implementations
    python scripts/memory/migrate_add_fields.py

Architecture Compliance:
- Python naming: snake_case functions, PascalCase classes
- Structured logging with extras dict
- Batch updates (100 per batch) for efficiency
- Graceful degradation: continue on individual point failures
- Exit 0 for success/partial, Exit 1 for critical errors

2025/2026 Best Practices Applied:
- argparse with type validation
- Structured logging for automation
- Non-blocking error handling
- Progress tracking with statistics

References:
- DEC-018: BMAD Agent Enrichment
- models.py:136-138 (New optional fields)
"""

import sys
import os
import argparse
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add project src to path for local imports
for path in [
    os.path.expanduser("~/.bmad-memory/src"),  # Installed location
    str(Path(__file__).parent.parent.parent / "src"),  # Development location
]:
    if os.path.exists(path):
        sys.path.insert(0, path)
        break

from memory.config import get_config
from memory.qdrant_client import get_qdrant_client, QdrantUnavailable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Collections to migrate
COLLECTIONS = ["implementations", "best_practices", "agent-memory"]

# Batch size for updates
BATCH_SIZE = 100

# Valid BMAD agents (from models.py)
VALID_AGENTS = [
    "architect",
    "analyst",
    "pm",
    "dev",
    "tea",
    "tech-writer",
    "ux-designer",
    "quick-flow-solo-dev",
    "sm",
]


def infer_agent_from_source(source_hook: str, content: str) -> Optional[str]:
    """Infer agent from source_hook or content if possible.

    Heuristics:
    - PostToolUse: Look for agent mentions in content
    - SessionStart/Stop: Extract from session context if available
    - Manual/seed_script: Check for BMAD agent patterns

    Args:
        source_hook: Hook that captured the memory
        content: Memory content to analyze

    Returns:
        str: Agent name if inferred, None otherwise
    """
    # Check for explicit agent mentions in content
    for agent in VALID_AGENTS:
        # Look for patterns like "dev agent", "Agent: dev", "@dev", etc.
        patterns = [
            rf'\b{agent}\s+agent\b',
            rf'Agent:\s*{agent}\b',
            rf'@{agent}\b',
            rf'\[{agent}\]',
        ]
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.debug(
                    "agent_inferred",
                    extra={
                        "agent": agent,
                        "pattern": pattern,
                        "source_hook": source_hook
                    }
                )
                return agent

    return None


def infer_component_from_content(content: str) -> Optional[str]:
    """Infer component from file paths or content patterns.

    Looks for common file path patterns and component keywords.

    Args:
        content: Memory content to analyze

    Returns:
        str: Component name if inferred, None otherwise
    """
    # Common component patterns (file paths, module names)
    component_patterns = {
        r'src/auth/|authentication|AuthService': 'auth',
        r'src/database/|db/|database|DatabaseService': 'database',
        r'src/api/|api/|APIService|endpoint': 'api',
        r'src/memory/|memory/|MemoryService': 'memory',
        r'src/queue/|queue/|QueueService': 'queue',
        r'src/embedding/|embedding/|EmbeddingService': 'embedding',
        r'src/search/|search/|SearchService': 'search',
        r'src/storage/|storage/|StorageService': 'storage',
        r'docker/|Docker|container': 'docker',
        r'tests?/|test_|Testing': 'tests',
        r'scripts?/': 'scripts',
        r'hooks?/|HookService': 'hooks',
    }

    for pattern, component in component_patterns.items():
        if re.search(pattern, content, re.IGNORECASE):
            logger.debug(
                "component_inferred",
                extra={"component": component, "pattern": pattern}
            )
            return component

    return None


def infer_story_id_from_content(content: str) -> Optional[str]:
    """Infer story_id from content patterns.

    Looks for story ID patterns like:
    - Story 1.2, Story 4.3
    - Epic 5
    - AUTH-12, DB-05

    Args:
        content: Memory content to analyze

    Returns:
        str: Story ID if inferred, None otherwise
    """
    # Story patterns
    story_patterns = [
        r'Story\s+(\d+\.\d+)',  # "Story 1.2"
        r'Epic\s+(\d+)',  # "Epic 5"
        r'\b([A-Z]+-\d+)\b',  # "AUTH-12"
    ]

    for pattern in story_patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            story_id = match.group(1)
            logger.debug(
                "story_id_inferred",
                extra={"story_id": story_id, "pattern": pattern}
            )
            return story_id

    return None


def get_default_importance(memory_type: str) -> str:
    """Get default importance based on memory type.

    Args:
        memory_type: Type of memory

    Returns:
        str: Default importance level
    """
    # Critical types
    if memory_type in ["architecture_decision", "error_pattern", "database_schema"]:
        return "high"
    # Normal types
    elif memory_type in ["implementation", "config_pattern", "integration_example"]:
        return "medium"
    # Best practices and sessions
    elif memory_type in ["best_practice", "session_summary"]:
        return "medium"
    # Everything else
    else:
        return "medium"


def process_point(point: Any, dry_run: bool = False) -> Dict[str, Any]:
    """Process a single point and determine updates needed.

    Args:
        point: Qdrant point object
        dry_run: If True, don't apply updates

    Returns:
        dict: Update information with keys:
            - needs_update: bool
            - updates: dict of field updates
            - point_id: str
    """
    payload = point.payload
    point_id = str(point.id)
    updates = {}

    # Check for missing fields and add defaults with inference
    if "agent" not in payload or payload.get("agent") is None:
        # Try to infer agent
        inferred_agent = infer_agent_from_source(
            payload.get("source_hook", ""),
            payload.get("content", "")
        )
        updates["agent"] = inferred_agent

    if "component" not in payload or payload.get("component") is None:
        # Try to infer component
        inferred_component = infer_component_from_content(
            payload.get("content", "")
        )
        updates["component"] = inferred_component

    if "story_id" not in payload or payload.get("story_id") is None:
        # Try to infer story_id
        inferred_story_id = infer_story_id_from_content(
            payload.get("content", "")
        )
        updates["story_id"] = inferred_story_id

    # Always add importance if missing (no inference, just default)
    if "importance" not in payload or payload.get("importance") is None:
        memory_type = payload.get("type", "implementation")
        updates["importance"] = get_default_importance(memory_type)

    needs_update = len(updates) > 0

    if needs_update:
        logger.debug(
            "point_needs_update",
            extra={
                "point_id": point_id[:8],
                "updates": updates,
                "dry_run": dry_run
            }
        )

    return {
        "needs_update": needs_update,
        "updates": updates,
        "point_id": point_id
    }


def migrate_collection(
    collection: str,
    dry_run: bool = False,
    qdrant_client: Any = None
) -> Dict[str, int]:
    """Migrate a single collection.

    Args:
        collection: Collection name to migrate
        dry_run: If True, show what would be done without applying
        qdrant_client: Qdrant client instance

    Returns:
        dict: Statistics with keys:
            - total: Total points in collection
            - updated: Points that needed updates
            - skipped: Points that were already up-to-date
            - failed: Points that failed to update
    """
    logger.info(
        "collection_migration_started",
        extra={"collection": collection, "dry_run": dry_run}
    )

    stats = {"total": 0, "updated": 0, "skipped": 0, "failed": 0}
    batch_updates = []

    # Scroll through all points in collection
    scroll_result = qdrant_client.scroll(
        collection_name=collection,
        limit=10000,  # Large batch for initial read
        with_payload=True,
        with_vectors=False  # Don't need vectors for this migration
    )

    points, next_page_offset = scroll_result

    while points:
        for point in points:
            stats["total"] += 1

            # Process point and determine updates
            result = process_point(point, dry_run=dry_run)

            if result["needs_update"]:
                stats["updated"] += 1

                if not dry_run:
                    batch_updates.append({
                        "id": result["point_id"],
                        "payload": result["updates"]
                    })

                    # Apply batch when full (each point individually since payloads differ)
                    if len(batch_updates) >= BATCH_SIZE:
                        failed_in_batch = 0
                        for item in batch_updates:
                            try:
                                qdrant_client.set_payload(
                                    collection_name=collection,
                                    payload=item["payload"],
                                    points=[item["id"]]
                                )
                            except Exception as e:
                                logger.error(
                                    "point_update_failed",
                                    extra={
                                        "collection": collection,
                                        "point_id": item["id"][:8],
                                        "error": str(e),
                                        "error_type": type(e).__name__
                                    }
                                )
                                failed_in_batch += 1

                        if failed_in_batch > 0:
                            stats["failed"] += failed_in_batch

                        logger.info(
                            "batch_applied",
                            extra={
                                "collection": collection,
                                "batch_size": len(batch_updates),
                                "failed": failed_in_batch
                            }
                        )
                        batch_updates = []
            else:
                stats["skipped"] += 1

        # Get next page
        if next_page_offset is None:
            break

        scroll_result = qdrant_client.scroll(
            collection_name=collection,
            offset=next_page_offset,
            limit=10000,
            with_payload=True,
            with_vectors=False
        )
        points, next_page_offset = scroll_result

    # Apply remaining batch (each point individually since payloads differ)
    if batch_updates and not dry_run:
        failed_in_batch = 0
        for item in batch_updates:
            try:
                qdrant_client.set_payload(
                    collection_name=collection,
                    payload=item["payload"],
                    points=[item["id"]]
                )
            except Exception as e:
                logger.error(
                    "point_update_failed",
                    extra={
                        "collection": collection,
                        "point_id": item["id"][:8],
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                failed_in_batch += 1

        if failed_in_batch > 0:
            stats["failed"] += failed_in_batch
            logger.warning(
                "final_batch_partial_failure",
                extra={
                    "collection": collection,
                    "total": len(batch_updates),
                    "failed": failed_in_batch
                }
            )
        else:
            logger.info(
                "final_batch_applied",
                extra={
                    "collection": collection,
                    "batch_size": len(batch_updates)
                }
            )

    logger.info(
        "collection_migration_complete",
        extra={
            "collection": collection,
            "stats": stats,
            "dry_run": dry_run
        }
    )

    return stats


def validate_collection(value: str) -> str:
    """Validate --collection argument.

    Args:
        value: Collection name from command line

    Returns:
        str: Validated collection name

    Raises:
        argparse.ArgumentTypeError: If validation fails
    """
    if value not in COLLECTIONS:
        raise argparse.ArgumentTypeError(
            f"Invalid collection '{value}'. Must be one of: {', '.join(COLLECTIONS)}"
        )
    return value


def main():
    """Main execution entry point.

    Exit Codes:
        0: Success (even if some points failed - they're logged)
        1: Critical error (Qdrant unavailable, invalid args)
    """
    parser = argparse.ArgumentParser(
        description="Migrate existing memories to add new fields (agent, component, story_id, importance)",
        epilog="Exit 0: success/partial, Exit 1: critical error"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    parser.add_argument(
        "--collection",
        type=validate_collection,
        help=f"Migrate single collection only. Options: {', '.join(COLLECTIONS)}"
    )
    args = parser.parse_args()

    # Determine collections to migrate
    collections_to_migrate = [args.collection] if args.collection else COLLECTIONS

    try:
        # Connect to Qdrant
        config = get_config()
        qdrant_client = get_qdrant_client(config)

        logger.info(
            "migration_started",
            extra={
                "collections": collections_to_migrate,
                "dry_run": args.dry_run,
                "batch_size": BATCH_SIZE
            }
        )

        # Track overall statistics
        total_stats = {"total": 0, "updated": 0, "skipped": 0, "failed": 0}

        # Migrate each collection
        for collection in collections_to_migrate:
            try:
                stats = migrate_collection(
                    collection=collection,
                    dry_run=args.dry_run,
                    qdrant_client=qdrant_client
                )

                # Accumulate stats
                for key in total_stats:
                    total_stats[key] += stats[key]

                # Print progress
                sys.stdout.write(
                    f"\n{collection}:\n"
                    f"  Total points: {stats['total']}\n"
                    f"  Updated: {stats['updated']}\n"
                    f"  Skipped (already current): {stats['skipped']}\n"
                    f"  Failed: {stats['failed']}\n"
                )

            except Exception as e:
                logger.error(
                    "collection_migration_failed",
                    extra={
                        "collection": collection,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                sys.stdout.write(f"\nERROR migrating {collection}: {e}\n")
                # Continue with other collections

        # Print summary
        sys.stdout.write(
            f"\n{'='*50}\n"
            f"Migration {'DRY RUN ' if args.dry_run else ''}Summary:\n"
            f"  Total points processed: {total_stats['total']}\n"
            f"  Updated: {total_stats['updated']}\n"
            f"  Skipped: {total_stats['skipped']}\n"
            f"  Failed: {total_stats['failed']}\n"
            f"{'='*50}\n"
        )

        logger.info(
            "migration_complete",
            extra={
                "total_stats": total_stats,
                "dry_run": args.dry_run,
                "collections": collections_to_migrate
            }
        )

    except QdrantUnavailable as e:
        logger.error(
            "qdrant_unavailable",
            extra={"error": str(e)}
        )
        sys.stdout.write(f"\nERROR: Qdrant unavailable: {e}\n")
        sys.stdout.write("Please ensure Qdrant is running:\n")
        sys.stdout.write("  docker compose -f docker/docker-compose.yml up -d\n")
        sys.exit(1)

    except Exception as e:
        logger.exception(
            "migration_critical_error",
            extra={"error_type": type(e).__name__}
        )
        sys.stdout.write(f"\nCRITICAL ERROR: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
