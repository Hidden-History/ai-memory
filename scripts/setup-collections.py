#!/usr/bin/env python3
"""Create Qdrant collections for AI Memory Module.

Creates up to five v2.0 collections:
- code-patterns: HOW things are built (implementation, error_pattern, refactor, file_pattern)
- conventions: WHAT rules to follow (guideline, anti_pattern, decision)
- discussions: WHY things were decided (session, conversation, analysis, reflection)
- github: GitHub code/issues/PRs (PLAN-010: separated from discussions)
- jira-data: Jira issues and comments (enabled when jira_sync_enabled=true)

Implements Story 1.3 AC 1.3.1.

v2.2.1 (PLAN-013): Added sparse vector config (BM25/IDF) for hybrid search,
and optional ColBERT named vector for late interaction reranking.
"""

import logging
import os
import sys
from pathlib import Path

# Add src to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseVectorParams,
    VectorParams,
)

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
    get_config,
)
from memory.qdrant_client import ensure_payload_indexes, get_qdrant_client

logger = logging.getLogger(__name__)


def create_collections(dry_run: bool = False, force: bool = False) -> None:
    """Create Qdrant collections with proper schema.

    Args:
        dry_run: If True, preview what would be created without making changes
        force: If True, delete and recreate existing collections (DATA LOSS).
            Default (False) skips existing collections for safe re-install.

    Raises:
        Exception: If connection to Qdrant fails
    """
    config = get_config()
    client = get_qdrant_client(config)

    if dry_run:
        print(
            f"DRY RUN: Would connect to Qdrant at {config.qdrant_host}:{config.qdrant_port}"
        )
        print(
            f"DRY RUN: API key configured: {'Yes' if config.qdrant_api_key else 'No'}"
        )
        print(f"DRY RUN: HTTPS enabled: {config.qdrant_use_https}")

    # Vector configuration (DEC-010: 768 dimensions from jina-embeddings-v2-base-code)
    vector_config = VectorParams(size=768, distance=Distance.COSINE)

    # v2.2.1 (PLAN-013): Sparse vector config for hybrid dense+sparse search
    sparse_config = {
        "bm25": SparseVectorParams(modifier=Modifier.IDF),
    }

    # v2.2.1 (PLAN-013): Optional ColBERT named vector for late interaction reranking
    # When enabled, vectors_config becomes a dict with "" (default dense) + "colbert"
    colbert_enabled = os.getenv("COLBERT_RERANKING_ENABLED", "false").lower() == "true"
    vectors_config_dict = None
    if colbert_enabled:
        from qdrant_client.models import MultiVectorComparator, MultiVectorConfig

        vectors_config_dict = {
            "": VectorParams(size=768, distance=Distance.COSINE),  # Default dense
            "colbert": VectorParams(
                size=128,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(
                    comparator=MultiVectorComparator.MAX_SIM
                ),
                hnsw_config=HnswConfigDiff(m=0),  # Disable HNSW for reranking-only
            ),
        }
        print(
            "ColBERT reranking enabled — adding 'colbert' named vector to collections"
        )

    # V2.0 Collections (Memory System Spec v2.0, 2026-01-17)
    collection_names = [
        COLLECTION_CODE_PATTERNS,  # code-patterns
        COLLECTION_CONVENTIONS,  # conventions
        COLLECTION_DISCUSSIONS,  # discussions
        COLLECTION_GITHUB,  # github
    ]

    # Conditionally add jira-data collection (PLAN-004 Phase 2)
    if config.jira_sync_enabled:
        collection_names.append(COLLECTION_JIRA_DATA)
        print(f"Jira sync enabled - adding {COLLECTION_JIRA_DATA} collection")

    failed_collections = []

    for collection_name in collection_names:
        # Create collection (delete first if exists)
        # Note: recreate_collection is deprecated in qdrant-client 1.8+
        if dry_run:
            exists = client.collection_exists(collection_name)
            print(f"DRY RUN: Collection '{collection_name}' exists: {exists}")
            action = (
                "recreate" if exists and force else ("skip" if exists else "create")
            )
            print(f"DRY RUN: Would {action} collection '{collection_name}'")
            continue

        try:
            if client.collection_exists(collection_name):
                if not force:
                    print(
                        f"Collection '{collection_name}' already exists (skipping, use --force to recreate)"
                    )
                    continue
                client.delete_collection(collection_name)

            # BP-038 Section 2.1: HNSW on-disk for memory efficiency
            # BUG-114: full_scan_threshold=10000 means Qdrant uses brute-force search
            # (not HNSW) for collections with fewer than 10K vectors. This is expected
            # behavior — indexed_vectors_count=0 does NOT mean search is broken; it means
            # no HNSW graph was built yet. Search works via brute-force scan for any
            # points that have real (non-zero) embeddings.
            # Reference: https://qdrant.tech/documentation/concepts/indexing/#vector-index
            # TD-106: inline_storage=True (v1.16.3) stores vectors inline in HNSW graph
            # nodes for improved CPU cache efficiency during ANN traversal.
            hnsw_config = HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
                on_disk=True,
                inline_storage=True,
            )

            # BP-038 Section 2.1: Scalar int8 quantization for 4x compression
            quantization_config = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            )

            # Use ColBERT dict (with default "" + "colbert") when enabled,
            # otherwise use the single VectorParams (unnamed default)
            effective_vectors_config = (
                vectors_config_dict if colbert_enabled else vector_config
            )

            client.create_collection(
                collection_name=collection_name,
                vectors_config=effective_vectors_config,
                sparse_vectors_config=sparse_config,
                hnsw_config=hnsw_config,
                quantization_config=quantization_config,
            )

            # Create the canonical payload indexes for filtering.
            # These enable fast payload filtering for multi-tenancy and
            # provenance, full-text hybrid search, and recency ordering.
            # The set (base + per-collection extras) is authored once in
            # memory.qdrant_client so every recreate path stays in sync.
            ensured = ensure_payload_indexes(client, collection_name)
            print(f"  Created {len(ensured)} payload indexes")

        except Exception as e:
            logger.error(f"Failed to setup {collection_name}: {e}")
            print(f"WARNING: Setup failed for {collection_name}: {e}", file=sys.stderr)
            failed_collections.append(collection_name)
            continue

        print(f"Created collection: {collection_name}")

    if failed_collections:
        print(
            f"WARNING: Failed collections: {', '.join(failed_collections)}",
            file=sys.stderr,
        )
        sys.exit(1)


