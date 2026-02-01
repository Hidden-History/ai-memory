"""Unit tests for SDK wrapper (TECH-DEBT-035 Phase 1).

Tests SDKWrapper and ConversationCapture with mocked dependencies.
Validates prompt→response→capture flow and graceful degradation.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from anthropic.types import Message, TextBlock, Usage

from src.memory.config import COLLECTION_DISCUSSIONS
from src.memory.models import MemoryType
from src.memory.sdk_wrapper import ConversationCapture, SDKWrapper


@pytest.fixture
def mock_storage():
    """Mock MemoryStorage."""
    mock_store = Mock()
    mock_store.store_memory = Mock(
        return_value={
            "status": "stored",
            "memory_id": "test_mem_123",
            "embedding_status": "complete",
        }
    )
    return mock_store


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client with Message response."""
    mock_client = Mock()

    # Create mock message response
    mock_message = Mock(spec=Message)
    mock_message.id = "msg_123"
    mock_message.model = "claude-3-5-sonnet-20241022"
    mock_message.role = "assistant"

    # Create mock text block
    mock_text_block = Mock(spec=TextBlock)
    mock_text_block.text = "The capital of France is Paris."
    mock_text_block.type = "text"

    mock_message.content = [mock_text_block]
    mock_message.stop_reason = "end_turn"
    mock_message.usage = Usage(input_tokens=10, output_tokens=8)

    mock_client.messages.create = Mock(return_value=mock_message)

    return mock_client


@pytest.fixture
def mock_stream_manager():
    """Mock streaming response manager."""
    mock_stream = MagicMock()
    mock_stream.__enter__ = Mock(return_value=mock_stream)
    mock_stream.__exit__ = Mock(return_value=False)
    mock_stream.text_stream = ["The ", "capital ", "is ", "Paris."]
    return mock_stream


@pytest.fixture
def conversation_capture(mock_storage, tmp_path):
    """ConversationCapture instance with mocked storage."""
    return ConversationCapture(
        storage=mock_storage, cwd=str(tmp_path), session_id="test_session_123"
    )


# ==============================================================================
# ConversationCapture Tests
# ==============================================================================


def test_capture_user_message(conversation_capture, mock_storage):
    """Test user message capture stores to discussions collection with USER_MESSAGE type."""
    result = conversation_capture.capture_user_message("What is the capital of France?")

    # Verify store_memory called with correct parameters
    mock_storage.store_memory.assert_called_once()
    call_kwargs = mock_storage.store_memory.call_args[1]

    assert call_kwargs["content"] == "What is the capital of France?"
    assert call_kwargs["memory_type"] == MemoryType.USER_MESSAGE
    assert call_kwargs["source_hook"] == "SDKWrapper"
    assert call_kwargs["session_id"] == "test_session_123"
    assert call_kwargs["collection"] == COLLECTION_DISCUSSIONS
    assert call_kwargs["turn_number"] == 1

    # Verify result
    assert result["status"] == "stored"
    assert result["memory_id"] == "test_mem_123"


def test_capture_agent_response(conversation_capture, mock_storage):
    """Test agent response capture stores to discussions collection with AGENT_RESPONSE type."""
    # First capture user message to increment turn number
    conversation_capture.capture_user_message("Test question")
    mock_storage.store_memory.reset_mock()

    # Capture agent response
    result = conversation_capture.capture_agent_response("Test answer")

    # Verify store_memory called with correct parameters
    mock_storage.store_memory.assert_called_once()
    call_kwargs = mock_storage.store_memory.call_args[1]

    assert call_kwargs["content"] == "Test answer"
    assert call_kwargs["memory_type"] == MemoryType.AGENT_RESPONSE
    assert call_kwargs["source_hook"] == "SDKWrapper"
    assert call_kwargs["session_id"] == "test_session_123"
    assert call_kwargs["collection"] == COLLECTION_DISCUSSIONS
    assert call_kwargs["turn_number"] == 1  # Same turn as user message

    # Verify result
    assert result["status"] == "stored"


