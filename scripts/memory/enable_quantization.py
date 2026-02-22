#!/usr/bin/env python3
"""Enable 8-bit scalar quantization on all BMAD memory collections.

Reduces memory usage by ~75% with minimal accuracy loss (<1%).
Reference: BP-002 P2, Qdrant Quantization Guide 2026

Architecture Compliance:
- Python naming: snake_case functions, PascalCase classes
- Structured logging with extras dict
- Graceful degradation: continue on individual collection failures
- Exit 0 for success/partial, Exit 1 for critical errors

Idempotency:
- Script detects already-quantized collections and skips them
- Safe to run multiple times without side effects

Reversibility:
- To disable: Run update_collection() with quantization_config=None
- Data is not lost - original vectors remain
- Quantized versions are regenerated on next enable

References:
- TECH-DEBT-065
- Qdrant Quantization Docs: https://qdrant.tech/documentation/guides/quantization/
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project src to path for local imports
# CRITICAL: Check development location FIRST for testing unreleased changes
for path in [
    str(Path(__file__).parent.parent.parent / "src"),  # Development location (priority)
    os.path.expanduser("~/.ai-memory/src"),  # Installed location (fallback)
]:
    if os.path.exists(path):
        sys.path.insert(0, path)
        break

from qdrant_client.models import (
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
)

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

# Collections to quantize (V2.0)
COLLECTIONS = [
    COLLECTION_CODE_PATTERNS,  # "code-patterns"
    COLLECTION_CONVENTIONS,  # "conventions"
    COLLECTION_DISCUSSIONS,  # "discussions"
]


def enable_quantization(client, collection: str) -> tuple[bool, str]:
    """Enable INT8 scalar quantization on a collection.

    2026 Best Practice (Qdrant Quantization):
    - ScalarType.INT8: Best balance of compression vs accuracy
    - quantile=0.99: Exclude outliers for better distribution
    - always_ram=True: Keep quantized vectors in RAM for speed

    Args:
        client: Qdrant client instance
        collection: Collection name

    Returns:
        Tuple of (success: bool, status: str)
        status is one of: "enabled", "already_enabled", "failed", "config_mismatch"
    """
    try:
        # Get current collection info
        info = client.get_collection(collection)
        current_points = info.points_count

        # CRIT-2: Check if already quantized with same config (idempotency)
        existing_quant = info.config.quantization_config
        if existing_quant is not None:
            # Check if it's INT8 with our exact settings
            if hasattr(existing_quant, "scalar"):
                scalar_config = existing_quant.scalar
                if (
                    scalar_config.type == ScalarType.INT8
                    and scalar_config.quantile == 0.99
                    and scalar_config.always_ram is True
                ):
                    logger.info(
                        "quantization_already_enabled",
                        extra={
                            "collection": collection,
                            "points_count": current_points,
                        },
                    )
                    return True, "already_enabled"

        logger.info(
            "enabling_quantization",
            extra={
                "collection": collection,
                "points_count": current_points,
                "quantization_type": "int8",
            },
        )

        # 2026 Best Practice: Use update_collection for live quantization
        client.update_collection(
            collection_name=collection,
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            ),
        )

        # MED-1: Verify quantization enabled with actual value validation
        updated_info = client.get_collection(collection)
        quant = updated_info.config.quantization_config

        # Validate actual values match expected
        if quant and hasattr(quant, "scalar"):
            actual = quant.scalar
            expected_type = ScalarType.INT8
            expected_quantile = 0.99
            expected_ram = True

            if (
                actual.type != expected_type
                or actual.quantile != expected_quantile
                or actual.always_ram != expected_ram
            ):
                logger.warning(
                    "quantization_config_mismatch",
                    extra={
                        "collection": collection,
                        "expected_type": str(expected_type),
                        "actual_type": str(actual.type),
                        "expected_quantile": expected_quantile,
                        "actual_quantile": actual.quantile,
                    },
                )
                return False, "config_mismatch"

            logger.info(
                "quantization_verified",
                extra={
                    "collection": collection,
                    "type": "INT8",
                    "quantile": 0.99,
                    "always_ram": True,
                },
            )
            return True, "enabled"
        else:
            # Quantization config missing after update
            logger.error(
                "quantization_verification_failed",
                extra={
                    "collection": collection,
                    "error": "Quantization config missing after update",
                },
            )
            return False, "failed"

    except Exception as e:
        logger.error(
            "quantization_failed",
            extra={
                "collection": collection,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return False, "failed"


def parse_args():
    """Parse command line arguments.

    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Enable INT8 scalar quantization on BMAD memory collections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (asks for confirmation)
  python enable_quantization.py

  # Skip confirmation
  python enable_quantization.py -y

  # Preview changes without applying
  python enable_quantization.py --dry-run
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying quantization",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    return parser.parse_args()


