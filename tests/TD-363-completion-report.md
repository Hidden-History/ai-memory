# TD-363 Completion Report

## Summary
Fixed time.sleep() calls creating flaky CI in priority target files by replacing fixed unconditional waits with polling/retry patterns using `wait_for_condition()` helper.

## Categorization Summary
- **Category A (SKIP)**: 11 calls - Already mocked/patched in unit tests
- **Category B (SKIP)**: 8 calls - Tiny delays <100ms for interleaving/scheduling
- **Category C (FIX)**: 19+ calls - Replaced with polling/retry pattern
- **Category D (KEEP)**: 2 calls - Intentional time-based tests (circuit breaker)
- **Category E (REDUCE)**: Converted to polling patterns

## Files Modified

### Priority Target 1: `tests/integration/test_multi_project.py` (7 calls fixed)
- Replaced 30-150s fixed sleeps with `wait_for_condition()` polling
- Each wait now polls for memory existence in Qdrant before proceeding
- Fails fast when condition met, provides clear timeout errors

### Priority Target 2: `tests/test_cross_project_best_practices.py` (7 calls fixed)
- Replaced 2-5s fixed sleeps with polling for best practice indexing
- Uses `wait_for_condition()` helper from conftest.py

### Priority Target 3: `tests/integration/test_persistence.py` (3 calls fixed)
- Replaced 2-3s sleeps with polling for memory indexing
- Kept 2s stabilization delay after Qdrant restart (Category D - WSL2 environmental issue)

### Priority Target 4: `tests/integration/test_grafana_dashboards.py` (2 calls fixed)
- Replaced 5s provisioning delay with polling for datasource readiness
- Kept 2s retry delay (Category B - polling pattern already in place)

### Priority Target 5: `tests/integration/test_hook_integration.py` (2 calls fixed)
- Replaced fixed `wait_for_background_storage()` with new `wait_for_memory_to_appear()` function
- Polls for memory existence in Qdrant instead of fixed 60s timeout

## New Helper Added

### `wait_for_condition()` in `tests/conftest.py`
```python
def wait_for_condition(
    condition_fn: callable,
    timeout: float = 30.0,
    poll_interval: float = 0.5,
    message: str = "Condition not met",
) -> None:
    """Poll for condition with timeout - TD-363 helper for flaky test fixes."""
```

Standard pattern used across all fixed tests:
```python
def memory_indexed() -> bool:
    results = search.search(query="...", collection="...", limit=1)
    return len(results) > 0

wait_for_condition(
    memory_indexed,
    timeout=60.0,
    message="Memory not indexed within timeout"
)
```

## Remaining Files (Lower Priority)

The following files still have time.sleep() calls that could benefit from polling patterns in a future wave:
- `tests/integration/test_multi_project_quick.py` (7 calls) - Started but not completed
- `tests/integration/test_backfill_integration.py` (3 calls)
- `tests/integration/test_docker_stack.py` (2 calls)
- `tests/test_async_sdk_wrapper.py` (2 calls)
- `tests/integration/test_edge_cases.py` (1 call)
- `tests/test_bmad_hooks_integration.py` (1 call)
- `tests/integration/test_multi_session.py` (1 call)

Category A (Already Mocked) - No changes needed:
- `tests/unit/test_evaluator_retry.py`
- `tests/unit/test_langfuse_config_retry.py`
- `tests/unit/test_embedding_retry.py`
- `tests/unit/connectors/github/test_github_sync_service.py`
- `tests/unit/test_trace_flush_degraded.py`

Category B (Tiny Delays) - No changes needed:
- `tests/integration/test_queue_concurrent.py`
- `tests/integration/test_session_logging_integration.py`
- `tests/test_logging.py`
- `tests/test_trace_flush_worker.py`
- `tests/integration/test_search.py`
- `tests/integration/test_performance.py`

Category D (Intentional) - Kept as-is with comments:
- `tests/test_classifier/test_circuit_breaker.py` (2 calls) - Testing circuit breaker timing

## Validation
- `ruff check src/ tests/` - PASS
- `black --check src/ tests/` - PASS
- `pytest tests/` - Not run (requires Docker stack)

## Benefits
1. **Faster Tests**: Polling fails fast when condition is met (e.g., 0.5s vs 60s fixed wait)
2. **Clearer Failures**: TimeoutError with descriptive message instead of silent failure
3. **More Reliable**: Tests don't rely on arbitrary timing that varies across CI runners
4. **Maintainable**: Standard pattern in `conftest.py` for consistent usage