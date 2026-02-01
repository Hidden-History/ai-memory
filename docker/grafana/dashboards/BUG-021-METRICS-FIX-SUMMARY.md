# BUG-021 Metrics Fix Summary

**Date**: 2026-01-26
**Status**: ✓ Code changes complete, awaiting verification

## Root Cause Analysis

### Issue 1: Classifier Metrics Not Appearing in Prometheus

**Problem**: `memory_classifier_requests_total`, `memory_classifier_tokens_total`, `memory_classifier_fallbacks_total` metrics were defined and incremented but NEVER pushed to Prometheus.

**Root Cause**:
- Metrics defined in `src/memory/classifier/metrics.py` using **global REGISTRY**
- Queue worker in `scripts/memory/process_classification_queue.py` uses **custom registry**
- Worker's `push_metrics()` only pushed its own registry, not global REGISTRY

**Fix Applied**:
```python
# scripts/memory/process_classification_queue.py:112-148
def push_metrics() -> None:
    """Push metrics to Pushgateway.

    Pushes TWO registries:
    1. Worker's custom registry (queue_processed_total, batch_duration, etc.)
    2. Global REGISTRY (classifier metrics from src/memory/classifier/metrics.py)
    """
    # Push worker's custom registry
    pushadd_to_gateway(PUSHGATEWAY_URL, job=JOB_NAME, registry=registry, timeout=2.0)

    # BUG-021 FIX: Also push global REGISTRY (classifier LLM metrics)
    pushadd_to_gateway(PUSHGATEWAY_URL, job=JOB_NAME, registry=REGISTRY, timeout=2.0)
```

### Issue 2: Deduplication Metrics Not Appearing in Prometheus

**Problem**: `ai_memory_dedup_matches` was defined and incremented but NEVER pushed to Prometheus.

**Root Cause**:
- No `push_deduplication_metrics_async()` function existed
- Metric only incremented in-process, never sent to Pushgateway
- Label mismatch: defined with `["project"]` but dashboards expected `["action", "collection", "project"]`

**Fixes Applied**:

1. **Updated metric definition** (`src/memory/metrics.py:45-50`):
```python
deduplication_events_total = Counter(
    "ai_memory_dedup_matches",
    "Memories deduplicated (not stored)",
    ["action", "collection", "project"]  # BUG-021: Added action/collection for dashboard granularity
    # action: skipped_duplicate (when dedup detected), stored (when unique)
    # collection: code-patterns, conventions, discussions
)
```

2. **Created push function** (`src/memory/metrics_push.py:759-821`):
```python
def push_deduplication_metrics_async(
    action: str,
    collection: str,
    project: str
):
    """Push deduplication event metrics asynchronously (fire-and-forget).

    Uses subprocess fork pattern to avoid blocking hook execution.
    Tracks when duplicates are detected vs unique memories stored.
    """
    # Forks subprocess to push metric without blocking
```

3. **Updated deduplication code** (`src/memory/deduplication.py`):
```python
# Import the push function
from .metrics_push import push_deduplication_metrics_async

# Call it when duplicates detected (2 locations: hash match + semantic match)
if push_deduplication_metrics_async:
    push_deduplication_metrics_async(
        action="skipped_duplicate",
        collection=collection,
        project=group_id
    )
```

## Files Modified

| File | Changes |
|------|---------|
| `scripts/memory/process_classification_queue.py` | Added `REGISTRY` import, updated `push_metrics()` to push both registries |
| `src/memory/metrics.py` | Updated `deduplication_events_total` labels from `["project"]` to `["action", "collection", "project"]` |
| `src/memory/metrics_push.py` | Added `push_deduplication_metrics_async()` function |
| `src/memory/deduplication.py` | Added import and calls to `push_deduplication_metrics_async()` at 2 locations |

## Expected Behavior After Fix

### Classifier Metrics
When the classifier worker processes queue items, these metrics should now appear in Prometheus:

```
memory_classifier_requests_total{provider="ollama", status="success", classified_type="decision"}
memory_classifier_requests_total{provider="ollama", status="success", classified_type="error_fix"}
memory_classifier_tokens_total{provider="ollama", direction="input"}
memory_classifier_tokens_total{provider="ollama", direction="output"}
memory_classifier_fallbacks_total{from_provider="ollama", to_provider="openrouter", reason="unavailable"}
memory_classifier_rule_matches_total{rule_type="port_number"}
```

### Deduplication Metrics
When memories are stored or duplicates detected:

```
ai_memory_dedup_matches{action="skipped_duplicate", collection="code-patterns", project="ai-memory-module"}
ai_memory_dedup_matches{action="skipped_duplicate", collection="conventions", project="ai-memory-module"}
ai_memory_dedup_matches{action="skipped_duplicate", collection="discussions", project="ai-memory-module"}
```

## Verification Steps

**Current Status**: Classifier worker restarted, but queue is empty (51 items already processed with old code).

**To Verify Fix**:
1. Generate activity that creates classification queue items
2. Wait for worker to process items (~5 seconds)
3. Query Prometheus:
   ```bash
   # Use the helper script (reads password from PROMETHEUS_PASSWORD env var)
   python3 scripts/monitoring/prometheus_query.py "memory_classifier_requests_total"

   # Or with curl (set PROMETHEUS_PASSWORD first):
   curl -s -u admin:$PROMETHEUS_PASSWORD \
     "http://localhost:29090/api/v1/series?match[]=memory_classifier_requests_total"
   ```
4. Should see series with `provider`, `status`, `classified_type` labels

**To Verify Deduplication**:
1. Create duplicate memories (same content twice)
2. Check Prometheus for `ai_memory_dedup_matches` with `action="skipped_duplicate"`

## Related Issues

- **BUG-021**: Grafana Dashboard Rebuild - No data in panels
- **T1-BUG-021-Grafana-Dashboard-Architect.md**: Original architect prompt defined expected metrics
- **BUG-021-METRICS-ALIGNMENT-REQUIRED.md**: Detailed analysis of mismatches

## Testing Notes

The classifier worker logs show it's polling every 5 seconds:
```json
{"message": "batch_dequeued", "context": {"count": 0, "remaining": 0}}
```

Once NEW items are queued, the worker will:
1. Dequeue batch (up to 10 items)
2. Call `llm_classifier.classify()` which increments global REGISTRY metrics
3. After batch completion, call `push_metrics()` which NOW pushes both registries
4. Metrics appear in Prometheus within 5-10 seconds

## Confidence

**High**: The fix is architecturally sound - the worker runs in a single Python process, `classify()` is called via `run_in_executor` (ThreadPoolExecutor, not subprocess), so the global REGISTRY is shared and the metrics will be pushed.

**Verification Pending**: Need to generate queue items to confirm metrics appear with correct labels.