def test_capture_increments_turn_number(conversation_capture):
    """Test turn number increments with each user message."""
    conversation_capture.capture_user_message("First question")
    assert conversation_capture.turn_number == 1

    conversation_capture.capture_user_message("Second question")
    assert conversation_capture.turn_number == 2

    conversation_capture.capture_user_message("Third question")
    assert conversation_capture.turn_number == 3


def test_capture_user_message_graceful_degradation(conversation_capture, mock_storage):
    """Test graceful degradation when storage fails."""
    mock_storage.store_memory.side_effect = Exception("Storage unavailable")

    result = conversation_capture.capture_user_message("Test question")

    assert result["status"] == "failed"
    assert "Storage unavailable" in result["error"]


# ==============================================================================
# SDKWrapper Tests
# ==============================================================================


@patch("src.memory.sdk_wrapper.Anthropic")
@patch("src.memory.sdk_wrapper.MemoryStorage")
def test_sdk_wrapper_initialization(MockStorage, MockAnthropic, tmp_path):
    """Test SDKWrapper initializes with correct dependencies."""
    wrapper = SDKWrapper(cwd=str(tmp_path), api_key="test_api_key")

    # Verify Anthropic client created with API key
    MockAnthropic.assert_called_once_with(api_key="test_api_key")

    # Verify storage created
    MockStorage.assert_called_once()

    # Verify session ID generated
    assert wrapper.capture.session_id.startswith("sdk_sess_")


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env_api_key"})
@patch("src.memory.sdk_wrapper.Anthropic")
@patch("src.memory.sdk_wrapper.MemoryStorage")
def test_sdk_wrapper_uses_env_api_key(MockStorage, MockAnthropic, tmp_path):
    """Test SDKWrapper uses ANTHROPIC_API_KEY from environment if not provided."""
    SDKWrapper(cwd=str(tmp_path))

    MockAnthropic.assert_called_once_with(api_key="env_api_key")


@patch.dict("os.environ", {}, clear=True)
@patch("src.memory.sdk_wrapper.Anthropic")
def test_sdk_wrapper_raises_without_api_key(MockAnthropic, tmp_path):
    """Test SDKWrapper raises ValueError if no API key available."""
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"):
        SDKWrapper(cwd=str(tmp_path))


def test_send_message_captures_conversation(
    mock_storage, mock_anthropic_client, tmp_path
):
    """Test send_message captures both user message and agent response (AC Phase1.3)."""
    with patch("src.memory.sdk_wrapper.Anthropic", return_value=mock_anthropic_client):
        wrapper = SDKWrapper(
            cwd=str(tmp_path), api_key="test_key", storage=mock_storage
        )

        result = wrapper.send_message(
            prompt="What is the capital of France?",
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
        )

    # Verify API called
    mock_anthropic_client.messages.create.assert_called_once()
    call_kwargs = mock_anthropic_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
    assert call_kwargs["max_tokens"] == 1024
    assert call_kwargs["messages"][0]["content"] == "What is the capital of France?"

    # Verify both messages captured (user + agent)
    assert mock_storage.store_memory.call_count == 2

    # Verify user message capture (first call)
    first_call = mock_storage.store_memory.call_args_list[0][1]
    assert first_call["content"] == "What is the capital of France?"
    assert first_call["memory_type"] == MemoryType.USER_MESSAGE

    # Verify agent response capture (second call)
    second_call = mock_storage.store_memory.call_args_list[1][1]
    assert second_call["content"] == "The capital of France is Paris."
    assert second_call["memory_type"] == MemoryType.AGENT_RESPONSE

    # Verify result structure
    assert result["content"] == "The capital of France is Paris."
    assert result["capture_status"]["user"] == "stored"
    assert result["capture_status"]["agent"] == "stored"
    assert "session_id" in result
    assert result["turn_number"] == 1


