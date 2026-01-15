#!/usr/bin/env python3
# tests/test_session_retrieval_logging.py
"""Unit tests for session retrieval logging functions (Story 6.5).

NOTE: This file carefully mocks memory modules to test session_start.py
without polluting the global sys.modules for other test files.
"""

import sys
import logging
import atexit
from datetime import datetime
from unittest.mock import Mock, patch, call
import pytest

# Mock the memory imports before importing session_start
sys.path.insert(0, "src")

# Save original modules to restore later (prevents pollution of other tests)
_original_modules = {}
_modules_to_mock = [
    'memory.search', 'memory.config', 'memory.qdrant_client',
    'memory.health', 'memory.project', 'memory.logging_config',
    'memory.metrics', 'memory.session_logger'
]
for mod_name in _modules_to_mock:
    if mod_name in sys.modules:
        _original_modules[mod_name] = sys.modules[mod_name]

# Create mock modules
mock_search = Mock()
mock_config = Mock()
mock_qdrant_client = Mock()
mock_health = Mock()
mock_project = Mock()
mock_logging_config = Mock()

sys.modules['memory.search'] = mock_search
sys.modules['memory.config'] = mock_config
sys.modules['memory.qdrant_client'] = mock_qdrant_client
sys.modules['memory.health'] = mock_health
sys.modules['memory.project'] = mock_project
sys.modules['memory.logging_config'] = mock_logging_config
sys.modules['memory.metrics'] = Mock()
sys.modules['memory.session_logger'] = Mock()

# Mock StructuredFormatter
mock_logging_config.StructuredFormatter = Mock


def _restore_original_modules():
    """Restore original modules that were saved before mocking."""
    for mod_name, mod in _original_modules.items():
        sys.modules[mod_name] = mod
    # Remove mocked modules that weren't originally present
    for mod_name in _modules_to_mock:
        if mod_name not in _original_modules and mod_name in sys.modules:
            del sys.modules[mod_name]


# Register cleanup to run when Python exits
atexit.register(_restore_original_modules)

# Now import the functions to test
import importlib.util
spec = importlib.util.spec_from_file_location(
    "session_start",
    ".claude/hooks/scripts/session_start.py"
)
session_start = importlib.util.module_from_spec(spec)
sys.modules['session_start'] = session_start
spec.loader.exec_module(session_start)

log_session_retrieval = session_start.log_session_retrieval
log_empty_session = session_start.log_empty_session


@pytest.fixture
def mock_logger():
    """Mock logger for testing log calls."""
    return Mock(spec=logging.Logger)


@pytest.fixture
def sample_results():
    """Sample search results for testing."""
    return [
        {
            "id": "mem-1",
            "score": 0.95,
            "type": "implementation",
            "source_hook": "PostToolUse",
            "content": "Sample implementation memory"
        },
        {
            "id": "mem-2",
            "score": 0.85,
            "type": "pattern",
            "source_hook": "PostToolUse",
            "content": "Sample pattern memory"
        },
        {
            "id": "mem-3",
            "score": 0.80,
            "type": "decision",
            "source_hook": "Stop",
            "content": "Sample decision memory"
        }
    ]


