"""E2E tests for Memory System V2.0 integrated features.

Tests the complete Memory System V2.0 as an integrated system, validating that
all components work together correctly:
- Phase 1: 3 collections (code-patterns, conventions, discussions) with type system
- Phase 2: Intent detection, cascading search, type filtering, attribution
- Phase 3: Triggers (error detection, new file, first edit, decision keywords)
- Phase 4: Conversation memory hooks
- Phase 5: SessionStart only injects on compact

Requirements:
- Real Qdrant (not mocks) - port 26350
- Real embedding service - port 28080
- Test data isolation with unique group_id
- Complete cleanup after each test
- Tests must be idempotent

Reference: oversight/specs/MEMORY-SYSTEM-REDESIGN-v2.md Section 15.7
"""

import uuid
from collections.abc import Generator

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
)
from src.memory.embeddings import EmbeddingClient
from src.memory.intent import (
    IntentType,
    detect_intent,
    get_target_collection,
)
from src.memory.models import MemoryType
from src.memory.search import search_memories
from src.memory.storage import MemoryStorage
from src.memory.triggers import (
    detect_decision_keywords,
    detect_error_signal,
    is_first_edit_in_session,
    is_new_file,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def e2e_qdrant_client() -> Generator[QdrantClient, None, None]:
    """Real Qdrant client for E2E tests (not mocks).

    Connects to localhost:26350 per project configuration.
    """
    client = QdrantClient(host="localhost", port=26350, timeout=30.0)
    yield client


@pytest.fixture(scope="function")
def e2e_embedding_client() -> Generator[EmbeddingClient, None, None]:
    """Real embedding client for E2E tests (not mocks).

    Connects to localhost:28080 per project configuration.
    """
    client = EmbeddingClient()
    # Verify service is available
    assert client.health_check(), "Embedding service not available at localhost:28080"
    yield client


@pytest.fixture(scope="function")
def e2e_storage() -> Generator[MemoryStorage, None, None]:
    """Real MemoryStorage instance for E2E tests.

    Creates a MemoryStorage instance with real Qdrant and embedding service.
    """
    storage = MemoryStorage()
    yield storage


@pytest.fixture(scope="function")
def test_group_id() -> str:
    """Generate unique group_id for test isolation.

    Returns unique identifier like 'e2e-test-v2-<uuid>' to isolate
    test data from real project memories.
    """
    return f"e2e-test-v2-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="function")
def clean_test_data(e2e_qdrant_client: QdrantClient, test_group_id: str):
    """Ensure test isolation - clean up before and after test.

    Removes all memories with test group_id from all collections
    to ensure tests don't pollute each other.
    """
    # Cleanup before test
    for collection in [
        COLLECTION_CODE_PATTERNS,
        COLLECTION_CONVENTIONS,
        COLLECTION_DISCUSSIONS,
    ]:
        try:
            e2e_qdrant_client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="group_id", match=MatchValue(value=test_group_id)
                        )
                    ]
                ),
            )
        except Exception:
            # Collection may not exist yet - acceptable
            pass

    yield

    # Cleanup after test
    for collection in [
        COLLECTION_CODE_PATTERNS,
        COLLECTION_CONVENTIONS,
        COLLECTION_DISCUSSIONS,
    ]:
        try:
            e2e_qdrant_client.delete(
                collection_name=collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="group_id", match=MatchValue(value=test_group_id)
                        )
                    ]
                ),
            )
        except Exception:
            # Best effort cleanup - don't fail test
            pass


# =============================================================================
# T1: Collection & Type System E2E
# =============================================================================


