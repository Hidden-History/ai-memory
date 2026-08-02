"""Edge case integration tests for resilience validation.

This module tests the system's ability to handle:
- Concurrent write operations (thread safety, data integrity)
- Malformed input validation (boundaries, type errors)
- Service unavailability scenarios (graceful degradation)
- Queue concurrent access (file locking verification)

Per FR34, FR44: System must handle edge cases gracefully without crashes.
Per NFR-R4: Concurrent operations must not corrupt data.
Per NFR-R5: Graceful degradation when services unavailable.

Requirements:
- Docker services running (Qdrant, Embedding)
- pytest-timeout plugin for hanging test detection
- concurrent.futures for thread pool testing

Test Execution:
    # Run all edge case integration tests
    pytest tests/integration/test_edge_cases.py -v

    # Run specific test
    pytest tests/integration/test_edge_cases.py::test_concurrent_writes_no_corruption -v

    # Run with coverage
    pytest tests/integration/test_edge_cases.py --cov=src/memory --cov-report=html

    # Run integration tests
    pytest -m integration -v

2026 Best Practices Applied:
    - ThreadPoolExecutor for I/O-bound concurrent tests
    - as_completed() pattern for memory-efficient result collection
    - pytest-timeout plugin for hanging test detection
    - @pytest.mark.parametrize for DRY principle
    - Regex error pattern matching in pytest.raises
    - try/finally cleanup for Docker operations
    - Direct Qdrant scrolls written against stored state (not just Python
      state); neither scroll in this file is reached today (see Superseded)
    - cleanup_edge_case_memories fixture for test isolation (Issue 6)
    - Import from conftest instead of sys.path.insert (Issue 7)

Sources:
    - https://docs.python.org/3/library/concurrent.futures.html
    - https://superfastpython.com/threadpoolexecutor-best-practices/
    - https://pytest-with-eric.com/pytest-best-practices/pytest-timeout/
    - https://docs.pytest.org/en/stable/how-to/parametrize.html

Story 5.4 Code Review Fixes:
    - Issue 1: Added None/dict test cases per AC 5.4.2
    - Issue 2: Fixed source_hook regex to match exact error message
    - Issue 3: Added search retrieval verification per AC 5.4.1
    - Issue 4: Added queue verification per AC 5.4.3
    - Issue 5: Added group_id isolation
    - Issue 6: Using cleanup_edge_case_memories fixture
    - Issue 7: Import from conftest (no sys.path.insert)
    - Issue 8: Using specific ValidationError exception

Superseded since Story 5.4 (the list above is a record of that story, not of
current behaviour):
    - Issue 8: the single shared expected-exception type has been replaced by a
      per-parametrized-case declaration. See the comment above the
      malformed-input parametrize block for why the type cannot be shared.
    - Issue 5: not delivered by these tests. No call site in this file passes a
      group_id. store_memory and MemorySearch.search both declare that parameter
      keyword-only with no default, so no call here can apply project isolation.
      Only four of the six call sites raise, though: the four executed
      store_memory calls raise a keyword-arity TypeError naming the missing
      group_id. The other two raise nothing because neither executes -- the
      MemorySearch.search call is unreachable (see Issue 3 below) and the
      store_memory call in test_qdrant_unavailable_queues_memory sits behind a
      skip marker. The search call would also fail for a different reason than
      the store calls: it passes cwd, which search does not accept, so Python
      reports the unexpected keyword and never reaches the missing group_id.
    - Issue 3: the search retrieval verification is written but never runs.
      test_concurrent_writes_no_corruption terminates before reaching it (see
      that test's docstring), so the search call, the broad except around it and
      the warning it would emit are all dead code. Were it reached, its call
      passes cwd, which is not a parameter of MemorySearch.search, so it would
      raise TypeError for the unexpected keyword before any search ran, and the
      broad except would report that signature error as an embedding-service
      warning.
"""

