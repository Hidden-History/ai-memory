#!/usr/bin/env python3
# tests/test_session_logger.py
"""Unit tests for session logger module (Story 6.5)."""

import os
import gzip
import json
import logging
from pathlib import Path
import pytest
import tempfile
import shutil

from memory.session_logger import (
    GzipRotatingFileHandler,
    get_session_logger,
    log_to_session_file,
    SESSION_LOG_PATH
)


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create temporary log directory for tests."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def session_log_path(temp_log_dir):
    """Temporary session log path."""
    return temp_log_dir / "sessions.jsonl"


class TestGzipRotatingFileHandler:
    """Tests for GzipRotatingFileHandler class."""

    def test_rotation_filename_adds_gz_extension(self, temp_log_dir):
        """Test that rotation_filename adds .gz extension."""
        handler = GzipRotatingFileHandler(
            filename=str(temp_log_dir / "test.log"),
            maxBytes=1024,
            backupCount=2
        )

        default_name = str(temp_log_dir / "test.log.1")
        rotated_name = handler.rotation_filename(default_name)

        assert rotated_name == default_name + ".gz"

    def test_rotate_compresses_file_with_gzip(self, temp_log_dir):
        """Test that rotate() compresses file using gzip."""
        source = temp_log_dir / "source.log"
        dest = temp_log_dir / "dest.log.gz"

        # Write test content
        source.write_text("Line 1\nLine 2\nLine 3\n")

        # Create handler and rotate
        handler = GzipRotatingFileHandler(
            filename=str(temp_log_dir / "test.log"),
            maxBytes=1024,
            backupCount=2
        )
        handler.rotate(str(source), str(dest))

        # Verify source deleted
        assert not source.exists()

        # Verify destination is gzipped
        assert dest.exists()
        with gzip.open(dest, 'rt') as f:
            content = f.read()
        assert content == "Line 1\nLine 2\nLine 3\n"

    def test_rotate_handles_missing_source_gracefully(self, temp_log_dir):
        """Test that rotate() handles missing source file gracefully."""
        source = temp_log_dir / "missing.log"
        dest = temp_log_dir / "dest.log.gz"

        handler = GzipRotatingFileHandler(
            filename=str(temp_log_dir / "test.log"),
            maxBytes=1024,
            backupCount=2
        )

        # Should not raise exception
        handler.rotate(str(source), str(dest))

        # Destination should not be created
        assert not dest.exists()


class TestGetSessionLogger:
    """Tests for get_session_logger() function."""

    def test_returns_none_when_disabled(self, monkeypatch):
        """Test that get_session_logger returns None when SESSION_LOG_ENABLED=false."""
        monkeypatch.setenv("SESSION_LOG_ENABLED", "false")
        logger = get_session_logger()
        assert logger is None

    def test_returns_logger_when_enabled(self, monkeypatch, session_log_path):
        """Test that get_session_logger returns logger when SESSION_LOG_ENABLED=true."""
        import memory.session_logger as session_logger_module
        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(session_log_path))

        logger = get_session_logger()
        assert logger is not None
        assert isinstance(logger, logging.Logger)
        assert logger.name == "bmad.memory.sessions"

    def test_creates_log_directory_if_not_exists(self, monkeypatch, temp_log_dir):
        """Test that get_session_logger creates log directory if it doesn't exist."""
        import memory.session_logger as session_logger_module
        log_path = temp_log_dir / "new_dir" / "sessions.jsonl"

        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))

        logger = get_session_logger()
        assert logger is not None
        assert log_path.parent.exists()

    def test_logger_does_not_propagate(self, monkeypatch, session_log_path):
        """Test that session logger does not propagate to root logger."""
        import memory.session_logger as session_logger_module
        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(session_log_path))

        logger = get_session_logger()
        assert logger.propagate is False

    def test_logger_reuses_existing_handlers(self, monkeypatch, session_log_path):
        """Test that get_session_logger reuses existing handlers."""
        import memory.session_logger as session_logger_module
        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(session_log_path))

        # Clear any existing logger
        logging.getLogger("bmad.memory.sessions").handlers.clear()

        logger1 = get_session_logger()
        handler_count_1 = len(logger1.handlers)

        logger2 = get_session_logger()
        handler_count_2 = len(logger2.handlers)

        # Should reuse existing handler
        assert handler_count_1 == handler_count_2
        assert logger1 is logger2


class TestLogToSessionFile:
    """Tests for log_to_session_file() function."""

    def test_logs_to_jsonl_file(self, monkeypatch, session_log_path):
        """Test that log_to_session_file writes JSONL to file."""
        import memory.session_logger as session_logger_module
        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(session_log_path))

        # Clear existing logger
        logging.getLogger("bmad.memory.sessions").handlers.clear()

        session_data = {
            "session_id": "sess-123",
            "project": "test-project",
            "results_count": 5,
            "duration_ms": 123.45
        }

        log_to_session_file(session_data)

        # Verify file exists and contains data
        assert session_log_path.exists()

        # Read and parse JSONL
        with open(session_log_path, 'r') as f:
            lines = f.readlines()

        assert len(lines) >= 1
        log_entry = json.loads(lines[0])

        # Verify context contains session data
        assert "message" in log_entry
        assert log_entry["message"] == "session_retrieval"

    def test_does_nothing_when_disabled(self, monkeypatch, session_log_path):
        """Test that log_to_session_file does nothing when SESSION_LOG_ENABLED=false."""
        monkeypatch.setenv("SESSION_LOG_ENABLED", "false")

        session_data = {
            "session_id": "sess-456",
            "project": "test-project"
        }

        log_to_session_file(session_data)

        # File should not be created
        assert not session_log_path.exists()

    def test_handles_empty_data(self, monkeypatch, session_log_path):
        """Test that log_to_session_file handles empty data dict."""
        import memory.session_logger as session_logger_module
        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(session_log_path))

        # Clear existing logger
        logging.getLogger("bmad.memory.sessions").handlers.clear()

        # Should not raise exception
        log_to_session_file({})

        assert session_log_path.exists()


class TestSessionLogRotation:
    """Integration tests for session log rotation."""

    def test_log_rotation_at_max_bytes(self, monkeypatch, temp_log_dir):
        """Test that log rotates at maxBytes threshold."""
        import memory.session_logger as session_logger_module
        log_path = temp_log_dir / "sessions.jsonl"

        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_MAX_BYTES", 1024)  # 1KB

        # Clear existing logger
        logging.getLogger("bmad.memory.sessions").handlers.clear()

        # Write enough data to trigger rotation
        large_data = {"large_field": "x" * 500}
        for i in range(10):  # ~5KB of data
            log_to_session_file(large_data)

        # Check for rotated file
        rotated_files = list(temp_log_dir.glob("sessions.jsonl.*.gz"))
        assert len(rotated_files) > 0

        # Verify rotated file is gzipped
        rotated_file = rotated_files[0]
        with gzip.open(rotated_file, 'rt') as f:
            content = f.read()
        assert len(content) > 0