@pytest.mark.requires_qdrant
def test_collection_type_system_e2e(
    e2e_qdrant_client: QdrantClient,
    e2e_storage: MemoryStorage,
    test_group_id: str,
    clean_test_data,
):
    """Test complete flow: store → retrieve with types.

    1. Store memory to code-patterns with type="implementation"
    2. Store memory to conventions with type="naming"
    3. Store memory to discussions with type="decision"
    4. Verify type filtering returns only matching types
    5. Verify cross-collection isolation
    """
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    test_cwd = "/tmp/e2e-test-project"

    # 1. Store to code-patterns with implementation type
    impl_content = "Use async/await for database queries to avoid blocking"
    impl_result = e2e_storage.store_memory(
        content=impl_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_CODE_PATTERNS,
    )
    assert impl_result["status"] in [
        "stored",
        "duplicate",
    ], f"Failed to store implementation: {impl_result}"

    # 2. Store to conventions with naming type
    naming_content = "Use snake_case for Python function names"
    naming_result = e2e_storage.store_memory(
        content=naming_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.NAMING,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_CONVENTIONS,
    )
    assert naming_result["status"] in [
        "stored",
        "duplicate",
    ], f"Failed to store naming convention: {naming_result}"

    # 3. Store to discussions with decision type
    decision_content = "Decided to use PostgreSQL because it supports JSON columns and has better ACID guarantees"
    decision_result = e2e_storage.store_memory(
        content=decision_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.DECISION,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_DISCUSSIONS,
    )
    assert decision_result["status"] in [
        "stored",
        "duplicate",
    ], f"Failed to store decision: {decision_result}"

    # 4. Verify type filtering returns only matching types
    # Search code-patterns for implementation type
    impl_results = search_memories(
        query="database queries",
        group_id=test_group_id,
        collection=COLLECTION_CODE_PATTERNS,
        memory_type=[MemoryType.IMPLEMENTATION.value],
        limit=5,
    )
    assert len(impl_results) >= 1, "Should find implementation memory"
    assert all(
        r["type"] == MemoryType.IMPLEMENTATION.value for r in impl_results
    ), "Type filter should only return implementation memories"

    # Search conventions for naming type
    naming_results = search_memories(
        query="function names",
        group_id=test_group_id,
        collection=COLLECTION_CONVENTIONS,
        memory_type=[MemoryType.NAMING.value],
        limit=5,
    )
    assert len(naming_results) >= 1, "Should find naming convention"
    assert all(
        r["type"] == MemoryType.NAMING.value for r in naming_results
    ), "Type filter should only return naming memories"

    # 5. Verify cross-collection isolation
    # Search code-patterns should NOT find convention memory
    code_search = search_memories(
        query="snake_case naming",
        group_id=test_group_id,
        collection=COLLECTION_CODE_PATTERNS,
        limit=5,
    )
    # Should not contain the naming convention (it's in conventions collection)
    naming_in_code = any("snake_case" in r.get("content", "") for r in code_search)
    assert not naming_in_code, "Code-patterns collection should not contain conventions"


# =============================================================================
# T2: Intent Detection → Search Flow E2E
# =============================================================================


@pytest.mark.requires_qdrant
def test_intent_detection_search_flow_e2e(
    e2e_qdrant_client: QdrantClient,
    e2e_storage: MemoryStorage,
    test_group_id: str,
    clean_test_data,
):
    """Test intent-based routing end-to-end.

    1. "how do I implement X" → routes to code-patterns
    2. "what is the naming convention" → routes to conventions
    3. "why did we decide X" → routes to discussions
    4. Verify attribution shows collection/type in results
    """
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    test_cwd = "/tmp/e2e-test-project"

    # Store test memories in each collection
    impl_content = (
        "Implement error handling using try-except with specific exception types"
    )
    e2e_storage.store_memory(
        content=impl_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_CODE_PATTERNS,
    )

    naming_content = "Use UPPER_CASE for constants in Python modules"
    e2e_storage.store_memory(
        content=naming_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.NAMING,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_CONVENTIONS,
    )

    decision_content = "Decided to use async/await pattern to improve concurrency for I/O bound operations"
    e2e_storage.store_memory(
        content=decision_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.DECISION,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_DISCUSSIONS,
    )

    # Test 1: HOW query routes to code-patterns
    how_query = "how do I implement error handling in Python"
    how_intent = detect_intent(how_query)
    assert how_intent == IntentType.HOW, f"Expected HOW intent, got {how_intent}"

    how_collection = get_target_collection(how_intent)
    assert (
        how_collection == COLLECTION_CODE_PATTERNS
    ), f"HOW should route to {COLLECTION_CODE_PATTERNS}, got {how_collection}"

    how_results = search_memories(
        query=how_query,
        group_id=test_group_id,
        collection=how_collection,
        limit=5,
    )
    assert len(how_results) >= 1, "Should find error handling implementation"

    # Test 2: WHAT query routes to conventions
    what_query = "what is the naming convention for constants"
    what_intent = detect_intent(what_query)
    assert what_intent == IntentType.WHAT, f"Expected WHAT intent, got {what_intent}"

    what_collection = get_target_collection(what_intent)
    assert (
        what_collection == COLLECTION_CONVENTIONS
    ), f"WHAT should route to {COLLECTION_CONVENTIONS}, got {what_collection}"

    what_results = search_memories(
        query=what_query,
        group_id=test_group_id,
        collection=what_collection,
        limit=5,
    )
    assert len(what_results) >= 1, "Should find naming convention"

    # Test 3: WHY query routes to discussions
    why_query = "why did we decide to use async patterns"
    why_intent = detect_intent(why_query)
    assert why_intent == IntentType.WHY, f"Expected WHY intent, got {why_intent}"

    why_collection = get_target_collection(why_intent)
    assert (
        why_collection == COLLECTION_DISCUSSIONS
    ), f"WHY should route to {COLLECTION_DISCUSSIONS}, got {why_collection}"

    why_results = search_memories(
        query=why_query,
        group_id=test_group_id,
        collection=why_collection,
        limit=5,
    )
    assert len(why_results) >= 1, "Should find async decision"

    # Test 4: Verify attribution in results
    for result in how_results:
        assert "collection" in result, "Result should include collection attribution"
        assert "type" in result, "Result should include type attribution"


