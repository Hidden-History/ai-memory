"""Push metrics to Prometheus Pushgateway for short-lived hook processes.

Provides async push functions for hooks aligned with NFR performance requirements:
- push_hook_metrics_async() - Hook execution duration (NFR-P1: <500ms)
- push_embedding_metrics_async() - Embedding generation (NFR-P2/P6)
- push_session_injection_metrics_async() - SessionStart injection (NFR-P3: <3s)
- push_dedup_metrics_async() - Deduplication checks (NFR-P4: <100ms)
- push_retrieval_metrics_async() - Query latency (NFR-P5: <500ms)
- push_trigger_metrics_async() - Trigger activations
- push_token_metrics_async() - Token consumption
- push_context_injection_metrics_async() - Context injection
- push_capture_metrics_async() - Memory captures

Metric naming follows BP-045: aimemory_{component}_{metric}_{unit}

All push functions use subprocess fork pattern to avoid blocking hook execution.
"""

import json
import logging
import os
import subprocess
import sys
import time
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Histogram, pushadd_to_gateway

logger = logging.getLogger("ai_memory.metrics")

PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "localhost:29091")
PUSHGATEWAY_ENABLED = os.getenv("PUSHGATEWAY_ENABLED", "true").lower() == "true"

# Job name per Monitoring-System-V2-Spec.md
JOB_NAME = "ai_memory_hooks"

# Validation sets for label values (HIGH-1)
VALID_STATUSES = {"success", "empty", "error", "failed", "queued", "skipped", "timeout"}
VALID_OPERATIONS = {"capture", "retrieval", "trigger", "injection", "classification"}

# MEDIUM-3: Direction label semantics clarification
# These labels describe data flow relative to the memory system:
#   "input"  - Data flowing INTO an operation (e.g., prompt to classifier, query to search)
#   "output" - Data flowing OUT of an operation (e.g., LLM response, search results)
#   "stored" - Data persisted to Qdrant collections (e.g., captured code, user messages)
VALID_DIRECTIONS = {"input", "output", "stored"}

VALID_HOOK_TYPES = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "Stop",
}
VALID_EMBEDDING_TYPES = {"dense", "sparse_bm25", "sparse_splade"}
VALID_COLLECTIONS = {"code-patterns", "conventions", "discussions"}
VALID_COMPONENTS = {"qdrant", "embedding", "queue", "hook"}
VALID_ERROR_CODES = {
    "QDRANT_UNAVAILABLE",
    "EMBEDDING_TIMEOUT",
    "EMBEDDING_ERROR",
    "VALIDATION_ERROR",
}


def _validate_label(
    value: str, param_name: str, allowed: set[str] | None = None
) -> str:
    """Validate and sanitize label value.

    Args:
        value: Label value to validate
        param_name: Parameter name for logging
        allowed: Optional set of allowed values

    Returns:
        Validated label value or "unknown" if invalid
    """
    if not value or not isinstance(value, str):
        logger.warning(
            "invalid_label_value", extra={"param": param_name, "value": repr(value)}
        )
        return "unknown"
    if allowed and value not in allowed:
        logger.warning(
            "unexpected_label_value",
            extra={"param": param_name, "value": value, "allowed": list(allowed)},
        )
    return value