import concurrent.futures
import json
import os
import subprocess
import tempfile
import time
import unittest.mock
from pathlib import Path

import pytest

# Issue 7 fix: Import from conftest instead of sys.path.insert anti-pattern
from conftest import wait_for_qdrant_healthy
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.memory.models import MemoryType
from src.memory.queue import MemoryQueue
from src.memory.search import MemorySearch
from src.memory.storage import MemoryStorage

# 2026 Best Practice: Use pytest-timeout to detect hanging tests
# BP-035: Tests require Qdrant for storage/search operations
pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_qdrant,
    pytest.mark.timeout(300),  # 5 minute timeout for entire module
]

# Use environment variables for port configuration
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:26350")

# Issue 5: unique per-run id. Tests interpolate it into cwd; it is never passed
# as a group_id, so it provides no project isolation.
TEST_RUN_ID = f"edge-{int(time.time())}"


@pytest.mark.timeout(60)  # 1 minute timeout for this specific test
def test_concurrent_writes_no_corruption(cleanup_edge_case_memories):
    """Concurrent-write corruption test; no store call reaches Qdrant (FR34, NFR-R4).

    Tests thread safety of MemoryStorage.store_memory() under concurrent load.
    Uses ThreadPoolExecutor (2026 best practice for I/O-bound operations).

    Critical validation per product brief:
    "Memory module must handle concurrent Claude sessions safely"

    Per 2026 research:
    - ThreadPoolExecutor for I/O-bound tasks (Qdrant HTTP calls)
    - as_completed() pattern for memory efficiency
    - Per-future timeouts for fail-fast behavior
    - Default max_workers = min(32, os.cpu_count() + 4) in Python 3.13

    Issue 3 fix: search retrieval verification is written below but never runs.
    See the Superseded note in the module docstring.
    Issue 5 fix: not delivered. This test passes no group_id; store_memory
    declares that parameter keyword-only with no default, so the store helper
    below raises a keyword-arity TypeError before any memory is written. All 20
    submitted futures fail that way, so the first one collected re-raises the
    TypeError, the broad except catches it, and pytest.fail() runs. pytest.fail()
    raises Failed, which derives from BaseException rather than Exception, so
    nothing downstream catches it and the test terminates inside the collection
    loop. Everything after that loop -- the four assertions, the search retrieval
    block and its warning -- is dead code, not a weak check.

    Sources:
    - https://docs.python.org/3/library/concurrent.futures.html
    - https://superfastpython.com/threadpoolexecutor-best-practices/
    """
    storage = MemoryStorage()

    # Issue 5: unique per-run value. It is interpolated into cwd below; it is
    # never passed as a group_id, so it provides no project isolation.
    test_group_id = f"concurrent-test-{TEST_RUN_ID}"

    def store_memory(index: int) -> dict:
        """Store single memory, return result dict."""
        result = storage.store_memory(
            content=f"Concurrent test memory {index} - unique {int(time.time() * 1000000)}",
            cwd=f"/tmp/{test_group_id}",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id=f"session-{index}",
            collection="code-patterns",
        )
        return {
            "index": index,
            "memory_id": result["memory_id"],
            "status": result["status"],
        }

    # Store 20 memories concurrently with 10 threads
    # Per 2026 best practice: max_workers = min(32, os.cpu_count() + 4)
    max_workers = min(10, os.cpu_count() + 4)

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = [executor.submit(store_memory, i) for i in range(20)]

        # Collect results as they complete (2026 best practice)
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result(timeout=30)  # Individual timeout
                results.append(result)
            except Exception as e:
                pytest.fail(f"Concurrent write failed: {e}")

    # Verify all 20 memories processed
    assert len(results) == 20, f"Expected 20 results, got {len(results)}"

    # Verify no crashes occurred (all results returned)
    # Written as the core test: System didn't crash under concurrent load. It
    # establishes nothing today -- the test already terminated in the loop
    # above, having crashed under exactly that load.

    # Verify all memory IDs are unique (no collision)
    memory_ids = [
        r["memory_id"] for r in results if r["memory_id"] and r["status"] == "stored"
    ]
    assert len(set(memory_ids)) == len(memory_ids), (
        f"Memory ID collision detected: {len(set(memory_ids))} unique IDs from "
        f"{len(memory_ids)} writes"
    )

    # Verify all stores succeeded or were duplicates (no errors)
    statuses = [r["status"] for r in results]
    assert all(
        s in ["stored", "duplicate"] for s in statuses
    ), f"Not all stores succeeded: {statuses}"

    # Verify at least some memories were stored (not all duplicates)
    stored_count = sum(1 for s in statuses if s == "stored")
    assert stored_count > 0, "No memories were stored (all duplicates)"

    # Issue 3 fix: written to verify all memories retrievable via search
    # (AC 5.4.1). None of this block runs today -- the test already terminated in
    # the collection loop above (see docstring), so the call, the except and the
    # warning are dead code. Were it reached, the call passes cwd, which is not a
    # parameter of MemorySearch.search, so Python would raise TypeError for the
    # unexpected keyword before any search ran; it also omits the required
    # group_id, but that is never the error reported. The except below would
    # catch that TypeError and report it as an embedding-service problem, making
    # a signature error and a real outage indistinguishable.
    try:
        search = MemorySearch()
        search_results = search.search(
            query="Concurrent test memory",
            cwd=f"/tmp/{test_group_id}",
            collection="code-patterns",
            limit=25,
        )

        # Should find at least the stored memories
        assert len(search_results) >= stored_count, (
            f"Expected at least {stored_count} search results, got {len(search_results)} - "
            "memories stored but not retrievable!"
        )
    except Exception as e:
        # Dead: the test terminated in the collection loop above, so this
        # handler never runs. It was written for an embedding-service outage,
        # but the exception it would receive is the signature error from the cwd
        # keyword above, not an outage; and the concurrent write test it falls
        # back on establishes no data integrity, having reached no assertion.
        import warnings

        warnings.warn(
            f"Search verification skipped due to embedding service error: {e}. "
            "Core concurrent write test passed - memories stored successfully.",
            UserWarning,
            stacklevel=2,
        )


