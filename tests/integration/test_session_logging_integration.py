#!/usr/bin/env python3
# tests/integration/test_session_logging_integration.py
"""Integration tests for session logging (Story 6.5)."""

import gzip
import json
import subprocess
import sys
import time

import pytest

# Add src to path
sys.path.insert(0, "src")

from memory.session_logger import log_to_session_file

pytestmark = pytest.mark.integration


@pytest.fixture
def temp_session_log(tmp_path, monkeypatch):
    """Create temporary session log path for testing."""
    import memory.session_logger as session_logger_module

    log_path = tmp_path / "sessions.jsonl"
    monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
    monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))

    # Clear any existing loggers
    import logging

    logging.getLogger("bmad.memory.sessions").handlers.clear()

    yield log_path

    # Cleanup
    logging.getLogger("bmad.memory.sessions").handlers.clear()


class TestSessionLogFileCreation:
    """Integration tests for session log file creation."""

    def test_creates_jsonl_file_on_first_log(self, temp_session_log):
        """Test that JSONL file is created on first log entry."""
        assert not temp_session_log.exists()

        log_to_session_file(
            {
                "session_id": "sess-integration-1",
                "project": "test-project",
                "results_count": 5,
            }
        )

        assert temp_session_log.exists()

    def test_appends_to_existing_jsonl_file(self, temp_session_log):
        """Test that subsequent logs append to existing file."""
        # First log
        log_to_session_file({"session_id": "sess-1"})

        # Second log
        log_to_session_file({"session_id": "sess-2"})

        # Verify both entries exist
        with open(temp_session_log) as f:
            lines = f.readlines()

        assert len(lines) == 2

    def test_each_line_is_valid_json(self, temp_session_log):
        """Test that each line in JSONL is valid JSON."""
        # Write multiple entries
        for i in range(5):
            log_to_session_file({"session_id": f"sess-{i}", "results_count": i})

        # Verify each line is parseable
        with open(temp_session_log) as f:
            for line in f:
                entry = json.loads(line.strip())
                assert "message" in entry


class TestSessionLogRotation:
    """Integration tests for session log rotation."""

    def test_rotates_at_max_bytes_threshold(self, tmp_path, monkeypatch):
        """Test that log rotates when exceeding maxBytes."""
        import memory.session_logger as session_logger_module

        log_path = tmp_path / "sessions.jsonl"

        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_MAX_BYTES", 2048)  # 2KB

        # Clear existing logger
        import logging

        logging.getLogger("bmad.memory.sessions").handlers.clear()

        # Write enough data to trigger rotation
        large_data = {"large_field": "x" * 500}
        for _i in range(20):  # ~10KB of data
            log_to_session_file(large_data)
            time.sleep(0.01)  # Small delay for rotation to occur

        # Check for rotated files
        rotated_files = list(tmp_path.glob("sessions.jsonl.*.gz"))
        assert len(rotated_files) > 0, "Expected rotated .gz files"

    def test_rotated_files_are_gzipped(self, tmp_path, monkeypatch):
        """Test that rotated files are compressed with gzip."""
        import memory.session_logger as session_logger_module

        log_path = tmp_path / "sessions.jsonl"

        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_MAX_BYTES", 1024)  # 1KB

        # Clear existing logger
        import logging

        logging.getLogger("bmad.memory.sessions").handlers.clear()

        # Trigger rotation
        large_data = {"large_field": "x" * 400}
        for _i in range(15):
            log_to_session_file(large_data)
            time.sleep(0.01)

        # Find rotated file
        rotated_files = list(tmp_path.glob("sessions.jsonl.*.gz"))
        if rotated_files:
            rotated_file = rotated_files[0]

            # Verify it's actually gzipped
            with gzip.open(rotated_file, "rt") as f:
                content = f.read()

            # Should contain JSON lines
            assert len(content) > 0
            assert "message" in content