def main():
    """Enable quantization on all BMAD collections.

    Exit Codes:
        0: Success (full or partial - all attempted collections processed)
        1: Critical error (Qdrant unavailable, all collections failed, connection error)
    """
    args = parse_args()

    try:
        # Connect to Qdrant
        config = get_config()
        client = get_qdrant_client(config)

        print(f"Connecting to Qdrant at {config.qdrant_host}:{config.qdrant_port}")

        # CRIT-3: Verify collections exist before processing
        existing_collections = {c.name for c in client.get_collections().collections}
        missing = [c for c in COLLECTIONS if c not in existing_collections]

        if missing:
            print(f"\nWARNING: Collections not found (skipping): {', '.join(missing)}")
            collections_to_process = [
                c for c in COLLECTIONS if c in existing_collections
            ]
        else:
            collections_to_process = COLLECTIONS

        if not collections_to_process:
            print("\nERROR: No collections to process")
            sys.exit(1)

        # HIGH-4: Confirmation prompt (unless --yes or --dry-run)
        if not args.yes and not args.dry_run:
            print(
                f"\nThis will enable INT8 quantization on {len(collections_to_process)} collection(s):"
            )
            for c in collections_to_process:
                print(f"  - {c}")
            response = input("\nContinue? [y/N]: ")
            if response.lower() != "y":
                print("Aborted.")
                sys.exit(0)

        # HIGH-4: Dry run mode
        if args.dry_run:
            print("\n[DRY RUN] Would process:")
            for c in collections_to_process:
                print(f"  - {c}")
            print("\n[DRY RUN] No changes made.")
            sys.exit(0)

        # Process collections
        results = {}
        for collection in collections_to_process:
            print(f"\nProcessing: {collection}")
            success, status = enable_quantization(client, collection)

            if status == "already_enabled":
                results[collection] = "⏭️  ALREADY QUANTIZED"
            elif status == "enabled":
                results[collection] = "✅ SUCCESS"
            elif status == "config_mismatch":
                results[collection] = "⚠️  CONFIG MISMATCH"
            else:  # "failed"
                results[collection] = "❌ FAILED"

        # Print summary
        print("\n" + "=" * 50)
        print("QUANTIZATION RESULTS")
        print("=" * 50)
        for collection, status in results.items():
            print(f"  {collection}: {status}")

        # CRIT-1: Fixed exit code logic - partial success is still success
        failed_count = sum(
            1 for s in results.values() if "FAILED" in s or "MISMATCH" in s
        )

        if failed_count == len(collections_to_process):
            # Only exit 1 if ALL collections failed
            print("\nERROR: All collections failed to quantize")
            sys.exit(1)
        elif failed_count > 0:
            # Partial success - some failed but some succeeded
            print(
                f"\nWARNING: {failed_count}/{len(collections_to_process)} collection(s) failed (partial success)"
            )
            print("Check logs above for details")
            sys.exit(0)  # Exit 0 for partial success (graceful degradation)
        else:
            # Full success
            print("\n✓ Quantization enabled on all collections")

        print("\nVerify in Qdrant dashboard:")
        print(f"  http://{config.qdrant_host}:{config.qdrant_port}/dashboard")

    except QdrantUnavailable as e:
        logger.error("qdrant_unavailable", extra={"error": str(e)})
        print(f"\nERROR: Qdrant unavailable: {e}")
        print("Please ensure Qdrant is running:")
        print("  docker compose -f docker/docker-compose.yml up -d")
        sys.exit(1)

    except Exception as e:
        logger.exception(
            "quantization_critical_error", extra={"error_type": type(e).__name__}
        )
        print(f"\nCRITICAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
