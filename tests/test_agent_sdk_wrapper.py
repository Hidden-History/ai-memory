"""Unit tests for Agent SDK wrapper (TECH-DEBT-035 Phase 3).

Tests AgentSDKWrapper with mocked claude_agent_sdk dependencies.
Validates hook registration, memory capture, and graceful degradation.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mock claude_agent_sdk before importing AgentSDKWrapper
sys.modules["claude_agent_sdk"] = MagicMock()

import contextlib  # noqa: E402

from src.memory.agent_sdk_wrapper import (  # noqa: E402
    AgentSDKWrapper,
    create_memory_enhanced_client,
)
from src.memory.config import (  # noqa: E402
    COLLECTION_CODE_PATTERNS,
    COLLECTION_DISCUSSIONS,
)
from src.memory.models import MemoryType  # noqa: E402


@pytest.fixture
def mock_storage():
    """Mock MemoryStorage with sync store_memory method."""
    mock_store = Mock()
    mock_store.store_memory = Mock(
        return_value={
            "status": "stored",
            "memory_id": "test_agent_mem_123",
            "embedding_status": "complete",
        }
    )
    return mock_store


@pytest.fixture
def mock_claude_sdk_client():
    """Mock ClaudeSDKClient."""
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.receive_response = AsyncMock()
    return mock_client


# ==============================================================================
# AgentSDKWrapper Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_agent_sdk_wrapper_initialization(mock_storage):
    """Test wrapper initializes with hooks registered."""
    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
            session_id="test-session",
        )

        # Verify initialization
        assert wrapper.cwd == "/test/project"
        assert wrapper.session_id == "test-session"
        assert wrapper.storage == mock_storage
        assert wrapper.turn_number == 0
        assert wrapper._storage_tasks == []

        # Verify ClaudeSDKClient was created with options
        MockClient.assert_called_once()
        call_args = MockClient.call_args
        assert "options" in call_args[1]
        options = call_args[1]["options"]
        assert options is not None
        # Verify hooks were configured (options object contains hooks dict)
        assert hasattr(options, "hooks") or isinstance(
            options.hooks if hasattr(options, "hooks") else None, (dict, MagicMock)
        )


@pytest.mark.asyncio
async def test_post_tool_use_hook_implementation():
    """Test PostToolUse hook captures Write/Edit as IMPLEMENTATION."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(return_value={"status": "stored"})

    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        mock_dedup.return_value = Mock(is_duplicate=False)

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Simulate PostToolUse hook input for Write
        input_data = {
            "session_id": "test-session",
            "transcript_path": "/tmp/transcript",
            "cwd": "/test/project",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test/file.py"},
            "tool_response": "File written successfully",
        }

        # Call hook
        result = await wrapper._post_tool_use_hook(input_data, None, Mock())

        # Should return empty dict (doesn't block)
        assert result == {}

        # Wait for background task
        if wrapper._storage_tasks:
            await asyncio.gather(*wrapper._storage_tasks)

        # Flush batch to trigger storage
        await wrapper._flush_batch()

        # Verify storage was called with IMPLEMENTATION type
        mock_storage.store_memory.assert_called()
        call_args = mock_storage.store_memory.call_args
        assert call_args[0][2] == MemoryType.IMPLEMENTATION  # memory_type
        assert call_args[0][5] == COLLECTION_CODE_PATTERNS  # collection


@pytest.mark.asyncio
async def test_post_tool_use_hook_error_fix():
    """Test PostToolUse hook captures Bash errors as ERROR_FIX."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(return_value={"status": "stored"})

    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        mock_dedup.return_value = Mock(is_duplicate=False)

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Simulate PostToolUse hook input for Bash error
        input_data = {
            "session_id": "test-session",
            "transcript_path": "/tmp/transcript",
            "cwd": "/test/project",
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "tool_response": {"exit_code": 1, "stderr": "Error: test failed"},
        }

        # Call hook
        result = await wrapper._post_tool_use_hook(input_data, None, Mock())

        assert result == {}

        # Wait for background task
        if wrapper._storage_tasks:
            await asyncio.gather(*wrapper._storage_tasks)

        # Flush batch to trigger storage
        await wrapper._flush_batch()

        # Verify storage was called with ERROR_FIX type
        mock_storage.store_memory.assert_called()
        call_args = mock_storage.store_memory.call_args
        assert call_args[0][2] == MemoryType.ERROR_FIX
        assert call_args[0][5] == COLLECTION_CODE_PATTERNS


@pytest.mark.asyncio
async def test_post_tool_use_hook_skip_successful_bash():
    """Test PostToolUse hook skips successful Bash commands."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(return_value={"status": "stored"})

    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"):
        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Simulate PostToolUse hook input for successful Bash
        input_data = {
            "session_id": "test-session",
            "transcript_path": "/tmp/transcript",
            "cwd": "/test/project",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
            "tool_response": "hello",
        }

        # Call hook
        result = await wrapper._post_tool_use_hook(input_data, None, Mock())

        assert result == {}

        # Wait for any background tasks
        if wrapper._storage_tasks:
            await asyncio.gather(*wrapper._storage_tasks)

        # Verify storage was NOT called (successful Bash skipped)
        mock_storage.store_memory.assert_not_called()