def test_send_message_extracts_text_from_blocks(mock_storage, tmp_path):
    """Test send_message correctly extracts text from multiple TextBlock content."""
    # Create mock client with multiple text blocks
    mock_client = Mock()
    mock_message = Mock(spec=Message)

    # Multiple text blocks
    block1 = Mock(spec=TextBlock)
    block1.text = "First part. "
    block2 = Mock(spec=TextBlock)
    block2.text = "Second part."

    mock_message.content = [block1, block2]
    mock_client.messages.create = Mock(return_value=mock_message)

    with patch("src.memory.sdk_wrapper.Anthropic", return_value=mock_client):
        wrapper = SDKWrapper(
            cwd=str(tmp_path), api_key="test_key", storage=mock_storage
        )

        result = wrapper.send_message(prompt="Test")

    # Verify concatenation
    assert result["content"] == "First part. Second part."

    # Verify agent response captured with full text
    agent_call = mock_storage.store_memory.call_args_list[1][1]
    assert agent_call["content"] == "First part. Second part."


def test_send_message_streaming(mock_storage, mock_stream_manager, tmp_path):
    """Test send_message_streaming captures conversation after streaming completes."""
    mock_client = Mock()
    mock_client.messages.stream = Mock(return_value=mock_stream_manager)

    with patch("src.memory.sdk_wrapper.Anthropic", return_value=mock_client):
        wrapper = SDKWrapper(
            cwd=str(tmp_path), api_key="test_key", storage=mock_storage
        )

        # Consume stream
        chunks = list(
            wrapper.send_message_streaming(
                prompt="What is the capital?", model="claude-3-5-sonnet-20241022"
            )
        )

    # Verify streaming output
    assert chunks == ["The ", "capital ", "is ", "Paris."]

    # Verify API called
    mock_client.messages.stream.assert_called_once()

    # Verify both messages captured
    assert mock_storage.store_memory.call_count == 2

    # Verify user message
    user_call = mock_storage.store_memory.call_args_list[0][1]
    assert user_call["content"] == "What is the capital?"
    assert user_call["memory_type"] == MemoryType.USER_MESSAGE

    # Verify agent response (reconstructed from stream)
    agent_call = mock_storage.store_memory.call_args_list[1][1]
    assert agent_call["content"] == "The capital is Paris."
    assert agent_call["memory_type"] == MemoryType.AGENT_RESPONSE

    # Verify capture status available
    assert wrapper.last_capture_status["user"] == "stored"
    assert wrapper.last_capture_status["agent"] == "stored"


def test_send_message_propagates_api_errors(mock_storage, tmp_path):
    """Test send_message propagates Anthropic API errors."""
    mock_client = Mock()
    mock_client.messages.create.side_effect = Exception("API Error")

    with patch("src.memory.sdk_wrapper.Anthropic", return_value=mock_client):
        wrapper = SDKWrapper(
            cwd=str(tmp_path), api_key="test_key", storage=mock_storage
        )

        with pytest.raises(Exception, match="API Error"):
            wrapper.send_message(prompt="Test")


def test_send_message_continues_on_capture_failure(
    mock_storage, mock_anthropic_client, tmp_path
):
    """Test send_message continues even if capture fails (graceful degradation)."""
    # Make storage fail
    mock_storage.store_memory.side_effect = Exception("Storage failed")

    with patch("src.memory.sdk_wrapper.Anthropic", return_value=mock_anthropic_client):
        wrapper = SDKWrapper(
            cwd=str(tmp_path), api_key="test_key", storage=mock_storage
        )

        # Should not raise - graceful degradation
        result = wrapper.send_message(prompt="Test question")

    # API call succeeded
    assert result["content"] == "The capital of France is Paris."

    # Capture failed gracefully
    assert result["capture_status"]["user"] == "failed"
    assert result["capture_status"]["agent"] == "failed"