def push_hook_metrics(
    hook_name: str,
    duration_seconds: float,
    success: bool = True,
    project: str = "unknown",
):
    """Push hook execution metrics to Pushgateway (NFR-P1: <500ms).

    Args:
        hook_name: Name of the hook (e.g., 'session_start', 'post_tool_capture')
        duration_seconds: Hook execution duration in seconds
        success: Whether the hook executed successfully
        project: Project name for multi-tenancy (Core-Architecture-Principle-V2.md §7.3)
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels
    project = _validate_label(project, "project")

    registry = CollectorRegistry()

    duration = Histogram(
        "aimemory_hook_duration_seconds",
        "Hook execution duration (NFR-P1: <500ms)",
        ["hook_type", "status", "project"],
        registry=registry,
        buckets=(
            0.05,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.75,
            1.0,
            2.0,
            5.0,
        ),  # Focus on <500ms requirement
    )
    duration.labels(
        hook_type=hook_name,
        status="success" if success else "error",
        project=project,
    ).observe(duration_seconds)

    try:
        pushadd_to_gateway(
            PUSHGATEWAY_URL, job=JOB_NAME, registry=registry, timeout=0.5
        )
    except Exception as e:
        logger.warning(
            "pushgateway_push_failed",
            extra={
                "metric": "aimemory_hook_duration_seconds",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )


def push_hook_metrics_async(
    hook_name: str,
    duration_seconds: float,
    success: bool = True,
    project: str = "unknown",
):
    """Push hook execution metrics to Pushgateway asynchronously (fire-and-forget).

    NFR-P1: Hook execution time <500ms

    Uses subprocess.Popen to fork the push operation to background, ensuring
    hooks complete in <500ms even if Pushgateway is unreachable.

    Args:
        hook_name: Name of the hook (e.g., 'session_start', 'post_tool_capture')
        duration_seconds: Hook execution duration in seconds
        success: Whether the hook executed successfully
        project: Project name for multi-tenancy (Core-Architecture-Principle-V2.md §7.3)
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "hook_name": hook_name,
            "duration_seconds": duration_seconds,
            "success": success,
            "project": project,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()
