"""Unit tests for structured logging infrastructure.

Tests for AC 6.2.1 - AC 6.2.5:
- StructuredFormatter produces valid JSON
- Logger hierarchy configuration
- timed_operation context manager
- Environment variable control
"""

import json
import logging
import os
import time
from io import StringIO
from unittest.mock import patch

import pytest


class TestStructuredFormatter:
    """Tests for AC 6.2.1: Logger Configuration with StructuredFormatter."""

    def test_formatter_produces_valid_json(self):
        """Test that StructuredFormatter outputs valid JSON."""
        from src.memory.logging_config import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="bmad.memory.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="test_message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        # Should be valid JSON
        log_data = json.loads(output)
        assert isinstance(log_data, dict)

    def test_formatter_includes_required_fields(self):
        """Test that JSON output includes timestamp, level, logger, message."""
        from src.memory.logging_config import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="bmad.memory.storage",
            level=logging.INFO,
            pathname="storage.py",
            lineno=42,
            msg="memory_stored",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        # Required fields per AC 6.2.1
        assert "timestamp" in log_data
        assert "level" in log_data
        assert "logger" in log_data
        assert "message" in log_data

        assert log_data["level"] == "INFO"
        assert log_data["logger"] == "bmad.memory.storage"
        assert log_data["message"] == "memory_stored"

    def test_timestamp_is_utc_iso8601(self):
        """Test that timestamp is in UTC ISO 8601 format with Z suffix."""
        from src.memory.logging_config import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="bmad.memory",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        log_data = json.loads(output)

        timestamp = log_data["timestamp"]
        # Should end with 'Z' for UTC
        assert timestamp.endswith("Z")
        # Should be ISO 8601 format (basic validation)
        assert "T" in timestamp
        assert len(timestamp) > 20  # Minimum length for ISO format

    def test_extras_merged_into_context(self):
        """Test that extras dict is properly merged into context field."""
        from src.memory.logging_config import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="bmad.memory.capture",
            level=logging.INFO,
            pathname="capture.py",
            lineno=100,
            msg="memory_captured",
            args=(),
            exc_info=None,
        )
        # Add extras
        record.memory_id = "abc123"
        record.type = "implementation"
        record.duration_ms = 145

        output = formatter.format(record)
        log_data = json.loads(output)

        # Extras should be in context field per AC 6.2.1
        assert "context" in log_data
        context = log_data["context"]
        assert context["memory_id"] == "abc123"
        assert context["type"] == "implementation"
        assert context["duration_ms"] == 145


class TestLoggerHierarchy:
    """Tests for AC 6.2.2: Logger Hierarchy."""

    def test_configure_logging_creates_bmad_memory_logger(self):
        """Test that configure_logging sets up bmad.memory root logger."""
        from src.memory.logging_config import configure_logging

        configure_logging(level="INFO")

        logger = logging.getLogger("bmad.memory")
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0

    def test_child_loggers_inherit_configuration(self):
        """Test that child loggers inherit from bmad.memory root."""
        from src.memory.logging_config import configure_logging

        configure_logging(level="DEBUG")

        # Child loggers should inherit
        capture_logger = logging.getLogger("bmad.memory.capture")
        storage_logger = logging.getLogger("bmad.memory.storage")

        # Should inherit level from parent
        assert capture_logger.level == logging.NOTSET  # Inherits from parent
        assert storage_logger.level == logging.NOTSET

        # Should be able to log
        assert capture_logger.isEnabledFor(logging.DEBUG)

    def test_logger_propagation_disabled(self):
        """Test that bmad.memory logger does not propagate to root."""
        from src.memory.logging_config import configure_logging

        configure_logging()

        logger = logging.getLogger("bmad.memory")
        # Per AC, propagate should be False to avoid duplicate logs
        assert logger.propagate is False


class TestEnvironmentVariableControl:
    """Tests for AC 6.2.5: Environment Variable Control."""

    def test_log_level_from_environment(self):
        """Test that BMAD_LOG_LEVEL environment variable controls log level."""
        from src.memory.logging_config import configure_logging

        with patch.dict(os.environ, {"BMAD_LOG_LEVEL": "DEBUG"}):
            configure_logging()
            logger = logging.getLogger("bmad.memory")
            assert logger.level == logging.DEBUG

        with patch.dict(os.environ, {"BMAD_LOG_LEVEL": "ERROR"}):
            # Need to remove existing handlers to reconfigure
            logger = logging.getLogger("bmad.memory")
            logger.handlers.clear()
            configure_logging()
            assert logger.level == logging.ERROR

    def test_optional_text_format_for_development(self):
        """Test that BMAD_LOG_FORMAT=text produces human-readable output."""
        from src.memory.logging_config import configure_logging

        with patch.dict(os.environ, {"BMAD_LOG_FORMAT": "text"}):
            # Clear existing handlers
            logger = logging.getLogger("bmad.memory")
            logger.handlers.clear()

            configure_logging()

            # Capture log output
            stream = StringIO()
            # Replace handler stream
            logger.handlers[0].stream = stream

            test_logger = logging.getLogger("bmad.memory.test")
            test_logger.info("test message", extra={"key": "value"})

            output = stream.getvalue()
            # Text format should NOT be JSON
            with pytest.raises(json.JSONDecodeError):
                json.loads(output.strip())


