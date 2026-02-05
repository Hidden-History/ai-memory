"""
Prometheus metrics definitions for AI Memory Module.

Defines Counter, Gauge, Histogram, and Info metrics for monitoring
memory capture, retrieval, embedding generation, and system health.

Complies with:
- AC 6.1.2: Core metrics definitions
- AC 6.1.4: Failure event counters for alerting
- AC 6.6.3: Collection statistics gauge updates
- prometheus_client v0.24.0 best practices (2026)
- BP-045: Naming convention aimemory_{component}_{metric}_{unit}
- NFR-P1 through NFR-P6 performance requirements

NFR Metric Mapping:
| NFR ID  | Target    | Metric Name                                |
|---------|-----------|-------------------------------------------|
| NFR-P1  | <500ms    | aimemory_hook_duration_seconds            |
| NFR-P2  | <2s       | aimemory_embedding_batch_duration_seconds |
| NFR-P3  | <3s       | aimemory_session_injection_duration_seconds|
| NFR-P4  | <100ms    | aimemory_dedup_check_duration_seconds     |
| NFR-P5  | <500ms    | aimemory_retrieval_query_duration_seconds |
| NFR-P6  | <500ms    | aimemory_embedding_realtime_duration_seconds|
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ==============================================================================
# COUNTERS - Monotonically increasing values
# ==============================================================================

memory_captures_total = Counter(
    "aimemory_captures_total",
    "Total memory capture attempts",
    ["hook_type", "status", "project", "collection"],
    # status: success, queued, failed
    # hook_type: PostToolUse, SessionStart, Stop
    # collection: code-patterns, conventions, discussions
)

memory_retrievals_total = Counter(
    "aimemory_retrievals_total",
    "Total memory retrieval attempts",
    ["collection", "status", "project"],
    # status: success, empty, failed
    # collection: code-patterns, conventions, discussions, combined
    # project: project name for multi-tenancy filtering (required per §7.3)
)

embedding_requests_total = Counter(
    "aimemory_embedding_requests_total",
    "Total embedding generation requests",
    ["status", "embedding_type", "context", "project"],
    # status: success, timeout, failed
    # embedding_type: dense, sparse_bm25, sparse_splade
    # context: realtime (NFR-P6), batch (NFR-P2) - for distinguishing latency targets
    # project: project name for multi-tenancy filtering
)

# Deduplication events - Counter for tracking dedup outcomes
# Note: Use dedup_check_duration_seconds (Histogram) for NFR-P4 timing
deduplication_events_total = Counter(
    "aimemory_dedup_events_total",
    "Deduplication outcomes (stored vs skipped)",
    [
        "action",
        "collection",
        "project",
    ],  # BUG-021: Added action/collection for dashboard granularity
    # action: skipped_duplicate (when dedup detected), stored (when unique)
    # collection: code-patterns, conventions, discussions
)

failure_events_total = Counter(
    "aimemory_failure_events_total",
    "Total failure events for alerting",
    ["component", "error_code", "project"],
    # component: qdrant, embedding, queue, hook
    # error_code: QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT, QUEUE_FULL, VALIDATION_ERROR
    # project: project name for multi-tenancy filtering
)

# ==============================================================================
# TOKEN TRACKING (V2.0 - TECH-DEBT-067)
# ==============================================================================

tokens_consumed_total = Counter(
    "aimemory_tokens_consumed_total",
    "Total tokens consumed by memory operations",
    ["operation", "direction", "project"],
    # operation: capture, retrieval, trigger, injection
    # direction: input, output, stored
    # project: project name (from group_id)
)

# ==============================================================================
# TRIGGER TRACKING (V2.0 - TECH-DEBT-067)
# ==============================================================================

trigger_fires_total = Counter(
    "aimemory_trigger_fires_total",
    "Total trigger activations by type",
    ["trigger_type", "status", "project"],
    # trigger_type: decision_keywords, best_practices_keywords, session_history_keywords,
    #               error_detection, new_file, first_edit
    # status: success, empty, failed
    # project: project name
)

trigger_results_returned = Histogram(
    "aimemory_trigger_results_returned",
    "Number of results returned per trigger",
    ["trigger_type", "project"],
    buckets=[0, 1, 2, 3, 5, 10, 20],
)

# ==============================================================================
# GAUGES - Point-in-time values (can go up or down)
# ==============================================================================

collection_size = Gauge(
    "aimemory_collection_size",
    "Number of memories in collection",
    ["collection", "project"],
)

queue_size = Gauge(
    "aimemory_queue_size",
    "Pending items in retry queue",
    ["status"],
    # status: pending, exhausted, ready
)

# ==============================================================================
# HISTOGRAMS - Distributions of observed values
# NFR-aligned metrics with proper naming per BP-045
# ==============================================================================

# NFR-P1: Hook execution time <500ms
hook_duration_seconds = Histogram(
    "aimemory_hook_duration_seconds",
    "Hook execution time in seconds (NFR-P1: <500ms)",
    ["hook_type", "status", "project"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0, 5.0],
    # Buckets focused around 500ms target with fine granularity below threshold
    # project: Required per Core-Architecture-Principle-V2.md §7.3 for tenant isolation
)

# NFR-P2: Batch embedding latency <2s
embedding_batch_duration_seconds = Histogram(
    "aimemory_embedding_batch_duration_seconds",
    "Batch embedding generation time in seconds (NFR-P2: <2s)",
    ["embedding_type", "project"],
    buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
    # Buckets focused around 2s target for batch operations
    # embedding_type: dense, sparse_bm25, sparse_splade
)

# NFR-P3: SessionStart injection time <3s
session_injection_duration_seconds = Histogram(
    "aimemory_session_injection_duration_seconds",
    "SessionStart context injection time in seconds (NFR-P3: <3s)",
    ["project"],
    buckets=[0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    # Buckets focused around 3s target
)

# NFR-P4: Deduplication check time <100ms
dedup_check_duration_seconds = Histogram(
    "aimemory_dedup_check_duration_seconds",
    "Deduplication check time in seconds (NFR-P4: <100ms)",
    ["collection", "project"],
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.5, 1.0],
    # Buckets focused around 100ms target with fine granularity
)

# NFR-P5: Retrieval query latency <500ms
retrieval_query_duration_seconds = Histogram(
    "aimemory_retrieval_query_duration_seconds",
    "Memory retrieval query time in seconds (NFR-P5: <500ms)",
    ["collection", "project"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0],
    # Buckets focused around 500ms target
)

# NFR-P6: Real-time embedding latency <500ms
embedding_realtime_duration_seconds = Histogram(
    "aimemory_embedding_realtime_duration_seconds",
    "Real-time embedding generation time in seconds (NFR-P6: <500ms)",
    ["embedding_type", "project"],
    buckets=[0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0],
    # Buckets focused around 500ms target for real-time path
    # embedding_type: dense, sparse_bm25, sparse_splade
)

# Legacy metrics - kept for backward compatibility during migration
# TODO: Remove deprecated metrics after Grafana V3 dashboards deployed (TECH-DEBT-123)
embedding_duration_seconds = Histogram(
    "ai_memory_embedding_latency",
    "[DEPRECATED] Use aimemory_embedding_*_duration_seconds instead",
    ["embedding_type"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

retrieval_duration_seconds = Histogram(
    "ai_memory_search_latency",
    "[DEPRECATED] Use aimemory_retrieval_query_duration_seconds instead",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0],
)

context_injection_tokens = Histogram(
    "aimemory_context_injection_tokens",
    "Tokens injected into Claude context per hook",
    ["hook_type", "collection", "project"],
    buckets=[100, 250, 500, 1000, 1500, 2000, 3000, 5000],
    # hook_type: SessionStart, UserPromptSubmit, PreToolUse
    # collection: code-patterns, conventions, discussions, combined
    # project: project name for multi-tenancy filtering
)

# ==============================================================================
# INFO - Static metadata about the system
# ==============================================================================

system_info = Info("aimemory_system", "Memory system configuration")

# Initialize system info with static metadata
system_info.info(
    {
        "version": "2.0.0",
        "embedding_model": "jina-embeddings-v2-base-en",
        "vector_dimensions": "768",
        "collections": "code-patterns,conventions,discussions",
    }
)


# ==============================================================================
# COLLECTION STATISTICS UPDATES (AC 6.6.3)
# ==============================================================================


def update_collection_metrics(stats) -> None:
    """Update Prometheus gauges with current collection stats.

    Updates collection_size gauge with both overall collection metrics
    and per-project breakdown. Enables monitoring of collection growth
    and per-project memory usage.

    Args:
        stats: CollectionStats with current collection data

    Example:
        >>> from memory.config import get_config
        >>> from qdrant_client import QdrantClient
        >>> from memory.stats import get_collection_stats
        >>> config = get_config()
        >>> client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
        >>> stats = get_collection_stats(client, "code-patterns")
        >>> update_collection_metrics(stats)
    """
    # Overall collection size
    collection_size.labels(collection=stats.collection_name, project="all").set(
        stats.total_points
    )

    # Per-project sizes
    for project, count in stats.points_by_project.items():
        collection_size.labels(collection=stats.collection_name, project=project).set(
            count
        )
