"""Integration tests for Agent SDK wrapper with real Qdrant.

These tests require running services:
- Qdrant on port 26350
- Embedding service on port 28080

Run with: pytest tests/integration/test_sdk_integration.py -v
Skip if services unavailable: pytest -m "not requires_docker_stack"

Test Organization:
- TestSDKStorageIntegration: Basic storage to Qdrant
- TestSDKQueryIntegration: Query-back verification
- TestSDKErrorHandling: Graceful degradation
- TestSDKPerformance: Performance baselines

References:
- TECH-DEBT-044: SDK Integration Tests with Real Qdrant
- src/memory/agent_sdk_wrapper.py: SDK wrapper implementation
- tests/conftest.py: Shared fixtures and patterns

Note: These tests mock the claude_agent_sdk dependency since we're testing
the memory integration layer, not the SDK client itself.
"""

import asyncio
import sys
import time
import uuid
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from qdrant_client.models import FieldCondition, Filter, MatchValue

# Mock claude_agent_sdk before importing AgentSDKWrapper
sys.modules["claude_agent_sdk"] = MagicMock()

from src.memory.agent_sdk_wrapper import AgentSDKWrapper
from src.memory.config import COLLECTION_CODE_PATTERNS, COLLECTION_DISCUSSIONS
from src.memory.models import MemoryType
from src.memory.storage import MemoryStorage

# Skip entire module if services unavailable
pytestmark = [
    pytest.mark.requires_qdrant,
    pytest.mark.requires_embedding,
    pytest.mark.integration,
]


# =============================================================================
# Helper Functions
# =============================================================================


async def wait_for_sdk_storage(sdk_wrapper):
    """Wait for SDK wrapper to queue and store all memories.

    This helper encapsulates the required pattern:
    1. Wait for background tasks to queue memories
    2. Flush the batch queue
    3. Add small delay for storage to complete
    """
    # Wait for background tasks to queue memories
    if sdk_wrapper._storage_tasks:
        await asyncio.wait(sdk_wrapper._storage_tasks, timeout=2.0)

    # Flush batch to actually store memories (blocks until storage completes)
    await sdk_wrapper._flush_batch()

    # Add delay to ensure all executor operations complete
    # Note: run_in_executor may not fully block until thread pool completes
    await asyncio.sleep(1.0)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def test_session_id():
    """Generate unique session ID for test isolation."""
    return f"test-sdk-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_group_id():
    """Generate unique group ID for test isolation."""
    return f"sdk-integration-test-{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def sdk_wrapper(test_session_id, test_group_id, tmp_path, mocker):
    """Create SDK wrapper for testing.

    Note: This fixture mocks the ClaudeSDKClient since we're testing
    the memory integration layer only, not the full SDK client.
    """
    from src.memory.storage import MemoryStorage

    storage = MemoryStorage()

    # Mock the ClaudeSDKClient to avoid requiring SDK installation
    mock_client = MagicMock()
    mock_client.connect = MagicMock(return_value=asyncio.Future())
    mock_client.connect.return_value.set_result(None)

    # Patch ClaudeSDKClient before creating wrapper
    mocker.patch(
        "src.memory.agent_sdk_wrapper.ClaudeSDKClient", return_value=mock_client
    )

    # Mock detect_project globally to return test_group_id
    # This ensures storage.store_memory() uses the test group_id
    mocker.patch("src.memory.project.detect_project", return_value=test_group_id)

    # Create wrapper but don't connect to CLI (not needed for memory testing)
    wrapper = AgentSDKWrapper(
        cwd=str(tmp_path),
        storage=storage,
        session_id=test_session_id,
        api_key="test-key-not-used",  # Won't connect to CLI
    )

    # Override _get_group_id on the wrapper instance as well
    # The wrapper's method was already bound, so we need to override it directly
    wrapper._get_group_id = lambda: test_group_id

    yield wrapper

    # Cleanup: Wait for background storage tasks and check for exceptions
    if wrapper._storage_tasks:
        done, _pending = await asyncio.wait(wrapper._storage_tasks, timeout=5.0)

        # Check for exceptions in completed tasks
        for task in done:
            if task.exception():
                print(f"Background task failed: {task.exception()}")
                import traceback

                traceback.print_exception(
                    type(task.exception()),
                    task.exception(),
                    task.exception().__traceback__,
                )

    # Cleanup: Delete test data
    await cleanup_test_data(storage, test_group_id)


