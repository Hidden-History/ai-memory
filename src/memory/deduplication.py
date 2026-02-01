"""Memory deduplication module with dual-stage checking.

Implements Story 2.2: Deduplication Module with modern 2025/2026 patterns:
- Stage 1: Hash-based exact match (fast, O(1) lookup)
- Stage 2: Embedding-based semantic similarity (thorough, O(log n) with ANN)

Architecture Reference: architecture.md - Dual-Stage Deduplication Decision
Best Practices: https://github.com/MinishLab/semhash (SemHash 2025 patterns)
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import (
    ApiException,
    ResponseHandlingException,
    UnexpectedResponse,
)
from qdrant_client.models import FieldCondition, Filter, MatchValue

from .config import get_config
from .embeddings import EmbeddingClient, EmbeddingError

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import deduplication_events_total
    from .metrics_push import (
        push_deduplication_metrics_async,  # BUG-021: Push to Pushgateway
    )
except ImportError:
    deduplication_events_total = None
    push_deduplication_metrics_async = None

__all__ = ["DuplicationCheckResult", "compute_content_hash", "is_duplicate"]

logger = logging.getLogger("ai_memory.dedup")


@dataclass
class DuplicationCheckResult:
    """Result of deduplication check.

    Attributes:
        is_duplicate: True if content is duplicate, False otherwise
        reason: Reason for result (hash_match, semantic_similarity, etc.)
        existing_id: ID of existing duplicate memory (if found)
        similarity_score: Cosine similarity score (if semantic check performed)
    """

    is_duplicate: bool
    reason: str | None = None
    existing_id: str | None = None
    similarity_score: float | None = None


def compute_content_hash(content: str | bytes) -> str:
    """Compute SHA-256 hash of content.

    Implements AC 2.2.5 (Content Hash Function).

    Uses SHA-256 industry standard (2025 recommendation) with utf-8 encoding.
    For large content (>4KB), uses chunked reading for memory efficiency.
    Supports both string and bytes input per AC 2.2.5.

    Args:
        content: String or bytes content to hash

    Returns:
        Hash string in format "sha256:<64-char hex digest>"

    Example:
        >>> compute_content_hash("def hello(): return 'world'")
        'sha256:a3f8d9e2...'
        >>> compute_content_hash(b"binary data")
        'sha256:...'
    """
    # Use chunked hashing for large content (>4KB) per 2025 best practices
    # Source: https://www.freecodecamp.org/news/how-to-perform-secure-hashing-using-pythons-hashlib-module/
    hash_obj = hashlib.sha256()

    # AC 2.2.5: Handle both string and bytes input
    content_bytes = content if isinstance(content, bytes) else content.encode("utf-8")

    # Chunk size: 4096 bytes (standard for file I/O)
    chunk_size = 4096
    for i in range(0, len(content_bytes), chunk_size):
        chunk = content_bytes[i : i + chunk_size]
        hash_obj.update(chunk)

    return f"sha256:{hash_obj.hexdigest()}"


async def is_duplicate(
    content: str,
    group_id: str,
    collection: str = "memories",
    threshold: float | None = None,
) -> DuplicationCheckResult:
    """Check if content is duplicate using dual-stage approach.

    Implements AC 2.2.1 (Dual-Stage Deduplication Module).
    Implements AC 2.2.2 (Configurable Similarity Threshold).
    Implements AC 2.2.3 (Async Error Handling).
    Implements AC 2.2.6 (Edge Cases and Error Scenarios).

    Process:
    1. Fast hash check (exact match detection) - Stage 1
    2. Semantic similarity check (near-duplicate detection) - Stage 2
    3. Fail open on errors (allow storage, false negative better than blocking)

    Args:
        content: Memory content to check
        group_id: Project identifier for multi-tenancy filtering
        collection: Qdrant collection name (default: "memories")
        threshold: Custom similarity threshold (overrides env var)

    Returns:
        DuplicationCheckResult with is_duplicate flag and metadata

    Performance:
        - Hash check: <50ms (AC 2.2.1)
        - Similarity check: <100ms (AC 2.2.1)
        - Total overhead: <100ms (NFR-P5)

    Example:
        >>> result = await is_duplicate("def test(): pass", "project-name")
        >>> result.is_duplicate
        False
    """
    # AC 2.2.6: Handle edge cases
    if not content or len(content) == 0:
        logger.debug("dedup_check_skipped", extra={"reason": "empty_content"})
        return DuplicationCheckResult(
            is_duplicate=False, reason="empty_content", existing_id=None
        )

    if len(content) < 10:
        logger.debug(
            "dedup_check_skipped",
            extra={"reason": "content_too_short", "length": len(content)},
        )
        return DuplicationCheckResult(
            is_duplicate=False, reason="content_too_short", existing_id=None
        )

    # Get configuration
    config = get_config()
    dedup_threshold = threshold if threshold is not None else config.dedup_threshold

    logger.debug(
        "dedup_check_started",
        extra={
            "group_id": group_id,
            "content_length": len(content),
            "threshold": dedup_threshold,
            "collection": collection,
        },
    )

    # Compute content hash for Stage 1
    content_hash = compute_content_hash(content)

    # Stage 1: Hash-based exact match (fast O(1) lookup)
    client = None
    try:
        # Fix: AsyncQdrantClient doesn't support async context manager protocol
        # Use manual client lifecycle management instead
        # BP-040: API key + HTTPS configurable via environment variables
        protocol = "https" if config.qdrant_use_https else "http"
        client = AsyncQdrantClient(
            url=f"{protocol}://{config.qdrant_host}:{config.qdrant_port}",
            api_key=config.qdrant_api_key,
        )

        # Query by content_hash field (indexed for fast lookup)
        results, _ = await client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="group_id", match=MatchValue(value=group_id)),
                    FieldCondition(
                        key="content_hash", match=MatchValue(value=content_hash)
                    ),
                ]
            ),
            limit=1,
        )

        if results:
            existing_id = str(results[0].id)
            logger.info(
                "duplicate_detected_hash",
                extra={
                    "content_hash": content_hash,
                    "existing_id": existing_id,
                    "group_id": group_id,
                },
            )

            # Metrics: Deduplication event detected (Story 6.1, AC 6.1.3)
            # BUG-021: Push to Pushgateway with action/collection labels
            if push_deduplication_metrics_async:
                push_deduplication_metrics_async(
                    action="skipped_duplicate", collection=collection, project=group_id
                )

            return DuplicationCheckResult(
                is_duplicate=True,
                reason="hash_match",
                existing_id=existing_id,
                similarity_score=None,
            )

        logger.debug(
            "hash_check_no_match",
            extra={"content_hash": content_hash, "group_id": group_id},
        )

        # Stage 2: Semantic similarity check (thorough, near-duplicate detection)
        try:
            # Generate embedding for query
            # Use asyncio.to_thread to avoid blocking event loop (2025 async best practice)
            def _get_embedding():
                with EmbeddingClient(config) as embed_client:
                    return embed_client.embed([content])[0]

            query_vector = await asyncio.to_thread(_get_embedding)

            # Search for similar memories with threshold
            search_results = await client.search(
                collection_name=collection,
                query_vector=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(key="group_id", match=MatchValue(value=group_id))
                    ]
                ),
                limit=1,
                score_threshold=dedup_threshold,
            )

            if search_results:
                match = search_results[0]
                existing_id = str(match.id)
                similarity_score = match.score

                logger.info(
                    "duplicate_detected_semantic",
                    extra={
                        "existing_id": existing_id,
                        "similarity_score": similarity_score,
                        "threshold": dedup_threshold,
                        "group_id": group_id,
                    },
                )

                # Metrics: Deduplication event detected (Story 6.1, AC 6.1.3)
                # BUG-021: Push to Pushgateway with action/collection labels
                if push_deduplication_metrics_async:
                    push_deduplication_metrics_async(
                        action="skipped_duplicate",
                        collection=collection,
                        project=group_id,
                    )

                return DuplicationCheckResult(
                    is_duplicate=True,
                    reason="semantic_similarity",
                    existing_id=existing_id,
                    similarity_score=similarity_score,
                )

            logger.debug(
                "similarity_check_no_match",
                extra={"threshold": dedup_threshold, "group_id": group_id},
            )

            # No duplicates found
            return DuplicationCheckResult(
                is_duplicate=False, reason=None, existing_id=None
            )

        except (EmbeddingError, Exception) as e:
            # AC 2.2.6: Embedding service down - skip similarity check, use hash only
            logger.warning(
                "embedding_failed_hash_only",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "group_id": group_id,
                },
            )
            # Hash check passed (no exact match), embedding failed
            # Fail open: allow storage
            return DuplicationCheckResult(
                is_duplicate=False,
                reason="embedding_failed_hash_only",
                existing_id=None,
            )

    except ResponseHandlingException as e:
        # AC 2.2.3: Handle Qdrant API errors (includes 429 rate limiting)
        logger.warning(
            "dedup_failed_response_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "group_id": group_id,
                "stage": "qdrant_query",
            },
        )
        # Fail open: allow storage on error
        return DuplicationCheckResult(
            is_duplicate=False, reason="error_fail_open", existing_id=None
        )

    except UnexpectedResponse as e:
        # AC 2.2.3: Handle malformed responses
        logger.warning(
            "dedup_failed_unexpected_response",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "group_id": group_id,
                "stage": "qdrant_query",
            },
        )
        # Fail open: allow storage on error
        return DuplicationCheckResult(
            is_duplicate=False, reason="error_fail_open", existing_id=None
        )

    except ConnectionRefusedError as e:
        # AC 2.2.6: Qdrant unavailable - fail open
        logger.warning(
            "dedup_failed_qdrant_unavailable",
            extra={"error": str(e), "group_id": group_id},
        )
        return DuplicationCheckResult(
            is_duplicate=False, reason="error_fail_open", existing_id=None
        )

    except ApiException as e:
        # AC 2.2.3: Handle base Qdrant API exception (catches any Qdrant error not
        # caught above by ResponseHandlingException or UnexpectedResponse)
        logger.warning(
            "dedup_failed_api_error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "group_id": group_id,
                "stage": "qdrant_query",
            },
        )
        # Fail open: allow storage on error
        return DuplicationCheckResult(
            is_duplicate=False, reason="error_fail_open", existing_id=None
        )

    except Exception as e:
        # AC 2.2.6: NEVER crash - catch-all for unexpected errors
        logger.error(
            "dedup_failed_unexpected",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "group_id": group_id,
            },
        )
        # Fail open: allow storage on any error
        return DuplicationCheckResult(
            is_duplicate=False, reason="error_fail_open", existing_id=None
        )

    finally:
        # Clean up client connection
        if client is not None:
            try:
                await client.close()
            except Exception as e:
                # Silently ignore close errors to avoid masking return values
                logger.debug(
                    "client_close_failed",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
