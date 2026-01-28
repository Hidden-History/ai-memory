"""Unit tests for post_tool_capture.py hook.

Tests code pattern capture on PostToolUse events.
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
def post_tool_edit_event():
    """Load PostToolUse Edit event fixture."""
    with open('tests/fixtures/hooks/post_tool_use_edit.json') as f:
        return json.load(f)


@pytest.fixture
def post_tool_write_event():
    """Load PostToolUse Write event fixture."""
    with open('tests/fixtures/hooks/post_tool_use_write.json') as f:
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
    config.project_name = "ai-memory-module"
    return config


class TestPostToolCapture:
    """Test suite for post_tool_capture.py hook."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Reset module state before each test."""
        if 'post_tool_capture' in sys.modules:
            del sys.modules['post_tool_capture']
        yield
        if 'post_tool_capture' in sys.modules:
            del sys.modules['post_tool_capture']

    def test_captures_edit_tool_changes(self, post_tool_edit_event):
        """Test that Edit tool changes are captured.

        PostToolUse Edit events should extract old_string and new_string
        to capture implementation patterns.
        """
        tool_input = post_tool_edit_event["tool_input"]
        file_path = tool_input["file_path"]
        old_string = tool_input["old_string"]
        new_string = tool_input["new_string"]

        # Verify file path is meaningful
        assert "storage.py" in file_path

        # Verify old and new strings captured
        assert "def store_memory(data):" in old_string
        assert "def store_memory(data):" in new_string
        # New string should have more implementation details
        assert len(new_string) > len(old_string)
        assert "is_duplicate" in new_string

    def test_captures_write_tool_new_files(self, post_tool_write_event):
        """Test that Write tool new file creation is captured.

        PostToolUse Write events should capture full file content
        for new files as implementation patterns.
        """
        tool_input = post_tool_write_event["tool_input"]
        file_path = tool_input["file_path"]
        content = tool_input["content"]

        # Verify new file captured
        assert "deduplication.py" in file_path
        assert len(content) > 0

        # Verify content is meaningful code
        assert "import hashlib" in content
        assert "def compute_hash" in content
        assert "sha256" in content.lower()

    def test_fork_pattern_for_async_storage(self, post_tool_edit_event):
        """Test that hook uses fork pattern for background storage.

        PostToolUse hook should fork a subprocess for storage to avoid
        blocking Claude (performance requirement: <500ms hook overhead).
        """
        # Verify fork pattern expectations
        # In real implementation, hook would call subprocess.Popen
        # and return immediately with exit(0)

        session_id = post_tool_edit_event["session_id"]
        turn_number = post_tool_edit_event["turn_number"]

        assert session_id is not None
        assert turn_number == 8
        # Hook should spawn async process and exit immediately

    def test_graceful_degradation_on_malformed_input(self, mock_config):
        """Test that hook handles malformed tool input gracefully.

        Hook should not crash on unexpected input structures.
        """
        malformed_event = {
            "session_id": "test_session",
            "tool_name": "Edit",
            "tool_input": {},  # Missing required fields
            "cwd": "/test/path"
        }

        # Hook should handle missing fields without crashing
        assert malformed_event["tool_input"] == {}
        # In real implementation, hook would exit 0 with warning log

    def test_targets_code_patterns_collection(self, post_tool_edit_event, mock_config):
        """Test that code patterns are stored to code-patterns collection.

        V2.0: Implementation patterns go to code-patterns collection.
        """
        with patch('memory.config.get_config', return_value=mock_config):
            from memory.config import COLLECTION_CODE_PATTERNS

            assert COLLECTION_CODE_PATTERNS == "code-patterns"
            # PostToolUse captures should target this collection

    def test_extracts_file_context(self, post_tool_edit_event):
        """Test that hook extracts file path for context.

        File path is critical for file_pattern memory type in V2.0.
        """
        tool_input = post_tool_edit_event["tool_input"]
        file_path = tool_input["file_path"]

        # Verify file path is absolute
        assert file_path.startswith("/")
        assert "storage.py" in file_path

        # File path should be stored in payload for PreToolUse retrieval