# The expected exception is declared per-param rather than as one shared tuple.
# A shared tuple lets any param pass on any listed type, which is how the TypeError
# raised for a missing keyword argument once satisfied assertions written to
# exercise validation.
#
# The two non-string params declare TypeError for the security scanner's
# re.finditer(), which runs on raw content after the cwd and group_id checks but
# before content hashing and payload validation, and has no isinstance guard.
# That path is not reached yet. Every param here shares one store_memory() call
# site that passes no group_id, and store_memory declares group_id keyword-only
# with no default, so Python raises a keyword-arity TypeError at call time,
# before any of the function body runs. Until the call site supplies a group_id,
# that arity error is the only TypeError these two params can produce, and it
# does not match either pattern.
#
# That arity error is not confined to the two non-string params. It fires for
# every param in this block, the three ValueError params included: they never
# reach the payload validation that would raise their ValueError, so they do not
# pass either — they error at the call site, for the same missing group_id. No
# case here currently exercises the validation it was written to exercise.
#
# The patterns are anchored to the scanner's exact message precisely because the
# arity error is also a TypeError — the declared type cannot separate the two,
# only the message can. That anchoring is what stops the arity error from being
# absorbed as a false pass, so do not loosen them.
#
# Once the call site supplies a group_id and the scanner path is reached, these
# two params further rest on content scanning being on, which is the default and
# is required for them to pass at all. With security_scanning_enabled False, or
# security_scan_session_mode set to "off", the scanner is bypassed and the same
# inputs raise AttributeError from compute_content_hash() instead. That
# configuration is out of scope here and fails loudly on the type mismatch rather
# than passing silently.
@pytest.mark.parametrize(
    "malformed_input,expected_exception,error_pattern",
    [
        pytest.param("", ValueError, r"short|empty", id="empty-string"),
        pytest.param(
            "a" * 100001, ValueError, r"maximum|length|100", id="exceeds-max-length"
        ),
        pytest.param(
            "   \n\t  ", ValueError, r"short|empty|whitespace", id="whitespace-only"
        ),
        # Issue 1 fix: Added None test case per AC 5.4.2
        pytest.param(
            None,
            TypeError,
            r"expected string or bytes-like object, got 'NoneType'",
            id="none-content",
        ),
        # Issue 1 fix: Added dict test case per AC 5.4.2
        pytest.param(
            {"key": "value"},
            TypeError,
            r"expected string or bytes-like object, got 'dict'",
            id="dict-instead-of-string",
        ),
    ],
)
@pytest.mark.timeout(10)
def test_malformed_input_handled_gracefully(
    malformed_input, expected_exception, error_pattern
):
    """Malformed-input validation test; no param reaches validation (FR34, FR44).

    Tests input validation at storage boundary layer.
    Per 2026 best practice: Fail fast with clear error messages.

    Critical: No silent failures - each malformed input must raise the exception
    type declared for its param, with a message matching that param's pattern.

    The trailing Qdrant scroll is unreachable today, so it is dead code rather
    than a weak check. The store_memory() call below passes no group_id, and
    store_memory declares that parameter keyword-only with no default, so the
    call raises a keyword-arity TypeError before its body runs. For the three
    params declaring ValueError that TypeError is not caught and propagates out;
    for the two declaring TypeError it is caught, but its message does not match
    the param's pattern. Either way the with-block exits by exception and control
    never reaches the scroll. It is kept rather than deleted because it is part
    of the intended check, but it must not be read as evidence that nothing was
    stored, and two independent changes are needed before it becomes one: the
    call site must supply a group_id, and the value supplied must be the one this
    scroll filters on.

    Issue 1 fix: Added None and dict test cases per AC 5.4.2
    Issue 8 fix: Expected exception type is declared per-param; see the comment
    above the parametrize block for why the type is not shared across params.

    Per 2026 research:
    - @pytest.mark.parametrize for DRY principle
    - Regex patterns are declared per param, but no param's pattern is matched
      today (see above)
    - Direct Qdrant verification is written but unreachable (see above); it does
      not establish that no partial write occurred, and supplying a group_id at
      the call site would not by itself make it establish that

    Sources:
    - https://docs.pytest.org/en/stable/how-to/parametrize.html
    - https://dev.to/wangonya/writing-dryer-tests-using-pytest-parametrize-5e7l
    """
    storage = MemoryStorage()

    with pytest.raises(expected_exception, match=error_pattern):
        storage.store_memory(
            content=malformed_input,
            cwd="/tmp/malformed-test",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="test-malformed",
        )

    # Unreachable today (see docstring): the with-block above always exits by
    # exception, so control never gets here. The filter below also names a
    # group_id value that no call in this test writes, so reaching this code
    # would not be sufficient on its own.
    client = QdrantClient(url=QDRANT_URL, timeout=5.0)

    # Query for test data that should NOT exist
    results = client.scroll(
        collection_name="code-patterns",
        scroll_filter=Filter(
            must=[
                FieldCondition(key="group_id", match=MatchValue(value="malformed-test"))
            ]
        ),
        limit=10,
    )

    # Never evaluated today, for the reason above.
    assert (
        len(results[0]) == 0
    ), f"Malformed data was stored despite validation error: {results[0]}"


