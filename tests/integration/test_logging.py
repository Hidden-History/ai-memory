"""Integration tests for structured logging with real operations.

Tests AC 6.2.4: Log Output Examples
Verifies that actual operations produce valid JSON logs with correct schema.
"""

import json
import logging
from io import StringIO

import pytest

from src.memory.logging_config import StructuredFormatter
from src.memory.timing import timed_operation


class TestLogOutputFormat:
    """Tests for AC 6.2.4: Verify log output format in real operations."""

    def test_successful_operation_log_format(self):
        """Test that successful operations produce valid JSON with correct schema."""
        # Setup logger with structured formatting
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Simulate a successful capture operation
        logger.info(
            "memory_stored",
            extra={
                "memory_id": "abc123",
                "type": "implementation",
                "project": "my-project",
                "duration_ms": 145,
            },
        )

        output = stream.getvalue().strip()

        # Parse JSON
        log_data = json.loads(output)

        # Verify schema per AC 6.2.4
        assert "timestamp" in log_data
        assert "level" in log_data
        assert "logger" in log_data
        assert "message" in log_data
        assert "context" in log_data

        # Verify values
        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "bmad.memory.test_integration"
        assert log_data["message"] == "memory_stored"

        # Verify context fields
        context = log_data["context"]
        assert context["memory_id"] == "abc123"
        assert context["type"] == "implementation"
        assert context["project"] == "my-project"
        assert context["duration_ms"] == 145

    def test_failed_operation_log_format(self):
        """Test that failed operations produce error logs with proper schema."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration2")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        # Simulate a failed retrieval
        logger.error(
            "retrieval_failed",
            extra={
                "error": "Connection refused",
                "error_code": "QDRANT_UNAVAILABLE",
                "duration_ms": 2034,
            },
        )

        output = stream.getvalue().strip()
        log_data = json.loads(output)

        # Verify error log structure per AC 6.2.4
        assert log_data["level"] == "ERROR"
        assert log_data["message"] == "retrieval_failed"

        context = log_data["context"]
        assert context["error"] == "Connection refused"
        assert context["error_code"] == "QDRANT_UNAVAILABLE"
        assert context["duration_ms"] == 2034

    def test_hook_timing_log_format(self):
        """Test that hook timing logs match expected format per AC 6.2.4."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration3")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Use timed_operation to simulate hook execution
        with timed_operation("hook", logger, extra={"hook_type": "PostToolUse"}):
            pass  # Simulated hook work

        output = stream.getvalue().strip()
        log_data = json.loads(output)

        # Verify hook log format per AC 6.2.4
        assert log_data["message"] == "hook_completed"

        context = log_data["context"]
        assert context["hook_type"] == "PostToolUse"
        assert "duration_ms" in context
        assert context["status"] == "success"

    def test_timestamp_iso8601_utc_format(self):
        """Test that timestamps are in ISO 8601 UTC format with Z suffix."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration4")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("test_event")

        output = stream.getvalue().strip()
        log_data = json.loads(output)

        timestamp = log_data["timestamp"]

        # Must end with 'Z' for UTC
        assert timestamp.endswith("Z"), f"Timestamp must end with 'Z': {timestamp}"

        # Must contain 'T' separator (ISO 8601)
        assert "T" in timestamp, f"Timestamp must contain 'T' separator: {timestamp}"

        # Basic format check (YYYY-MM-DDTHH:MM:SS.sssZ)
        assert len(timestamp) >= 20, f"Timestamp too short: {timestamp}"

    def test_logger_hierarchy_in_output(self):
        """Test that logger names follow bmad.memory hierarchy in output."""
        test_loggers = [
            "bmad.memory",
            "bmad.memory.capture",
            "bmad.memory.retrieve",
            "bmad.memory.storage",
            "bmad.memory.embed",
            "bmad.memory.queue",
            "bmad.memory.hooks",
        ]

        for logger_name in test_loggers:
            stream = StringIO()
            handler = logging.StreamHandler(stream)
            handler.setFormatter(StructuredFormatter())

            logger = logging.getLogger(logger_name)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

            logger.info("test_hierarchy")

            output = stream.getvalue().strip()
            log_data = json.loads(output)

            # Verify logger name in output
            assert log_data["logger"] == logger_name

            # Clean up handler
            logger.removeHandler(handler)

    def test_multiple_log_entries_valid_json(self):
        """Test that multiple log entries are each valid JSON on separate lines."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration5")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Log multiple events
        logger.info("event_1", extra={"id": 1})
        logger.info("event_2", extra={"id": 2})
        logger.info("event_3", extra={"id": 3})

        output = stream.getvalue()
        lines = output.strip().split("\n")

        # Should have 3 lines
        assert len(lines) == 3

        # Each line should be valid JSON
        for i, line in enumerate(lines, 1):
            log_data = json.loads(line)
            assert log_data["message"] == f"event_{i}"
            assert log_data["context"]["id"] == i

    def test_timing_accuracy(self):
        """Test that timing measurements are accurate within tolerance."""
        import time

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration6")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Time a 100ms operation
        with timed_operation("test_timing", logger):
            time.sleep(0.1)

        output = stream.getvalue().strip()
        log_data = json.loads(output)

        duration = log_data["context"]["duration_ms"]

        # Should be approximately 100ms (within 50ms tolerance)
        assert 90 < duration < 150, f"Duration {duration}ms outside expected range"

    def test_exception_logging_format(self):
        """Test that exceptions are logged with proper error context."""
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(StructuredFormatter())

        logger = logging.getLogger("bmad.memory.test_integration7")
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        # Simulate an operation that fails
        with pytest.raises(ValueError), timed_operation(
            "failing_op", logger, extra={"attempt": 1}
        ):
            raise ValueError("Test error")

        output = stream.getvalue().strip()
        log_data = json.loads(output)

        # Verify error log structure
        assert log_data["level"] == "ERROR"
        assert log_data["message"] == "failing_op_failed"

        context = log_data["context"]
        assert context["status"] == "failed"
        assert context["error"] == "Test error"
        assert context["error_type"] == "ValueError"
        assert "duration_ms" in context
        assert context["attempt"] == 1