# =============================================================================
# T3: Cascading Search E2E
# =============================================================================


@pytest.mark.requires_qdrant
def test_cascading_search_e2e(
    e2e_qdrant_client: QdrantClient,
    e2e_storage: MemoryStorage,
    test_group_id: str,
    clean_test_data,
):
    """Test search expansion when primary results insufficient.

    1. Store memory in secondary collection only
    2. Query with intent matching primary (empty)
    3. Verify cascading expands to secondary
    4. Verify results include attribution showing expansion
    """
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    test_cwd = "/tmp/e2e-test-project"

    # 1. Store memory ONLY in conventions (secondary for HOW queries)
    # HOW queries normally search code-patterns first, but we store in conventions
    content = "Always use type hints in function signatures for better code clarity"
    e2e_storage.store_memory(
        content=content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.GUIDELINE,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_CONVENTIONS,  # Store in secondary for HOW queries
    )

    # 2. Query with HOW intent (primary = code-patterns, secondary = conventions)
    query = "how to use type hints in Python"
    intent = detect_intent(query)
    assert intent == IntentType.HOW, "Should detect HOW intent"

    # 3. Use cascading search which should expand to conventions
    results = search_memories(
        query=query,
        group_id=test_group_id,
        use_cascading=True,
        intent=intent.value,
        limit=5,
    )

    # Should find the memory even though it's in secondary collection
    assert (
        len(results) >= 1
    ), "Cascading search should find memory in secondary collection"

    # 4. Verify attribution shows collection
    found_in_conventions = False
    for result in results:
        if result.get("collection") == COLLECTION_CONVENTIONS:
            found_in_conventions = True
            assert (
                "type hints" in result.get("content", "").lower()
            ), "Should find the type hints guideline"

    assert (
        found_in_conventions
    ), "Results should include attribution showing expansion to conventions collection"


# =============================================================================
# T4: Trigger System E2E
# =============================================================================


@pytest.mark.requires_qdrant
def test_trigger_error_detection_e2e(clean_test_data):
    """Test error trigger detection.

    1. Error detection: "TypeError: expected str" → detects, extracts type
    2. Verify NO false positives for edge cases
    """
    # 1. Test error detection
    error_text = "TypeError: expected str, got int"
    detected = detect_error_signal(error_text)
    assert detected is not None, "Should detect TypeError"
    assert "TypeError" in detected, "Should extract error type"

    # Test other error patterns
    assert detect_error_signal("Error: Connection refused") is not None
    assert detect_error_signal("Exception: Invalid input") is not None
    assert detect_error_signal("Traceback (most recent call last):") is not None

    # 2. Verify NO false positives
    assert detect_error_signal("Everything works fine") is None
    assert detect_error_signal("The user made an error in judgment") is None
    assert detect_error_signal("This is a normal message") is None
    assert detect_error_signal("No errors here") is None