async def cleanup_test_data(storage: MemoryStorage, group_id: str):
    """Remove test data from Qdrant collections.

    Uses scroll + delete pattern for efficient cleanup across all collections.
    """
    from src.memory.qdrant_client import get_qdrant_client

    try:
        client = get_qdrant_client()

        # Cleanup all V2.0 collections
        collections = [COLLECTION_CODE_PATTERNS, COLLECTION_DISCUSSIONS, "conventions"]

        for collection_name in collections:
            try:
                # Scroll to find all points with this group_id
                results, _ = client.scroll(
                    collection_name=collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="group_id",
                                match=MatchValue(value=group_id),
                            )
                        ]
                    ),
                    limit=1000,
                    with_payload=False,
                    with_vectors=False,
                )

                # Delete all matching points
                if results:
                    point_ids = [point.id for point in results]
                    client.delete(
                        collection_name=collection_name,
                        points_selector=point_ids,
                    )
            except Exception:
                # Best effort cleanup - don't fail if collection doesn't exist
                pass

    except Exception:
        # Graceful degradation - cleanup failure shouldn't fail tests
        pass


# =============================================================================
# Stage 2: Basic Storage Integration Tests
# =============================================================================


class TestSDKStorageIntegration:
    """Test SDK wrapper stores to real Qdrant."""

    @pytest.mark.asyncio
    async def test_tool_use_captured_to_qdrant(self, sdk_wrapper, test_group_id):
        """Test PostToolUse hook stores to code-patterns collection."""
        # Simulate a Write tool use via the hook
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py"},
            "tool_response": "File written successfully",
        }

        # Call the hook directly
        await sdk_wrapper._post_tool_use_hook(input_data, "tool-123", {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(sdk_wrapper)

        # Verify point exists in code-patterns
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=10,
            with_payload=True,
        )

        assert len(results) == 1, f"Expected 1 memory, found {len(results)}"

        payload = results[0].payload
        assert payload["type"] == MemoryType.IMPLEMENTATION.value
        assert payload["group_id"] == test_group_id
        assert payload["session_id"] == sdk_wrapper.session_id
        assert "/tmp/test.py" in payload["content"]

    @pytest.mark.asyncio
    async def test_agent_response_captured_to_qdrant(
        self, sdk_wrapper, test_group_id, tmp_path
    ):
        """Test Stop hook stores to discussions collection."""
        # Create a fake transcript file
        transcript_path = tmp_path / "transcript.txt"
        transcript_content = "Agent response: The implementation is complete."
        transcript_path.write_text(transcript_content)

        # Simulate Stop hook
        input_data = {
            "transcript_path": str(transcript_path),
        }

        await sdk_wrapper._stop_hook(input_data, None, {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(sdk_wrapper)

        # Verify point exists in discussions
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=10,
            with_payload=True,
        )

        assert len(results) == 1, f"Expected 1 memory, found {len(results)}"

        payload = results[0].payload
        assert payload["type"] == MemoryType.AGENT_RESPONSE.value
        assert payload["group_id"] == test_group_id
        assert transcript_content in payload["content"]

    @pytest.mark.asyncio
    async def test_error_pattern_captured(self, sdk_wrapper, test_group_id):
        """Test Bash error captured as ERROR_FIX type."""
        # Simulate Bash tool with error exit code
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "false"},
            "tool_response": {"exit_code": 1, "stderr": "Command failed"},
        }

        await sdk_wrapper._post_tool_use_hook(input_data, "tool-456", {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(sdk_wrapper)

        # Verify error pattern stored
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=10,
            with_payload=True,
        )

        assert len(results) == 1
        payload = results[0].payload
        assert payload["type"] == MemoryType.ERROR_FIX.value
        assert "false" in payload["content"]

    @pytest.mark.asyncio
    async def test_session_isolation(self, test_group_id, tmp_path, mocker):
        """Test different sessions don't interfere."""
        from src.memory.storage import MemoryStorage

        storage = MemoryStorage()

        # Mock the ClaudeSDKClient
        mock_client = MagicMock()
        mocker.patch(
            "src.memory.agent_sdk_wrapper.ClaudeSDKClient", return_value=mock_client
        )

        # Mock detect_project to return test_group_id for test isolation
        mocker.patch("src.memory.project.detect_project", return_value=test_group_id)

        # Create two wrappers with different session IDs
        session_1 = f"test-session-1-{uuid.uuid4().hex[:4]}"
        session_2 = f"test-session-2-{uuid.uuid4().hex[:4]}"

        wrapper1 = AgentSDKWrapper(
            cwd=str(tmp_path),
            storage=storage,
            session_id=session_1,
            api_key="test-key",
        )
        # Override _get_group_id for test isolation
        wrapper1._get_group_id = lambda: test_group_id

        wrapper2 = AgentSDKWrapper(
            cwd=str(tmp_path),
            storage=storage,
            session_id=session_2,
            api_key="test-key",
        )
        # Override _get_group_id for test isolation
        wrapper2._get_group_id = lambda: test_group_id

        # Store from both sessions
        input_data_1 = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/session1.py"},
            "tool_response": "Session 1 content",
        }

        input_data_2 = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/session2.py"},
            "tool_response": "Session 2 content",
        }

        await wrapper1._post_tool_use_hook(input_data_1, "tool-1", {})
        await wrapper2._post_tool_use_hook(input_data_2, "tool-2", {})

        # Wait for SDK to queue and store memories from both wrappers
        await wait_for_sdk_storage(wrapper1)
        await wait_for_sdk_storage(wrapper2)

        # Query each session, verify isolation
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        # Query session 1
        results_1, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id", match=MatchValue(value=test_group_id)
                    ),
                    FieldCondition(key="session_id", match=MatchValue(value=session_1)),
                ]
            ),
            limit=10,
            with_payload=True,
        )

        # Query session 2
        results_2, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id", match=MatchValue(value=test_group_id)
                    ),
                    FieldCondition(key="session_id", match=MatchValue(value=session_2)),
                ]
            ),
            limit=10,
            with_payload=True,
        )

        # Each session should have exactly 1 memory
        assert len(results_1) == 1
        assert len(results_2) == 1

        # Verify content isolation
        assert "session1.py" in results_1[0].payload["content"]
        assert "session2.py" in results_2[0].payload["content"]


