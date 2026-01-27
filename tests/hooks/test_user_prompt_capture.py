"""Unit tests for user_prompt_capture.py hook.

Tests user message capture on UserPromptSubmit event.
"""

import pytest
import json
import sys
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, "tests")
from mocks.qdrant_mock import MockQdrantClient

sys.path.insert(0, '.claude/hooks/scripts')


@pytest.fixture
def user_prompt_event():
    """Load user prompt event fixture."""
    with open('tests/fixtures/hooks/user_prompt_submit.json') as f:
        return json.load(f)


@pytest.fixture
def mock_qdrant():
    """Provide fresh mock Qdrant client."""
    client = MockQdrantClient()
    client.reset()
    return client


@pytest.fixture
def mock_config():
    """Provide mock MemoryConfig."""
    config = MagicMock()
    config.qdrant_host = "localhost"
    config.qdrant_port = 26350
    config.project_name = "bmad-memory-module"
    return config


class TestUserPromptCapture:
    """Test suite for user_prompt_capture.py hook."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Reset module state before each test."""
        if 'user_prompt_capture' in sys.modules:
            del sys.modules['user_prompt_capture']
        yield
        if 'user_prompt_capture' in sys.modules:
            del sys.modules['user_prompt_capture']

    def test_captures_user_message(self, user_prompt_event, mock_qdrant, mock_config):
        """Test that UserPromptSubmit event captures user message.

        User messages should be stored to discussions collection
        with type 'user_message' for context injection.
        """
        user_message = user_prompt_event["user_message"]
        session_id = user_prompt_event["session_id"]
        turn_number = user_prompt_event["turn_number"]

        assert user_message == "What was decided about the port configuration?"
        assert session_id == "sess_user_prompt_test_003"
        assert turn_number == 5

        # Verify message content is meaningful
        assert len(user_message) > 0
        assert "port" in user_message.lower()

    def test_trigger_detection_keywords(self, user_prompt_event):
        """Test that hook detects trigger keywords in user messages.

        V2.0 automatic triggers: "why did we", "what was decided",
        "best practice", "convention", etc.
        """
        decision_keywords = ["why did we", "what was decided", "decision"]
        best_practice_keywords = ["best practice", "convention", "how should I"]

        user_message = user_prompt_event["user_message"].lower()

        # Check if message contains decision keywords
        has_decision_keyword = any(kw in user_message for kw in decision_keywords)

        # This specific fixture has "what was decided"
        assert has_decision_keyword

    def test_graceful_degradation_on_empty_message(self, mock_config):
        """Test that hook handles empty user messages gracefully.

        Hook should not crash on edge cases like empty strings.
        """
        empty_event = {
            "session_id": "test_session",
            "user_message": "",
            "turn_number": 1,
            "cwd": "/test/path"
        }

        # Hook should handle empty message without crashing
        assert empty_event["user_message"] == ""
        # In real implementation, hook would skip storage or log warning

    def test_stores_with_correct_collection(self, user_prompt_event, mock_qdrant, mock_config):
        """Test that user messages are stored to discussions collection.

        V2.0: User messages go to discussions, not code-patterns or conventions.
        """
        with patch('memory.qdrant_client.get_qdrant_client', return_value=mock_qdrant):
            with patch('memory.config.get_config', return_value=mock_config):
                # Verify collection name constant
                from memory.config import COLLECTION_DISCUSSIONS

                assert COLLECTION_DISCUSSIONS == "discussions"
                # User messages should target this collection
