"""Qdrant client wrapper for AI Memory Module.

Provides singleton-pattern Qdrant client with health checking and structured logging.
Implements 2025 best practices for connection management and error handling.

Architecture Reference: architecture.md:235-287 (Service Client Architecture)
Best Practices: https://softlandia.com/articles/deploying-qdrant-with-grpc-auth-on-azure-a-fastapi-singleton-client-guide
"""

import hashlib
import logging
import os
import warnings
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    KeywordIndexParams,
    PayloadSchemaType,
    TextIndexParams,
    TokenizerType,
)

from .config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
    MemoryConfig,
    get_config,
)

__all__ = [
    "BASE_PAYLOAD_INDEXES",
    "COLLECTION_PAYLOAD_INDEXES",
    "QdrantUnavailable",
    "canonical_payload_indexes",
    "check_qdrant_health",
    "ensure_payload_indexes",
    "get_qdrant_client",
]

logger = logging.getLogger("ai_memory.storage")

_client_cache: dict[str, "QdrantClient"] = {}

# ─── Canonical payload-index set (BUG-530 / PLAN-036 P1) ──────────────────────
# Single authoring site for the payload indexes every collection must carry.
# Previously duplicated only in scripts/setup-collections.py, so every other
# collection-recreate path left a collection with zero or partial indexes —
# silently degrading retrieval (a missing `timestamp` range index makes
# get_recent() raise QdrantUnavailable).

# Indexes every collection gets.
BASE_PAYLOAD_INDEXES: dict[str, Any] = {
    # group_id uses is_tenant=True for optimized multi-project storage layout
    "group_id": KeywordIndexParams(type="keyword", is_tenant=True),
    "type": PayloadSchemaType.KEYWORD,
    "source_hook": PayloadSchemaType.KEYWORD,
    # BP-038 Section 3.3: content_hash index for O(1) dedup lookup
    "content_hash": KeywordIndexParams(type="keyword"),
    # Full-text index on content enables hybrid search (semantic + keyword)
    "content": TextIndexParams(
        type="text",
        tokenizer=TokenizerType.WORD,
        min_token_len=2,
        max_token_len=20,
    ),
    # BP-038 Section 2.1: timestamp index for recency queries (order_by)
    "timestamp": PayloadSchemaType.DATETIME,
    # v2.0.6: Freshness and decay payload indexes (SPEC-008, FAIL-003 fix)
    "decay_score": PayloadSchemaType.FLOAT,
    "freshness_status": PayloadSchemaType.KEYWORD,
    "source_authority": PayloadSchemaType.FLOAT,
    "is_current": PayloadSchemaType.BOOL,
    "version": PayloadSchemaType.INTEGER,
}

# Additional indexes for specific collections.
COLLECTION_PAYLOAD_INDEXES: dict[str, dict[str, Any]] = {
    # BP-038 Section 2.1: file_path enables file-specific pattern lookup
    COLLECTION_CODE_PATTERNS: {
        "file_path": PayloadSchemaType.KEYWORD,
    },
    # Parzival agent_id index enables tenant-optimized agent_id filtering
    COLLECTION_DISCUSSIONS: {
        "agent_id": KeywordIndexParams(type="keyword", is_tenant=True),
    },
    # PLAN-010: GitHub-specific indexes
    COLLECTION_GITHUB: {
        "source": KeywordIndexParams(type="keyword", is_tenant=True),
        "github_id": PayloadSchemaType.INTEGER,
        "file_path": PayloadSchemaType.KEYWORD,
        "sha": PayloadSchemaType.KEYWORD,
        "state": PayloadSchemaType.KEYWORD,
        "last_synced": PayloadSchemaType.DATETIME,
        "update_batch_id": PayloadSchemaType.KEYWORD,
    },
    # PLAN-004 Phase 2: Jira-specific indexes
    COLLECTION_JIRA_DATA: {
        "jira_project": PayloadSchemaType.KEYWORD,
        "jira_issue_key": PayloadSchemaType.KEYWORD,
        "jira_issue_type": PayloadSchemaType.KEYWORD,
        "jira_status": PayloadSchemaType.KEYWORD,
        "jira_priority": PayloadSchemaType.KEYWORD,
        "jira_author": PayloadSchemaType.KEYWORD,
        "jira_reporter": PayloadSchemaType.KEYWORD,
        "jira_labels": PayloadSchemaType.KEYWORD,
        "jira_comment_id": PayloadSchemaType.KEYWORD,
    },
}


class QdrantUnavailable(Exception):
    """Raised when Qdrant is not available.

    This exception indicates Qdrant is unreachable or unhealthy.
    Callers should implement graceful degradation (e.g., queue to file).
    """

    pass


