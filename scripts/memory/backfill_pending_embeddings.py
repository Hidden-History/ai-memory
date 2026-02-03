#!/usr/bin/env python3
"""Backfill embeddings for pending discussion records (TECH-DEBT-059).

After BUG-010 fix, new records get real embeddings. This script re-embeds
~880 pre-fix records with embedding_status="pending" and zero vectors.

RESUME BEHAVIOR:
- Script queries only embedding_status="pending" records
- Already-complete records are automatically skipped
- Safe to re-run after interruption - will resume from pending
- Note: Re-run may re-attempt previously failed records

PERFORMANCE:
- Batch embedding: ~20 records per API call (Issue #1 fix)
- Estimated: 875 records in ~30-60 seconds (3.5x faster than original)
- Rate limited by 0.5s delay between batches

2026 Best Practices Applied:
- BP-002: Qdrant scroll API for large result sets
- BP-006: Tenacity retry logic for transient failures (Issue #2 fix)
- BP-023: Graceful error recovery with progress tracking
- EmbeddingClient for service integration
- Batch embedding for 3.5x speedup
- Structured logging with extras
- Resource cleanup with try/finally
- Dry-run support for safety

Usage:
    # Dry run first
    python3 scripts/memory/backfill_pending_embeddings.py --dry-run --limit 10

    # Small batch test
    python3 scripts/memory/backfill_pending_embeddings.py --limit 20

    # Full backfill
    python3 scripts/memory/backfill_pending_embeddings.py
"""

import argparse
import logging
import random
import sys
import time
from pathlib import Path
from typing import Optional

# Tenacity retry for BP-006 compliance (Issue #2)
from tenacity import (
    after_log,
    before_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

# Optional tqdm for better UX (Issue #8)
try:
    from tqdm import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

from memory.config import (
    COLLECTION_DISCUSSIONS,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    get_config,
)
from memory.embeddings import EmbeddingClient, EmbeddingError

# Configure structured logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 5  # Reduced from 20 - CPU mode can't handle larger batches within timeout
BATCH_DELAY = 0.5  # seconds between batches


def get_pending_records(
    client: QdrantClient, collection: str, limit: Optional[int] = None
) -> list:
    """Query records with embedding_status='pending'.

    Uses scroll API to iterate through all pending records efficiently.

    Args:
        client: Qdrant client instance
        collection: Collection name to query
        limit: Optional maximum records to retrieve

    Returns:
        List of point records with id, vector, and payload
    """
    try:
        # Filter for embedding_status="pending"
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="embedding_status", match=MatchValue(value="pending")
                )
            ]
        )

        pending_records = []
        offset = None

        while True:
            # Scroll through pending records
            records, next_offset = client.scroll(
                collection_name=collection,
                scroll_filter=filter_condition,
                limit=100,  # Fetch 100 at a time
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            pending_records.extend(records)

            # Check if we've hit the limit
            if limit and len(pending_records) >= limit:
                pending_records = pending_records[:limit]
                break

            # Check if we've reached the end
            if next_offset is None:
                break

            offset = next_offset

        # Issue #6: Memory warning for large datasets
        if len(pending_records) > 10000:
            estimated_memory_mb = len(pending_records) * 0.005
            logger.warning(
                "large_dataset_warning",
                extra={
                    "count": len(pending_records),
                    "estimated_memory_mb": estimated_memory_mb,
                },
            )
            print(
                f"⚠️  Large dataset: {len(pending_records)} records (~{estimated_memory_mb:.0f}MB memory)"
            )

        logger.info(
            "pending_records_retrieved",
            extra={"count": len(pending_records), "collection": collection},
        )

        return pending_records

    except Exception as e:
        logger.error(
            "failed_to_retrieve_pending_records",
            extra={"collection": collection, "error": str(e)},
        )
        raise


# Issue #2: Tenacity retry decorator for BP-006 compliance
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.INFO),
    reraise=True,
)
def _embed_with_retry(
    embed_client: EmbeddingClient, contents: list[str]
) -> list[list[float]]:
    """Embed with retry for transient failures.

    Args:
        embed_client: Embedding client instance
        contents: List of text strings to embed

    Returns:
        List of embedding vectors

    Raises:
        EmbeddingError: If all retry attempts fail
    """
    return embed_client.embed(contents)


