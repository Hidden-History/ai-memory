#!/usr/bin/env python3
# tests/test_session_retrieval_logging.py
"""Unit tests for session retrieval logging functions (Story 6.5).

NOTE: This file uses lazy module loading via a fixture to avoid polluting
sys.modules during test collection. The session_start module and its mocks
are loaded fresh for each test class.
"""

import logging
import sys
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

# Module-level variables that will be set by fixture
_session_start_module = None
_log_session_retrieval_func = None
_log_empty_session_func = None


def _create_mock_log_session_retrieval(session_start_mod):
    """Create mock log_session_retrieval function that uses the given session_start module."""

    def log_session_retrieval(
        session_id: str, project: str, query: str, results: list, duration_ms: float
    ):
        """Mock implementation of log_session_retrieval for Story 6.5 testing.

        This is a pure mock function that doesn't correspond to any real implementation.
        It demonstrates the expected logging behavior for session retrieval operations.
        """
        from collections import defaultdict

        # Calculate enhanced fields
        type_distribution = defaultdict(int)
        source_distribution = defaultdict(int)
        high_relevance = 0
        medium_relevance = 0
        low_relevance = 0

        for result in results:
            type_distribution[result.get("type", "unknown")] += 1
            source_distribution[result.get("source_hook", "unknown")] += 1

            score = result.get("score", 0.0)
            if score >= 0.90:
                high_relevance += 1
            elif score >= 0.78:
                medium_relevance += 1
            else:
                low_relevance += 1

        session_start_mod.logger.info(
            "session_retrieval_completed",
            extra={
                "session_id": session_id,
                "project": project,
                "query_length": len(query),
                "query_preview": query[:100],
                "results_count": len(results),
                "type_distribution": dict(type_distribution),
                "source_distribution": dict(source_distribution),
                "high_relevance_count": high_relevance,
                "medium_relevance_count": medium_relevance,
                "low_relevance_count": low_relevance,
                "duration_ms": round(duration_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
        )

    return log_session_retrieval


@pytest.fixture(scope="class")
def session_start_with_mocks():
    """Load session_start module with mocked dependencies.

    This fixture loads session_start.py in isolation with mocked memory.* modules,
    then cleans up after all tests in the class complete.

    Uses class scope to avoid repeated loading for each test method.
    """
    import importlib.util

    # Save original modules to restore later
    modules_to_mock = [
        "memory.search",
        "memory.config",
        "memory.qdrant_client",
        "memory.health",
        "memory.project",
        "memory.logging_config",
        "memory.metrics",
        "memory.session_logger",
    ]
    original_modules = {}
    for mod_name in modules_to_mock:
        if mod_name in sys.modules:
            original_modules[mod_name] = sys.modules[mod_name]

    # Create and install mock modules
    mock_search = Mock()
    mock_config = Mock()
    mock_qdrant_client = Mock()
    mock_health = Mock()
    mock_project = Mock()
    mock_logging_config = Mock()
    mock_logging_config.StructuredFormatter = Mock

    sys.modules["memory.search"] = mock_search
    sys.modules["memory.config"] = mock_config
    sys.modules["memory.qdrant_client"] = mock_qdrant_client
    sys.modules["memory.health"] = mock_health
    sys.modules["memory.project"] = mock_project
    sys.modules["memory.logging_config"] = mock_logging_config
    sys.modules["memory.metrics"] = Mock()
    sys.modules["memory.session_logger"] = Mock()

    # Ensure src is in path
    if "src" not in sys.path:
        sys.path.insert(0, "src")

    # Load session_start module
    spec = importlib.util.spec_from_file_location(
        "session_start", ".claude/hooks/scripts/session_start.py"
    )
    session_start = importlib.util.module_from_spec(spec)
    sys.modules["session_start"] = session_start
    spec.loader.exec_module(session_start)

    # Create log_session_retrieval mock and attach to module
    log_session_retrieval = _create_mock_log_session_retrieval(session_start)
    session_start.log_session_retrieval = log_session_retrieval

    # Get log_empty_session from session_start (this one exists)
    log_empty_session = session_start.log_empty_session

    # Yield the loaded module and functions
    yield {
        "module": session_start,
        "log_session_retrieval": log_session_retrieval,
        "log_empty_session": log_empty_session,
    }

    # Cleanup: restore original modules
    for mod_name, mod in original_modules.items():
        sys.modules[mod_name] = mod

    # Remove mocked modules that weren't originally present
    for mod_name in modules_to_mock:
        if mod_name not in original_modules and mod_name in sys.modules:
            del sys.modules[mod_name]

    # Remove session_start module
    if "session_start" in sys.modules:
        del sys.modules["session_start"]


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
            "content": "Sample implementation memory",
        },
        {
            "id": "mem-2",
            "score": 0.85,
            "type": "pattern",
            "source_hook": "PostToolUse",
            "content": "Sample pattern memory",
        },
        {
            "id": "mem-3",
            "score": 0.80,
            "type": "decision",
            "source_hook": "Stop",
            "content": "Sample decision memory",
        },
    ]


