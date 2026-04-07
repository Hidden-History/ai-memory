# TD-363: time.sleep() Categorization Report

**Branch**: `feature/v2.3.0-phased-sprint`  
**Generated**: 2026-04-06  
**Total Calls**: 72

## Category A: SKIP - Already Mocked/Patched (11 calls)

These tests use `patch("time.sleep")` or `patch("module.time.sleep")` - the sleeps are already mocked out during testing. **No changes needed.**

| File | Line | Context |
|------|------|---------|
| `tests/unit/connectors/github/test_github_sync_service.py` | 215 | `patch("github_sync_service.time.sleep")` |
| `tests/unit/connectors/github/test_github_sync_service.py` | 251 | `patch("github_sync_service.time.sleep")` |
| `tests/unit/connectors/github/test_github_sync_service.py` | 287 | `patch("github_sync_service.time.sleep")` |
| `tests/unit/test_embedding_retry.py` | 54 | `patch("memory.embeddings.time.sleep")` |
| `tests/unit/test_embedding_retry.py` | 72 | `patch("memory.embeddings.time.sleep")` |
| `tests/unit/test_embedding_retry.py` | 114 | `patch("memory.embeddings.time.sleep")` |
| `tests/unit/test_evaluator_retry.py` | 77-234 | Multiple `patch("memory.evaluator.provider.time.sleep")` |
| `tests/unit/test_langfuse_config_retry.py` | 73, 105, 134 | `patch("time.sleep")` |
| `tests/unit/test_trace_flush_degraded.py` | 38, 120 | `patch("time.sleep")` |

**Action**: None required.

---

## Category B: SKIP - Tiny Delays <100ms (8 calls)

These are intentional small delays for thread interleaving, scheduling, or signal delivery. They are NOT waiting for async conditions - they're for controlled test timing. **No changes needed.**

| File | Line | Sleep | Purpose |
|------|------|-------|---------|
| `tests/integration/test_backfill_integration.py` | 175 | 0.5s | Wait for signal delivery |
| `tests/integration/test_backfill_integration.py` | 249 | 0.1s | Tiny delay for file operations |
| `tests/integration/test_queue_concurrent.py` | 97, 107, 158 | 0.001s (1ms) | Thread interleaving for concurrent tests |
| `tests/integration/test_search.py` | 74 | 0.5s | Small delay for search propagation |
| `tests/integration/test_session_logging_integration.py` | 104, 129 | 0.01s (10ms) | Log rotation delay |
| `tests/test_logging.py` | 252 | 0.1s (100ms) | Log rotation delay |
| `tests/test_trace_flush_worker.py` | 147 | 0.05s (50ms) | Signal delivery |

**Note**: `tests/test_logging.py:221` is a comment, not an actual sleep call.

**Action**: None required.

---

## Category C: FIX - Poll for Async Condition (PRIORITY TARGETS - 19 calls)

These sleep calls are waiting for an async condition (embedding completion, Qdrant indexing, etc.) and **SHOULD BE REPLACED** with polling/retry patterns.

### Priority 1: test_multi_project.py (7 calls, 30-150s sleeps) - **CRITICAL**

| Line | Current Sleep | Condition Being Waited For |
|------|---------------|---------------------------|
| 150 | 60s | Embedding completion (2 memories) |
| 261 | 60s | Embedding completion (switching tests) |
| 404 | 90s | Embedding completion (3 projects) |
| 502 | 150s | Embedding completion (5 projects) |
| 603 | 30s | Best practice embedding |
| 678 | 30s | Implementation embedding |
| 820 | 60s | Hook background storage |

### Priority 2: test_cross_project_best_practices.py (7 calls, 2-5s sleeps)

| Line | Current Sleep | Condition Being Waited For |
|------|---------------|---------------------------|
| 51 | 2s | Embedding + indexing |
| 98 | 2s | Embedding completion |
| 134 | 2s | Embedding completion |
| 164 | 5s | Embedding completion (100 entries) |
| 255 | 2s | Embedding completion |
| 285 | 2s | Embedding completion |
| 328 | 2s | Embedding completion |

### Priority 3: test_persistence.py (3 calls, 2-3s sleeps)