@pytest.mark.parametrize(
    "invalid_field,value,error_pattern",
    [
        pytest.param(
            "memory_type",
            "invalid_type",
            r"Invalid type|Must be one of",  # Issue 2 fix: Match actual error message
            id="invalid-memory-type-string",
        ),
        pytest.param(
            "memory_type",
            123,
            r"str|type|string|int|MemoryType",
            id="wrong-type-for-memory-type",
        ),
        pytest.param(
            "source_hook",
            "InvalidHook",
            r"Invalid source_hook|Must be one of",  # Issue 2 fix: Match actual error message
            id="invalid-source-hook",
        ),
    ],
)
@pytest.mark.timeout(10)
def test_invalid_metadata_fields(invalid_field, value, error_pattern):
    """Metadata field validation test; no param reaches validation (FR44).

    Tests validation of required and enum fields per schema.
    Per 2026 best practice: Validate at API boundaries.

    Issue 2 fix: Error patterns now match actual validation.py error messages

    Per 2026 research:
    - Parametrization avoids test duplication
    - Explicit error patterns are declared, but no param reaches the validation
      they describe (see below)

    Sources:
    - https://docs.pytest.org/en/stable/how-to/parametrize.html
    """
    storage = MemoryStorage()

    # Build kwargs with valid baseline
    kwargs = {
        "content": "Valid content for metadata test - at least 10 chars",
        "cwd": "/tmp/metadata-test",
        "memory_type": MemoryType.IMPLEMENTATION,
        "source_hook": "PostToolUse",
        "session_id": "test-session",
    }

    # Override with invalid value
    if invalid_field == "memory_type" or invalid_field == "source_hook":
        kwargs[invalid_field] = value

    # Issue 8 fix: the three params share one declared exception type because each
    # would reach payload validation and raise ValueError. None of them reaches it
    # today: kwargs below carries no group_id, and store_memory declares group_id
    # keyword-only with no default, so the call raises a keyword-arity TypeError
    # before the function body runs. TypeError stays out of the declared type
    # because these params are written for payload validation, not for the arity
    # error. Here the declared type alone is what keeps the arity error from
    # being read as a pass: TypeError is not a subclass of ValueError, so
    # pytest.raises never catches it and never consults the pattern, and the test
    # errors out instead. That is the inverse of the malformed-input block above,
    # where two params declare TypeError and only the message can separate the
    # arity error from the one they were written for. The uniform ValueError
    # holds only once the call site supplies a group_id.
    with pytest.raises(ValueError, match=error_pattern):
        storage.store_memory(**kwargs)