@pytest.mark.requires_qdrant
def test_trigger_new_file_detection_e2e(clean_test_data):
    """Test new file detection trigger.

    Verifies that is_new_file() correctly identifies file creation vs. modification.
    """
    # New file detection - returns True if file path doesn't exist
    new_file_path = f"/tmp/test-new-file-{uuid.uuid4().hex[:8]}.py"
    assert is_new_file(new_file_path), "Non-existent file should be detected as new"

    # Existing file - create it first
    existing_file_path = f"/tmp/test-existing-{uuid.uuid4().hex[:8]}.py"
    with open(existing_file_path, "w") as f:
        f.write("# test file")

    try:
        assert not is_new_file(
            existing_file_path
        ), "Existing file should NOT be detected as new"
    finally:
        # Cleanup
        import os

        if os.path.exists(existing_file_path):
            os.remove(existing_file_path)


@pytest.mark.requires_qdrant
def test_trigger_first_edit_detection_e2e(clean_test_data):
    """Test first edit detection trigger.

    1. Session A edits file X → tracked
    2. Session B edits file X → should trigger (different session)
    3. Session A edits file X again → should NOT trigger (already tracked)
    """
    file_path = "/tmp/test-file.py"
    session_a = f"session-a-{uuid.uuid4().hex[:8]}"
    session_b = f"session-b-{uuid.uuid4().hex[:8]}"

    # 1. Session A edits file X → should trigger (first edit)
    # Note: is_first_edit_in_session tracks automatically
    assert is_first_edit_in_session(
        file_path, session_a
    ), "First edit in session A should trigger"

    # 2. Session B edits file X → should trigger (different session)
    assert is_first_edit_in_session(
        file_path, session_b
    ), "First edit in session B should trigger (different session)"

    # 3. Session A edits file X again → should NOT trigger (already tracked)
    assert not is_first_edit_in_session(
        file_path, session_a
    ), "Second edit in session A should NOT trigger"


@pytest.mark.requires_qdrant
def test_trigger_decision_keywords_e2e(clean_test_data):
    """Test decision keyword detection trigger.

    Verifies that decision keywords are detected in user questions.
    """
    # Test decision keyword patterns
    assert detect_decision_keywords(
        "why did we choose PostgreSQL"
    ), "Should detect 'why did we' pattern"
    assert detect_decision_keywords(
        "why do we use async patterns"
    ), "Should detect 'why do we' pattern"
    assert detect_decision_keywords(
        "what was decided about the API design"
    ), "Should detect 'what was decided' pattern"
    assert detect_decision_keywords(
        "what did we decide for error handling"
    ), "Should detect 'what did we decide' pattern"

    # Verify NO false positives
    assert not detect_decision_keywords(
        "how do I implement this feature"
    ), "HOW questions should not trigger decision keywords"
    assert not detect_decision_keywords(
        "what is the port number"
    ), "Generic WHAT questions should not trigger"


# =============================================================================
# T5: Session Isolation E2E
# =============================================================================


