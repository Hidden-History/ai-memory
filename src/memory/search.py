"""Memory search operations with semantic similarity and filtering.

Provides MemorySearch class for searching stored memories using Qdrant vector search
with configurable filtering, dual-collection support, and tiered result formatting.

Architecture Reference: architecture.md:747-863 (Search Module)
Best Practices (2025/2026):
- https://qdrant.tech/articles/vector-search-filtering/
- https://qdrant.tech/articles/vector-search-resource-optimization/
"""

import logging
import time
from typing import Optional

from qdrant_client.models import Filter, FieldCondition, MatchValue

from .config import MemoryConfig, get_config
from .embeddings import EmbeddingClient, EmbeddingError
from .qdrant_client import get_qdrant_client, QdrantUnavailable

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import (
        retrieval_duration_seconds,
        memory_retrievals_total,
        failure_events_total,
    )
except ImportError:
    retrieval_duration_seconds = None
    memory_retrievals_total = None
    failure_events_total = None

__all__ = ["MemorySearch", "retrieve_best_practices"]

logger = logging.getLogger("bmad.memory.retrieve")


class MemorySearch:
    """Handles memory search operations with semantic similarity.

    Provides semantic search with configurable filtering by group_id and memory_type,
    dual-collection search (implementations + best_practices), and tiered result
    formatting for context injection.

    Implements 2025 best practices:
    - Filter, FieldCondition, MatchValue for type-safe filtering
    - Client reuse for connection pooling (60%+ latency reduction)
    - Fail-fast error handling for graceful degradation
    - Structured logging with extras dict

    Attributes:
        config: MemoryConfig instance with search parameters
        client: Qdrant client for vector search operations
        embedding_client: Client for generating query embeddings

    Example:
        >>> search = MemorySearch()
        >>> results = search.search(
        ...     query="Python async patterns",
        ...     group_id="my-project",
        ...     limit=5
        ... )
        >>> len(results)
        5
        >>> results[0]["score"]
        0.95
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        """Initialize memory search with configuration.

        Args:
            config: Optional MemoryConfig instance. Uses get_config() if not provided.

        Note:
            Creates long-lived clients with connection pooling. Reuse this
            MemorySearch instance across requests for optimal performance.
        """
        self.config = config or get_config()
        self.client = get_qdrant_client(self.config)
        self.embedding_client = EmbeddingClient(self.config)

    def search(
        self,
        query: str,
        collection: str = "implementations",
        cwd: Optional[str] = None,
        group_id: Optional[str] = None,
        limit: Optional[int] = None,
        score_threshold: Optional[float] = None,
        memory_type: Optional[str] = None,
    ) -> list[dict]:
        """Search for relevant memories using semantic similarity with project scoping.

        Generates query embedding, builds filter conditions, and searches Qdrant
        collection for matching memories. Returns results sorted by similarity score.

        Implements AC 4.2.2: Supports automatic project detection via cwd parameter.

        Args:
            query: Search query text (will be embedded for semantic search)
            collection: Collection name ("implementations" or "best_practices")
            cwd: Optional path for automatic project detection (auto-sets group_id)
            group_id: Optional filter by project group_id (None = search all, overrides cwd)
            limit: Maximum results to return (defaults to config.max_retrievals)
            score_threshold: Minimum similarity score (defaults to config.similarity_threshold)
            memory_type: Optional filter by memory type (e.g., "implementation", "pattern")

        Returns:
            List of memory dicts with score, id, and all payload fields.
            Sorted by similarity score (highest first).

        Raises:
            EmbeddingError: If embedding service is unavailable
            QdrantUnavailable: If Qdrant search fails (caller handles graceful degradation)

        Example:
            >>> search = MemorySearch()
            >>> results = search.search(
            ...     query="database connection pooling",
            ...     cwd="/path/to/project",  # Auto-detect project
            ...     memory_type="implementation"
            ... )
            >>> results[0].keys()
            dict_keys(['id', 'score', 'content', 'group_id', 'type', ...])
        """
        # Auto-detect group_id from cwd if not explicitly provided (AC 4.2.2)
        if cwd is not None and group_id is None:
            try:
                from .project import detect_project

                group_id = detect_project(cwd)
                logger.debug(
                    "search_project_detected",
                    extra={"cwd": cwd, "group_id": group_id},
                )
            except Exception as e:
                # Graceful degradation: search without filter
                logger.warning(
                    "search_project_detection_failed",
                    extra={
                        "cwd": cwd,
                        "error": str(e),
                        "fallback": "no_filter",
                    },
                )
                group_id = None
        # Use config defaults if not provided
        limit = limit or self.config.max_retrievals
        score_threshold = score_threshold or self.config.similarity_threshold

        # Generate query embedding
        # Propagates EmbeddingError for graceful degradation
        query_embedding = self.embedding_client.embed([query])[0]

        # Build filter conditions using 2025 best practice: model-based Filter API
        filter_conditions = []
        # CRITICAL: Use explicit None check (not truthy) per AC 4.3.2
        # Prevents incorrect behavior with empty string group_id=""
        if group_id is not None:
            filter_conditions.append(
                FieldCondition(key="group_id", match=MatchValue(value=group_id))
            )
            logger.debug(
                "group_id_filter_applied",
                extra={"group_id": group_id, "collection": collection},
            )
        else:
            logger.debug(
                "no_group_id_filter",
                extra={"collection": collection, "reason": "group_id is None"},
            )
        if memory_type:
            filter_conditions.append(
                FieldCondition(key="type", match=MatchValue(value=memory_type))
            )

        query_filter = (
            Filter(must=filter_conditions) if filter_conditions else None
        )

        # Search Qdrant using query_points (qdrant-client 1.16+ API)
        # Wraps exceptions in QdrantUnavailable for graceful degradation (AC 1.6.4)
        start_time = time.perf_counter()
        try:
            response = self.client.query_points(
                collection_name=collection,
                query=query_embedding,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            results = response.points

            # Metrics: Record retrieval duration (Story 6.1, AC 6.1.3)
            if retrieval_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                retrieval_duration_seconds.observe(duration_seconds)

        except Exception as e:
            # Metrics: Record failed retrieval duration (Story 6.1, AC 6.1.3)
            if retrieval_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                retrieval_duration_seconds.observe(duration_seconds)

            # Metrics: Increment failed retrieval counter (Story 6.1, AC 6.1.3)
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=collection, status="failed"
                ).inc()

            # Metrics: Increment failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="qdrant", error_code="QDRANT_UNAVAILABLE"
                ).inc()

            logger.error(
                "qdrant_search_failed",
                extra={
                    "collection": collection,
                    "group_id": group_id,
                    "error": str(e),
                },
            )
            raise QdrantUnavailable(f"Search failed: {e}") from e

        # Format results with collection attribution (AC 3.2.4)
        memories = []
        for result in results:
            memory = {
                "id": result.id,
                "score": result.score,
                "collection": collection,  # Add collection attribution
                **result.payload,
            }
            memories.append(memory)

        # Metrics: Increment retrieval counter with success/empty status (Story 6.1, AC 6.1.3)
        if memory_retrievals_total:
            status = "success" if memories else "empty"
            memory_retrievals_total.labels(collection=collection, status=status).inc()

        # Structured logging
        logger.info(
            "search_completed",
            extra={
                "collection": collection,
                "results_count": len(memories),
                "group_id": group_id,
                "threshold": score_threshold,
            },
        )

        return memories

    def search_both_collections(
        self,
        query: str,
        group_id: Optional[str] = None,
        cwd: Optional[str] = None,
        limit: int = 5,
    ) -> dict:
        """Search implementations (filtered) and best_practices (shared).

        Performs parallel search on both collections with different filtering:
        - implementations: Filtered by group_id (project-specific)
        - best_practices: No group_id filter (shared across all projects)

        Implements AC 4.2.2: Supports automatic project detection via cwd parameter.

        Args:
            query: Search query text
            group_id: Optional explicit project identifier (takes precedence over cwd)
            cwd: Optional working directory for auto project detection
            limit: Maximum results per collection (default 5)

        Returns:
            Dict with "implementations" and "best_practices" keys, each containing
            list of search results.

        Note:
            Either group_id or cwd should be provided for implementations filtering.
            If neither provided, implementations search uses no project filter.

        Example:
            >>> search = MemorySearch()
            >>> results = search.search_both_collections(
            ...     query="error handling patterns",
            ...     cwd="/path/to/my-project",  # Auto-detects group_id
            ...     limit=3
            ... )
            >>> len(results["implementations"])
            3
            >>> len(results["best_practices"])
            3
        """
        # Resolve group_id from cwd if not explicitly provided (AC 4.2.2)
        effective_group_id = group_id
        if not effective_group_id and cwd:
            try:
                from .project import detect_project

                effective_group_id = detect_project(cwd)
                logger.debug(
                    "dual_search_project_detected",
                    extra={"cwd": cwd, "group_id": effective_group_id},
                )
            except Exception as e:
                logger.warning(
                    "dual_search_project_detection_failed",
                    extra={"cwd": cwd, "error": str(e), "fallback": "no_filter"},
                )
                effective_group_id = None

        # Search implementations with group_id filter (project-specific)
        implementations = self.search(
            query=query,
            collection="implementations",
            group_id=effective_group_id,  # May be None if no project context
            limit=limit,
        )

        # Search best_practices without group_id filter (shared)
        best_practices = self.search(
            query=query,
            collection="best_practices",
            group_id=None,  # Shared across all projects
            limit=limit,
        )

        # Log dual-collection search operation (AC 1.6.2)
        logger.info(
            "dual_collection_search_completed",
            extra={
                "group_id": group_id,
                "implementations_count": len(implementations),
                "best_practices_count": len(best_practices),
                "total_results": len(implementations) + len(best_practices),
            },
        )

        return {
            "implementations": implementations,
            "best_practices": best_practices,
        }

    def format_tiered_results(
        self,
        results: list[dict],
        high_threshold: float = 0.90,
        medium_threshold: float = 0.50,  # DEC-009: Medium tier 50-90%
    ) -> str:
        """Format search results into tiered markdown for context injection.

        Categorizes results by similarity score into high and medium relevance tiers.
        High relevance shows full content, medium shows truncated (500 chars).
        Results below medium_threshold are excluded.

        Args:
            results: List of search results with "score", "type", and "content" fields
            high_threshold: Minimum score for high relevance tier (default 0.90)
            medium_threshold: Minimum score for medium relevance tier (default 0.50, per DEC-009)

        Returns:
            Markdown-formatted string with tiered results and score percentages.

        Example:
            >>> search = MemorySearch()
            >>> results = [
            ...     {"score": 0.95, "type": "implementation", "content": "High relevance content"},
            ...     {"score": 0.85, "type": "pattern", "content": "Medium relevance content"}
            ... ]
            >>> formatted = search.format_tiered_results(results)
            >>> print(formatted)
            ## High Relevance Memories (>90%)
            <BLANKLINE>
            ### implementation (95%)
            High relevance content
            <BLANKLINE>
            ## Medium Relevance Memories (50-90%)
            <BLANKLINE>
            ### pattern (85%)
            Medium relevance content
        """
        high_relevance = [r for r in results if r["score"] >= high_threshold]
        medium_relevance = [
            r
            for r in results
            if medium_threshold <= r["score"] < high_threshold
        ]

        output = []

        # High relevance tier: full content
        if high_relevance:
            output.append("## High Relevance Memories (>90%)")
            for mem in high_relevance:
                memory_type = mem.get("type", "unknown")
                content = mem.get("content", "")
                output.append(f"\n### {memory_type} ({mem['score']:.0%})")
                output.append(content)

        # Medium relevance tier: truncated content
        if medium_relevance:
            output.append("\n## Medium Relevance Memories (50-90%)")
            for mem in medium_relevance:
                memory_type = mem.get("type", "unknown")
                content = mem.get("content", "")
                output.append(f"\n### {memory_type} ({mem['score']:.0%})")
                # Truncate to 500 chars
                if len(content) > 500:
                    content = content[:500] + "..."
                output.append(content)

        return "\n".join(output)

    def close(self) -> None:
        """Close underlying clients and release resources.

        Call this method when done with the MemorySearch instance, or use as context manager.

        Example:
            >>> search = MemorySearch()
            >>> try:
            ...     results = search.search("query")
            ... finally:
            ...     search.close()
        """
        if hasattr(self, "embedding_client") and self.embedding_client is not None:
            self.embedding_client.close()

    def __enter__(self) -> "MemorySearch":
        """Enter context manager.

        Returns:
            Self for use in with statement.

        Example:
            >>> with MemorySearch() as search:
            ...     results = search.search("query")
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close clients.

        Args:
            exc_type: Exception type if raised, None otherwise.
            exc_val: Exception value if raised, None otherwise.
            exc_tb: Exception traceback if raised, None otherwise.
        """
        self.close()

    def __del__(self) -> None:
        """Close clients on garbage collection.

        Note:
            Uses try/except to handle interpreter shutdown safely.
            Prefer using context manager or explicit close() instead.
        """
        try:
            self.close()
        except Exception:
            # Silently ignore errors during interpreter shutdown
            pass


def retrieve_best_practices(
    query: str,
    limit: int = 3,
    config: Optional[MemoryConfig] = None,
) -> list[dict]:
    """Retrieve best practices regardless of current project.

    Implements AC 4.3.2 (Best Practices Retrieval) and FR16 (Cross-Project Sharing).

    Best practices are shared across all projects (FR16), so no group_id
    filter is applied. This enables universal pattern discovery.

    Unlike implementations (Story 4.2), best practices:
    - NO group_id filter applied (searches all best practices)
    - Collection is always "best_practices" (not "implementations")
    - NO cwd parameter (best practices are intentionally global)
    - Smaller default limit (3 vs 5) for context efficiency

    Args:
        query: Semantic search query for best practices
        limit: Maximum number of results (default: 3 for context efficiency)
        config: Optional MemoryConfig instance. Uses get_config() if not provided.

    Returns:
        list[dict]: Best practice memories with content and metadata, sorted by
                    similarity score (highest first). Each result contains:
                    - id: Memory UUID
                    - score: Similarity score (0-1)
                    - content: Best practice text
                    - group_id: Always "shared"
                    - type: Always "pattern"
                    - collection: Always "best_practices"
                    - Other payload fields (session_id, source_hook, timestamp, etc.)

    Raises:
        EmbeddingError: If embedding service is unavailable
        QdrantUnavailable: If Qdrant search fails

    Example:
        >>> results = retrieve_best_practices(
        ...     query="Python type hints best practice",
        ...     limit=3
        ... )
        >>> len(results) <= 3
        True
        >>> results[0]["group_id"]
        'shared'
        >>> results[0]["collection"]
        'best_practices'

    Note:
        No 'cwd' parameter - best practices are intentionally global.
        Search uses only semantic similarity, not project filtering.

    Performance Considerations (2026):
        Per Qdrant Multitenancy Guide (https://qdrant.tech/articles/multitenancy/):
        - Unfiltered queries (no group_id filter) scan all vectors in collection
        - For best_practices collection with ~100-1000 entries, overhead is minimal (<50ms)
        - Much faster than maintaining separate collections per project
        - Use smaller default limit=3 vs implementations limit=5 to reduce context load

    2026 Best Practice Rationale:
        Per Qdrant Filtering Guide (https://qdrant.tech/articles/vector-search-filtering/):
        - Filter construction: group_id=None MUST NOT apply filter (searches all)
        - If no conditions, query_filter=None (not empty Filter object)
        - This pattern enables cross-project sharing while maintaining type safety
    """
    try:
        search = MemorySearch(config=config)

        # No group_id filter - accessible from all projects (FR16)
        # CRITICAL: group_id=None means search ALL best practices, not just one project
        results = search.search(
            query=query,
            collection="best_practices",  # CRITICAL: Separate collection for shared content
            group_id=None,  # CRITICAL: No project filter for shared collection
            limit=limit,
        )

        logger.info(
            "best_practices_retrieved",
            extra={
                "query": query[:50],  # Truncate for logs
                "count": len(results),
                "limit": limit,
            },
        )

        return results

    except EmbeddingError as e:
        logger.error(
            "best_practice_retrieval_embedding_failed",
            extra={
                "query": query[:50],
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        # Return empty list for graceful degradation
        return []

    except QdrantUnavailable as e:
        logger.error(
            "best_practice_retrieval_qdrant_failed",
            extra={
                "query": query[:50],
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        # Return empty list for graceful degradation
        return []

    except Exception as e:
        logger.error(
            "best_practice_retrieval_failed",
            extra={
                "query": query[:50],
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        # Return empty list for graceful degradation (explicit error per user requirements)
        return []
