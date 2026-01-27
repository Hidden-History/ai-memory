#!/usr/bin/env python3
"""Optimize HNSW configuration for multi-tenancy in Qdrant collections.

Applies BP-002 best practices:
- m=0: Disable global HNSW index (reduces overhead)
- payload_m=16: Enable per-tenant HNSW graphs
- Works with existing is_tenant=True group_id index

This is a configuration-only change that improves tenant-filtered search performance.

References:
- BP-002: oversight/knowledge/best-practices/BP-002-qdrant-best-practices-2026.md
- Setup script: scripts/setup-collections.py
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from qdrant_client import QdrantClient
from qdrant_client.models import HnswConfigDiff
from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_NAMES,
)

# FIX-9: Use structured logging per project standards
from memory.logging_config import configure_logging

# Configure structured logging
configure_logging()
logger = logging.getLogger("bmad.memory.hnsw_optimizer")


def get_hnsw_config(client: QdrantClient, collection_name: str) -> dict:
    """Get current HNSW configuration for a collection.

    Args:
        client: Qdrant client instance
        collection_name: Name of collection to query

    Returns:
        Dictionary with HNSW config parameters

    Raises:
        Exception: If collection doesn't exist or query fails
    """
    try:
        collection_info = client.get_collection(collection_name)
        config = collection_info.config
        hnsw = config.hnsw_config

        return {
            "m": hnsw.m,
            "ef_construct": hnsw.ef_construct,
            "full_scan_threshold": hnsw.full_scan_threshold,
            "max_indexing_threads": hnsw.max_indexing_threads,
            "on_disk": hnsw.on_disk,
            "payload_m": hnsw.payload_m if hasattr(hnsw, 'payload_m') else None,
        }
    except Exception as e:
        logger.error(
            "failed_to_get_hnsw_config",
            extra={"collection": collection_name, "error": str(e)}
        )
        raise


def verify_tenant_index(collection_info, collection_name: str) -> bool:
    """Verify group_id index has is_tenant=True for co-location.

    FIX-7: Per BP-002, tenant index is critical for optimization effectiveness.

    Args:
        collection_info: Collection info object (to avoid redundant API calls)
        collection_name: Collection name for logging

    Returns:
        True if is_tenant is set, False otherwise
    """
    try:

        # Check payload schema for group_id index
        if hasattr(collection_info, 'payload_schema') and collection_info.payload_schema:
            for field_name, field_info in collection_info.payload_schema.items():
                if field_name == "group_id":
                    # Check if is_tenant parameter exists
                    if hasattr(field_info, 'params') and hasattr(field_info.params, 'is_tenant'):
                        is_tenant = field_info.params.is_tenant
                        if not is_tenant:
                            logger.warning(
                                "is_tenant_not_set",
                                extra={
                                    "collection": collection_name,
                                    "recommendation": "Add is_tenant=True to group_id index for co-location"
                                }
                            )
                            return False
                        return True

        logger.warning(
            "group_id_index_not_found",
            extra={"collection": collection_name, "recommendation": "Create group_id index first"}
        )
        return False

    except Exception as e:
        logger.error("tenant_index_check_failed", extra={"error": str(e)})
        return False


def optimize_collection(
    client: QdrantClient,
    collection_name: str,
    dry_run: bool = False
) -> None:
    """Apply HNSW multi-tenancy optimization to a collection.

    Args:
        client: Qdrant client instance
        collection_name: Collection to optimize
        dry_run: If True, preview changes without applying

    Raises:
        Exception: If collection doesn't exist or update fails
    """
    # Verify collection exists
    if not client.collection_exists(collection_name):
        logger.error(
            "collection_not_found",
            extra={"collection": collection_name}
        )
        raise ValueError(f"Collection '{collection_name}' does not exist")

    # Get collection info once (used for multiple checks)
    collection_info = client.get_collection(collection_name)

    # FIX-8: Check if collection is empty
    points_count = collection_info.points_count if hasattr(collection_info, 'points_count') else 0

    if points_count == 0:
        logger.warning(
            "empty_collection_skipped",
            extra={"collection": collection_name, "reason": "No points to optimize"}
        )
        if not dry_run:
            return  # Skip empty collections

    # FIX-7: Verify tenant index configuration (reuse collection_info)
    verify_tenant_index(collection_info, collection_name)

    # Get current HNSW config from collection_info (avoid redundant call)
    logger.info(
        "reading_current_config",
        extra={"collection": collection_name}
    )
    config = collection_info.config
    hnsw = config.hnsw_config

    before_config = {
        "m": hnsw.m,
        "ef_construct": hnsw.ef_construct,
        "full_scan_threshold": hnsw.full_scan_threshold,
        "max_indexing_threads": hnsw.max_indexing_threads,
        "on_disk": hnsw.on_disk,
        "payload_m": hnsw.payload_m if hasattr(hnsw, 'payload_m') else None,
    }

    logger.info(
        "current_hnsw_config",
        extra={
            "collection": collection_name,
            "m": before_config["m"],
            "payload_m": before_config["payload_m"],
            "ef_construct": before_config["ef_construct"],
        }
    )

    if dry_run:
        logger.info(
            "dry_run_preview",
            extra={
                "collection": collection_name,
                "action": "would_update",
                "target_m": 0,
                "target_payload_m": 16,
            }
        )
        return

    # Apply optimization
    logger.info(
        "applying_optimization",
        extra={"collection": collection_name}
    )

    try:
        client.update_collection(
            collection_name=collection_name,
            hnsw_config=HnswConfigDiff(
                m=0,           # Disable global index
                payload_m=16,  # Enable per-tenant index
            )
        )

        logger.info(
            "optimization_applied",
            extra={"collection": collection_name}
        )

        # Verify update
        after_config = get_hnsw_config(client, collection_name)

        logger.info(
            "hnsw_config_updated",
            extra={
                "collection": collection_name,
                "before_m": before_config["m"],
                "after_m": after_config["m"],
                "before_payload_m": before_config["payload_m"],
                "after_payload_m": after_config["payload_m"],
            }
        )

        # Verify expected values
        if after_config["m"] != 0 or after_config["payload_m"] != 16:
            logger.warning(
                "unexpected_config_values",
                extra={
                    "collection": collection_name,
                    "expected_m": 0,
                    "actual_m": after_config["m"],
                    "expected_payload_m": 16,
                    "actual_payload_m": after_config["payload_m"],
                }
            )

    except Exception as e:
        logger.error(
            "optimization_failed",
            extra={"collection": collection_name, "error": str(e)}
        )
        raise


def main():
    """Main entry point for HNSW optimization script."""
    parser = argparse.ArgumentParser(
        description="Optimize HNSW configuration for multi-tenancy (BP-002)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    parser.add_argument(
        "--collection",
        choices=COLLECTION_NAMES,
        help="Target specific collection (default: all collections)"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Qdrant host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=26350,
        help="Qdrant port (default: 26350)"
    )

    args = parser.parse_args()

    # Determine collections to optimize
    collections = [args.collection] if args.collection else COLLECTION_NAMES

    logger.info(
        "starting_optimization",
        extra={
            "collections": collections,
            "dry_run": args.dry_run,
            "host": args.host,
            "port": args.port,
        }
    )

    # Connect to Qdrant (BP-040)
    try:
        import os
        api_key = os.getenv("QDRANT_API_KEY")
        use_https = os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true"
        client = QdrantClient(
            host=args.host, port=args.port, api_key=api_key, https=use_https
        )
    except Exception as e:
        logger.error(
            "qdrant_connection_failed",
            extra={"host": args.host, "port": args.port, "error": str(e)}
        )
        sys.exit(1)

    # Optimize each collection
    failed_collections = []
    for collection_name in collections:
        try:
            optimize_collection(client, collection_name, dry_run=args.dry_run)
        except Exception as e:
            failed_collections.append(collection_name)
            logger.error(
                "collection_optimization_failed",
                extra={"collection": collection_name, "error": str(e)}
            )

    # Summary
    if args.dry_run:
        logger.info(
            "dry_run_complete",
            extra={
                "collections_checked": len(collections),
                "would_optimize": len(collections) - len(failed_collections),
            }
        )
    else:
        logger.info(
            "optimization_complete",
            extra={
                "collections_attempted": len(collections),
                "succeeded": len(collections) - len(failed_collections),
                "failed": len(failed_collections),
            }
        )

    if failed_collections:
        sys.exit(1)


if __name__ == "__main__":
    main()