# =============================================================================
# Stage 3: Query-Back Verification Tests
# =============================================================================


class TestSDKQueryIntegration:
    """Test stored memories can be queried back."""

    @pytest.mark.asyncio
    async def test_stored_memory_queryable(self, sdk_wrapper, test_group_id):
        """Test stored memory can be found via semantic search."""
        # Store a specific implementation pattern
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/auth.py"},
            "tool_response": "Implemented JWT authentication middleware",
        }

        await sdk_wrapper._post_tool_use_hook(input_data, "tool-auth", {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(sdk_wrapper)

        # Query with related terms
        from src.memory.search import search_memories

        results = search_memories(
            query="authentication implementation",
            group_id=test_group_id,
            limit=5,
        )

        # Verify the stored memory is in results
        assert len(results) > 0, "Expected at least 1 result from semantic search"

        # Check if our memory is in the results
        found = False
        for result in results:
            if "JWT authentication" in result["content"]:
                found = True
                assert result["type"] == MemoryType.IMPLEMENTATION.value
                assert result["group_id"] == test_group_id
                break

        assert found, "Stored memory not found in semantic search results"

    @pytest.mark.asyncio
    async def test_embedding_generated_correctly(self, sdk_wrapper, test_group_id):
        """Test embeddings are 768-dimensional (jina-v2)."""
        # Store memory
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/utils.py"},
            "tool_response": "Utility functions for data processing",
        }

        await sdk_wrapper._post_tool_use_hook(input_data, "tool-utils", {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(sdk_wrapper)

        # Retrieve point directly from Qdrant
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=True,
        )

        assert len(results) == 1

        # Verify vector dimension is 768 (DEC-010: Jina Embeddings v2 Base)
        vector = results[0].vector
        assert len(vector) == 768, f"Expected 768 dimensions, got {len(vector)}"

    @pytest.mark.asyncio
    async def test_payload_fields_complete(self, sdk_wrapper, test_group_id):
        """Test all required payload fields present."""
        # Store memory
        input_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/config.yaml"},
            "tool_response": "Updated configuration",
        }

        await sdk_wrapper._post_tool_use_hook(input_data, "tool-edit", {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(sdk_wrapper)

        # Retrieve and verify
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )

        assert len(results) == 1
        payload = results[0].payload

        # Verify all required fields present
        required_fields = [
            "content",
            "content_hash",
            "group_id",
            "type",
            "source_hook",  # Not "source"
            "session_id",
            # Note: turn_number not in MemoryPayload schema
            "timestamp",
            "embedding_status",
            "embedding_model",
        ]

        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"

        # Verify field values
        assert payload["group_id"] == test_group_id
        assert payload["session_id"] == sdk_wrapper.session_id
        assert payload["type"] == MemoryType.IMPLEMENTATION.value
        assert payload["source_hook"] == "PostToolUse"
        # Note: turn_number not stored in MemoryPayload


# =============================================================================
# Stage 4: Error Handling Tests
# =============================================================================


class TestSDKErrorHandling:
    """Test graceful degradation on failures."""

    @pytest.mark.asyncio
    async def test_storage_failure_doesnt_crash(
        self, test_session_id, tmp_path, mocker
    ):
        """Test SDK continues if storage fails."""
        from src.memory.storage import MemoryStorage

        # Mock the ClaudeSDKClient
        mock_client = MagicMock()
        mocker.patch(
            "src.memory.agent_sdk_wrapper.ClaudeSDKClient", return_value=mock_client
        )

        # Create wrapper with mocked storage that raises exception
        storage = MemoryStorage()
        mocker.patch.object(
            storage, "store_memory", side_effect=Exception("Storage failed")
        )

        wrapper = AgentSDKWrapper(
            cwd=str(tmp_path),
            storage=storage,
            session_id=test_session_id,
            api_key="test-key",
        )

        # Simulate tool use - should not crash
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py"},
            "tool_response": "Content",
        }

        # This should complete without raising exception
        result = await wrapper._post_tool_use_hook(input_data, "tool-123", {})

        # Hook should return empty dict (graceful degradation)
        assert result == {}

        # Wait for background task (will fail but shouldn't crash)
        if wrapper._storage_tasks:
            await asyncio.wait(wrapper._storage_tasks, timeout=2.0)

    @pytest.mark.asyncio
    async def test_embedding_failure_graceful(
        self, test_session_id, test_group_id, tmp_path, mocker
    ):
        """Test graceful handling of embedding service failure."""
        from src.memory.embeddings import EmbeddingError
        from src.memory.storage import MemoryStorage

        # Mock the ClaudeSDKClient
        mock_client = MagicMock()
        mocker.patch(
            "src.memory.agent_sdk_wrapper.ClaudeSDKClient", return_value=mock_client
        )

        storage = MemoryStorage()

        # Mock detect_project to return test_group_id for test isolation
        mocker.patch("src.memory.project.detect_project", return_value=test_group_id)

        # Mock embedding client to fail
        mocker.patch(
            "src.memory.embeddings.EmbeddingClient.embed",
            side_effect=EmbeddingError("Embedding service down"),
        )

        wrapper = AgentSDKWrapper(
            cwd=str(tmp_path),
            storage=storage,
            session_id=test_session_id,
            api_key="test-key",
        )

        # Store should succeed with embedding_status = pending
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py"},
            "tool_response": "Test content",
        }

        await wrapper._post_tool_use_hook(input_data, "tool-123", {})

        # Wait for SDK to queue and store the memory
        await wait_for_sdk_storage(wrapper)

        # Verify memory stored with pending status
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )

        # Should still have stored the memory
        assert len(results) == 1
        assert results[0].payload["embedding_status"] == "pending"

    @pytest.mark.asyncio
    async def test_qdrant_unavailable_graceful(self, test_session_id, tmp_path, mocker):
        """Test graceful handling when Qdrant is down."""
        from src.memory.qdrant_client import QdrantUnavailable
        from src.memory.storage import MemoryStorage

        # Mock the ClaudeSDKClient
        mock_client = MagicMock()
        mocker.patch(
            "src.memory.agent_sdk_wrapper.ClaudeSDKClient", return_value=mock_client
        )

        storage = MemoryStorage()

        # Mock Qdrant client to fail
        mocker.patch(
            "src.memory.qdrant_client.get_qdrant_client",
            side_effect=QdrantUnavailable("Qdrant unavailable"),
        )

        wrapper = AgentSDKWrapper(
            cwd=str(tmp_path),
            storage=storage,
            session_id=test_session_id,
            api_key="test-key",
        )

        # Attempt to store - should not crash
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py"},
            "tool_response": "Content",
        }

        # Hook should complete without raising
        result = await wrapper._post_tool_use_hook(input_data, "tool-123", {})
        assert result == {}

        # Wait for background task
        if wrapper._storage_tasks:
            await asyncio.wait(wrapper._storage_tasks, timeout=2.0)