def migrate_inline_storage() -> tuple[list[str], list[str]]:
    """Update existing collections to enable inline_storage in HNSW config.

    TD-106: Qdrant v1.16.3 supports inline_storage for improved HNSW graph
    cache efficiency. Updates existing collections without recreating them.

    Returns:
        Tuple of (updated_collections, skipped_collections).
    """
    config = get_config()
    client = get_qdrant_client(config)

    collection_names = [
        COLLECTION_CODE_PATTERNS,
        COLLECTION_CONVENTIONS,
        COLLECTION_DISCUSSIONS,
        COLLECTION_GITHUB,
    ]
    if config.jira_sync_enabled:
        collection_names.append(COLLECTION_JIRA_DATA)

    updated: list[str] = []
    skipped: list[str] = []

    for name in collection_names:
        if not client.collection_exists(name):
            logger.info("Collection does not exist, skipping migration: %s", name)
            skipped.append(name)
            continue
        try:
            client.update_collection(
                collection_name=name,
                hnsw_config=HnswConfigDiff(inline_storage=True),
            )
            updated.append(name)
            print(f"Migrated inline_storage: {name}")
        except Exception as e:
            logger.warning("Failed to migrate %s: %s", name, e)
            skipped.append(name)

    print(f"Migration complete: {len(updated)} updated, {len(skipped)} skipped")
    return updated, skipped


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Create Qdrant collections for AI Memory Module (V2.0)"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Default command: create collections
    create_parser = subparsers.add_parser(
        "create", help="Create Qdrant collections (default)"
    )
    create_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be created without making changes",
    )
    create_parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and recreate existing collections (DATA LOSS)",
    )

    # TD-106: migrate existing collections to enable inline_storage
    subparsers.add_parser(
        "migrate-inline-storage",
        help="Update existing collections to enable inline_storage in HNSW config (TD-106)",
    )

    # Legacy: no subcommand → behave as 'create' for backwards compatibility
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be created without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete and recreate existing collections (DATA LOSS)",
    )

    args = parser.parse_args()

    if args.command == "migrate-inline-storage":
        migrate_inline_storage()
    else:
        create_collections(dry_run=args.dry_run, force=args.force)
