"""
Prometheus metrics definitions for AI Memory Module.

Defines Counter, Gauge, Histogram, and Info metrics for monitoring
memory capture, retrieval, embedding generation, and system health.

Complies with:
- AC 6.1.2: Core metrics definitions
- AC 6.1.4: Failure event counters for alerting
- AC 6.6.3: Collection statistics gauge updates
- prometheus_client v0.24.0 best practices (2026)
- Project naming conventions: snake_case, ai_memory_ prefix
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ==============================================================================
# COUNTERS - Monotonically increasing values
# ==============================================================================

memory_captures_total = Counter(
    "ai_memory_captures_total",
    "Total memory capture attempts",
    ["hook_type", "status", "project"],
    # status: success, queued, failed
    # hook_type: PostToolUse, SessionStart, Stop
)

memory_retrievals_total = Counter(
    "ai_memory_retrievals_total",
    "Total memory retrieval attempts",
    ["collection", "status"],
    # status: success, empty, failed
    # collection: code-patterns, conventions, discussions, combined
)

embedding_requests_total = Counter(
    "ai_memory_embedding_requests_total",
    "Total embedding generation requests",
    ["status", "embedding_type"],
    # status: success, timeout, failed
    # embedding_type: dense, sparse_bm25, sparse_splade
)

deduplication_events_total = Counter(
    "ai_memory_dedup_matches",
    "Memories deduplicated (not stored)",
    [
        "action",
        "collection",
        "project",
    ],  # BUG-021: Added action/collection for dashboard granularity
    # action: skipped_duplicate (when dedup detected), stored (when unique)
    # collection: code-patterns, conventions, discussions
)

failure_events_total = Counter(
    "ai_memory_failure_events_total",
    "Total failure events for alerting",
    ["component", "error_code"],
    # component: qdrant, embedding, queue, hook
    # error_code: QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT, QUEUE_FULL, VALIDATION_ERROR
)

# ==============================================================================
# TOKEN TRACKING (V2.0 - TECH-DEBT-067)
# ==============================================================================

tokens_consumed_total = Counter(
    "ai_memory_tokens_consumed_total",
    "Total tokens consumed by memory operations",
    ["operation", "direction", "project"],
    # operation: capture, retrieval, trigger, injection
    # direction: input, output
    # project: project name (from group_id)
)

# ==============================================================================
# TRIGGER TRACKING (V2.0 - TECH-DEBT-067)
# ==============================================================================

trigger_fires_total = Counter(
    "ai_memory_trigger_fires_total",
    "Total trigger activations by type",
    ["trigger_type", "status", "project"],
    # trigger_type: decision_keywords, best_practices_keywords, session_history_keywords,
    #               error_detection, new_file, first_edit
    # status: success, empty, failed
    # project: project name
)

trigger_results_returned = Histogram(
    "ai_memory_trigger_results_returned",
    "Number of results returned per trigger",
    ["trigger_type"],
    buckets=[0, 1, 2, 3, 5, 10, 20],
)

# ==============================================================================
# GAUGES - Point-in-time values (can go up or down)
# ==============================================================================

collection_size = Gauge(
    "ai_memory_collection_size",
    "Number of memories in collection",
    ["collection", "project"],
)

queue_size = Gauge(
    "ai_memory_queue_size",
    "Pending items in retry queue",
    ["status"],
    # status: pending, exhausted
)

# ==============================================================================
# HISTOGRAMS - Distributions of observed values
# ==============================================================================

hook_duration_seconds = Histogram(
    "ai_memory_hook_latency",
    "Hook execution time in seconds",
    ["hook_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
    # Buckets optimized for NFR-P1 <500ms target
)

embedding_duration_seconds = Histogram(
    "ai_memory_embedding_latency",
    "Embedding generation time in seconds",
    ["embedding_type"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
    # Buckets optimized for NFR-P2 <2s target
    # embedding_type: dense, sparse_bm25, sparse_splade
)

retrieval_duration_seconds = Histogram(
    "ai_memory_search_latency",
    "Memory retrieval time in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0],
    # Buckets optimized for SessionStart <3s target
)

context_injection_tokens = Histogram(
    "ai_memory_context_injection_tokens",
    "Tokens injected into Claude context per hook",
    ["hook_type", "collection"],
    buckets=[100, 250, 500, 1000, 1500, 2000, 3000, 5000],
    # hook_type: SessionStart, UserPromptSubmit, PreToolUse
    # collection: code-patterns, conventions, discussions, combined
)

# ==============================================================================
# INFO - Static metadata about the system
# ==============================================================================

system_info = Info("ai_memory_system", "Memory system configuration")

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
