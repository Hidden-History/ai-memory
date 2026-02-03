#!/usr/bin/env python3
"""Create Qdrant collections for AI Memory Module.

Creates three v2.0 collections:
- code-patterns: HOW things are built (implementation, error_fix, refactor, file_pattern)
- conventions: WHAT rules to follow (guideline, anti_pattern, decision)
- discussions: WHY things were decided (session, conversation, analysis, reflection)

Implements Story 1.3 AC 1.3.1.
"""

import sys
from pathlib import Path

# Add src to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client.models import (
    Distance,
    KeywordIndexParams,
    PayloadSchemaType,
    TextIndexParams,
    TokenizerType,
    VectorParams,
)

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    get_config,
)
from memory.qdrant_client import get_qdrant_client


def create_collections(dry_run: bool = False) -> None:
    """Create Qdrant collections with proper schema.

    Args:
        dry_run: If True, preview what would be created without making changes

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

    for collection_name in collection_names:
        # Create collection (delete first if exists)
        # Note: recreate_collection is deprecated in qdrant-client 1.8+
        if dry_run:
            exists = client.collection_exists(collection_name)
            print(f"DRY RUN: Collection '{collection_name}' exists: {exists}")
            print(
                f"DRY RUN: Would {'recreate' if exists else 'create'} collection '{collection_name}'"
            )
            continue

        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
        client.create_collection(
            collection_name=collection_name, vectors_config=vector_config
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

        print(f"Created collection: {collection_name}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create Qdrant collections for AI Memory Module (V2.0)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be created without making changes",
    )
    args = parser.parse_args()
    create_collections(dry_run=args.dry_run)
