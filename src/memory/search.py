"""Memory search operations with semantic similarity and filtering.

Provides MemorySearch class for searching stored memories using Qdrant vector search
with configurable filtering, dual-collection support, and tiered result formatting.

Architecture Reference: architecture.md:747-863 (Search Module)
Best Practices (2025/2026):
- https://qdrant.tech/articles/vector-search-filtering/
- https://qdrant.tech/articles/vector-search-resource-optimization/
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4
# SDK VERSION: V3 ONLY. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import contextlib
import json
import logging
import os
import time
from datetime import datetime, timezone

from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Prefetch,
    SearchParams,
    SparseVector,
)

from .activity_log import log_memory_search
from .config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    MemoryConfig,
    get_config,
)
from .decay import build_decay_formula
from .embeddings import EmbeddingClient, EmbeddingError
from .metrics_push import push_failure_metrics_async, push_retrieval_metrics_async
from .qdrant_client import QdrantUnavailable, get_qdrant_client

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import (
        failure_events_total,
        memory_retrievals_total,
        retrieval_duration_seconds,
    )
except ImportError:
    retrieval_duration_seconds = None
    memory_retrievals_total = None
    failure_events_total = None

# SPEC-021: Trace buffer for search instrumentation
try:
    from .trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000  # Max chars per result preview in traces

__all__ = [
    "MemorySearch",
    "format_attribution",
    "retrieve_best_practices",
    "search_memories",
]

logger = logging.getLogger("ai_memory.retrieve")


def format_attribution(
    collection: str,
    memory_type: str,
    score: float | None = None,
) -> str:
    """Format attribution string for display.

    Creates consistent attribution strings for memory search results,
    combining collection name and memory type with optional relevance score.

    Args:
        collection: Collection name (code-patterns, conventions, discussions)
        memory_type: Memory type from payload (e.g., implementation, error_pattern)
        score: Optional relevance score (0.0 to 1.0)

    Returns:
        Formatted attribution string.

    Examples:
        >>> format_attribution("code-patterns", "implementation")
        '[code-patterns:implementation]'
        >>> format_attribution("conventions", "naming", 0.87)
        '[conventions:naming] (87%)'
        >>> format_attribution("discussions", "unknown", 0.5)
        '[discussions:unknown] (50%)'
    """
    base = f"[{collection}:{memory_type}]"
    if score is not None:
        return f"{base} ({int(score * 100)}%)"
    return base


class MemorySearch:
    """Handles memory search operations with semantic similarity.

    Provides semantic search with configurable filtering by group_id and memory_type,
    dual-collection search (code-patterns + conventions), and tiered result
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

    def __init__(self, config: MemoryConfig | None = None):
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

    def _get_embedding_model(
        self,
        collection: str,
        memory_type: str | list[str] | None = None,
        content_type: str | None = None,
    ) -> str:
        """Route embedding model based on collection and content type.

        Mirrors MemoryStorage._get_embedding_model routing rules.
        SPEC-010 Section 4.2: Routing Rules
        - content_type="github_code_blob" -> code model (highest priority)
        - code-patterns collection -> code model
        - github_code_blob in memory_type list -> code model
        - Everything else -> prose (en) model

        Args:
            collection: Qdrant collection name.
            memory_type: Optional memory type filter (str or list).
            content_type: Optional explicit content type override. When set to
                "github_code_blob", forces "code" model regardless of collection.
        """
        # TD-225: content_type takes highest priority for model routing
        if content_type == "github_code_blob":
            return "code"
        if collection == COLLECTION_CODE_PATTERNS:
            return "code"
        # Content-type routing: github_code_blob stored in discussions uses code model
        if memory_type is not None:
            types = memory_type if isinstance(memory_type, list) else [memory_type]
            if "github_code_blob" in types:
                return "code"
        return "en"

    def search(
        self,
        query: str,
        collection: str = COLLECTION_CODE_PATTERNS,
        cwd: str | None = None,
        group_id: str | None = None,
        limit: int | None = None,
        score_threshold: float | None = None,
        memory_type: str | list[str] | None = None,
        fast_mode: bool = False,  # NEW: Use hnsw_ef=64 for triggers
        source: str | None = None,  # SPEC-005: Namespace filter (e.g., "github")
        agent_id: str | None = None,  # SPEC-015: Agent-scoped filter
        must_not_types: (
            list[str] | None
        ) = None,  # F13/TD-243: Qdrant-level type exclusion
        exclude_expired_freshness: bool = False,  # WP-2: Pre-filter expired from code-patterns queries (Spec §4.5.3)
        _access_count_dedup: (
            list[str] | None
        ) = None,  # H-3: Cross-turn dedup list (mutated in-place)
    ) -> list[dict]:
        """Search for relevant memories using semantic similarity with project scoping.

        Generates query embedding, builds filter conditions, and searches Qdrant
        collection for matching memories. Returns results sorted by similarity score.

        Implements AC 4.2.2: Supports automatic project detection via cwd parameter.

        Memory System v2.0: Supports new collections (code-patterns, conventions, discussions)
        with type-level filtering for precision.

        Args:
            query: Search query text (will be embedded for semantic search)
            collection: Collection name (code-patterns, conventions, discussions) - default: code-patterns
            cwd: Optional path for automatic project detection (auto-sets group_id)
            group_id: Optional filter by project group_id (None = search all, overrides cwd)
            limit: Maximum results to return (defaults to config.max_retrievals)
            score_threshold: Minimum similarity score (defaults to config.similarity_threshold)
            memory_type: Optional memory type(s) to filter by - accepts string or list
                        (e.g., "implementation" or ["implementation", "error_pattern"])
            fast_mode: If True, use hnsw_ef=64 for faster search (triggers).
                      If False (default), use hnsw_ef=128 for accuracy (user searches).
            source: Optional namespace filter (e.g., "github"). When set to "github",
                   also applies is_current=True filter to exclude superseded points (BP-074).

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
            ...     memory_type=["implementation", "error_pattern"]
            ... )
            >>> results[0].keys()
            dict_keys(['id', 'score', 'content', 'group_id', 'type', ...])
        """
        # Normalize memory_type to list for internal use
        # CR-2 FIX: Add type validation with warning if wrong type passed
        memory_types = None
        if memory_type is not None:
            if isinstance(memory_type, str):
                memory_types = [memory_type]
            elif isinstance(memory_type, list):
                memory_types = memory_type
            else:
                # Defensive programming: log warning for invalid type
                logger.warning(
                    "invalid_memory_type_parameter",
                    extra={
                        "received_type": type(memory_type).__name__,
                        "expected": "str or list[str]",
                        "value": str(memory_type)[:50],
                    },
                )
                memory_types = None  # Skip type filtering if invalid

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
        limit = limit if limit is not None else self.config.max_retrievals
        score_threshold = (
            score_threshold
            if score_threshold is not None
            else self.config.similarity_threshold
        )

        # Generate query embedding
        # Propagates EmbeddingError for graceful degradation
        _trace_start = datetime.now(tz=timezone.utc)
        # TD-225: Extract content_type for embedding model routing when a single
        # type is filtered (e.g., github_code_blob in github collection).
        _content_type = (
            memory_types[0] if memory_types and len(memory_types) == 1 else None
        )
        model = self._get_embedding_model(
            collection, memory_type=memory_types, content_type=_content_type
        )
        query_embedding = self.embedding_client.embed([query], model=model)[0]

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
        if memory_types:
            filter_conditions.append(
                FieldCondition(key="type", match=MatchAny(any=memory_types))
            )

        # SPEC-005: Namespace filter (e.g., source="github")
        if source is not None:
            filter_conditions.append(
                FieldCondition(key="source", match=MatchValue(value=source))
            )
            # BP-074: When searching GitHub namespace, exclude superseded points.
            # Only applied when source="github" to avoid breaking existing
            # non-GitHub discussions searches (Option A — backward compatible).
            if source == "github":
                filter_conditions.append(
                    FieldCondition(key="is_current", match=MatchValue(value=True))
                )

        # SPEC-015: Agent-scoped filter (e.g., agent_id="parzival")
        if agent_id is not None:
            filter_conditions.append(
                FieldCondition(
                    key="agent_id",
                    match=MatchValue(value=agent_id),
                )
            )

        # F13/TD-243: Build must_not conditions for Qdrant-level type exclusion
        must_not_conditions = []
        if must_not_types:
            must_not_conditions.append(
                FieldCondition(key="type", match=MatchAny(any=must_not_types))
            )

        # WP-2: Belt-and-suspenders pre-filter — exclude EXPIRED from code-patterns at Qdrant query layer
        if exclude_expired_freshness and collection == COLLECTION_CODE_PATTERNS:
            must_not_conditions.append(
                FieldCondition(
                    key="freshness_status",
                    match=MatchValue(value="expired"),
                )
            )

        if filter_conditions or must_not_conditions:
            query_filter = Filter(
                must=filter_conditions if filter_conditions else None,
                must_not=must_not_conditions if must_not_conditions else None,
            )
        else:
            query_filter = None

        # Search Qdrant using query_points (qdrant-client 1.16+ API)
        # Wraps exceptions in QdrantUnavailable for graceful degradation (AC 1.6.4)
        # 2026 Best Practice: Tune hnsw_ef based on use case
        # - Triggers (fast_mode=True): config.hnsw_ef_fast for <100ms response
        # - User searches (fast_mode=False): config.hnsw_ef_accurate for accuracy
        try:
            hnsw_ef = (
                self.config.hnsw_ef_fast if fast_mode else self.config.hnsw_ef_accurate
            )
            search_params = SearchParams(hnsw_ef=hnsw_ef)
        except Exception as e:
            # Graceful degradation: let Qdrant use defaults
            logger.warning(
                "search_params_creation_failed",
                extra={"error": str(e), "fast_mode": fast_mode},
            )
            search_params = None

        logger.debug(
            "search_params_configured",
            extra={
                "hnsw_ef": search_params.hnsw_ef if search_params else "default",
                "fast_mode": fast_mode,
                "collection": collection,
            },
        )

        _search_mode = "dense"  # Track mode for logging/tracing
        start_time = time.perf_counter()
        try:
            # Search path selection: hybrid and decay COMPOSE (not exclusive).
            # Priority order:
            #   1. hybrid+decay  — RRF fusion of dense+sparse, then decay rerank
            #   2. hybrid only   — RRF fusion (or ColBERT rerank) of dense+sparse
            #   3. decay only    — dense prefetch, then decay rerank
            #   4. plain dense   — simple dense vector search

            # Step 1: Attempt to build hybrid prefetch stages (dense+sparse)
            hybrid_prefetch_stages = None
            if self.config.hybrid_search_enabled:
                hybrid_prefetch_stages = self._build_hybrid_prefetch(
                    query=query,
                    query_embedding=query_embedding,
                    collection=collection,
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=score_threshold,
                    search_params=search_params,
                )
                # hybrid_prefetch_stages is None if sparse embedding failed

            # Step 2: Execute query based on available capabilities
            if hybrid_prefetch_stages is not None and self.config.decay_enabled:
                # PATH 1: Hybrid + Decay (best quality)
                # Architecture: [dense -> decay formula, sparse] -> RRF fusion
                # Decay must be applied to dense FIRST because:
                # - Dense scores are cosine similarity (0-1 scale) — compatible with
                #   decay formula's 0.7*$score + 0.3*temporal weighting
                # - RRF scores are reciprocal rank (~0.01-0.05) — NOT compatible with
                #   the decay formula. Applying decay after RRF would zero out semantics.
                _search_mode = "hybrid_rrf_decay"
                prefetch_limit = max(50, limit * 5)

                # Build decay formula + dense prefetch (decay applied to dense scores)
                formula, decay_dense_prefetch = build_decay_formula(
                    query_embedding=query_embedding,
                    collection=collection,
                    config=self.config,
                    extra_filter=query_filter,
                    prefetch_limit=prefetch_limit,
                    score_threshold=score_threshold,
                    search_params=search_params,
                )

                # Decay-scored dense prefetch: dense -> decay formula reranks
                decay_dense_stage = Prefetch(
                    prefetch=decay_dense_prefetch,
                    query=formula,
                    limit=prefetch_limit,
                )

                # Extract sparse prefetch from hybrid stages (index 1)
                sparse_stage = hybrid_prefetch_stages[1]
                # Ensure sparse stage has enough candidates
                sparse_stage.limit = prefetch_limit

                # RRF fusion of decay-adjusted dense + raw sparse scores
                try:
                    response = self.client.query_points(
                        collection_name=collection,
                        prefetch=[decay_dense_stage, sparse_stage],
                        query=FusionQuery(fusion=Fusion.RRF),
                        limit=limit,
                        with_payload=True,
                    )
                except Exception as hybrid_err:
                    # Graceful degradation: collection may lack sparse config
                    logger.warning(
                        "hybrid_query_failed_falling_back_to_decay",
                        extra={"error": str(hybrid_err), "collection": collection},
                    )
                    _search_mode = "decay"
                    response = self.client.query_points(
                        collection_name=collection,
                        prefetch=decay_dense_prefetch,
                        query=formula,
                        limit=limit,
                        with_payload=True,
                    )

            elif hybrid_prefetch_stages is not None:
                # PATH 2: Hybrid only (no decay)
                # Try ColBERT reranking first, then RRF fusion
                _search_mode = self._hybrid_query_with_fallback(
                    query=query,
                    collection=collection,
                    query_filter=query_filter,
                    limit=limit,
                    hybrid_prefetch_stages=hybrid_prefetch_stages,
                )
                if isinstance(_search_mode, tuple):
                    response, _search_mode = _search_mode
                else:
                    # ColBERT and RRF both failed — fall through to dense
                    _search_mode = "dense"
                    response = self.client.query_points(
                        collection_name=collection,
                        query=query_embedding,
                        query_filter=query_filter,
                        limit=limit,
                        score_threshold=score_threshold,
                        with_payload=True,
                        search_params=search_params,
                    )

            elif self.config.decay_enabled:
                # PATH 3: Decay only (no hybrid — sparse unavailable or hybrid disabled)
                _search_mode = "decay"
                prefetch_limit = max(50, limit * 5)
                formula, prefetch = build_decay_formula(
                    query_embedding=query_embedding,
                    collection=collection,
                    config=self.config,
                    extra_filter=query_filter,
                    prefetch_limit=prefetch_limit,
                    score_threshold=score_threshold,
                    search_params=search_params,
                )
                # formula is guaranteed non-None when decay_enabled=True
                response = self.client.query_points(
                    collection_name=collection,
                    prefetch=prefetch,
                    query=formula,
                    limit=limit,
                    with_payload=True,
                )

            else:
                # PATH 4: Plain dense search (no hybrid, no decay)
                response = self.client.query_points(
                    collection_name=collection,
                    query=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=score_threshold,
                    with_payload=True,
                    search_params=search_params,
                )
            results = response.points

            # Metrics: Record retrieval duration (Story 6.1, AC 6.1.3)
            if retrieval_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                retrieval_duration_seconds.observe(duration_seconds)

        except Exception as e:
            # Metrics: Record failed retrieval duration (Story 6.1, AC 6.1.3)
            duration_seconds = time.perf_counter() - start_time
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_seconds)

            # Metrics: Increment failed retrieval counter (Story 6.1, AC 6.1.3)
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=collection,
                    status="failed",
                    project=group_id or "unknown",
                ).inc()

            # Metrics: Increment failure event for alerting (Story 6.1, AC 6.1.4)
            if failure_events_total:
                failure_events_total.labels(
                    component="qdrant",
                    error_code="QDRANT_UNAVAILABLE",
                    project=group_id or "unknown",
                ).inc()

            # Push to Pushgateway for hook subprocess visibility
            push_retrieval_metrics_async(
                collection=collection,
                status="failed",
                duration_seconds=duration_seconds,
                project=group_id or "unknown",
            )
            push_failure_metrics_async(
                component="qdrant",
                error_code="QDRANT_UNAVAILABLE",
                project=group_id or "unknown",
            )

            logger.error(
                "qdrant_search_failed",
                extra={
                    "collection": collection,
                    "group_id": group_id,
                    "error": str(e),
                },
            )
            raise QdrantUnavailable(f"Search failed: {e}") from e

        # Format results with collection and type attribution (AC 3.2.4, T4)
        # Note: Spread payload first, then set explicit fields to ensure consistency
        memories = []
        for result in results:
            payload = result.payload or {}
            memory_type = payload.get("type", "unknown")
            # L-9: Normalize freshness_status to lowercase for case-insensitive comparison
            # Belt-and-suspenders: pre-retrieval Qdrant filter (line 364) is case-sensitive,
            # so normalize here for downstream post-retrieval penalty consistency.
            _raw_freshness = payload.get("freshness_status")
            _freshness_status = (_raw_freshness or "unknown").lower()
            memory = {
                **payload,  # Spread first - explicit fields below take precedence
                "id": result.id,
                "score": result.score,
                "collection": collection,
                "type": memory_type,
                "freshness_status": _freshness_status,
                "attribution": format_attribution(
                    collection, memory_type, result.score
                ),
            }
            memories.append(memory)

        # PLAN-013 / DEC-062: Normalize hybrid search scores to [0.5, 0.95] range.
        # RRF scores are reciprocal rank (~0.01-0.05), NOT cosine similarity (0-1).
        # Without normalization, downstream confidence gating (threshold=0.6)
        # would ALWAYS skip injection — a silent regression.
        #
        # Min-max normalization to [0.5, 0.95] (not [0, 1.0]) because:
        # - Best result gets 0.95 (not 1.0) → preserves quality signal for
        #   adaptive budget and is not excluded by score gap filter (which
        #   skips deterministic score=1.0 results from get_recent()).
        # - Worst result gets 0.5 → below confidence threshold (0.55 skip)
        #   so low-quality tail results are naturally filtered.
        # - Single result gets 0.75 → above threshold, moderate budget.
        if _search_mode.startswith("hybrid") and memories:
            scores = [m["score"] for m in memories]
            max_score = max(scores)
            min_score = min(scores)
            if max_score > 0:
                score_range = max_score - min_score
                for m in memories:
                    if score_range > 0:
                        m["score"] = 0.5 + 0.45 * (m["score"] - min_score) / score_range
                    else:
                        # All same score (or single result) → use midpoint
                        m["score"] = 0.75
                    # Update attribution with normalized score
                    m["attribution"] = format_attribution(
                        m["collection"], m["type"], m["score"]
                    )

        # Tag results with search mode for downstream observability
        for m in memories:
            m["search_mode"] = _search_mode

        # G-10: Emit search path selection trace event
        if emit_trace_event:
            with contextlib.suppress(Exception):
                emit_trace_event(
                    event_type="search_path_selection",
                    data={
                        "input": json.dumps(
                            {
                                "query": query[:200],
                                "collection": collection,
                                "search_mode": _search_mode,
                            }
                        )[:TRACE_CONTENT_MAX],
                        "output": json.dumps(
                            {
                                "path": _search_mode,
                                "result_count": len(memories),
                                "hybrid_available": hybrid_prefetch_stages is not None,
                                "decay_enabled": self.config.decay_enabled,
                            }
                        )[:TRACE_CONTENT_MAX],
                        "metadata": {"path": _search_mode, "collection": collection},
                    },
                    session_id=os.environ.get("CLAUDE_SESSION_ID"),
                    tags=["search", "retrieval"],
                )

        # SPEC-021: Emit search trace event
        if emit_trace_event:
            try:
                _trace_end = datetime.now(tz=timezone.utc)
                _top_score = memories[0]["score"] if memories else 0.0
                _search_duration_ms = (time.perf_counter() - start_time) * 1000
                # Build content preview for trace span (display only, not storage truncation).
                # 500 chars per result x 10 results = ~5000 chars fits within TRACE_CONTENT_MAX.
                _result_previews = "\n---\n".join(
                    f"[{m.get('type','?')}|{round(m.get('score',0)*100)}%] {m.get('content','')[:500]}"
                    for m in memories[:10]
                )
                emit_trace_event(
                    event_type="search_query",
                    data={
                        "input": query[:TRACE_CONTENT_MAX],
                        "output": (
                            _result_previews[:TRACE_CONTENT_MAX]
                            if _result_previews
                            else f"No results (collection={collection})"
                        ),
                        "metadata": {
                            "collection": collection,
                            "group_id": group_id,
                            "limit": limit,
                            "memory_type": memory_type,
                            "fast_mode": fast_mode,
                            "source": source,
                            "agent_id": agent_id,
                            "embedding_model": model,
                            "search_mode": _search_mode,
                            "search_duration_ms": round(_search_duration_ms, 2),
                            "result_count": len(memories),
                            "top_score": round(_top_score, 4),
                            "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                            "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                        },
                    },
                    session_id=os.environ.get("CLAUDE_SESSION_ID"),
                    project_id=group_id,
                    start_time=_trace_start,
                    end_time=_trace_end,
                    tags=["search", "retrieval"],
                )
            except Exception:
                pass

        # Metrics: Increment retrieval counter with success/empty status (Story 6.1, AC 6.1.3)
        status = "success" if memories else "empty"
        if memory_retrievals_total:
            memory_retrievals_total.labels(
                collection=collection, status=status, project=group_id or "unknown"
            ).inc()

        # Push to Pushgateway for hook subprocess visibility
        push_retrieval_metrics_async(
            collection=collection,
            status=status,
            duration_seconds=time.perf_counter() - start_time,
            project=group_id or "unknown",
        )

        # Structured logging
        logger.info(
            "search_completed",
            extra={
                "collection": collection,
                "results_count": len(memories),
                "group_id": group_id,
                "threshold": score_threshold,
                "search_mode": _search_mode,
            },
        )

        # Remembrance Protection: increment access_count for retrieved points (PLAN-015 §5.3)
        # Only on search() — get_recent() is deterministic, no decay applied
        # NOTE (L-11): Non-atomic read-increment-write. Qdrant lacks atomic increment.
        # Acceptable for access_count (advisory, not critical). See L-11.
        try:
            _point_updates: dict[str, list[str]] = {}  # collection -> [point_ids]
            for _mem in memories:
                _coll = _mem.get("collection", collection)
                _pid = _mem.get("id")
                if _pid is not None and _coll:
                    _point_updates.setdefault(_coll, []).append(str(_pid))

            # H-3: Cross-turn dedup — skip points already incremented this turn.
            # The caller passes a mutable list that persists across multiple search()
            # calls in the same turn. If not provided, no cross-turn dedup.
            _dedup_set = (
                set(_access_count_dedup) if _access_count_dedup is not None else None
            )

            for _coll, _pids in _point_updates.items():
                # H6: Batch retrieve — one call per collection instead of one per point
                try:
                    _unique_pids = list(
                        dict.fromkeys(_pids)
                    )  # deduplicate within this search() call, preserve order

                    # H-3: Filter out points already incremented this turn
                    if _dedup_set is not None:
                        _unique_pids = [p for p in _unique_pids if p not in _dedup_set]
                    if not _unique_pids:
                        continue

                    _retrieved_points = self.client.retrieve(
                        collection_name=_coll,
                        ids=_unique_pids,
                        with_payload=True,
                        with_vectors=False,
                    )
                    # Build lookup: point_id -> current access_count (L2: guard payload None)
                    _count_map: dict[str, int] = {
                        str(point.id): int(
                            (point.payload or {}).get("access_count") or 0
                        )
                        for point in _retrieved_points
                    }
                except Exception:
                    _unique_pids = list(dict.fromkeys(_pids))
                    if _dedup_set is not None:
                        _unique_pids = [p for p in _unique_pids if p not in _dedup_set]
                    _count_map = {}

                # M-7: Batch set_payload per collection instead of per-point.
                # Group all points needing update, then issue one set_payload per
                # distinct new access_count value per collection.
                _batch_by_count: dict[int, list[str]] = {}  # new_count -> [point_ids]
                _transition_pids: list[str] = []  # Points hitting threshold=3

                for _pid in _unique_pids:
                    _current_count = _count_map.get(_pid, 0)
                    _new_count = _current_count + 1
                    _batch_by_count.setdefault(_new_count, []).append(_pid)
                    if _new_count == 3:
                        _transition_pids.append(_pid)
                    # H-3: Record that we incremented this point this turn
                    if _access_count_dedup is not None:
                        _access_count_dedup.append(_pid)
                    if _dedup_set is not None:
                        _dedup_set.add(_pid)

                # M-7: Issue one set_payload call per distinct count value
                for _new_count, _batch_pids in _batch_by_count.items():
                    with contextlib.suppress(Exception):
                        self.client.set_payload(
                            collection_name=_coll,
                            payload={"access_count": _new_count},
                            points=_batch_pids,
                        )  # Never block results for access_count update failures

                # M1: emit trace only on transition from 2 to 3
                if _transition_pids and emit_trace_event:
                    for _pid in _transition_pids:
                        with contextlib.suppress(Exception):
                            emit_trace_event(
                                event_type="remembrance_protection",
                                data={
                                    "input": f"access_count reached 3 for point {_pid}"[
                                        :TRACE_CONTENT_MAX
                                    ],
                                    "output": "temporal_score override active (access_count >= 3)"[
                                        :TRACE_CONTENT_MAX
                                    ],
                                    "metadata": {
                                        "point_id": _pid,
                                        "collection": _coll,
                                        "access_count": 3,
                                        "temporal_score_override": 1.0,
                                    },
                                },
                                session_id=os.environ.get("CLAUDE_SESSION_ID"),
                                tags=["search", "retrieval"],
                                project_id=group_id,
                            )
        except Exception:
            pass  # Remembrance protection failure must never affect search results

        return memories

    def _build_hybrid_prefetch(
        self,
        query: str,
        query_embedding: list[float],
        collection: str,
        query_filter: Filter | None,
        limit: int,
        score_threshold: float | None,
        search_params: SearchParams | None,
    ) -> list[Prefetch] | None:
        """Build dense+sparse prefetch stages for hybrid search.

        Generates sparse embedding and constructs the two Prefetch stages
        (dense + BM25 sparse) needed for hybrid search. Returns None if
        sparse embedding is unavailable, signaling the caller to fall back
        to dense-only search.

        Args:
            query: Original query text (for sparse embedding generation).
            query_embedding: Pre-computed dense embedding vector.
            collection: Qdrant collection name (for logging).
            query_filter: Pre-built filter conditions.
            limit: Maximum results (used to compute prefetch_limit).
            score_threshold: Minimum similarity score (applied to dense prefetch).
            search_params: HNSW search parameters (applied to dense prefetch).

        Returns:
            List of [dense_prefetch, sparse_prefetch] on success, or None on failure.
        """
        # Generate sparse embedding
        sparse_embedding = None
        try:
            sparse_results = self.embedding_client.embed_sparse([query])
            sparse_embedding = sparse_results[0] if sparse_results else None
        except Exception as e:
            logger.warning(
                "hybrid_sparse_embedding_failed",
                extra={"error": str(e), "collection": collection},
            )

        if sparse_embedding is None:
            logger.debug(
                "hybrid_fallback_no_sparse",
                extra={
                    "collection": collection,
                    "reason": "sparse_embedding_unavailable",
                },
            )
            return None

        # Build prefetch stages: dense + sparse (BM25)
        # max(50, limit * 5) ensures enough candidates for downstream RRF + decay
        prefetch_limit = max(50, limit * 5)

        dense_prefetch = Prefetch(
            query=query_embedding,
            limit=prefetch_limit,
            score_threshold=score_threshold,
            filter=query_filter,
        )
        if search_params is not None:
            dense_prefetch.params = search_params

        sparse_prefetch = Prefetch(
            query=SparseVector(
                indices=sparse_embedding["indices"],
                values=sparse_embedding["values"],
            ),
            using="bm25",
            limit=prefetch_limit,
            filter=query_filter,
        )

        return [dense_prefetch, sparse_prefetch]

    def _hybrid_query_with_fallback(
        self,
        query: str,
        collection: str,
        query_filter: Filter | None,
        limit: int,
        hybrid_prefetch_stages: list[Prefetch],
    ) -> str | tuple:
        """Execute hybrid search query using pre-built prefetch stages.

        PLAN-013: Hybrid search execution with graceful degradation.
        Called when hybrid is enabled but decay is NOT (hybrid-only path).

        Ordering of attempts:
        1. ColBERT reranking (if colbert_reranking_enabled and ColBERT embeddings available)
        2. RRF fusion (dense + sparse prefetch fused with Reciprocal Rank Fusion)
        3. "dense" string fallback (caller handles dense-only search)

        Args:
            query: Original query text (for late/ColBERT embedding generation).
            collection: Qdrant collection name.
            query_filter: Pre-built filter conditions.
            limit: Maximum results to return.
            hybrid_prefetch_stages: Pre-built [dense_prefetch, sparse_prefetch] list.

        Returns:
            Tuple of (QueryResponse, mode_name) on success, or "dense" string on fallback.
        """
        # Step 1: Try ColBERT reranking path (highest quality, optional)
        if self.config.colbert_reranking_enabled:
            try:
                late_results = self.embedding_client.embed_late([query])
                late_embedding = late_results[0] if late_results else None
            except Exception as e:
                logger.warning(
                    "hybrid_colbert_embedding_failed",
                    extra={"error": str(e), "collection": collection},
                )
                late_embedding = None

            if late_embedding is not None:
                try:
                    response = self.client.query_points(
                        collection_name=collection,
                        prefetch=hybrid_prefetch_stages,
                        query=late_embedding,
                        using="colbert",
                        query_filter=query_filter,
                        limit=limit,
                        with_payload=True,
                    )
                    logger.debug(
                        "hybrid_colbert_search_completed",
                        extra={
                            "collection": collection,
                            "results_count": len(response.points),
                        },
                    )
                    return (response, "hybrid_colbert")
                except Exception as e:
                    logger.warning(
                        "hybrid_colbert_query_failed",
                        extra={"error": str(e), "collection": collection},
                    )
                    # Fall through to RRF fusion

        # Step 2: RRF fusion path (dense + sparse combined)
        try:
            response = self.client.query_points(
                collection_name=collection,
                prefetch=hybrid_prefetch_stages,
                query=FusionQuery(fusion=Fusion.RRF),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            logger.debug(
                "hybrid_rrf_search_completed",
                extra={
                    "collection": collection,
                    "results_count": len(response.points),
                },
            )
            return (response, "hybrid_rrf")
        except Exception as e:
            logger.warning(
                "hybrid_rrf_query_failed",
                extra={"error": str(e), "collection": collection},
            )
            # Fall through to dense-only
            return "dense"

    def get_recent(
        self,
        collection: str,
        group_id: str | None = None,
        memory_type: str | list[str] | None = None,
        agent_id: str | None = None,
        source: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve most recent memories by timestamp (deterministic, no vector search).

        Uses Qdrant scroll with order_by timestamp descending to retrieve the most
        recent memories. No embedding or similarity scoring is involved — this is
        a pure chronological retrieval for use cases where recency matters more
        than semantic similarity.

        Args:
            collection: Qdrant collection name to search.
            group_id: Optional project/group filter. Uses explicit None check.
            memory_type: Optional type filter. String or list of strings.
            agent_id: Optional agent-scoped filter (e.g., "parzival").
            source: Optional namespace filter (e.g., "github").
            limit: Maximum number of results to return (default 5).

        Returns:
            List of memory dicts with keys matching search() output format:
            id, score, collection, type, attribution, plus all payload fields.
            Score is always 1.0 for deterministic (non-vector) results.

        Raises:
            QdrantUnavailable: If Qdrant is unreachable or the scroll fails.
        """
        logger.debug(
            "get_recent_query",
            extra={
                "collection": collection,
                "group_id": group_id,
                "memory_type": memory_type,
                "agent_id": agent_id,
                "limit": limit,
            },
        )

        # Normalize memory_type to list
        if memory_type is not None:
            memory_types = (
                memory_type if isinstance(memory_type, list) else [memory_type]
            )
        else:
            memory_types = None

        # Build filter conditions using 2025 best practice: model-based Filter API
        filter_conditions = []
        # CRITICAL: Use explicit None check (not truthy) per AC 4.3.2
        if group_id is not None:
            filter_conditions.append(
                FieldCondition(key="group_id", match=MatchValue(value=group_id))
            )
        if memory_types:
            filter_conditions.append(
                FieldCondition(key="type", match=MatchAny(any=memory_types))
            )
        # SPEC-005: Namespace filter (e.g., source="github")
        if source is not None:
            filter_conditions.append(
                FieldCondition(key="source", match=MatchValue(value=source))
            )
            if source == "github":
                filter_conditions.append(
                    FieldCondition(key="is_current", match=MatchValue(value=True))
                )
        # SPEC-015: Agent-scoped filter (e.g., agent_id="parzival")
        if agent_id is not None:
            filter_conditions.append(
                FieldCondition(
                    key="agent_id",
                    match=MatchValue(value=agent_id),
                )
            )

        start_time = time.perf_counter()
        try:
            points, _ = self.client.scroll(
                collection_name=collection,
                scroll_filter=(
                    Filter(must=filter_conditions) if filter_conditions else None
                ),
                limit=limit,
                order_by={"key": "timestamp", "direction": "desc"},
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            duration_seconds = time.perf_counter() - start_time
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_seconds)

            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=collection,
                    status="failed",
                    project=group_id or "unknown",
                ).inc()

            if failure_events_total:
                failure_events_total.labels(
                    component="qdrant",
                    error_code="QDRANT_UNAVAILABLE",
                    project=group_id or "unknown",
                ).inc()

            push_retrieval_metrics_async(
                collection=collection,
                status="failed",
                duration_seconds=duration_seconds,
                project=group_id or "unknown",
            )
            push_failure_metrics_async(
                component="qdrant",
                error_code="QDRANT_UNAVAILABLE",
                project=group_id or "unknown",
            )

            logger.error(
                "qdrant_get_recent_failed",
                extra={
                    "collection": collection,
                    "group_id": group_id,
                    "error": str(e),
                },
            )
            raise QdrantUnavailable(f"Get recent failed: {e}") from e

        # Format results with collection and type attribution matching search() output
        memories = []
        for point in points:
            payload = point.payload or {}
            memory_type_val = payload.get("type", "unknown")
            memory = {
                **payload,
                "id": point.id,
                "score": 1.0,  # Deterministic retrieval — score is always 1.0
                "collection": collection,
                "type": memory_type_val,
                "attribution": format_attribution(collection, memory_type_val, 1.0),
            }
            memories.append(memory)

        # Metrics: Record retrieval duration (same pattern as search())
        if retrieval_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            retrieval_duration_seconds.observe(duration_seconds)

        # Metrics: Record successful retrieval
        status = "success" if memories else "empty"
        if memory_retrievals_total:
            memory_retrievals_total.labels(
                collection=collection,
                status=status,
                project=group_id or "unknown",
            ).inc()

        # Push to Pushgateway for hook subprocess visibility
        push_retrieval_metrics_async(
            collection=collection,
            status=status,
            duration_seconds=time.perf_counter() - start_time,
            project=group_id or "unknown",
        )

        logger.info(
            "get_recent_completed",
            extra={
                "collection": collection,
                "results_count": len(memories),
                "group_id": group_id,
                "duration_seconds": round(time.perf_counter() - start_time, 4),
            },
        )

        # Remembrance Protection: access_count NOT incremented for get_recent() — deterministic, no decay
        return memories

    def search_both_collections(
        self,
        query: str,
        group_id: str | None = None,
        cwd: str | None = None,
        limit: int = 5,
        fast_mode: bool = False,
    ) -> dict:
        """Search code-patterns (filtered) and conventions (shared).

        Performs parallel search on both collections with different filtering:
        - code-patterns: Filtered by group_id (project-specific)
        - conventions: No group_id filter (shared across all projects)

        Implements AC 4.2.2: Supports automatic project detection via cwd parameter.

        Args:
            query: Search query text
            group_id: Optional explicit project identifier (takes precedence over cwd)
            cwd: Optional working directory for auto project detection
            limit: Maximum results per collection (default 5)
            fast_mode: If True, use hnsw_ef_fast for faster search (triggers).
                      If False (default), use hnsw_ef_accurate for accuracy.

        Returns:
            Dict with "code-patterns" and "conventions" keys, each containing
            list of search results.

        Note:
            Either group_id or cwd should be provided for code-patterns filtering.
            If neither provided, code-patterns search uses no project filter.

        Example:
            >>> search = MemorySearch()
            >>> results = search.search_both_collections(
            ...     query="error handling patterns",
            ...     cwd="/path/to/my-project",  # Auto-detects group_id
            ...     limit=3
            ... )
            >>> len(results["code-patterns"])
            3
            >>> len(results["conventions"])
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

        _trace_start = datetime.now(tz=timezone.utc)

        # Search code-patterns with group_id filter (project-specific)
        code_patterns = self.search(
            query=query,
            collection=COLLECTION_CODE_PATTERNS,
            group_id=effective_group_id,  # May be None if no project context
            limit=limit,
            fast_mode=fast_mode,
        )

        # Search conventions without group_id filter (shared)
        conventions = self.search(
            query=query,
            collection=COLLECTION_CONVENTIONS,
            group_id=None,  # Shared across all projects
            limit=limit,
            fast_mode=fast_mode,
        )

        # Log dual-collection search operation (AC 1.6.2)
        logger.info(
            "dual_collection_search_completed",
            extra={
                "group_id": group_id,
                "code_patterns_count": len(code_patterns),
                "conventions_count": len(conventions),
                "total_results": len(code_patterns) + len(conventions),
            },
        )

        # SPEC-021: Emit dual-collection search trace event
        if emit_trace_event:
            try:
                _trace_end = datetime.now(tz=timezone.utc)
                _all_results = code_patterns + conventions
                _dual_previews = "\n---\n".join(
                    f"[{m.get('type','?')}|{m.get('collection','?')}|{round(m.get('score',0)*100)}%] {m.get('content','')[:400]}"
                    for m in _all_results[:10]
                )
                emit_trace_event(
                    event_type="dual_collection_search",
                    data={
                        "input": query[:TRACE_CONTENT_MAX],
                        "output": (
                            _dual_previews[:TRACE_CONTENT_MAX]
                            if _dual_previews
                            else "No results from dual search"
                        ),
                        "metadata": {
                            "group_id": effective_group_id,
                            "code_patterns_count": len(code_patterns),
                            "conventions_count": len(conventions),
                            "total_results": len(code_patterns) + len(conventions),
                            "limit": limit,
                            "fast_mode": fast_mode,
                            "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                            "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                        },
                    },
                    session_id=os.environ.get("CLAUDE_SESSION_ID"),
                    project_id=effective_group_id,
                    start_time=_trace_start,
                    end_time=_trace_end,
                    tags=["search", "retrieval"],
                )
            except Exception:
                pass

        return {
            "code-patterns": code_patterns,
            "conventions": conventions,
        }

    def cascading_search(
        self,
        query: str,
        group_id: str | None,
        primary_collection: str,
        secondary_collections: list[str],
        limit: int = 5,
        min_results: int = 3,
        min_relevance: float = 0.5,
        memory_type: str | list[str] | None = None,
        fast_mode: bool = False,  # NEW: Pass through to search() for hnsw_ef tuning
        source: str | None = None,  # SPEC-005: Namespace filter (e.g., "github")
    ) -> list[dict]:
        """Search primary collection first, expand to secondary if results insufficient.

        Implements V2.0 cascading search strategy: search the primary collection based
        on detected intent, and only expand to secondary collections if results are
        insufficient (fewer than min_results OR best result below min_relevance).

        This approach is more efficient than searching all collections upfront.

        Args:
            query: Search query text
            group_id: Project isolation filter (None = search all)
            primary_collection: Collection to search first (based on intent)
            secondary_collections: Collections to search if primary insufficient
            limit: Maximum results to return (default: 5)
            min_results: Minimum results before expanding (default: 3)
            min_relevance: Minimum relevance score before expanding (default: 0.5)
            memory_type: Optional filter by memory type(s). Can be a single string
                        or list of strings. If None, no type filtering is applied.
            fast_mode: If True, use hnsw_ef=64 for faster search (triggers).
                      If False (default), use hnsw_ef=128 for accuracy (user searches).
            source: Optional source namespace filter (e.g., "github"). When set,
                   adds source and is_current filters per SPEC-005.

        Returns:
            List of search results with collection attribution. Each result dict
            contains: id, score, collection, content, and other payload fields.

        Example:
            >>> search = MemorySearch()
            >>> results = search.cascading_search(
            ...     query="how do I implement auth",
            ...     group_id="my-project",
            ...     primary_collection="code-patterns",
            ...     secondary_collections=["conventions", "discussions"],
            ...     limit=5
            ... )
            >>> results[0]["collection"]
            'code-patterns'
        """
        _trace_start = datetime.now(tz=timezone.utc)

        # Step 1: Search primary collection
        primary_results = self.search(
            query=query,
            collection=primary_collection,
            group_id=group_id,
            limit=limit,
            memory_type=memory_type,
            fast_mode=fast_mode,
            source=source,
        )

        # Step 2: Check if results are sufficient
        results_count = len(primary_results)
        best_score = primary_results[0]["score"] if primary_results else 0.0

        if results_count >= min_results and best_score >= min_relevance:
            # Primary results are sufficient - no expansion needed
            logger.debug(
                "cascading_search_primary_sufficient",
                extra={
                    "primary_collection": primary_collection,
                    "results_count": results_count,
                    "best_score": best_score,
                    "min_results": min_results,
                    "min_relevance": min_relevance,
                    "expansion_needed": False,
                },
            )
            # SPEC-021: Emit cascading search trace (primary sufficient)
            if emit_trace_event:
                try:
                    _trace_end = datetime.now(tz=timezone.utc)
                    _casc_previews = "\n---\n".join(
                        f"[{m.get('type','?')}|{primary_collection}|{round(m.get('score',0)*100)}%] {m.get('content','')[:400]}"
                        for m in primary_results[:10]
                    )
                    emit_trace_event(
                        event_type="cascading_search",
                        data={
                            "input": query[:TRACE_CONTENT_MAX],
                            "output": (
                                _casc_previews[:TRACE_CONTENT_MAX]
                                if _casc_previews
                                else "No results"
                            ),
                            "metadata": {
                                "primary_collection": primary_collection,
                                "secondary_collections": secondary_collections,
                                "total_results": len(primary_results),
                                "primary_results_count": len(primary_results),
                                "secondary_results_count": 0,
                                "expanded": False,
                                "intent_type": str(memory_type),
                                "search_type": "cascading",
                                "agent_name": os.environ.get(
                                    "CLAUDE_AGENT_NAME", "main"
                                ),
                                "agent_role": os.environ.get(
                                    "CLAUDE_AGENT_ROLE", "user"
                                ),
                            },
                        },
                        session_id=os.environ.get("CLAUDE_SESSION_ID"),
                        project_id=group_id,
                        start_time=_trace_start,
                        end_time=_trace_end,
                        tags=["search", "retrieval"],
                    )
                except Exception:
                    pass
            return primary_results

        # Step 3: Results insufficient - expand to secondary collections
        logger.debug(
            "cascading_search_expanding",
            extra={
                "primary_collection": primary_collection,
                "primary_count": results_count,
                "best_score": best_score,
                "min_results": min_results,
                "min_relevance": min_relevance,
                "secondary_collections": secondary_collections,
                "reason": (
                    "insufficient_results"
                    if results_count < min_results
                    else "low_relevance"
                ),
            },
        )

        # Collect all results (primary + secondary)
        all_results = list(primary_results)

        for secondary in secondary_collections:
            secondary_results = self.search(
                query=query,
                collection=secondary,
                group_id=group_id,
                limit=limit,
                memory_type=None,  # Primary intent types may not exist in secondary
                # collections (e.g., "implementation" in code-patterns but not conventions)
                fast_mode=fast_mode,
                source=source,
            )
            all_results.extend(secondary_results)

        # Step 4: Sort by score (descending) and return top `limit`
        all_results.sort(key=lambda r: r["score"], reverse=True)
        final_results = all_results[:limit]

        logger.info(
            "cascading_search_completed",
            extra={
                "primary_collection": primary_collection,
                "secondary_collections": secondary_collections,
                "total_candidates": len(all_results),
                "returned_count": len(final_results),
                "expanded": True,
            },
        )

        # SPEC-021: Emit cascading search trace (expanded)
        _secondary_count = len(all_results) - results_count
        _collections_searched = 1 + len(secondary_collections)
        if emit_trace_event:
            try:
                _trace_end = datetime.now(tz=timezone.utc)
                _casc_exp_previews = "\n---\n".join(
                    f"[{m.get('type','?')}|{m.get('collection','?')}|{round(m.get('score',0)*100)}%] {m.get('content','')[:400]}"
                    for m in final_results[:10]
                )
                emit_trace_event(
                    event_type="cascading_search",
                    data={
                        "input": query[:TRACE_CONTENT_MAX],
                        "output": (
                            _casc_exp_previews[:TRACE_CONTENT_MAX]
                            if _casc_exp_previews
                            else "No results"
                        ),
                        "metadata": {
                            "primary_collection": primary_collection,
                            "secondary_collections": secondary_collections,
                            "total_results": len(final_results),
                            "primary_results_count": results_count,
                            "secondary_results_count": _secondary_count,
                            "expanded": True,
                            "intent_type": str(memory_type),
                            "search_type": "cascading",
                            "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                            "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                        },
                    },
                    session_id=os.environ.get("CLAUDE_SESSION_ID"),
                    project_id=group_id,
                    start_time=_trace_start,
                    end_time=_trace_end,
                    tags=["search", "retrieval"],
                )
            except Exception:
                pass

        return final_results

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
            r for r in results if medium_threshold <= r["score"] < high_threshold
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
                # Display truncation for stdout (not a trace limit)
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
            Uses contextlib.suppress to handle interpreter shutdown safely.
            Prefer using context manager or explicit close() instead.
        """
        # Silently ignore errors during interpreter shutdown
        with contextlib.suppress(Exception):
            self.close()


def retrieve_best_practices(
    query: str,
    limit: int = 3,
    fast_mode: bool = False,
    config: MemoryConfig | None = None,
) -> list[dict]:
    """Retrieve best practices regardless of current project.

    Implements AC 4.3.2 (Best Practices Retrieval) and FR16 (Cross-Project Sharing).

    Best practices are shared across all projects (FR16), so no group_id
    filter is applied. This enables universal pattern discovery.

    Unlike code-patterns (Story 4.2), best practices:
    - NO group_id filter applied (searches all best practices)
    - Collection is always "conventions" (not "code-patterns")
    - NO cwd parameter (best practices are intentionally global)
    - Smaller default limit (3 vs 5) for context efficiency

    Args:
        query: Semantic search query for best practices
        limit: Maximum number of results (default: 3 for context efficiency)
        fast_mode: If True, use hnsw_ef_fast for faster search.
                  If False (default), use hnsw_ef_accurate for accuracy.
                  Note: Best practices are typically user-facing, so
                  accuracy is preferred over speed (default=False).
        config: Optional MemoryConfig instance. Uses get_config() if not provided.

    Returns:
        list[dict]: Best practice memories with content and metadata, sorted by
                    similarity score (highest first). Each result contains:
                    - id: Memory UUID
                    - score: Similarity score (0-1)
                    - content: Best practice text
                    - group_id: Always "shared"
                    - type: Always "pattern"
                    - collection: Always "conventions"
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
        'conventions'

    Note:
        No 'cwd' parameter - best practices are intentionally global.
        Search uses only semantic similarity, not project filtering.

    Performance Considerations (2026):
        Per Qdrant Multitenancy Guide (https://qdrant.tech/articles/multitenancy/):
        - Unfiltered queries (no group_id filter) scan all vectors in collection
        - For conventions collection with ~100-1000 entries, overhead is minimal (<50ms)
        - Much faster than maintaining separate collections per project
        - Use smaller default limit=3 vs code-patterns limit=5 to reduce context load

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
            collection=COLLECTION_CONVENTIONS,  # CRITICAL: Separate collection for shared content
            group_id=None,  # CRITICAL: No project filter for shared collection
            limit=limit,
            fast_mode=fast_mode,
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


def search_memories(
    query: str,
    collection: str | None = None,
    group_id: str | None = None,
    limit: int = 5,
    memory_type: str | list[str] | None = None,
    use_cascading: bool = False,
    intent: str | None = None,
    fast_mode: bool = False,
    source: str | None = None,
    config: MemoryConfig | None = None,
) -> list[dict]:
    """Search memories with optional intent-based cascading.

    Convenience function for searching memories with backward compatibility.
    When use_cascading=True and collection=None, uses intent detection to
    route to the appropriate primary collection and cascades if needed.

    Memory System V2.0: Supports cascading search across collections based
    on detected user intent (HOW → code-patterns, WHAT → conventions,
    WHY → discussions).

    Args:
        query: Search query text
        collection: Collection to search. If None with use_cascading=True,
                   auto-detects based on intent.
        group_id: Optional project isolation filter
        limit: Maximum results to return (default: 5)
        memory_type: Optional memory type(s) to filter by - accepts string or list
        use_cascading: If True and collection=None, use cascading search
                      based on detected intent (default: False)
        intent: Optional pre-detected intent ("how", "what", "why").
               If not provided, will be auto-detected from query.
        fast_mode: If True, use hnsw_ef_fast for faster search (triggers).
                  If False (default), use hnsw_ef_accurate for accuracy.
        source: Optional source filter (e.g., "github" for GitHub namespace isolation)
        config: Optional MemoryConfig instance

    Returns:
        List of memory dicts with score, id, collection, and payload fields.
        Sorted by similarity score (highest first).

    Raises:
        EmbeddingError: If embedding service is unavailable
        QdrantUnavailable: If Qdrant search fails

    Example (backward compatible - explicit collection):
        >>> results = search_memories(
        ...     query="how do I implement auth",
        ...     collection="code-patterns",
        ...     group_id="my-project"
        ... )
        >>> len(results)
        5

    Example (cascading search):
        >>> results = search_memories(
        ...     query="how do I implement auth",
        ...     group_id="my-project",
        ...     use_cascading=True
        ... )
        >>> results[0]["collection"]  # Attribution included
        'code-patterns'

    Note:
        - Backward compatible: Existing callers passing collection work unchanged
        - Collection attribution: All results include 'collection' field
        - Efficient: Only expands to secondary collections if primary insufficient
    """
    search = MemorySearch(config=config)
    start_time = time.perf_counter()

    def _log_search(results):
        duration_ms = (time.perf_counter() - start_time) * 1000
        log_memory_search(
            project=group_id or "unknown",
            query=query,
            results_count=len(results),
            duration_ms=duration_ms,
            results=results,
        )

    # Backward compatible: If collection explicitly provided, use direct search
    if collection is not None:
        logger.debug(
            "search_memories_direct",
            extra={"collection": collection, "group_id": group_id},
        )
        try:
            results = search.search(
                query=query,
                collection=collection,
                group_id=group_id,
                limit=limit,
                memory_type=memory_type,
                fast_mode=fast_mode,
                source=source,
            )
            _log_search(results)
            return results
        except Exception:
            _log_search([])
            raise

    # If not using cascading and no collection, default to code-patterns
    if not use_cascading:
        logger.debug(
            "search_memories_default_collection",
            extra={"collection": COLLECTION_CODE_PATTERNS, "group_id": group_id},
        )
        try:
            results = search.search(
                query=query,
                collection=COLLECTION_CODE_PATTERNS,
                group_id=group_id,
                limit=limit,
                memory_type=memory_type,
                fast_mode=fast_mode,
                source=source,
            )
            _log_search(results)
            return results
        except Exception:
            _log_search([])
            raise

    # Cascading search: Detect intent and route appropriately
    from .intent import (
        IntentType,
        detect_intent,
        get_target_collection,
        get_target_types,
    )

    # Detect or use provided intent
    detected_intent = IntentType(intent.lower()) if intent else detect_intent(query)

    # Get primary collection and types for this intent
    primary_collection = get_target_collection(detected_intent)
    intent_types = get_target_types(detected_intent)

    # Explicit memory_type overrides intent-inferred types (intentional - user knows what they want)
    effective_types = (
        memory_type if memory_type else (intent_types if intent_types else None)
    )

    # Build secondary collections list (all collections except primary)
    all_collections = [
        COLLECTION_CODE_PATTERNS,
        COLLECTION_CONVENTIONS,
        COLLECTION_DISCUSSIONS,
    ]
    secondary_collections = [c for c in all_collections if c != primary_collection]

    logger.info(
        "search_memories_cascading",
        extra={
            "query": query[:50],
            "detected_intent": detected_intent.value,
            "primary_collection": primary_collection,
            "secondary_collections": secondary_collections,
            "memory_type": effective_types,
            "group_id": group_id,
        },
    )

    try:
        results = search.cascading_search(
            query=query,
            group_id=group_id,  # Pass None to use no filter
            primary_collection=primary_collection,
            secondary_collections=secondary_collections,
            limit=limit,
            memory_type=effective_types,
            fast_mode=fast_mode,
            source=source,
        )
        _log_search(results)
        return results
    except Exception:
        _log_search([])
        raise