class TestLogSessionRetrieval:
    """Tests for log_session_retrieval() function."""

    @patch('session_start.logger')
    def test_logs_with_structured_format(self, mock_logger_module, sample_results):
        """Test that log_session_retrieval uses structured logging with extras dict."""
        query = "Working on test-project using Python"

        log_session_retrieval(
            session_id="sess-123",
            project="test-project",
            query=query,
            results=sample_results,
            duration_ms=123.45
        )

        # Verify logger.info was called with message and extras
        mock_logger_module.info.assert_called_once()
        call_args = mock_logger_module.info.call_args

        assert call_args[0][0] == "session_retrieval_completed"
        assert "extra" in call_args[1]

        extra = call_args[1]["extra"]
        assert extra["session_id"] == "sess-123"
        assert extra["project"] == "test-project"
        assert extra["results_count"] == 3

    @patch('session_start.logger')
    def test_includes_enhanced_fields_from_story_6_5(self, mock_logger_module, sample_results):
        """Test that enhanced fields from Story 6.5 are included."""
        query = "Test query string" * 10  # Long query

        log_session_retrieval(
            session_id="sess-456",
            project="my-project",
            query=query,
            results=sample_results,
            duration_ms=456.78
        )

        extra = mock_logger_module.info.call_args[1]["extra"]

        # Story 6.5 enhanced fields
        assert "query_length" in extra
        assert extra["query_length"] == len(query)
        assert "type_distribution" in extra
        assert "source_distribution" in extra
        assert "timestamp" in extra

    @patch('session_start.logger')
    def test_calculates_type_distribution_correctly(self, mock_logger_module, sample_results):
        """Test that type_distribution is calculated correctly."""
        log_session_retrieval(
            session_id="sess-789",
            project="test-project",
            query="test query",
            results=sample_results,
            duration_ms=100.0
        )

        extra = mock_logger_module.info.call_args[1]["extra"]
        type_dist = extra["type_distribution"]

        assert type_dist["implementation"] == 1
        assert type_dist["pattern"] == 1
        assert type_dist["decision"] == 1

    @patch('session_start.logger')
    def test_calculates_source_distribution_correctly(self, mock_logger_module, sample_results):
        """Test that source_distribution is calculated correctly."""
        log_session_retrieval(
            session_id="sess-101",
            project="test-project",
            query="test query",
            results=sample_results,
            duration_ms=100.0
        )

        extra = mock_logger_module.info.call_args[1]["extra"]
        source_dist = extra["source_distribution"]

        assert source_dist["PostToolUse"] == 2
        assert source_dist["Stop"] == 1

    @patch('session_start.logger')
    def test_calculates_relevance_tiers(self, mock_logger_module, sample_results):
        """Test that relevance tier counts are calculated correctly."""
        log_session_retrieval(
            session_id="sess-202",
            project="test-project",
            query="test query",
            results=sample_results,
            duration_ms=100.0
        )

        extra = mock_logger_module.info.call_args[1]["extra"]

        assert extra["high_relevance_count"] == 1  # score >= 0.90
        assert extra["medium_relevance_count"] == 2  # 0.78 <= score < 0.90
        assert extra["low_relevance_count"] == 0  # score < 0.78

    @patch('session_start.logger')
    def test_truncates_query_preview_to_100_chars(self, mock_logger_module, sample_results):
        """Test that query_preview is truncated to 100 characters."""
        long_query = "x" * 200

        log_session_retrieval(
            session_id="sess-303",
            project="test-project",
            query=long_query,
            results=sample_results,
            duration_ms=100.0
        )

        extra = mock_logger_module.info.call_args[1]["extra"]
        assert len(extra["query_preview"]) == 100

    @patch('session_start.logger')
    def test_formats_timestamp_as_iso8601_with_z(self, mock_logger_module, sample_results):
        """Test that timestamp is formatted as ISO 8601 with Z suffix."""
        log_session_retrieval(
            session_id="sess-404",
            project="test-project",
            query="test query",
            results=sample_results,
            duration_ms=100.0
        )

        extra = mock_logger_module.info.call_args[1]["extra"]
        timestamp = extra["timestamp"]

        # Verify ISO 8601 format with Z
        assert timestamp.endswith("Z")
        # Verify parseable as datetime
        datetime.fromisoformat(timestamp.rstrip("Z"))

    @patch('session_start.logger')
    def test_handles_empty_results(self, mock_logger_module):
        """Test that logging handles empty results list."""
        log_session_retrieval(
            session_id="sess-505",
            project="test-project",
            query="test query",
            results=[],
            duration_ms=50.0
        )

        extra = mock_logger_module.info.call_args[1]["extra"]

        assert extra["results_count"] == 0
        assert extra["high_relevance_count"] == 0
        assert extra["type_distribution"] == {}
        assert extra["source_distribution"] == {}


class TestLogEmptySession:
    """Tests for log_empty_session() function."""

    @patch('session_start.logger')
    def test_logs_with_warning_level(self, mock_logger_module):
        """Test that log_empty_session uses WARNING level."""
        log_empty_session(
            session_id="sess-600",
            project="test-project",
            reason="no_memories"
        )

        mock_logger_module.warning.assert_called_once()

    @patch('session_start.logger')
    def test_includes_reason_code(self, mock_logger_module):
        """Test that log_empty_session includes reason code."""
        log_empty_session(
            session_id="sess-601",
            project="test-project",
            reason="qdrant_unavailable"
        )

        extra = mock_logger_module.warning.call_args[1]["extra"]
        assert extra["reason"] == "qdrant_unavailable"

    @patch('session_start.logger')
    def test_accepts_all_reason_codes(self, mock_logger_module):
        """Test that all documented reason codes are accepted."""
        reasons = ["no_memories", "qdrant_unavailable", "below_threshold"]

        for reason in reasons:
            mock_logger_module.reset_mock()

            log_empty_session(
                session_id=f"sess-{reason}",
                project="test-project",
                reason=reason
            )

            extra = mock_logger_module.warning.call_args[1]["extra"]
            assert extra["reason"] == reason

    @patch('session_start.logger')
    def test_handles_optional_query_parameter(self, mock_logger_module):
        """Test that log_empty_session handles optional query parameter."""
        log_empty_session(
            session_id="sess-602",
            project="test-project",
            reason="no_memories",
            query="test query"
        )

        extra = mock_logger_module.warning.call_args[1]["extra"]
        assert "query_preview" in extra
        assert extra["query_preview"] == "test query"

    @patch('session_start.logger')
    def test_handles_optional_duration_parameter(self, mock_logger_module):
        """Test that log_empty_session handles optional duration_ms parameter."""
        log_empty_session(
            session_id="sess-603",
            project="test-project",
            reason="qdrant_unavailable",
            duration_ms=123.45
        )

        extra = mock_logger_module.warning.call_args[1]["extra"]
        assert extra["duration_ms"] == 123.45

    @patch('session_start.logger')
    def test_truncates_query_to_100_chars(self, mock_logger_module):
        """Test that query_preview is truncated to 100 characters."""
        long_query = "x" * 200

        log_empty_session(
            session_id="sess-604",
            project="test-project",
            reason="no_memories",
            query=long_query
        )

        extra = mock_logger_module.warning.call_args[1]["extra"]
        assert len(extra["query_preview"]) == 100

    @patch('session_start.logger')
    def test_formats_timestamp_as_iso8601_with_z(self, mock_logger_module):
        """Test that timestamp is formatted as ISO 8601 with Z suffix."""
        log_empty_session(
            session_id="sess-605",
            project="test-project",
            reason="below_threshold"
        )

        extra = mock_logger_module.warning.call_args[1]["extra"]
        timestamp = extra["timestamp"]

        assert timestamp.endswith("Z")
        datetime.fromisoformat(timestamp.rstrip("Z"))