class TestQuerySessionLogs:
    """Integration tests for query_session_logs.py script."""

    def test_query_script_reads_jsonl_file(self, temp_session_log):
        """Test that query script can read and parse JSONL file."""
        # Create test data
        for i in range(5):
            log_to_session_file(
                {
                    "session_id": f"sess-{i}",
                    "project": "test-project",
                    "results_count": i + 1,
                }
            )

        # Run query script
        result = subprocess.run(
            [
                sys.executable,
                "scripts/memory/query_session_logs.py",
                "--log-path",
                str(temp_session_log),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # Parse JSON output
        output = json.loads(result.stdout)
        assert len(output) == 5

    def test_query_script_filters_by_project(self, temp_session_log):
        """Test that query script filters by project name."""
        # Create test data with different projects
        log_to_session_file({"session_id": "sess-1", "project": "project-a"})
        log_to_session_file({"session_id": "sess-2", "project": "project-b"})
        log_to_session_file({"session_id": "sess-3", "project": "project-a"})

        # Query for project-a only
        result = subprocess.run(
            [
                sys.executable,
                "scripts/memory/query_session_logs.py",
                "--log-path",
                str(temp_session_log),
                "--project",
                "project-a",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output) == 2

    def test_query_script_filters_by_min_results(self, temp_session_log):
        """Test that query script filters by minimum result count."""
        # Create test data with varying result counts
        log_to_session_file({"session_id": "sess-1", "results_count": 2})
        log_to_session_file({"session_id": "sess-2", "results_count": 5})
        log_to_session_file({"session_id": "sess-3", "results_count": 10})

        # Query for min_results >= 5
        result = subprocess.run(
            [
                sys.executable,
                "scripts/memory/query_session_logs.py",
                "--log-path",
                str(temp_session_log),
                "--min-results",
                "5",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output) == 2

    def test_query_script_outputs_table_format(self, temp_session_log):
        """Test that query script outputs table format by default."""
        # Create test data
        log_to_session_file(
            {
                "session_id": "sess-table-test",
                "project": "test-project",
                "results_count": 3,
            }
        )

        # Run query script without format arg (defaults to table)
        result = subprocess.run(
            [
                sys.executable,
                "scripts/memory/query_session_logs.py",
                "--log-path",
                str(temp_session_log),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Session ID" in result.stdout
        assert "Total:" in result.stdout

    def test_query_script_handles_missing_file_gracefully(self, tmp_path):
        """Test that query script handles missing log file gracefully."""
        missing_path = tmp_path / "missing.jsonl"

        result = subprocess.run(
            [
                sys.executable,
                "scripts/memory/query_session_logs.py",
                "--log-path",
                str(missing_path),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "not found" in result.stdout


class TestSessionLoggerGracefulDegradation:
    """Integration tests for graceful degradation."""

    def test_disabled_logging_does_not_create_file(self, tmp_path, monkeypatch):
        """Test that SESSION_LOG_ENABLED=false prevents file creation."""
        import memory.session_logger as session_logger_module

        log_path = tmp_path / "sessions.jsonl"

        monkeypatch.setenv("SESSION_LOG_ENABLED", "false")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))

        log_to_session_file({"session_id": "sess-disabled"})

        # File should not be created
        assert not log_path.exists()

    def test_missing_directory_is_created_automatically(self, tmp_path, monkeypatch):
        """Test that missing log directory is created automatically."""
        import memory.session_logger as session_logger_module

        log_path = tmp_path / "nested" / "dir" / "sessions.jsonl"

        monkeypatch.setenv("SESSION_LOG_ENABLED", "true")
        monkeypatch.setattr(session_logger_module, "SESSION_LOG_PATH", str(log_path))

        # Clear existing logger
        import logging

        logging.getLogger("bmad.memory.sessions").handlers.clear()

        log_to_session_file({"session_id": "sess-create-dir"})

        # Directory and file should be created
        assert log_path.parent.exists()
        assert log_path.exists()
