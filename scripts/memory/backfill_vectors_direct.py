#!/usr/bin/env python3
"""Direct vector backfill for pending embeddings.

Uses Qdrant's native update_vectors() API per BP-034.
Operates directly on Qdrant, not via queue.

Usage:
    python scripts/memory/backfill_vectors_direct.py
    python scripts/memory/backfill_vectors_direct.py --collection discussions
    python scripts/memory/backfill_vectors_direct.py --dry-run
    python scripts/memory/backfill_vectors_direct.py --batch-size 25
"""

import argparse
import logging
import sys
from pathlib import Path

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, PointVectors

from memory.config import (
    get_config,
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
)
from memory.embeddings import EmbeddingClient, EmbeddingError

# Structured logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bmad.memory.backfill")

# All V2.0 collections
ALL_COLLECTIONS = [COLLECTION_DISCUSSIONS, COLLECTION_CODE_PATTERNS, COLLECTION_CONVENTIONS]


def count_pending(client: QdrantClient, collection: str) -> int:
    """Count points with embedding_status=pending in a collection."""
    try:
        result = client.count(
            collection_name=collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="embedding_status",
                        match=MatchValue(value="pending"),
                    )
                ]
            ),
        )
        return result.count
    except Exception as e:
        logger.warning(
            "count_failed",
            extra={"collection": collection, "error": str(e)},
        )
        return 0


def backfill_collection(
    client: QdrantClient,
    embed_client: EmbeddingClient,
    collection: str,
    batch_size: int = 50,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Backfill pending embeddings for a collection.

    Args:
        client: Qdrant client instance
        embed_client: Embedding client instance
        collection: Collection name to process
        batch_size: Number of points per batch
        dry_run: If True, count only without processing

    Returns:
        Tuple of (succeeded, failed) counts
    """
    succeeded = 0
    failed = 0
    offset = None

    logger.info(
        "backfill_started",
        extra={"collection": collection, "dry_run": dry_run},
    )

    while True:
        # Query pending points
        try:
            result = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="embedding_status",
                            match=MatchValue(value="pending"),
                        )
                    ]
                ),
                limit=batch_size,
                offset=offset,
                with_vectors=False,
                with_payload=True,
            )
            points, next_offset = result
        except Exception as e:
            logger.error(
                "scroll_failed",
                extra={"collection": collection, "error": str(e)},
            )
            break

        if not points:
            break

        logger.info(
            "batch_retrieved",
            extra={"collection": collection, "count": len(points)},
        )

        if dry_run:
            succeeded += len(points)
            offset = next_offset
            if next_offset is None:
                break
            continue

        # Process each point
        for point in points:
            point_id = point.id
            payload = point.payload or {}
            content = payload.get("content", "")

            if not content:
                logger.warning(
                    "empty_content",
                    extra={"collection": collection, "point_id": str(point_id)},
                )
                failed += 1
                continue

            # Truncate content to 2000 chars for embedding
            content_truncated = content[:2000]

            try:
                # Generate embedding
                vector = embed_client.embed([content_truncated])[0]

                # Verify dimension
                if len(vector) != 768:
                    logger.error(
                        "invalid_vector_dimension",
                        extra={
                            "collection": collection,
                            "point_id": str(point_id),
                            "dimension": len(vector),
                        },
                    )
                    failed += 1
                    continue

                # Update vector using Qdrant's update_vectors API (BP-034)
                client.update_vectors(
                    collection_name=collection,
                    points=[
                        PointVectors(
                            id=point_id,
                            vector=vector,
                        )
                    ],
                )

                # Update payload status to complete
                client.set_payload(
                    collection_name=collection,
                    payload={"embedding_status": "complete"},
                    points=[point_id],
                )

                succeeded += 1
                logger.debug(
                    "point_updated",
                    extra={"collection": collection, "point_id": str(point_id)},
                )

            except EmbeddingError as e:
                logger.error(
                    "embedding_failed",
                    extra={
                        "collection": collection,
                        "point_id": str(point_id),
                        "error": str(e),
                    },
                )
                failed += 1

            except Exception as e:
                logger.error(
                    "update_failed",
                    extra={
                        "collection": collection,
                        "point_id": str(point_id),
                        "error": str(e),
                    },
                )
                failed += 1

        # Move to next batch
        offset = next_offset
        if next_offset is None:
            break

        logger.info(
            "batch_complete",
            extra={
                "collection": collection,
                "succeeded": succeeded,
                "failed": failed,
            },
        )

    logger.info(
        "backfill_complete",
        extra={
            "collection": collection,
            "succeeded": succeeded,
            "failed": failed,
        },
    )

    return succeeded, failed


def main():
    parser = argparse.ArgumentParser(
        description="Backfill pending embeddings using Qdrant update_vectors() API"
    )
    parser.add_argument(
        "--collection",
        choices=ALL_COLLECTIONS,
        help="Single collection to process (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count pending without processing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("bmad.memory.backfill").setLevel(logging.DEBUG)

    # Get configuration
    config = get_config()

    # Connect to Qdrant
    logger.info(
        "connecting_to_qdrant",
        extra={"host": config.qdrant_host, "port": config.qdrant_port},
    )

    try:
        client = QdrantClient(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=config.qdrant_api_key,
            https=config.qdrant_use_https  # BP-040
        )
    except Exception as e:
        logger.error("qdrant_connection_failed", extra={"error": str(e)})
        print(f"ERROR: Could not connect to Qdrant at {config.qdrant_host}:{config.qdrant_port}")
        sys.exit(1)

    # Determine collections to process
    collections = [args.collection] if args.collection else ALL_COLLECTIONS

    # Dry run: just count pending
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Counting pending embeddings")
        print("=" * 60)

        total_pending = 0
        for collection in collections:
            pending = count_pending(client, collection)
            total_pending += pending
            print(f"  {collection}: {pending} pending")

        print("-" * 60)
        print(f"  Total: {total_pending} pending")
        print("=" * 60)
        sys.exit(0)

    # Process collections
    print("\n" + "=" * 60)
    print("DIRECT VECTOR BACKFILL (BP-034)")
    print("=" * 60)

    total_succeeded = 0
    total_failed = 0

    with EmbeddingClient(config) as embed_client:
        # Health check
        if not embed_client.health_check():
            logger.error("embedding_service_unavailable")
            print(f"ERROR: Embedding service not available at {config.embedding_host}:{config.embedding_port}")
            sys.exit(1)

        for collection in collections:
            pending = count_pending(client, collection)
            print(f"\n{collection}: {pending} pending")

            if pending == 0:
                print("  Skipping - no pending points")
                continue

            succeeded, failed = backfill_collection(
                client=client,
                embed_client=embed_client,
                collection=collection,
                batch_size=args.batch_size,
                dry_run=False,
            )

            total_succeeded += succeeded
            total_failed += failed
            print(f"  Complete: {succeeded} succeeded, {failed} failed")

    # Final summary
    print("\n" + "=" * 60)
    print(f"Complete: {total_succeeded} succeeded, {total_failed} failed")
    print("=" * 60)

    # Exit code based on success
    if total_failed > 0 and total_succeeded == 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
