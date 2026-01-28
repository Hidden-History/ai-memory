"""Qdrant client wrapper for AI Memory Module.

Provides singleton-pattern Qdrant client with health checking and structured logging.
Implements 2025 best practices for connection management and error handling.

Architecture Reference: architecture.md:235-287 (Service Client Architecture)
Best Practices: https://softlandia.com/articles/deploying-qdrant-with-grpc-auth-on-azure-a-fastapi-singleton-client-guide
"""

import logging
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import KeywordIndexParams

from .config import MemoryConfig, get_config

__all__ = [
    "get_qdrant_client",
    "check_qdrant_health",
    "create_group_id_index",
    "QdrantUnavailable",
]

logger = logging.getLogger("ai_memory.storage")


class QdrantUnavailable(Exception):
    """Raised when Qdrant is not available.

    This exception indicates Qdrant is unreachable or unhealthy.
    Callers should implement graceful degradation (e.g., queue to file).
    """

    pass


def get_qdrant_client(config: Optional[MemoryConfig] = None) -> QdrantClient:
    """Get configured Qdrant client.

    Creates QdrantClient instance with connection parameters from config.
    Uses singleton pattern via module-level caching (future enhancement for FastAPI).

    Args:
        config: Optional MemoryConfig instance. Uses get_config() if not provided.

    Returns:
        Configured QdrantClient instance.

    Example:
        >>> client = get_qdrant_client()
        >>> collections = client.get_collections()
        >>> print([c.name for c in collections.collections])
        ['code-patterns', 'conventions', 'discussions']

    Note:
        For FastAPI applications, consider registering client in lifespan function
        for true singleton pattern. See:
        https://softlandia.com/articles/deploying-qdrant-with-grpc-auth-on-azure-a-fastapi-singleton-client-guide
    """
    config = config or get_config()

    # Create client with timeout configuration
    # Timeout prevents indefinite hangs if Qdrant is unresponsive
    # BP-040: API key + HTTPS configurable via environment variables
    client = QdrantClient(
        host=config.qdrant_host,
        port=config.qdrant_port,
        api_key=config.qdrant_api_key,
        https=config.qdrant_use_https,
        timeout=10,
    )

    return client


def check_qdrant_health(client: QdrantClient) -> bool:
    """Check if Qdrant is healthy.

    Attempts to list collections to verify Qdrant is accessible and responsive.

    Args:
        client: QdrantClient instance to check.

    Returns:
        True if Qdrant responds successfully, False otherwise.

    Example:
        >>> client = get_qdrant_client()
        >>> if check_qdrant_health(client):
        ...     # Proceed with Qdrant operations
        ...     client.upsert(...)
        ... else:
        ...     # Graceful degradation: queue to file
        ...     queue_to_file(memory)
    """
    try:
        # get_collections() is a lightweight operation that verifies connectivity
        client.get_collections()
        return True

    except Exception as e:
        # Log with structured extras for observability
        logger.warning(
            "qdrant_unhealthy",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return False


def create_group_id_index(
    client: QdrantClient, collection_name: str = "code-patterns"
) -> None:
    """Create payload index for group_id field with is_tenant=True optimization.

    Implements AC 4.2.3: Payload index creation for optimal multi-project filtering.

    Per Qdrant 1.16+ multitenancy best practices:
    - is_tenant=True co-locates same-tenant vectors for disk/CPU cache efficiency
    - Query planner can bypass HNSW for low-cardinality filters (<10ms overhead)
    - Single collection with payload filtering is more efficient than separate collections

    Args:
        client: QdrantClient instance
        collection_name: Collection to create index on (default: "code-patterns")

    Raises:
        Exception: If index creation fails (critical error - do not proceed)

    Example:
        >>> client = get_qdrant_client()
        >>> create_group_id_index(client, "code-patterns")
        >>> # Index now enables fast filtering by group_id

    References:
        - https://qdrant.tech/blog/qdrant-1.16.x/ (Tiered Multitenancy)
        - https://qdrant.tech/articles/multitenancy/ (Multitenancy Guide)
    """
    try:
        # Create keyword index with is_tenant=True for co-location (AC 4.2.3)
        client.create_payload_index(
            collection_name=collection_name,
            field_name="group_id",
            field_schema=KeywordIndexParams(
                type="keyword",
                is_tenant=True,  # Critical: co-locates same-tenant vectors
            ),
        )

        logger.info(
            "group_id_index_created",
            extra={
                "collection": collection_name,
                "field": "group_id",
                "is_tenant": True,
            },
        )

    except Exception as e:
        # Critical error: Log and re-raise (don't proceed without index)
        logger.error(
            "index_creation_failed",
            extra={
                "collection": collection_name,
                "field": "group_id",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