# =============================================================================
# Stage 5: Performance Baseline Tests
# =============================================================================


class TestSDKPerformance:
    """Baseline performance tests."""

    @pytest.mark.asyncio
    async def test_storage_latency_acceptable(self, sdk_wrapper, test_group_id):
        """Test storage completes within acceptable time."""
        # Hook should return immediately (<100ms per fire-and-forget pattern)
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/perf_test.py"},
            "tool_response": "Performance test content",
        }

        start = time.perf_counter()
        await sdk_wrapper._post_tool_use_hook(input_data, "tool-perf", {})
        elapsed = time.perf_counter() - start

        # Fire-and-forget should return immediately (<100ms)
        assert elapsed < 0.1, f"Hook took {elapsed:.3f}s, expected <0.1s"

        # Wait for actual storage to complete
        if sdk_wrapper._storage_tasks:
            await asyncio.wait(sdk_wrapper._storage_tasks, timeout=5.0)

    @pytest.mark.asyncio
    async def test_concurrent_storage_safe(self, sdk_wrapper, test_group_id):
        """Test concurrent storage doesn't cause issues."""
        # Create 10 concurrent storage tasks
        tasks = []
        for i in range(10):
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": f"/tmp/concurrent_{i}.py"},
                "tool_response": f"Concurrent test {i}",
            }
            task = sdk_wrapper._post_tool_use_hook(input_data, f"tool-{i}", {})
            tasks.append(task)

        # Wait for all hooks to complete
        await asyncio.gather(*tasks)

        # Wait for SDK to queue and store all memories
        await wait_for_sdk_storage(sdk_wrapper)

        # Verify all 10 points exist in Qdrant
        from src.memory.qdrant_client import get_qdrant_client

        client = get_qdrant_client()

        results, _ = client.scroll(
            collection_name=COLLECTION_CODE_PATTERNS,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="group_id",
                        match=MatchValue(value=test_group_id),
                    )
                ]
            ),
            limit=20,
            with_payload=True,
        )

        assert len(results) == 10, f"Expected 10 memories, found {len(results)}"
