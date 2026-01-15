#!/usr/bin/env python3
"""Create Qdrant collections for BMAD Memory Module.

Creates two collections:
- implementations: Project-specific memory (isolated by group_id)
- best_practices: Shared knowledge across projects

Implements Story 1.3 AC 1.3.1.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PayloadSchemaType,
    KeywordIndexParams,
    TextIndexParams,
    TokenizerType,
)


def create_collections(host: str = "localhost", port: int = 26350) -> None:
    """Create Qdrant collections with proper schema.

    Args:
        host: Qdrant host
        port: Qdrant port

    Raises:
        Exception: If connection to Qdrant fails
    """
    client = QdrantClient(host=host, port=port)

    # Vector configuration (DEC-010: 768 dimensions from jina-embeddings-v2-base-code)
    vector_config = VectorParams(size=768, distance=Distance.COSINE)

    collection_names = ["implementations", "best_practices"]

    for collection_name in collection_names:
        # Create collection (delete first if exists)
        # Note: recreate_collection is deprecated in qdrant-client 1.8+
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
    create_collections()