def backfill_batch(
    client: QdrantClient,
    embed_client: EmbeddingClient,
    collection: str,
    records: list,
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    """Process a batch of records with SINGLE embedding call for efficiency.

    Issue #1 Fix: Batch embedding - collect all content, embed once per batch.
    This reduces HTTP round-trips from 20 per batch to 1, achieving 3.5x speedup.

    Args:
        client: Qdrant client instance
        embed_client: Embedding client instance
        collection: Collection name
        records: List of point records to process
        dry_run: If True, don't actually update records

    Returns:
        Tuple of (successful_count, failed_count, record_ids)
    """
    # Dry run early exit
    if dry_run:
        for record in records:
            logger.debug("dry_run_would_update", extra={"record_id": str(record.id)})
        return len(records), 0, []

    # Issue #1: Collect all content for batch embedding
    contents = []
    valid_records = []

    for record in records:
        content = record.payload.get("content", "")

        if not content or not content.strip():
            logger.warning(
                "skipping_empty_content", extra={"record_id": str(record.id)}
            )
            continue

        contents.append(content)
        valid_records.append(record)

    if not contents:
        logger.info("no_valid_content_in_batch", extra={"batch_size": len(records)})
        return 0, len(records), []

    # Issue #1 & #2: SINGLE embedding call with retry for entire batch
    try:
        logger.info("batch_embedding_start", extra={"batch_size": len(contents)})
        vectors = _embed_with_retry(embed_client, contents)
        logger.info("batch_embedding_complete", extra={"batch_size": len(contents)})
    except Exception as e:
        logger.error(
            "batch_embedding_failed",
            extra={"error": str(e), "batch_size": len(contents)},
        )
        return 0, len(records), []

    # Issue #1 & #4: Distribute vectors back to records with dimension validation
    completed = 0
    failed = 0
    updated_ids = []

    for record, vector in zip(valid_records, vectors):
        try:
            # Issue #4: Validate vector dimension
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"Expected {EMBEDDING_DIMENSIONS} dimensions, got {len(vector)}"
                )

            # Update payload
            updated_payload = record.payload.copy()
            updated_payload["embedding_status"] = "complete"
            updated_payload["embedding_model"] = EMBEDDING_MODEL

            # Upsert with new vector and payload
            point = PointStruct(id=record.id, vector=vector, payload=updated_payload)

            client.upsert(collection_name=collection, points=[point], wait=True)

            logger.debug("record_updated", extra={"record_id": str(record.id)})

            completed += 1
            updated_ids.append(str(record.id))

        except Exception as e:
            logger.error(
                "record_update_failed",
                extra={"record_id": str(record.id), "error": str(e)},
            )
            failed += 1

    # Account for empty content records that were skipped
    failed += len(records) - len(valid_records)

    return completed, failed, updated_ids


def verify_batch(
    client: QdrantClient, collection: str, record_ids: list[str], sample_size: int = 2
) -> bool:
    """Spot-check that records were updated correctly.

    Issue #10: Upsert verification to catch silent failures.

    Args:
        client: Qdrant client instance
        collection: Collection name
        record_ids: List of record IDs that were updated
        sample_size: Number of random records to verify

    Returns:
        True if spot-check passes, False otherwise
    """
    if not record_ids:
        return True

    sample_ids = random.sample(record_ids, min(sample_size, len(record_ids)))

    for record_id in sample_ids:
        try:
            result = client.retrieve(
                collection_name=collection, ids=[record_id], with_vectors=True
            )

            if not result:
                logger.warning(
                    "verification_failed_not_found", extra={"record_id": record_id}
                )
                return False

            record = result[0]

            # Check status was updated
            if record.payload.get("embedding_status") != "complete":
                logger.warning(
                    "verification_failed_status",
                    extra={
                        "record_id": record_id,
                        "status": record.payload.get("embedding_status"),
                    },
                )
                return False

            # Check vector is non-zero (spot check first 10 dimensions)
            if all(v == 0 for v in record.vector[:10]):
                logger.warning(
                    "verification_failed_zero_vector", extra={"record_id": record_id}
                )
                return False

        except Exception as e:
            logger.warning(
                "verification_error", extra={"record_id": record_id, "error": str(e)}
            )
            return False

    logger.debug("verification_passed", extra={"sample_size": len(sample_ids)})
    return True