def get_qdrant_client(
    config: MemoryConfig | None = None, read_only: bool = False
) -> QdrantClient:
    """Get configured Qdrant client.

    Creates QdrantClient instance with connection parameters from config.
    Uses singleton pattern via module-level caching (future enhancement for FastAPI).

    Args:
        config: Optional MemoryConfig instance. Uses get_config() if not provided.
        read_only: If True, prefer qdrant_read_only_api_key for search operations.

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

    # Resolve effective API key: prefer read-only key for search, fall back to main key
    effective_key = None
    if read_only and config.qdrant_read_only_api_key:
        effective_key = config.qdrant_read_only_api_key
    elif config.qdrant_api_key:
        effective_key = config.qdrant_api_key

    key_fingerprint = ""
    if effective_key:
        # TD-371: hash prevents raw key from appearing in cache key or logs
        key_fingerprint = hashlib.sha256(
            effective_key.get_secret_value().encode()
        ).hexdigest()[:8]
    cache_key = f"{config.qdrant_host}:{config.qdrant_port}:{key_fingerprint}:{config.qdrant_use_https}"
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    # Create client with timeout configuration
    # Timeout prevents indefinite hangs if Qdrant is unresponsive
    # BP-040: API key + HTTPS configurable via environment variables
    # BUG-099/102: Suppress insecure connection warning for known-safe hosts.
    # Localhost and Docker internal DNS are safe — traffic never leaves the
    # machine or Docker network. Remote hosts are NOT suppressed to preserve
    # the security warning for genuine misconfigurations.
    _safe_hosts = {"localhost", "127.0.0.1", "qdrant", "host.docker.internal"}
    if config.qdrant_host in _safe_hosts and not config.qdrant_use_https:
        warnings.filterwarnings(
            "ignore", message="Api key is used with an insecure connection"
        )

    api_key_value = effective_key.get_secret_value() if effective_key else None

    # TD-107: prefer gRPC for lower latency; fall back to HTTP if unavailable.
    # NOTE: QdrantClient construction does not establish a connection, so we
    # probe with get_collections() to detect gRPC unavailability at init time.
    grpc_port = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
    try:
        client = QdrantClient(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=api_key_value,
            https=config.qdrant_use_https,
            timeout=config.qdrant_timeout,
            prefer_grpc=True,
            grpc_port=grpc_port,
            check_compatibility=False,
        )
        # Probe to verify gRPC is reachable (construction alone does not connect)
        client.get_collections()
        logger.debug("qdrant_client_grpc", extra={"grpc_port": grpc_port})
    except Exception as grpc_error:
        logger.warning(
            "grpc_unavailable_falling_back_to_http",
            extra={"error": str(grpc_error)},
        )
        client = QdrantClient(
            host=config.qdrant_host,
            port=config.qdrant_port,
            api_key=api_key_value,
            https=config.qdrant_use_https,
            timeout=config.qdrant_timeout,
            check_compatibility=False,
        )

    _client_cache[cache_key] = client
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


def canonical_payload_indexes(collection_name: str) -> dict[str, Any]:
    """Return the canonical payload indexes for a collection.

    Args:
        collection_name: Collection to resolve indexes for. Unknown names get
            the base set only.

    Returns:
        Mapping of field name to the field schema it must be indexed with.
    """
    return {
        **BASE_PAYLOAD_INDEXES,
        **COLLECTION_PAYLOAD_INDEXES.get(collection_name, {}),
    }


def ensure_payload_indexes(client: QdrantClient, collection_name: str) -> list[str]:
    """Create every canonical payload index on a collection.

    Idempotent: ``create_payload_index`` is a no-op when the index already
    exists, so this is safe to call unconditionally on both new and existing
    collections. Call it after any path that creates or recreates a collection.

    Args:
        client: QdrantClient instance.
        collection_name: Collection to index.

    Returns:
        The field names that were ensured, in creation order.

    Raises:
        Exception: Propagates the client error if an index cannot be created.
            Callers that must not abort on a single index failure (migration
            and restore backstops) are responsible for catching it.
        RuntimeError: if, after every create call, a canonical field is still
            missing from ``get_collection().payload_schema``. The SDK's
            ``create_payload_index`` defaults ``wait=True`` (synchronous), but
            BP-194 Q1: ``wait`` is itself bounded by an internal update-queue
            timeout, so this reads back the live schema to confirm the index
            actually landed rather than trusting the create call alone.
    """
    fields = canonical_payload_indexes(collection_name)
    for field_name, field_schema in fields.items():
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_schema,
        )

    live_fields = set(client.get_collection(collection_name).payload_schema or {})
    missing = set(fields) - live_fields
    if missing:
        raise RuntimeError(
            f"Canonical payload indexes missing on '{collection_name}' after "
            f"ensure_payload_indexes: {sorted(missing)}"
        )

    logger.info(
        "payload_indexes_ensured",
        extra={"collection": collection_name, "fields": len(fields)},
    )
    return list(fields)