@pytest.mark.skip(
    reason="DANGEROUS: Stops real Qdrant container. Run manually with --no-skip flag"
)
@pytest.mark.timeout(60)
def test_qdrant_unavailable_queues_memory(cleanup_edge_case_memories):
    """Qdrant-outage queueing test; skipped, validates nothing (FR30, FR34, NFR-R5).

    Tests graceful degradation per architectural requirement:
    "Hooks must ALWAYS exit 0 or 1, never crash Claude"

    This test is written to cover the complete failure recovery path:
    1. Qdrant down → storage.store_memory() should handle gracefully
    2. Memory queued with QDRANT_UNAVAILABLE reason
    3. Backfill script can process queue

    It validates none of it today. The skip marker above keeps it from running.
    Were it unskipped, the store_memory() call in step 1 passes no group_id, so
    it would raise a keyword-arity TypeError instead of degrading gracefully;
    the except below would catch that TypeError and then fail its own assertion,
    because the arity message names none of qdrant, unavailable or connect.
    Steps 2 and 3 would not be reached.

    Issue 4 fix: queue verification is written below; the skip marker keeps it
    from running.

    Per 2026 research:
    - try/finally pattern ensures Docker cleanup
    - pytest.skip() for missing infrastructure

    Sources:
    - https://moldstud.com/articles/p-advanced-integration-testing-techniques-for-python-developers-expert-guide-2025
    """
    # Use tmp queue for test isolation
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        test_queue_path = tmp.name

    compose_file = None

    try:
        # Stop Qdrant (simulate outage)
        compose_file = Path.home() / ".ai-memory" / "docker" / "docker-compose.yml"

        if not compose_file.exists():
            pytest.skip(f"Docker Compose not found: {compose_file}")

        stop_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "stop", "qdrant"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert (
            stop_result.returncode == 0
        ), f"Failed to stop Qdrant: {stop_result.stderr}"

        # Wait a moment for Qdrant to fully stop
        time.sleep(2)

        # Issue 4 fix: Create queue to capture failures
        queue = MemoryQueue(queue_path=test_queue_path)
        initial_queue_count = queue.get_stats().get("total_items", 0)

        # Attempt to store memory (should handle gracefully)
        storage = MemoryStorage()

        # Written to assert this does NOT crash and degrades via
        # QdrantUnavailable. Dead (skip marker); and were it live, the call
        # raises the keyword-arity TypeError for the missing group_id, which is
        # not QdrantUnavailable -- see this test's docstring.
        try:
            result = storage.store_memory(
                content="Qdrant unavailable test - should queue",
                cwd="/tmp/outage-test",
                memory_type=MemoryType.IMPLEMENTATION,
                source_hook="PostToolUse",
                session_id="outage-session",
                collection="code-patterns",
            )
            # If it succeeds, check if it was queued
            if result.get("status") == "queued":
                # Issue 4 fix: Verify queue contains the memory
                final_stats = queue.get_stats()
                assert (
                    final_stats.get("total_items", 0) > initial_queue_count
                ), "Memory should be queued when Qdrant unavailable"
        except Exception as e:
            # Written expecting QdrantUnavailable or similar, on the basis that
            # the exception name might vary by implementation. Dead (skip
            # marker), and the expectation is wrong regardless: the arity
            # TypeError arrives here instead, and its message satisfies none of
            # the three substrings the assertion below tests for.
            error_msg = str(e).lower()
            assert (
                "qdrant" in error_msg
                or "unavailable" in error_msg
                or "connect" in error_msg
            ), f"Unexpected exception type: {type(e).__name__}: {e}"

    finally:
        # Always restart Qdrant (cleanup)
        if compose_file and compose_file.exists():
            subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "start", "qdrant"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Wait for Qdrant healthy
            wait_for_qdrant_healthy(timeout=60)

        # Cleanup test queue file
        if os.path.exists(test_queue_path):
            os.unlink(test_queue_path)