| Line | Current Sleep | Condition Being Waited For |
|------|---------------|---------------------------|
| 155 | 3s | Embedding generation (NFR-P2 <2s) |
| 204 | 2s | Qdrant stabilization after restart |
| 483 | 3s | Wait for embeddings |

### Priority 4: test_grafana_dashboards.py (2 calls, 2-5s sleeps)

| Line | Current Sleep | Condition Being Waited For |
|------|---------------|---------------------------|
| 42 | 5s | Grafana provisioning completion |
| 46 | 2s (retry_delay) | Could be polling-based |

### Priority 5: test_hook_integration.py (2 calls)

| Line | Current Sleep | Condition Being Waited For |
|------|---------------|---------------------------|
| 202 | 60s (timeout param) | Background storage completion |
| 686 | 5s | Dedup check completion |

### Priority 6: test_multi_project_quick.py (7 calls, 1s sleeps)

| Line | Current Sleep | Condition Being Waited For |
|------|---------------|---------------------------|
| 143, 248, 385, 482, 582, 656, 797 | 1s each | Embedding completion |

### Priority 7: Other files

| File | Line | Sleep | Condition |
|------|------|-------|-----------|
| `tests/integration/test_edge_cases.py` | 390 | 2s | Qdrant indexing |
| `tests/test_bmad_hooks_integration.py` | 695 | 2s | Async embedding |
| `tests/integration/test_docker_stack.py` | 289 | 2s | Qdrant health check retry |
| `tests/test_async_sdk_wrapper.py` | 177 | 1s | Async operation |
| `tests/test_async_sdk_wrapper.py` | 367 | 0.5s | 500ms delay |
| `tests/integration/test_performance.py` | 117 | 0.5s | Performance timing |
| `tests/conftest.py` | 802 | variable | wait_time in fixture |

---

## Category D: KEEP - Intentional Time-Based Tests (2 calls)

These sleep calls are testing the **timing behavior** itself (e.g., circuit breaker timeouts). They are **intentional** and should not be changed.

| File | Line | Sleep | Purpose |
|------|------|-------|---------|
| `tests/test_classifier/test_circuit_breaker.py` | 43 | 1s | Circuit breaker timeout test |
| `tests/test_classifier/test_circuit_breaker.py` | 55 | 1.1s | Circuit breaker half-open state test |

**Action**: Add comment `# Intentional: testing circuit breaker timing behavior` for clarity.

---

## Category E: REDUCE - Long Unconditional Waits (0 calls after C categorization)

After analysis, all long sleeps are actually waiting for async conditions and belong in Category C. The `test_grafana_dashboards.py` sleeps could potentially be reduced but are better served by polling patterns.

---

## Summary

| Category | Count | Action |
|----------|-------|--------|
| A - Mocked | 11 | SKIP - No changes |
| B - Tiny delays | 8 | SKIP - No changes |
| C - Poll for async | 19 | **FIX** - Replace with polling/retry |
| D - Time-based tests | 2 | KEEP - Add comment |
| E - Reduce | 0 | N/A |
| **Total** | **40** | (32 already handled by comments/mocks) |

**Note**: 72 total calls includes duplicates from grep. After removing duplicates and categorizing, we have ~40 unique sleep() calls requiring analysis.

---

## Recommended Polling Pattern

For Category C fixes, use this standard pattern:

```python
def wait_for_condition(condition_fn, timeout: float = 30.0, poll_interval: float = 0.1) -> None:
    """Poll for condition with timeout.
    
    Args:
        condition_fn: Callable that returns True when condition is met
        timeout: Maximum seconds to wait
        poll_interval: Seconds between polls
    
    Raises:
        TimeoutError: If condition not met within timeout
    """
    for _ in range(int(timeout / poll_interval)):
        if condition_fn():
            return
        time.sleep(poll_interval)
    raise TimeoutError(f"Condition not met within {timeout}s")
```

Usage:
```python
# Before: time.sleep(60)
wait_for_condition(lambda: memory_exists_in_qdrant(memory_id), timeout=60.0)

# After: Fails fast when condition met, throws clear timeout error
```