duration = Histogram(
    "aimemory_hook_duration_seconds",
    "Hook execution duration (NFR-P1: <500ms)",
    ["hook_type", "status", "project"],
    registry=registry,
    buckets=(0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0, 5.0)
)
duration.labels(
    hook_type=data["hook_name"],
    status="success" if data["success"] else "error",
    project=data["project"]
).observe(data["duration_seconds"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "hook_duration"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Full detachment from parent
        )
    except Exception:
        pass  # Graceful degradation - don't fail hook if fork fails


@contextmanager
def track_hook_duration(hook_name: str, project: str = "unknown"):
    """Context manager to track and push hook duration.

    Uses async push to ensure <500ms hook performance even if Pushgateway is down.

    Args:
        hook_name: Name of the hook being tracked
        project: Project name for multi-tenancy (Core-Architecture-Principle-V2.md §7.3)

    Usage:
        with track_hook_duration("session_start", project="my-project"):
            # hook logic here
            pass
    """
    start = time.time()
    success = True
    try:
        yield
    except Exception:
        success = False
        raise
    finally:
        duration = time.time() - start
        push_hook_metrics_async(
            hook_name, duration, success, project
        )  # Fire-and-forget for <500ms


def push_trigger_metrics_async(
    trigger_type: str,
    status: str,
    project: str,
    results_count: int = 0,
    duration_seconds: float = 0.0,
):
    """Push trigger execution metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.

    Args:
        trigger_type: decision_keywords, best_practices_keywords, session_history_keywords
        status: success, empty, failed
        project: Project name from group_id
        results_count: Number of results returned
        duration_seconds: Trigger execution duration (not currently used)
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    status = _validate_label(status, "status", VALID_STATUSES)
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "trigger_type": trigger_type,
            "status": status,
            "project": project,
            "results_count": results_count,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

fires = Counter(
    "aimemory_trigger_fires_total",
    "Total trigger activations",
    ["trigger_type", "status", "project"],
    registry=registry
)
fires.labels(
    trigger_type=data["trigger_type"],
    status=data["status"],
    project=data["project"]
).inc()

results = Histogram(
    "aimemory_trigger_results_returned",
    "Number of results per trigger",
    ["trigger_type", "project"],
    registry=registry,
    buckets=(0, 1, 2, 3, 5, 10, 20)
)
results.labels(trigger_type=data["trigger_type"], project=data["project"]).observe(data["results_count"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "trigger"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "trigger"}
        )


def push_token_metrics_async(
    operation: str, direction: str, project: str, token_count: int
):
    """Push token consumption metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.

    Args:
        operation: capture, retrieval, trigger, injection
        direction: input, output, stored
        project: Project name
        token_count: Number of tokens
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    operation = _validate_label(operation, "operation", VALID_OPERATIONS)
    direction = _validate_label(direction, "direction", VALID_DIRECTIONS)
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "operation": operation,
            "direction": direction,
            "project": project,
            "token_count": token_count,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

tokens = Counter(
    "aimemory_tokens_consumed_total",
    "Total tokens consumed",
    ["operation", "direction", "project"],
    registry=registry
)
tokens.labels(
    operation=data["operation"],
    direction=data["direction"],
    project=data["project"]
).inc(data["token_count"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "token"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "token"}
        )


def push_context_injection_metrics_async(
    hook_type: str, collection: str, project: str, token_count: int
):
    """Push context injection token metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.

    Args:
        hook_type: SessionStart, UserPromptSubmit, PreToolUse
        collection: code-patterns, conventions, discussions, combined
        project: Project name for filtering in dashboards
        token_count: Tokens injected into context

    Note:
        Cardinality: 3 hook_types x 4 collections x N projects = 12N time series.
        Monitor Prometheus/Pushgateway memory usage if project count is high (>100).
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    hook_type = _validate_label(hook_type, "hook_type", VALID_HOOK_TYPES)
    collection = _validate_label(collection, "collection")
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "hook_type": hook_type,
            "collection": collection,
            "project": project,
            "token_count": token_count,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

injection = Histogram(
    "aimemory_context_injection_tokens",
    "Tokens injected per hook",
    ["hook_type", "collection", "project"],
    registry=registry,
    buckets=(100, 250, 500, 1000, 1500, 2000, 3000, 5000)
)
injection.labels(
    hook_type=data["hook_type"],
    collection=data["collection"],
    project=data["project"]
).observe(data["token_count"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "context_injection"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed",
            extra={"error": str(e), "metric": "context_injection"},
        )


def push_capture_metrics_async(
    hook_type: str, status: str, project: str, collection: str, count: int = 1
):
    """Push memory capture metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.

    Args:
        hook_type: PostToolUse, PreCompact, Stop, UserPromptSubmit
        status: success, failed, queued, duplicate
        project: Project name
        collection: code-patterns, conventions, discussions
        count: Number of captures (for batches)
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    hook_type = _validate_label(hook_type, "hook_type", VALID_HOOK_TYPES)
    status = _validate_label(status, "status", VALID_STATUSES)
    project = _validate_label(project, "project")
    collection = _validate_label(collection, "collection", VALID_COLLECTIONS)

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "hook_type": hook_type,
            "status": status,
            "project": project,
            "collection": collection,
            "count": count,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

captures = Counter(
    "aimemory_captures_total",
    "Total memory captures",
    ["hook_type", "status", "project", "collection"],
    registry=registry
)
captures.labels(
    hook_type=data["hook_type"],
    status=data["status"],
    project=data["project"],
    collection=data["collection"]
).inc(data["count"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "capture"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "capture"}
        )


def push_embedding_metrics_async(
    status: str,
    embedding_type: str,
    duration_seconds: float,
    context: str = "realtime",
    project: str = "unknown",
):
    """Push embedding request metrics asynchronously (fire-and-forget).

    NFR-P2: Batch embedding latency <2s (context="batch")
    NFR-P6: Real-time embedding latency <500ms (context="realtime")

    Uses subprocess fork pattern to avoid blocking hook execution.
    Pushes both Counter and Histogram metrics for Grafana dashboard visibility.

    Args:
        status: success, timeout, failed
        embedding_type: dense, sparse_bm25, sparse_splade
        duration_seconds: Embedding generation duration
        context: "realtime" (NFR-P6) or "batch" (NFR-P2) - determines latency target
        project: Project name for multi-tenancy
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    status = _validate_label(status, "status", VALID_STATUSES)
    embedding_type = _validate_label(
        embedding_type, "embedding_type", VALID_EMBEDDING_TYPES
    )
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "status": status,
            "embedding_type": embedding_type,
            "duration_seconds": duration_seconds,
            "context": context,
            "project": project,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

requests = Counter(
    "aimemory_embedding_requests_total",
    "Total embedding requests",
    ["status", "embedding_type", "context"],
    registry=registry
)
requests.labels(
    status=data["status"],
    embedding_type=data["embedding_type"],
    context=data["context"]
).inc()

# Use appropriate histogram based on context
if data["context"] == "batch":
    # NFR-P2: Batch embedding <2s
    duration = Histogram(
        "aimemory_embedding_batch_duration_seconds",
        "Batch embedding generation duration (NFR-P2: <2s)",
        ["embedding_type", "project"],
        registry=registry,
        buckets=(0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
    )
else:
    # NFR-P6: Real-time embedding <500ms
    duration = Histogram(
        "aimemory_embedding_realtime_duration_seconds",
        "Real-time embedding generation duration (NFR-P6: <500ms)",
        ["embedding_type", "project"],
        registry=registry,
        buckets=(0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0)
    )

duration.labels(embedding_type=data["embedding_type"], project=data["project"]).observe(data["duration_seconds"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "embedding"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "embedding"}
        )


def push_retrieval_metrics_async(
    collection: str, status: str, duration_seconds: float, project: str = "unknown"
):
    """Push memory retrieval metrics asynchronously (fire-and-forget).

    NFR-P5: Retrieval query latency <500ms

    Uses subprocess fork pattern to avoid blocking hook execution.
    Pushes both Counter and Histogram metrics for Grafana dashboard visibility.

    Args:
        collection: code-patterns, conventions, discussions
        status: success, empty, failed
        duration_seconds: Retrieval operation duration
        project: Project name for multi-tenancy
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    collection = _validate_label(collection, "collection", VALID_COLLECTIONS)
    status = _validate_label(status, "status", VALID_STATUSES)
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "collection": collection,
            "status": status,
            "duration_seconds": duration_seconds,
            "project": project,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

retrievals = Counter(
    "aimemory_retrievals_total",
    "Total memory retrievals",
    ["collection", "status", "project"],
    registry=registry
)
retrievals.labels(
    collection=data["collection"],
    status=data["status"],
    project=data["project"]
).inc()

# NFR-P5: Retrieval query latency <500ms
duration = Histogram(
    "aimemory_retrieval_query_duration_seconds",
    "Memory retrieval query duration (NFR-P5: <500ms)",
    ["collection", "project"],
    registry=registry,
    buckets=(0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 2.0)
)
duration.labels(collection=data["collection"], project=data["project"]).observe(data["duration_seconds"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "retrieval"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "retrieval"}
        )


def push_failure_metrics_async(
    component: str, error_code: str, project: str = "unknown"
):
    """Push failure event metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.
    Pushes Counter metric for alerting and Grafana dashboard visibility.

    Args:
        component: qdrant, embedding, queue, hook
        error_code: QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT, EMBEDDING_ERROR, VALIDATION_ERROR
        project: Project name for multi-tenancy
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels (HIGH-1)
    component = _validate_label(component, "component", VALID_COMPONENTS)
    error_code = _validate_label(error_code, "error_code", VALID_ERROR_CODES)
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "component": component,
            "error_code": error_code,
            "project": project,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

failures = Counter(
    "aimemory_failure_events_total",
    "Total failure events",
    ["component", "error_code", "project"],
    registry=registry
)
failures.labels(
    component=data["component"],
    error_code=data["error_code"],
    project=data["project"]
).inc()

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "failure"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "failure"}
        )


def push_skill_metrics_async(skill_name: str, status: str, duration_seconds: float):
    """Push skill invocation metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking skill execution.
    Tracks slash command usage for Grafana dashboards.

    TECH-DEBT-077: Created to track skill invocations.

    Args:
        skill_name: search-memory, memory-status, save-memory
        status: success, empty, failed
        duration_seconds: Skill execution duration
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels
    status = _validate_label(status, "status", VALID_STATUSES)
    skill_name = _validate_label(skill_name, "skill_name")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "skill_name": skill_name,
            "status": status,
            "duration_seconds": duration_seconds,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

invocations = Counter(
    "aimemory_skill_invocations_total",
    "Total skill invocations",
    ["skill_name", "status"],
    registry=registry
)
invocations.labels(
    skill_name=data["skill_name"],
    status=data["status"]
).inc()

duration = Histogram(
    "aimemory_skill_duration_seconds",
    "Skill execution duration",
    ["skill_name"],
    registry=registry,
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)
duration.labels(skill_name=data["skill_name"]).observe(data["duration_seconds"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "skill"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "skill"}
        )


def push_deduplication_metrics_async(action: str, collection: str, project: str):
    """Push deduplication event metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.
    Tracks when duplicates are detected vs unique memories stored.

    BUG-021: Created to push aimemory_dedup_events_total metric.

    Args:
        action: skipped_duplicate (duplicate detected), stored (unique memory)
        collection: code-patterns, conventions, discussions
        project: Project name
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels
    action = _validate_label(action, "action")
    collection = _validate_label(collection, "collection", VALID_COLLECTIONS)
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {"action": action, "collection": collection, "project": project}

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Counter, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

dedup = Counter(
    "aimemory_dedup_events_total",
    "Deduplication outcomes (stored vs skipped)",
    ["action", "collection", "project"],
    registry=registry
)
dedup.labels(
    action=data["action"],
    collection=data["collection"],
    project=data["project"]
).inc()

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "deduplication"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "deduplication"}
        )


def push_queue_metrics_async(
    pending_count: int, exhausted_count: int, ready_count: int = 0
):
    """Push retry queue metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking.

    Args:
        pending_count: Items awaiting retry (retry_count < max_retries)
        exhausted_count: Items that exceeded max_retries
        ready_count: Items ready for immediate retry (next_retry_at <= now)
    """
    if not PUSHGATEWAY_ENABLED:
        return

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "pending_count": pending_count,
            "exhausted_count": exhausted_count,
            "ready_count": ready_count,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Gauge, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

queue_size = Gauge(
    "aimemory_queue_size",
    "Pending items in retry queue",
    ["status"],
    registry=registry
)
queue_size.labels(status="pending").set(data["pending_count"])
queue_size.labels(status="exhausted").set(data["exhausted_count"])
queue_size.labels(status="ready").set(data["ready_count"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "queue_size"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "queue_size"}
        )


def push_dedup_duration_metrics_async(
    collection: str, project: str, duration_seconds: float
):
    """Push deduplication check duration metrics asynchronously (fire-and-forget).

    NFR-P4: Deduplication check time <100ms

    Uses subprocess fork pattern to avoid blocking hook execution.
    Tracks how long deduplication checks take.

    Args:
        collection: code-patterns, conventions, discussions
        project: Project name
        duration_seconds: Deduplication check duration
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels
    collection = _validate_label(collection, "collection", VALID_COLLECTIONS)
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "collection": collection,
            "project": project,
            "duration_seconds": duration_seconds,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

# NFR-P4: Deduplication check time <100ms
duration = Histogram(
    "aimemory_dedup_check_duration_seconds",
    "Deduplication check time (NFR-P4: <100ms)",
    ["collection", "project"],
    registry=registry,
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.5, 1.0)
)
duration.labels(
    collection=data["collection"],
    project=data["project"]
).observe(data["duration_seconds"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "dedup_duration"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed", extra={"error": str(e), "metric": "dedup_duration"}
        )


def push_session_injection_metrics_async(project: str, duration_seconds: float):
    """Push session injection duration metrics asynchronously (fire-and-forget).

    NFR-P3: SessionStart injection time <3s

    Uses subprocess fork pattern to avoid blocking hook execution.
    Tracks how long SessionStart context injection takes.

    Args:
        project: Project name
        duration_seconds: Session injection duration
    """
    if not PUSHGATEWAY_ENABLED:
        return

    # Validate labels
    project = _validate_label(project, "project")

    try:
        # Serialize metrics data for background process
        metrics_data = {
            "project": project,
            "duration_seconds": duration_seconds,
        }

        # Fork to background using subprocess.Popen
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"""
import json, os
from prometheus_client import CollectorRegistry, Histogram, pushadd_to_gateway

data = json.loads({json.dumps(metrics_data)!r})
registry = CollectorRegistry()

# NFR-P3: SessionStart injection time <3s
duration = Histogram(
    "aimemory_session_injection_duration_seconds",
    "SessionStart context injection time (NFR-P3: <3s)",
    ["project"],
    registry=registry,
    buckets=(0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
)
duration.labels(project=data["project"]).observe(data["duration_seconds"])

try:
    pushadd_to_gateway(
        os.getenv("PUSHGATEWAY_URL", "localhost:29091"),
        job="ai_memory_hooks",
        registry=registry,
        timeout=0.5
    )
except Exception as e:
    import logging
    logging.getLogger("ai_memory.metrics").warning(
        "pushgateway_async_failed",
        extra={{"error": str(e), "metric": "session_injection"}}
    )
""",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(
            "metrics_fork_failed",
            extra={"error": str(e), "metric": "session_injection"},
        )
