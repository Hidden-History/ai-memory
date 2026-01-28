#!/usr/bin/env python3
"""One-time backfill to reclassify user_message and agent_response memories.

Processes existing user_message and agent_response types in the discussions collection,
runs them through the LLM classifier, and updates Qdrant if reclassified.

Usage:
    python3 scripts/memory/backfill_reclassify_discussions.py --dry-run
    python3 scripts/memory/backfill_reclassify_discussions.py --batch-size 25 --delay 0.5
    python3 scripts/memory/backfill_reclassify_discussions.py --yes  # Non-interactive mode
    python3 scripts/memory/backfill_reclassify_discussions.py --resume  # Resume from checkpoint
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from memory.classifier.llm_classifier import classify
from memory.config import get_config

# Configure logging
logger = logging.getLogger("backfill_reclassify")

# Checkpoint file location
CHECKPOINT_FILE = Path.home() / ".ai-memory" / "queue" / "backfill_checkpoint.json"


def save_checkpoint(memory_type: str, offset: str, stats: dict):
    """Save progress checkpoint for resumability.

    Args:
        memory_type: Current memory type being processed
        offset: Current scroll offset
        stats: Processing statistics
    """
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_data = {
        "memory_type": memory_type,
        "offset": offset,
        "stats": stats
    }
    CHECKPOINT_FILE.write_text(json.dumps(checkpoint_data, indent=2))
    logger.debug("checkpoint_saved", extra={"memory_type": memory_type, "offset": offset})


def load_checkpoint():
    """Load checkpoint if exists.

    Returns:
        dict: Checkpoint data or None if no checkpoint exists
    """
    if not CHECKPOINT_FILE.exists():
        return None

    try:
        data = json.loads(CHECKPOINT_FILE.read_text())
        logger.info("checkpoint_loaded", extra={"memory_type": data.get("memory_type")})
        return data
    except Exception as e:
        logger.warning("checkpoint_load_failed", extra={"error": str(e)})
        return None


def clear_checkpoint():
    """Clear checkpoint file after successful completion."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        logger.info("checkpoint_cleared")