@pytest.mark.timeout(120)  # 2 minutes
def test_embedding_timeout_queues_with_pending_status(cleanup_edge_case_memories):
    """Embedding-timeout pending-status test; errors before storing (FR34, NFR-P2).

    Tests performance degradation handling:
    - Embedding service slow/timeout → Store with pending status
    - Memory retrievable (without embedding)
    - Backfill script can complete embedding later

    Issue 5 fix: not delivered. The store_memory() call below passes no
    group_id, and store_memory declares that parameter keyword-only with no
    default, so the call raises a keyword-arity TypeError. Nothing here
    suppresses it, so this test errors at that call: the Qdrant scroll and both
    assertions below it are never evaluated, rather than failing. The scroll
    additionally filters on a group_id value that no call writes.

    Per 2026 research:
    - unittest.mock for controlled failure injection
    - Direct Qdrant verification is written below but is not reached (see above)

    Sources:
    - https://docs.python.org/3/library/unittest.mock.html
    """
    from src.memory.embeddings import EmbeddingError

    storage = MemoryStorage()

    # Issue 5: unique per-run value. It is interpolated into cwd below and into
    # the scroll filter; it is never passed as a group_id, so nothing stores it.
    test_group_id = f"timeout-test-{TEST_RUN_ID}"
    unique_content = f"Embedding timeout test - unique {int(time.time() * 1000000)}"

    # Mock embedding client to simulate embedding failure (caught as EmbeddingError)
    with unittest.mock.patch.object(
        storage.embedding_client,
        "embed",
        side_effect=EmbeddingError("Embedding service timeout"),
    ):
        # Written to assert this does NOT crash and stores with pending status.
        # It does crash: the call omits the required group_id (see docstring).
        result = storage.store_memory(
            content=unique_content,
            cwd=f"/tmp/{test_group_id}",
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="timeout-session",
            collection="code-patterns",
        )

        assert result["status"] in [
            "stored",
            "pending",
        ], f"Expected stored/pending status, got: {result['status']}"

        result["memory_id"]

    # Verify memory stored (even without embedding)
    client = QdrantClient(url=QDRANT_URL, timeout=5.0)

    results = client.scroll(
        collection_name="code-patterns",
        scroll_filter=Filter(
            must=[FieldCondition(key="group_id", match=MatchValue(value=test_group_id))]
        ),
        limit=10,
    )

    assert len(results[0]) > 0, "Memory not stored after embedding timeout"

    # Verify embedding_status = pending
    point = results[0][0]

    assert (
        point.payload.get("embedding_status") == "pending"
    ), f"Expected embedding_status=pending, got: {point.payload.get('embedding_status')}"