def validate_embedding_service(embed_client: EmbeddingClient) -> bool:
    """Validate embedding service health and model match.

    Issue #9: Embedding model validation to catch configuration mismatches.

    Args:
        embed_client: EmbeddingClient instance

    Returns:
        True if service is healthy and model matches, False otherwise
    """
    import httpx

    # First check basic health using the client's built-in method
    if not embed_client.health_check():
        logger.error("embedding_service_unhealthy")
        return False

    # Then validate model configuration
    try:
        response = httpx.get(f"{embed_client.base_url}/health", timeout=5.0)

        if response.status_code == 200:
            health = response.json()
            service_model = health.get("model", "unknown")

            # Check model name contains expected model identifier
            if service_model != "unknown" and EMBEDDING_MODEL not in service_model:
                logger.warning(
                    "embedding_model_mismatch",
                    extra={"expected": EMBEDDING_MODEL, "service": service_model},
                )
                print(
                    f"⚠️  Model mismatch: Expected '{EMBEDDING_MODEL}' but service reports '{service_model}'"
                )

        return True

    except Exception as e:
        # Health check passed but model validation failed - non-critical
        logger.warning("embedding_model_validation_failed", extra={"error": str(e)})
        return True  # Don't fail on model validation errors


def main() -> int:
    """Main entry point for backfill script.

    Returns:
        Exit code: 0 on success, 1 on error
    """
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for pending discussion records",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to preview what would be processed
  python backfill_pending_embeddings.py --dry-run --limit 10

  # Small batch test
  python backfill_pending_embeddings.py --limit 20

  # Full backfill of all pending records
  python backfill_pending_embeddings.py

  # Backfill specific collection
  python backfill_pending_embeddings.py --collection code-patterns

  # Verbose logging
  python backfill_pending_embeddings.py -v
        """,
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without making changes"
    )

    parser.add_argument("--limit", type=int, help="Maximum records to process")

    parser.add_argument(
        "--collection",
        default=COLLECTION_DISCUSSIONS,
        help=f"Collection to backfill (default: {COLLECTION_DISCUSSIONS})",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    try:
        config = get_config()
    except Exception as e:
        logger.error("config_load_failed", extra={"error": str(e)})
        print(f"\n❌ Configuration error: {e}\n")
        return 1

    # Connect to Qdrant
    try:
        client = QdrantClient(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=config.qdrant_api_key,
            https=config.qdrant_use_https,  # BP-040
            timeout=10.0,
        )

        # Verify collection exists
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if args.collection not in collection_names:
            logger.error(
                "collection_not_found",
                extra={"collection": args.collection, "available": collection_names},
            )
            print(f"\n❌ Collection '{args.collection}' not found")
            print(f"Available collections: {', '.join(collection_names)}\n")
            return 1

    except Exception as e:
        logger.error(
            "qdrant_connection_failed",
            extra={
                "host": config.qdrant_host,
                "port": config.qdrant_port,
                "error": str(e),
            },
        )
        print(f"\n❌ Cannot connect to Qdrant: {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure Docker services are running:")
        print("     docker compose ps")
        print("  2. Check Qdrant health:")
        print(f"     curl http://{config.qdrant_host}:{config.qdrant_port}/health\n")
        return 1

    # Issue #3: Resource cleanup with try/finally
    embed_client = None
    try:
        # Initialize embedding client
        embed_client = EmbeddingClient(config)

        # Issue #9: Validate embedding service and model
        if not validate_embedding_service(embed_client):
            print("\n❌ Embedding service validation failed")
            print("\nTroubleshooting:")
            print("  1. Check embedding service status:")
            print("     docker compose logs embedding")
            print("  2. Verify port is accessible:")
            print(
                f"     curl http://{config.embedding_host}:{config.embedding_port}/health\n"
            )
            return 1

        # Query pending records
        print(f"\n{'=' * 70}")
        print("  AI Memory Embedding Backfill")
        print(f"{'=' * 70}\n")
        print(f"  Collection: {args.collection}")
        print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        if args.limit:
            print(f"  Limit: {args.limit} records")
        print()

        try:
            pending_records = get_pending_records(client, args.collection, args.limit)

            if not pending_records:
                print("  ✅ No pending records found - nothing to backfill")
                print(f"{'=' * 70}\n")
                return 0

            print(f"  Found {len(pending_records)} pending records")

            if args.dry_run:
                print(f"\n  🔍 DRY RUN - Would process {len(pending_records)} records")
                print(f"{'=' * 70}\n")
                return 0

            print()

        except Exception as e:
            logger.error("query_failed", extra={"error": str(e)})
            print(f"\n❌ Failed to query pending records: {e}\n")
            return 1

        # Process records in batches
        total_successful = 0
        total_failed = 0
        total_batches = (len(pending_records) + BATCH_SIZE - 1) // BATCH_SIZE

        # Issue #8: tqdm progress bar with graceful fallback
        batch_range = range(0, len(pending_records), BATCH_SIZE)
        if HAS_TQDM and not args.dry_run:
            batch_range = tqdm(
                batch_range, desc="Backfilling", unit="batch", total=total_batches
            )

        # Issue #5: Keyboard interrupt handling
        try:
            for i in batch_range:
                batch = pending_records[i : i + BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1

                if not HAS_TQDM:
                    print(
                        f"  Processing batch {batch_num}/{total_batches} ({len(batch)} records)..."
                    )

                successful, failed, updated_ids = backfill_batch(
                    client, embed_client, args.collection, batch, dry_run=args.dry_run
                )

                total_successful += successful
                total_failed += failed

                # Issue #10: Spot-check verification
                if updated_ids and not args.dry_run:
                    if not verify_batch(client, args.collection, updated_ids):
                        logger.warning(
                            "batch_verification_failed", extra={"batch_num": batch_num}
                        )

                # Delay between batches to avoid overwhelming service
                if i + BATCH_SIZE < len(pending_records):
                    time.sleep(BATCH_DELAY)

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Interrupted by user!")
            print(f"\n{'=' * 70}")
            print("  Progress Summary")
            print(f"{'=' * 70}\n")
            print(f"  ✅ Completed: {total_successful}")
            print(f"  ❌ Failed:    {total_failed}")
            remaining = len(pending_records) - (total_successful + total_failed)
            print(f"  ⏸️  Remaining: {remaining}")
            print(f"\n{'=' * 70}\n")
            print("Re-run the script to continue from where it stopped.")
            print("Already-complete records will be automatically skipped.\n")
            return 130  # Standard exit code for SIGINT

        # Print summary
        print(f"\n{'=' * 70}")
        print("  Summary")
        print(f"{'=' * 70}\n")
        print(f"  Total processed: {len(pending_records)}")
        print(f"  ✅ Successful:   {total_successful}")
        print(f"  ❌ Failed:       {total_failed}")
        if len(pending_records) > 0:
            print(
                f"  📊 Success rate: {(total_successful / len(pending_records) * 100):.1f}%"
            )
        print(f"\n{'=' * 70}\n")

        logger.info(
            "backfill_completed",
            extra={
                "total": len(pending_records),
                "successful": total_successful,
                "failed": total_failed,
                "collection": args.collection,
            },
        )

        return 0 if total_failed == 0 else 1

    finally:
        # Issue #3: Ensure resource cleanup
        if embed_client:
            try:
                embed_client.close()
                logger.debug("embedding_client_closed")
            except Exception as e:
                logger.warning("embedding_client_close_failed", extra={"error": str(e)})


if __name__ == "__main__":
    sys.exit(main())