@pytest.mark.requires_qdrant
def test_session_isolation_e2e(clean_test_data):
    """Test session tracking doesn't leak between sessions.

    1. Session A edits file X → tracked
    2. Session B edits file X → should trigger (different session)
    3. Session A edits file X again → should NOT trigger (already tracked)
    4. Verify thread safety under concurrent access
    """
    file_path = f"/tmp/test-isolation-{uuid.uuid4().hex[:8]}.py"
    session_1 = f"session-1-{uuid.uuid4().hex[:8]}"
    session_2 = f"session-2-{uuid.uuid4().hex[:8]}"

    # 1. Session 1 edits file X
    # Note: is_first_edit_in_session tracks automatically
    assert is_first_edit_in_session(
        file_path, session_1
    ), "First edit in session 1 should trigger"

    # 2. Session 2 edits file X → different session, should trigger
    assert is_first_edit_in_session(
        file_path, session_2
    ), "Session 2 should trigger on same file (different session)"

    # 3. Session 1 edits file X again → already tracked in session 1
    assert not is_first_edit_in_session(
        file_path, session_1
    ), "Session 1 second edit should not trigger"

    # Verify session 2 is still isolated
    assert not is_first_edit_in_session(
        file_path, session_2
    ), "Session 2 already tracked this file"

    # Test concurrent access with threading
    import threading

    results = []

    def session_worker(session_id: str, file: str):
        # Each thread checks (tracking happens automatically)
        is_first = is_first_edit_in_session(file, session_id)
        results.append((session_id, is_first))

    # Create multiple sessions accessing same file concurrently
    concurrent_file = f"/tmp/test-concurrent-{uuid.uuid4().hex[:8]}.py"
    sessions = [f"concurrent-{i}-{uuid.uuid4().hex[:8]}" for i in range(5)]

    threads = []
    for session in sessions:
        t = threading.Thread(target=session_worker, args=(session, concurrent_file))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # All sessions should see it as first edit (different sessions)
    assert len(results) == 5, "All threads should complete"
    assert all(
        is_first for _, is_first in results
    ), "All sessions should see first edit (different sessions)"


# =============================================================================
# T6: Integration Flow E2E
# =============================================================================


@pytest.mark.requires_qdrant
def test_integration_flow_e2e(
    e2e_qdrant_client: QdrantClient,
    e2e_storage: MemoryStorage,
    test_group_id: str,
    clean_test_data,
):
    """Test complete user flow from store to retrieval.

    1. Store code pattern with implementation type
    2. User asks "how do I implement similar feature"
    3. Verify intent detected as HOW
    4. Verify search returns stored pattern
    5. Verify attribution in results
    6. Verify token count reasonable (<500 tokens for single result)
    """
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    test_cwd = "/tmp/e2e-test-project"

    # 1. Store code pattern with implementation type
    pattern_content = """Implement caching with TTL using a dictionary:

cache = {}
cache_ttl = {}

def get_cached(key):
    if key in cache:
        if time.time() < cache_ttl.get(key, 0):
            return cache[key]
        else:
            del cache[key]
            del cache_ttl[key]
    return None

def set_cached(key, value, ttl_seconds=300):
    cache[key] = value
    cache_ttl[key] = time.time() + ttl_seconds
"""

    result = e2e_storage.store_memory(
        content=pattern_content,
        cwd=test_cwd,
        group_id=test_group_id,
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="manual",
        session_id=session_id,
        collection=COLLECTION_CODE_PATTERNS,
    )
    assert result["status"] in [
        "stored",
        "duplicate",
    ], f"Failed to store pattern: {result}"

    # 2. User asks "how do I implement similar feature"
    user_query = "how do I implement a cache with expiration in Python"

    # 3. Verify intent detected as HOW
    intent = detect_intent(user_query)
    assert intent == IntentType.HOW, f"Expected HOW intent, got {intent}"

    # 4. Verify search returns stored pattern
    collection = get_target_collection(intent)
    assert collection == COLLECTION_CODE_PATTERNS

    results = search_memories(
        query=user_query,
        group_id=test_group_id,
        collection=collection,
        limit=5,
    )

    assert len(results) >= 1, "Should find the cached pattern"
    found_pattern = any("cache" in r.get("content", "").lower() for r in results)
    assert found_pattern, "Should find the caching pattern in results"

    # 5. Verify attribution in results
    for result in results:
        assert "collection" in result, "Result should include collection attribution"
        assert result["collection"] == COLLECTION_CODE_PATTERNS
        assert "type" in result, "Result should include type attribution"
        assert result["type"] == MemoryType.IMPLEMENTATION.value

    # 6. Verify token count reasonable (<500 tokens for single result)
    # Rough estimate: 1 token ≈ 4 characters
    first_result = results[0]
    content_length = len(first_result.get("content", ""))
    estimated_tokens = content_length / 4

    # Single result should be under 500 tokens (as per spec requirement)
    assert (
        estimated_tokens < 500
    ), f"Single result should be <500 tokens, got ~{estimated_tokens} tokens"