class TestTimedOperation:
    """Tests for AC 6.2.3: Timing Context Manager."""

    def test_timed_operation_measures_duration(self):
        """Test that timed_operation accurately measures elapsed time."""
        from src.memory.timing import timed_operation

        logger = logging.getLogger("bmad.memory.test")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter

        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        with timed_operation("test_op", logger, extra={"test": "data"}):
            time.sleep(0.1)  # 100ms

        output = stream.getvalue()
        log_data = json.loads(output.strip())

        # Check duration is logged
        assert "context" in log_data
        assert "duration_ms" in log_data["context"]
        # Should be approximately 100ms (with tolerance)
        duration = log_data["context"]["duration_ms"]
        assert 90 < duration < 150  # 50ms tolerance

    def test_timed_operation_logs_on_success(self):
        """Test that successful operations log with status=success."""
        from src.memory.timing import timed_operation

        logger = logging.getLogger("bmad.memory.test2")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter

        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        with timed_operation("test_success", logger):
            pass  # Successful operation

        output = stream.getvalue()
        log_data = json.loads(output.strip())

        assert log_data["message"] == "test_success_completed"
        assert log_data["context"]["status"] == "success"

    def test_timed_operation_logs_on_failure_and_reraises(self):
        """Test that exceptions are logged with error details and re-raised."""
        from src.memory.timing import timed_operation

        logger = logging.getLogger("bmad.memory.test3")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter

        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)

        with pytest.raises(ValueError, match="test error"):
            with timed_operation("test_failure", logger):
                raise ValueError("test error")

        output = stream.getvalue()
        log_data = json.loads(output.strip())

        # Check error was logged
        assert log_data["level"] == "ERROR"
        assert log_data["message"] == "test_failure_failed"
        assert log_data["context"]["status"] == "failed"
        assert log_data["context"]["error"] == "test error"
        assert log_data["context"]["error_type"] == "ValueError"
        assert "duration_ms" in log_data["context"]

    def test_timed_operation_uses_perf_counter(self):
        """Test that timing uses time.perf_counter for precision."""
        from src.memory.timing import timed_operation

        logger = logging.getLogger("bmad.memory.test4")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter

        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Very short operation - perf_counter should capture sub-millisecond
        with timed_operation("fast_op", logger):
            x = 1 + 1  # Fast operation

        output = stream.getvalue()
        log_data = json.loads(output.strip())

        # Duration should be captured even if very small
        duration = log_data["context"]["duration_ms"]
        assert duration >= 0
        # Should be rounded to 2 decimal places per AC
        assert len(str(duration).split(".")[-1]) <= 2

    def test_timed_operation_merges_extra_context(self):
        """Test that extra context is properly merged with timing data."""
        from src.memory.timing import timed_operation

        logger = logging.getLogger("bmad.memory.test5")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        from src.memory.logging_config import StructuredFormatter

        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        extra_data = {"memory_id": "xyz789", "project": "test-project"}

        with timed_operation("store_op", logger, extra=extra_data):
            pass

        output = stream.getvalue()
        log_data = json.loads(output.strip())

        # Extra data should be merged
        context = log_data["context"]
        assert context["memory_id"] == "xyz789"
        assert context["project"] == "test-project"
        assert "duration_ms" in context
        assert context["status"] == "success"


class TestSensitiveDataRedaction:
    """Tests for sensitive data redaction in structured logging (Code Review H1 fix)."""

    def test_structured_formatter_redacts_sensitive_keys(self):
        """Sensitive keys should be redacted in log output."""
        from src.memory.logging_config import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="bmad.memory.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="test_message",
            args=(),
            exc_info=None,
        )
        # Add sensitive extras
        record.password = "secret123"
        record.api_key = "sk-12345"
        record.token = "bearer-token-xyz"
        record.authorization = "Basic abc123"
        record.normal_key = "visible_value"

        output = formatter.format(record)
        log_data = json.loads(output)

        # Sensitive keys should be redacted
        context = log_data["context"]
        assert context["password"] == "[REDACTED]"
        assert context["api_key"] == "[REDACTED]"
        assert context["token"] == "[REDACTED]"
        assert context["authorization"] == "[REDACTED]"
        # Normal keys should remain visible
        assert context["normal_key"] == "visible_value"

    def test_redaction_is_case_insensitive(self):
        """Sensitive key matching should be case-insensitive."""
        from src.memory.logging_config import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="bmad.memory.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="test_message",
            args=(),
            exc_info=None,
        )
        # Add mixed-case sensitive keys
        record.PASSWORD = "secret1"
        record.Api_Key = "secret2"
        record.TOKEN = "secret3"

        output = formatter.format(record)
        log_data = json.loads(output)

        context = log_data["context"]
        assert context["PASSWORD"] == "[REDACTED]"
        assert context["Api_Key"] == "[REDACTED]"
        assert context["TOKEN"] == "[REDACTED]"


class TestConfigureLoggingIdempotency:
    """Tests for configure_logging() idempotency (Code Review H2 fix)."""

    def test_configure_logging_is_idempotent(self):
        """Calling configure_logging() multiple times should not add duplicate handlers."""
        from src.memory.logging_config import configure_logging

        logger = logging.getLogger("bmad.memory")
        logger.handlers.clear()

        configure_logging()
        first_count = len(logger.handlers)

        configure_logging()  # Call again
        second_count = len(logger.handlers)

        configure_logging()  # Call a third time
        third_count = len(logger.handlers)

        # Should have exactly 1 handler, not accumulating
        assert first_count == 1
        assert second_count == 1
        assert third_count == 1

    def test_configure_logging_no_memory_leak(self):
        """Multiple imports should not cause handler accumulation."""
        from src.memory.logging_config import configure_logging

        logger = logging.getLogger("bmad.memory")
        logger.handlers.clear()

        # Simulate multiple imports/configurations
        for _ in range(10):
            configure_logging()

        # Should still have only 1 handler
        assert len(logger.handlers) == 1