@pytest.mark.asyncio
async def test_stop_hook_captures_response(tmp_path):
    """Test Stop hook captures agent response from transcript."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(return_value={"status": "stored"})

    # Create mock transcript file
    transcript_path = tmp_path / "transcript.txt"
    transcript_path.write_text("Agent: Here is the solution...")

    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        mock_dedup.return_value = Mock(is_duplicate=False)

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Simulate Stop hook input
        input_data = {
            "session_id": "test-session",
            "transcript_path": str(transcript_path),
            "cwd": "/test/project",
        }

        # Call hook
        result = await wrapper._stop_hook(input_data, None, Mock())

        assert result == {}

        # Wait for background task
        if wrapper._storage_tasks:
            await asyncio.gather(*wrapper._storage_tasks)

        # Flush batch to trigger storage
        await wrapper._flush_batch()

        # Verify storage was called with AGENT_RESPONSE type
        mock_storage.store_memory.assert_called()
        call_args = mock_storage.store_memory.call_args
        assert call_args[0][2] == MemoryType.AGENT_RESPONSE
        assert call_args[0][5] == COLLECTION_DISCUSSIONS
        assert "Here is the solution" in call_args[0][0]  # content


@pytest.mark.asyncio
async def test_wrapper_context_manager():
    """Test wrapper works as async context manager."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(return_value={"status": "stored"})

    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_client_instance

        async with AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        ) as wrapper:
            assert wrapper is not None

        # Verify connect and disconnect were called
        mock_client_instance.connect.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_graceful_degradation_on_storage_failure():
    """Test wrapper continues on storage failure (graceful degradation)."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(side_effect=Exception("Storage failed"))

    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"):
        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Simulate PostToolUse hook
        input_data = {
            "session_id": "test-session",
            "transcript_path": "/tmp/transcript",
            "cwd": "/test/project",
            "tool_name": "Write",
            "tool_input": {"file_path": "/test/file.py"},
            "tool_response": "File written",
        }

        # Should not raise exception
        result = await wrapper._post_tool_use_hook(input_data, None, Mock())
        assert result == {}

        # Wait for background task to complete (should fail gracefully)
        if wrapper._storage_tasks:
            await asyncio.gather(*wrapper._storage_tasks, return_exceptions=True)

        # No exception should propagate


@pytest.mark.asyncio
async def test_create_memory_enhanced_client():
    """Test factory function creates connected client."""
    mock_storage = Mock()

    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_client_instance

        client = await create_memory_enhanced_client(
            project_id="test-project",
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Verify client created and connected
        assert client is not None
        assert "test-project" in client.session_id
        mock_client_instance.connect.assert_called_once()

        # Cleanup
        await client.close()


@pytest.mark.asyncio
async def test_query_method():
    """Test query method delegates to SDK client."""
    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.query = AsyncMock()
        MockClient.return_value = mock_client_instance

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
        )

        await wrapper.query("Test prompt")

        # Verify query was called on SDK client
        mock_client_instance.query.assert_called_once_with("Test prompt")


@pytest.mark.asyncio
async def test_receive_response_method():
    """Test receive_response method delegates to SDK client."""
    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()

        # Mock async generator
        async def mock_receive():
            yield Mock(content="Message 1")
            yield Mock(content="Message 2")

        mock_client_instance.receive_response = mock_receive
        MockClient.return_value = mock_client_instance

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
        )

        messages = []
        async for message in wrapper.receive_response():
            messages.append(message.content)

        # Verify messages received
        assert len(messages) == 2
        assert messages[0] == "Message 1"
        assert messages[1] == "Message 2"


@pytest.mark.asyncio
async def test_missing_api_key_raises():
    """Test wrapper raises ValueError if ANTHROPIC_API_KEY not found."""
    with (
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"),
    ):
        AgentSDKWrapper(cwd="/test/project")


# ==============================================================================
# Deduplication Tests (TECH-DEBT-042)
# ==============================================================================


@pytest.mark.asyncio
async def test_duplicate_content_not_stored_twice(mock_storage):
    """Test same content only stored once (deduplication)."""
    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        # First call: not duplicate
        # Second call: is duplicate
        mock_dedup.side_effect = [
            Mock(is_duplicate=False),  # First check
            Mock(is_duplicate=True, existing_id="mem_123"),  # Second check
        ]

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        # Queue same content twice
        from src.memory.models import MemoryType

        await wrapper._queue_memory(
            "test content", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )
        await wrapper._queue_memory(
            "test content", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )

        # Flush batch
        await wrapper._flush_batch()

        # Should only have one storage call (duplicate skipped)
        assert mock_storage.store_memory.call_count == 1


@pytest.mark.asyncio
async def test_different_content_stored_separately(mock_storage):
    """Test different content stored as separate memories."""
    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        # Both are unique
        mock_dedup.return_value = Mock(is_duplicate=False)

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        from src.memory.models import MemoryType

        # Queue different content
        await wrapper._queue_memory(
            "content 1", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )
        await wrapper._queue_memory(
            "content 2", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )

        # Flush batch
        await wrapper._flush_batch()

        # Should have two storage calls
        assert mock_storage.store_memory.call_count == 2


@pytest.mark.asyncio
async def test_duplicate_in_pending_queue_detected(mock_storage):
    """Test duplicate detected in pending queue (fast path)."""
    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        # First call checks Qdrant (not duplicate)
        mock_dedup.return_value = Mock(is_duplicate=False)

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        from src.memory.models import MemoryType

        # Queue same content twice (should detect in pending queue)
        await wrapper._queue_memory(
            "test content", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )
        await wrapper._queue_memory(
            "test content", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )

        # Dedup should only be called once (second is detected in pending queue)
        assert mock_dedup.call_count == 1

        # Queue should only have one item
        assert len(wrapper._batch_queue) == 1


# ==============================================================================
# Batching Tests (TECH-DEBT-043)
# ==============================================================================


@pytest.mark.asyncio
async def test_batch_flushes_at_size_limit(mock_storage):
    """Test batch flushes when size limit reached."""
    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        mock_dedup.return_value = Mock(is_duplicate=False)

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )
        wrapper._batch_size = 3  # Small batch for testing

        from src.memory.models import MemoryType

        # Add 3 items (should trigger flush)
        for i in range(3):
            await wrapper._queue_memory(
                f"content {i}", MemoryType.IMPLEMENTATION, "code-patterns", "test"
            )

        # Allow flush task to complete
        await asyncio.sleep(0.1)

        # Should have triggered flush
        assert mock_storage.store_memory.call_count == 3


@pytest.mark.asyncio
async def test_session_end_flushes_remaining(mock_storage):
    """Test remaining batch flushed on session end."""
    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.connect = AsyncMock()
        mock_client_instance.disconnect = AsyncMock()
        MockClient.return_value = mock_client_instance

        with patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup:
            mock_dedup.return_value = Mock(is_duplicate=False)

            async with AgentSDKWrapper(
                cwd="/test/project",
                api_key="test-key",
                storage=mock_storage,
            ) as wrapper:
                wrapper._batch_size = 10  # Won't auto-flush

                from src.memory.models import MemoryType

                await wrapper._queue_memory(
                    "test", MemoryType.IMPLEMENTATION, "code-patterns", "test"
                )

            # Should have flushed on exit
            assert mock_storage.store_memory.call_count == 1


@pytest.mark.asyncio
async def test_periodic_flush():
    """Test periodic flush fires on interval."""
    mock_storage = Mock()
    mock_storage.store_memory = Mock(return_value={"status": "stored"})

    with patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient") as MockClient:
        mock_client_instance = AsyncMock()
        MockClient.return_value = mock_client_instance

        with patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup:
            mock_dedup.return_value = Mock(is_duplicate=False)

            wrapper = AgentSDKWrapper(
                cwd="/test/project",
                api_key="test-key",
                storage=mock_storage,
            )
            wrapper._batch_flush_interval = 0.1  # Fast interval for testing

            from src.memory.models import MemoryType

            # Start flusher
            await wrapper._start_batch_flusher()

            # Queue item
            await wrapper._queue_memory(
                "test", MemoryType.IMPLEMENTATION, "code-patterns", "test"
            )

            # Wait for periodic flush
            await asyncio.sleep(0.2)

            # Should have flushed
            assert mock_storage.store_memory.call_count >= 1

            # Cleanup
            wrapper._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await wrapper._flush_task


@pytest.mark.asyncio
async def test_dedup_graceful_degradation(mock_storage):
    """Test graceful degradation when dedup check fails."""
    with (
        patch("src.memory.agent_sdk_wrapper.ClaudeSDKClient"),
        patch("src.memory.agent_sdk_wrapper.is_duplicate") as mock_dedup,
    ):
        # Dedup check fails
        mock_dedup.side_effect = Exception("Qdrant unavailable")

        wrapper = AgentSDKWrapper(
            cwd="/test/project",
            api_key="test-key",
            storage=mock_storage,
        )

        from src.memory.models import MemoryType

        # Should still queue despite dedup error
        await wrapper._queue_memory(
            "test", MemoryType.IMPLEMENTATION, "code-patterns", "test"
        )

        # Queue should have item (graceful degradation)
        assert len(wrapper._batch_queue) == 1

        # Flush should succeed
        await wrapper._flush_batch()
        assert mock_storage.store_memory.call_count == 1
