#!/usr/bin/env python3
"""Create Qdrant collections for AI Memory Module.

Creates up to four v2.0 collections:
- code-patterns: HOW things are built (implementation, error_fix, refactor, file_pattern)
- conventions: WHAT rules to follow (guideline, anti_pattern, decision)
- discussions: WHY things were decided (session, conversation, analysis, reflection)
- jira-data: Jira issues and comments (enabled when jira_sync_enabled=true)

Implements Story 1.3 AC 1.3.1.
"""

import logging
import sys
from pathlib import Path

# Add src to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    KeywordIndexParams,
    PayloadSchemaType,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    TextIndexParams,
    TokenizerType,
    VectorParams,
)

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_JIRA_DATA,
    get_config,
)
from memory.qdrant_client import get_qdrant_client

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

    # V2.0 Collections (Memory System Spec v2.0, 2026-01-17)
    collection_names = [
        COLLECTION_CODE_PATTERNS,  # code-patterns
        COLLECTION_CONVENTIONS,  # conventions
        COLLECTION_DISCUSSIONS,  # discussions
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
            hnsw_config = HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
                on_disk=True,
            )

            # BP-038 Section 2.1: Scalar int8 quantization for 4x compression
            quantization_config = ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            )

            client.create_collection(
                collection_name=collection_name,
                vectors_config=vector_config,
                hnsw_config=hnsw_config,
                quantization_config=quantization_config,
            )

            # Create keyword indexes for filtering
            # These enable fast payload filtering for multi-tenancy and provenance

            # group_id uses is_tenant=True for optimized multi-project storage layout
            client.create_payload_index(
                collection_name=collection_name,
                field_name="group_id",
                field_schema=KeywordIndexParams(
                    type="keyword",
                    is_tenant=True,  # Optimizes storage for multi-tenant filtering
                ),
            )

            client.create_payload_index(
                collection_name=collection_name,
                field_name="type",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            client.create_payload_index(
                collection_name=collection_name,
                field_name="source_hook",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            # BP-038 Section 3.3: content_hash index for O(1) dedup lookup
            client.create_payload_index(
                collection_name=collection_name,
                field_name="content_hash",
                field_schema=KeywordIndexParams(type="keyword"),
            )

            # Create full-text index on content field
            # Enables hybrid search (semantic + keyword)
            client.create_payload_index(
                collection_name=collection_name,
                field_name="content",
                field_schema=TextIndexParams(
                    type="text",
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=20,
                ),
            )

            # BP-038 Section 2.1: timestamp index for recency queries
            client.create_payload_index(
                collection_name=collection_name,
                field_name="timestamp",
                field_schema=PayloadSchemaType.DATETIME,
            )

            # v2.0.6: Freshness and decay payload indexes (SPEC-008, FAIL-003 fix)
            client.create_payload_index(
                collection_name=collection_name,
                field_name="decay_score",
                field_schema=PayloadSchemaType.FLOAT,
            )

            client.create_payload_index(
                collection_name=collection_name,
                field_name="freshness_status",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            client.create_payload_index(
                collection_name=collection_name,
                field_name="source_authority",
                field_schema=PayloadSchemaType.FLOAT,
            )

            client.create_payload_index(
                collection_name=collection_name,
                field_name="is_current",
                field_schema=PayloadSchemaType.BOOL,
            )

            client.create_payload_index(
                collection_name=collection_name,
                field_name="version",
                field_schema=PayloadSchemaType.INTEGER,
            )

            # BP-038 Section 2.1: file_path index for code-patterns only
            # Enables file-specific pattern lookup
            if collection_name == COLLECTION_CODE_PATTERNS:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name="file_path",
                    field_schema=PayloadSchemaType.KEYWORD,
                )

            # PLAN-004 Phase 2: Jira-specific indexes for jira-data collection
            if collection_name == COLLECTION_JIRA_DATA:
                jira_indexes = [
                    ("jira_project", PayloadSchemaType.KEYWORD),
                    ("jira_issue_key", PayloadSchemaType.KEYWORD),
                    ("jira_issue_type", PayloadSchemaType.KEYWORD),
                    ("jira_status", PayloadSchemaType.KEYWORD),
                    ("jira_priority", PayloadSchemaType.KEYWORD),
                    ("jira_author", PayloadSchemaType.KEYWORD),
                    ("jira_reporter", PayloadSchemaType.KEYWORD),
                    ("jira_labels", PayloadSchemaType.KEYWORD),
                    ("jira_comment_id", PayloadSchemaType.KEYWORD),
                ]

                for field_name, schema_type in jira_indexes:
                    client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field_name,
                        field_schema=schema_type,
                    )

                print(f"  Created {len(jira_indexes)} Jira-specific indexes")

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


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Create Qdrant collections for AI Memory Module (V2.0)"
    )
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
    create_collections(dry_run=args.dry_run, force=args.force)