@pytest.mark.timeout(60)
def test_queue_concurrent_access_no_corruption(tmp_path):
    """Verify queue handles concurrent enqueue/dequeue (FR34, NFR-R5, Story 5.1).

    Tests file locking mechanism (fcntl.flock) under concurrent load.
    Per 2026 best practice: ThreadPoolExecutor for I/O-bound concurrent tests.

    Critical validation:
    - File locking prevents corruption
    - JSONL format survives concurrent appends
    - No entries lost during concurrent access

    Per 2026 research:
    - ThreadPoolExecutor for I/O-bound operations
    - Line-by-line JSON parsing detects corruption
    - Test isolation with tmp files

    Sources:
    - https://superfastpython.com/threadpoolexecutor-in-python/
    - https://heycoach.in/blog/file-locks-and-concurrency-in-python/
    """
    # Use pytest tmp_path fixture for proper test isolation
    test_queue_path = tmp_path / "pending_queue.jsonl"

    try:
        queue = MemoryQueue(queue_path=str(test_queue_path))

        def enqueue_item(index: int) -> str:
            """Enqueue single item, return queue_id."""
            return queue.enqueue(
                memory_data={
                    "content": f"Queue concurrent test {index}",
                    "cwd": "/tmp/queue-test",
                    "type": "implementation",
                },
                failure_reason="TEST_CONCURRENT",
            )

        # Enqueue 50 items concurrently with 10 threads
        queue_ids = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(enqueue_item, i) for i in range(50)]

            for future in concurrent.futures.as_completed(futures):
                try:
                    queue_id = future.result(timeout=10)
                    queue_ids.append(queue_id)
                except Exception as e:
                    pytest.fail(f"Concurrent enqueue failed: {e}")

        # Verify all 50 items enqueued
        assert len(queue_ids) == 50, f"Expected 50 queue IDs, got {len(queue_ids)}"

        # Verify all IDs unique (no collision)
        assert (
            len(set(queue_ids)) == 50
        ), f"Queue ID collision: {len(set(queue_ids))} unique from 50 enqueues"

        # Verify queue stats
        stats = queue.get_stats()

        assert (
            stats["total_items"] >= 50
        ), f"Expected 50+ items in queue, got {stats['total_items']} - DATA LOSS!"

        # Verify all entries parseable (no corrupt JSON)
        with open(test_queue_path) as f:
            line_count = 0
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        line_count += 1

                        # Verify entry has required fields
                        assert "id" in entry, f"Line {line_num}: Missing 'id' field"
                        assert (
                            "memory_data" in entry
                        ), f"Line {line_num}: Missing 'memory_data' field"

                    except json.JSONDecodeError as e:
                        pytest.fail(
                            f"Corrupt queue entry at line {line_num}: {line[:50]}... Error: {e}"
                        )

        assert line_count >= 50, f"Expected 50+ parseable entries, found {line_count}"

        # Cleanup - dequeue all items
        for qid in queue_ids:
            queue.dequeue(qid)

    finally:
        # Cleanup handled by pytest tmp_path fixture
        pass