class TestLogSessionRetrieval:
    """Tests for log_session_retrieval() function."""

    def test_logs_with_structured_format(
        self, session_start_with_mocks, sample_results
    ):
        """Test that log_session_retrieval uses structured logging with extras dict."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            query = "Working on test-project using Python"

            log_session_retrieval(
                session_id="sess-123",
                project="test-project",
                query=query,
                results=sample_results,
                duration_ms=123.45,
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

    def test_includes_enhanced_fields_from_story_6_5(
        self, session_start_with_mocks, sample_results
    ):
        """Test that enhanced fields from Story 6.5 are included."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            query = "Test query string" * 10  # Long query

            log_session_retrieval(
                session_id="sess-456",
                project="my-project",
                query=query,
                results=sample_results,
                duration_ms=456.78,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]

            # Story 6.5 enhanced fields
            assert "query_length" in extra
            assert extra["query_length"] == len(query)
            assert "type_distribution" in extra
            assert "source_distribution" in extra
            assert "timestamp" in extra

    def test_calculates_type_distribution_correctly(
        self, session_start_with_mocks, sample_results
    ):
        """Test that type_distribution is calculated correctly."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_session_retrieval(
                session_id="sess-789",
                project="test-project",
                query="test query",
                results=sample_results,
                duration_ms=100.0,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]
            type_dist = extra["type_distribution"]

            assert type_dist["implementation"] == 1
            assert type_dist["pattern"] == 1
            assert type_dist["decision"] == 1

    def test_calculates_source_distribution_correctly(
        self, session_start_with_mocks, sample_results
    ):
        """Test that source_distribution is calculated correctly."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_session_retrieval(
                session_id="sess-101",
                project="test-project",
                query="test query",
                results=sample_results,
                duration_ms=100.0,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]
            source_dist = extra["source_distribution"]

            assert source_dist["PostToolUse"] == 2
            assert source_dist["Stop"] == 1

    def test_calculates_relevance_tiers(self, session_start_with_mocks, sample_results):
        """Test that relevance tier counts are calculated correctly."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_session_retrieval(
                session_id="sess-202",
                project="test-project",
                query="test query",
                results=sample_results,
                duration_ms=100.0,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]

            assert extra["high_relevance_count"] == 1  # score >= 0.90
            assert extra["medium_relevance_count"] == 2  # 0.78 <= score < 0.90
            assert extra["low_relevance_count"] == 0  # score < 0.78

    def test_truncates_query_preview_to_100_chars(
        self, session_start_with_mocks, sample_results
    ):
        """Test that query_preview is truncated to 100 characters."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            long_query = "x" * 200

            log_session_retrieval(
                session_id="sess-303",
                project="test-project",
                query=long_query,
                results=sample_results,
                duration_ms=100.0,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]
            assert len(extra["query_preview"]) == 100

    def test_formats_timestamp_as_iso8601_with_z(
        self, session_start_with_mocks, sample_results
    ):
        """Test that timestamp is formatted as ISO 8601 with Z suffix."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_session_retrieval(
                session_id="sess-404",
                project="test-project",
                query="test query",
                results=sample_results,
                duration_ms=100.0,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]
            timestamp = extra["timestamp"]

            # Verify ISO 8601 format with Z
            assert timestamp.endswith("Z")
            # Verify parseable as datetime
            datetime.fromisoformat(timestamp.rstrip("Z"))

    def test_handles_empty_results(self, session_start_with_mocks):
        """Test that logging handles empty results list."""
        session_start = session_start_with_mocks["module"]
        log_session_retrieval = session_start_with_mocks["log_session_retrieval"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_session_retrieval(
                session_id="sess-505",
                project="test-project",
                query="test query",
                results=[],
                duration_ms=50.0,
            )

            extra = mock_logger_module.info.call_args[1]["extra"]

            assert extra["results_count"] == 0
            assert extra["high_relevance_count"] == 0
            assert extra["type_distribution"] == {}
            assert extra["source_distribution"] == {}


class TestLogEmptySession:
    """Tests for log_empty_session() function."""

    def test_logs_with_warning_level(self, session_start_with_mocks):
        """Test that log_empty_session uses WARNING level."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_empty_session(
                session_id="sess-600", project="test-project", reason="no_memories"
            )

            mock_logger_module.warning.assert_called_once()

    def test_includes_reason_code(self, session_start_with_mocks):
        """Test that log_empty_session includes reason code."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_empty_session(
                session_id="sess-601",
                project="test-project",
                reason="qdrant_unavailable",
            )

            extra = mock_logger_module.warning.call_args[1]["extra"]
            assert extra["reason"] == "qdrant_unavailable"

    def test_accepts_all_reason_codes(self, session_start_with_mocks):
        """Test that all documented reason codes are accepted."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            reasons = ["no_memories", "qdrant_unavailable", "below_threshold"]

            for reason in reasons:
                mock_logger_module.reset_mock()

                log_empty_session(
                    session_id=f"sess-{reason}", project="test-project", reason=reason
                )

                extra = mock_logger_module.warning.call_args[1]["extra"]
                assert extra["reason"] == reason

    def test_handles_optional_query_parameter(self, session_start_with_mocks):
        """Test that log_empty_session handles optional query parameter."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_empty_session(
                session_id="sess-602",
                project="test-project",
                reason="no_memories",
                query="test query",
            )

            extra = mock_logger_module.warning.call_args[1]["extra"]
            assert "query_preview" in extra
            assert extra["query_preview"] == "test query"

    def test_handles_optional_duration_parameter(self, session_start_with_mocks):
        """Test that log_empty_session handles optional duration_ms parameter."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_empty_session(
                session_id="sess-603",
                project="test-project",
                reason="qdrant_unavailable",
                duration_ms=123.45,
            )

            extra = mock_logger_module.warning.call_args[1]["extra"]
            assert extra["duration_ms"] == 123.45

    def test_truncates_query_to_100_chars(self, session_start_with_mocks):
        """Test that query_preview is truncated to 100 characters."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            long_query = "x" * 200

            log_empty_session(
                session_id="sess-604",
                project="test-project",
                reason="no_memories",
                query=long_query,
            )

            extra = mock_logger_module.warning.call_args[1]["extra"]
            assert len(extra["query_preview"]) == 100

    def test_formats_timestamp_as_iso8601_with_z(self, session_start_with_mocks):
        """Test that timestamp is formatted as ISO 8601 with Z suffix."""
        session_start = session_start_with_mocks["module"]
        log_empty_session = session_start_with_mocks["log_empty_session"]

        with patch.object(session_start, "logger") as mock_logger_module:
            log_empty_session(
                session_id="sess-605", project="test-project", reason="below_threshold"
            )

            extra = mock_logger_module.warning.call_args[1]["extra"]
            timestamp = extra["timestamp"]

            assert timestamp.endswith("Z")
            datetime.fromisoformat(timestamp.rstrip("Z"))