def backfill_reclassify(
    dry_run: bool = False,
    batch_size: int = 50,
    delay: float = 0.1,
    resume: bool = False,
    verbose: bool = False
):
    """Backfill reclassification for existing user_message and agent_response memories.

    Args:
        dry_run: If True, don't actually update Qdrant
        batch_size: Number of points to process per scroll batch
        delay: Delay between batches in seconds (rate limiting)
        resume: Resume from last checkpoint if available
        verbose: Enable verbose logging
    """
    config = get_config()

    # HIGH-3: Add Qdrant connection error handling at startup
    try:
        client = QdrantClient(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=config.qdrant_api_key,
            https=config.qdrant_use_https,  # BP-040
            timeout=30
        )
        # Verify connection by getting collection info
        client.get_collection("discussions")
        logger.info("qdrant_connected", extra={
            "host": config.qdrant_host,
            "port": config.qdrant_port
        })
    except Exception as e:
        logger.error("qdrant_connection_failed", extra={
            "host": config.qdrant_host,
            "port": config.qdrant_port,
            "error": str(e)
        })
        print(f"ERROR: Cannot connect to Qdrant at {config.qdrant_host}:{config.qdrant_port}")
        print(f"Details: {str(e)}")
        sys.exit(1)

    # MEDIUM-5: Replace print() with structured logging
    logger.info("backfill_started", extra={
        "mode": "DRY_RUN" if dry_run else "LIVE",
        "batch_size": batch_size,
        "delay": delay,
        "resume": resume
    })

    # MEDIUM-7: Load checkpoint if resuming
    checkpoint = load_checkpoint() if resume else None

    overall_stats = {
        "processed": 0,
        "reclassified": 0,
        "errors": 0,
        "skipped": 0
    }

    # Query for user_message and agent_response types
    memory_types = ["user_message", "agent_response"]

    # Resume from checkpoint if available
    if checkpoint:
        start_type = checkpoint.get("memory_type")
        if start_type in memory_types:
            # Skip types that were already completed
            start_idx = memory_types.index(start_type)
            memory_types = memory_types[start_idx:]
            overall_stats = checkpoint.get("stats", overall_stats)
            logger.info("resuming_from_checkpoint", extra={
                "memory_type": start_type,
                "stats": overall_stats
            })

    for memory_type in memory_types:
        logger.info("processing_type_started", extra={"type": memory_type})

        offset = checkpoint.get("offset") if checkpoint and checkpoint.get("memory_type") == memory_type else None
        checkpoint = None  # Clear checkpoint after first use

        type_stats = {
            "processed": 0,
            "reclassified": 0,
            "errors": 0
        }

        while True:
            try:
                # HIGH-3: Wrap Qdrant scroll in try/except
                points, offset = client.scroll(
                    collection_name="discussions",
                    scroll_filter={
                        "must": [
                            {"key": "type", "match": {"value": memory_type}}
                        ]
                    },
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False  # BP-034: Don't fetch vectors
                )
            except UnexpectedResponse as e:
                logger.error("scroll_failed", extra={
                    "type": memory_type,
                    "offset": offset,
                    "error": str(e)
                })
                print(f"ERROR: Qdrant scroll failed: {str(e)}")
                break

            if not points:
                break

            # Process batch
            for point in points:
                point_id = str(point.id)
                content = point.payload.get("content", "")

                # Truncate to 2000 chars for classifier
                truncated_content = content[:2000]

                # HIGH-1: Wrap classify() calls in try/except with timeout handling
                try:
                    result = classify(truncated_content, "discussions", memory_type, None)

                    # MEDIUM-8: Validate classify() result before accessing attributes
                    if result is None or not hasattr(result, 'was_reclassified'):
                        logger.warning("invalid_classify_result", extra={
                            "point_id": point_id,
                            "result": str(result)
                        })
                        type_stats["errors"] += 1
                        continue

                    if result.was_reclassified:
                        old_type = memory_type
                        new_type = result.classified_type

                        if not dry_run:
                            try:
                                # Update Qdrant payload
                                client.set_payload(
                                    collection_name="discussions",
                                    points=[point.id],
                                    payload={"type": new_type}
                                )
                                logger.info("reclassified", extra={
                                    "point_id": point_id,
                                    "old_type": old_type,
                                    "new_type": new_type
                                })
                            except Exception as e:
                                logger.error("update_failed", extra={
                                    "point_id": point_id,
                                    "error": str(e)
                                })
                                type_stats["errors"] += 1
                                continue
                        else:
                            logger.info("reclassified_dry_run", extra={
                                "point_id": point_id,
                                "old_type": old_type,
                                "new_type": new_type
                            })

                        type_stats["reclassified"] += 1

                        if verbose:
                            print(f"  ✓ {point_id}: {old_type} → {new_type}")

                except Exception as e:
                    logger.error("classify_failed", extra={
                        "point_id": point_id,
                        "type": memory_type,
                        "error": str(e)
                    })
                    type_stats["errors"] += 1
                    continue  # Skip this point, don't crash

                type_stats["processed"] += 1

            # MEDIUM-7: Save checkpoint after each batch
            overall_stats["processed"] += type_stats["processed"]
            overall_stats["reclassified"] += type_stats["reclassified"]
            overall_stats["errors"] += type_stats["errors"]

            save_checkpoint(memory_type, offset, overall_stats)

            # Progress reporting
            logger.info("batch_complete", extra={
                "type": memory_type,
                "processed": type_stats["processed"],
                "reclassified": type_stats["reclassified"],
                "errors": type_stats["errors"]
            })

            if verbose or type_stats["processed"] % 100 == 0:
                print(f"  Batch complete: {type_stats['processed']} processed, "
                      f"{type_stats['reclassified']} reclassified, {type_stats['errors']} errors")

            # MEDIUM-4: Add rate limiting delay between batches
            if delay > 0 and offset is not None:
                logger.debug("rate_limit_delay", extra={"delay": delay})
                time.sleep(delay)

            # Check if we're done scrolling
            if offset is None:
                break

        logger.info("type_complete", extra={
            "type": memory_type,
            "processed": type_stats["processed"],
            "reclassified": type_stats["reclassified"],
            "errors": type_stats["errors"]
        })

    # Clear checkpoint on successful completion
    clear_checkpoint()

    # Final summary
    logger.info("backfill_complete", extra={
        "total_processed": overall_stats["processed"],
        "total_reclassified": overall_stats["reclassified"],
        "total_errors": overall_stats["errors"],
        "mode": "DRY_RUN" if dry_run else "LIVE"
    })

    print(f"\n{'='*60}")
    print(f"BACKFILL COMPLETE")
    print(f"{'='*60}")
    print(f"Total processed: {overall_stats['processed']}")
    print(f"Total reclassified: {overall_stats['reclassified']}")
    print(f"Total errors: {overall_stats['errors']}")
    print(f"Mode: {'DRY RUN (no changes made)' if dry_run else 'LIVE (Qdrant updated)'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill reclassification for user_message and agent_response memories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview mode (safe)
  python3 scripts/memory/backfill_reclassify_discussions.py --dry-run

  # Live mode with confirmation
  python3 scripts/memory/backfill_reclassify_discussions.py

  # Non-interactive mode (automation)
  python3 scripts/memory/backfill_reclassify_discussions.py --yes

  # Resume from checkpoint
  python3 scripts/memory/backfill_reclassify_discussions.py --resume

  # With rate limiting
  python3 scripts/memory/backfill_reclassify_discussions.py --delay 0.5 --batch-size 25
        """
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update Qdrant (preview mode)"
    )

    # HIGH-2: Add --yes flag for non-interactive confirmation
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt (required for non-interactive/automation)"
    )

    # LOW-9: Add batch size validation
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of points to process per batch (1-200, default: 50)"
    )

    # MEDIUM-4: Add --delay argument for rate limiting
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between batches in seconds (default: 0.1)"
    )

    # MEDIUM-6: Add -v/--verbose flag
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output (show each reclassification)"
    )

    # MEDIUM-7: Add --resume flag for checkpoint recovery
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint (if available)"
    )

    args = parser.parse_args()

    # MEDIUM-6: Configure logging level based on verbose flag
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # LOW-9: Validate batch size
    if not 1 <= args.batch_size <= 200:
        logger.error("invalid_batch_size", extra={"value": args.batch_size})
        print(f"ERROR: --batch-size must be between 1 and 200 (got {args.batch_size})")
        sys.exit(1)

    # LOW-10: Detect non-interactive mode, require --yes
    if not sys.stdin.isatty() and not args.dry_run and not args.yes:
        logger.error("non_interactive_requires_yes")
        print("ERROR: Running non-interactively without --dry-run requires --yes flag")
        print("Use: python3 scripts/memory/backfill_reclassify_discussions.py --yes")
        sys.exit(1)

    # HIGH-2: Add confirmation prompt for live mode
    if not args.dry_run and not args.yes:
        print("\n" + "="*60)
        print("WARNING: LIVE MODE - This will update Qdrant")
        print("="*60)
        print("\nThis script will:")
        print("  - Reclassify ~1665 user_message and agent_response memories")
        print("  - Update their 'type' field in Qdrant discussions collection")
        print("  - Take approximately 2-4 hours (depending on Ollama speed)")
        print("\nRecommendation: Run with --dry-run first to preview changes\n")

        confirm = input("Proceed with live reclassification? [y/N]: ")
        if confirm.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    backfill_reclassify(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        delay=args.delay,
        resume=args.resume,
        verbose=args.verbose
    )
