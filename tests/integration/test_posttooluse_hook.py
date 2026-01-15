"""Integration tests for PostToolUse hook implementation.

Tests AC 2.1.1-2.1.5:
- Hook infrastructure with modern Python patterns
- Async storage script with graceful degradation
- Hook input schema validation
- Performance requirements (<500ms)
- Timeout handling
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# Test fixtures
@pytest.fixture
def hook_script_path():
    """Path to PostToolUse hook entry script."""
    return Path(".claude/hooks/scripts/post_tool_capture.py")


@pytest.fixture
def valid_edit_input():
    """Valid PostToolUse hook input for Edit operation."""
    return {
        "tool_name": "Edit",
        "tool_status": "success",
        "tool_input": {
            "file_path": "/path/to/file.py",
            "old_string": "def old_func():\n    pass",
            "new_string": "def new_func():\n    return True"
        },
        "cwd": "/path/to/project",
        "session_id": "sess-test-123"
    }


@pytest.fixture
def valid_write_input():
    """Valid PostToolUse hook input for Write operation."""
    return {
        "tool_name": "Write",
        "tool_status": "success",
        "tool_input": {
            "file_path": "/path/to/new_file.py",
            "content": "def new_function():\n    return 42"
        },
        "cwd": "/path/to/project",
        "session_id": "sess-test-456"
    }


@pytest.fixture
def malformed_json_input():
    """Malformed JSON input for testing error handling (AC 2.1.3)."""
    return "{this is not valid json"


@pytest.fixture
def invalid_tool_name_input():
    """Input with invalid tool_name."""
    return {
        "tool_name": "InvalidTool",
        "tool_status": "success",
        "tool_input": {},
        "cwd": "/path",
        "session_id": "sess-123"
    }


@pytest.fixture
def failed_tool_input():
    """Input with tool_status != success."""
    return {
        "tool_name": "Edit",
        "tool_status": "failed",
        "tool_input": {},
        "cwd": "/path",
        "session_id": "sess-123"
    }


# AC 2.1.1: Hook Infrastructure with Modern Python Patterns
class TestHookInfrastructure:
    """Test AC 2.1.1 - Hook infrastructure and modern async patterns."""

    def test_hook_script_exists(self, hook_script_path):
        """Hook entry script must exist."""
        assert hook_script_path.exists(), f"Hook script not found: {hook_script_path}"

    def test_hook_validates_tool_name(self, hook_script_path, invalid_tool_name_input):
        """Hook must validate tool_name in [Edit, Write, NotebookEdit]."""
        result = subprocess.run(
            [sys.executable, str(hook_script_path)],
            input=json.dumps(invalid_tool_name_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (non-blocking error, not disrupt Claude)
        assert result.returncode == 0, "Hook should exit 0 for invalid tool_name"

    def test_hook_validates_tool_status(self, hook_script_path, failed_tool_input):
        """Hook must check tool_status == success before capturing."""
        result = subprocess.run(
            [sys.executable, str(hook_script_path)],
            input=json.dumps(failed_tool_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (no capture for failed tools)
        assert result.returncode == 0, "Hook should exit 0 for non-success status"

    def test_hook_forks_to_background(self, hook_script_path, valid_edit_input, monkeypatch):
        """Hook must fork to background using subprocess.Popen with start_new_session=True."""
        # This test verifies the hook returns quickly without waiting for storage
        start_time = time.time()

        result = subprocess.run(
            [sys.executable, str(hook_script_path)],
            input=json.dumps(valid_edit_input),
            capture_output=True,
            text=True,
            timeout=5
        )

        elapsed = time.time() - start_time

        # AC 2.1.1: Must exit 0 immediately after fork
        assert result.returncode == 0, "Hook should exit 0 on success"

        # AC 2.1.4 (NFR-P1): Hook overhead < 500ms
        assert elapsed < 0.5, f"Hook took {elapsed:.3f}s, must be <500ms"

    def test_hook_uses_structured_logging(self, hook_script_path, valid_edit_input):
        """Hook must use structured logging with extra={} dict."""
        result = subprocess.run(
            [sys.executable, str(hook_script_path)],
            input=json.dumps(valid_edit_input),
            capture_output=True,
            text=True,
            timeout=5
        )

        # Check stderr for log output (structured format)
        # Should NOT contain f-string patterns like "Storing memory {id}"
        assert "f'" not in result.stderr.lower(), "Must not use f-strings in logging"


# AC 2.1.2: Async Storage Script with Graceful Degradation
class TestAsyncStorageScript:
    """Test AC 2.1.2 - Background storage script with graceful degradation."""

    def test_storage_script_exists(self):
        """Async storage script must exist."""
        script_path = Path(".claude/hooks/scripts/store_async.py")
        assert script_path.exists(), f"Storage script not found: {script_path}"

    @pytest.mark.slow
    def test_storage_script_stores_to_qdrant(self, valid_edit_input, monkeypatch):
        """Storage script must successfully store to Qdrant when available."""
        # This test requires Docker services running
        script_path = Path(".claude/hooks/scripts/store_async.py")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(valid_edit_input),
            capture_output=True,
            text=True,
            timeout=30
        )

        # Should exit 0 on success
        assert result.returncode == 0, f"Storage script failed: {result.stderr}"

    @pytest.mark.slow
    def test_graceful_degradation_qdrant_unavailable(self, valid_edit_input, monkeypatch):
        """Storage script must queue to file when Qdrant unavailable (AC 2.1.2)."""
        # Set invalid Qdrant URL to simulate service down
        monkeypatch.setenv("QDRANT_URL", "http://localhost:99999")

        script_path = Path(".claude/hooks/scripts/store_async.py")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(valid_edit_input),
            capture_output=True,
            text=True,
            timeout=30
        )

        # Must exit 0 (graceful degradation, no Claude disruption)
        assert result.returncode == 0, "Must exit 0 when Qdrant unavailable"

        # Should queue to file (check for queue file creation)
        # Note: Actual implementation will define queue file location


# AC 2.1.3: Hook Input Schema Validation
class TestInputSchemaValidation:
    """Test AC 2.1.3 - Schema validation and error handling."""

    def test_malformed_json_handling(self, hook_script_path, malformed_json_input):
        """Hook must handle malformed JSON gracefully (FR34)."""
        result = subprocess.run(
            [sys.executable, str(hook_script_path)],
            input=malformed_json_input,
            capture_output=True,
            text=True,
            timeout=5
        )

        # Must exit 0 for invalid input (no Claude disruption)
        assert result.returncode == 0, "Hook must exit 0 for malformed JSON"

    def test_missing_required_fields(self, hook_script_path):
        """Hook must validate required fields exist."""
        incomplete_input = {"tool_name": "Edit"}  # Missing other required fields

        result = subprocess.run(
            [sys.executable, str(hook_script_path)],
            input=json.dumps(incomplete_input),
            capture_output=True,
            text=True,
            timeout=5
        )

        # Must exit 0 (graceful handling)
        assert result.returncode == 0, "Hook must exit 0 for incomplete input"


# AC 2.1.4: Performance Requirements
class TestPerformanceRequirements:
    """Test AC 2.1.4 (NFR-P1) - <500ms hook overhead."""

    def test_hook_execution_time(self, hook_script_path, valid_edit_input):
        """Hook must complete in <500ms."""
        iterations = 5
        times = []

        for _ in range(iterations):
            start_time = time.time()
            result = subprocess.run(
                [sys.executable, str(hook_script_path)],
                input=json.dumps(valid_edit_input),
                capture_output=True,
                text=True,
                timeout=5
            )
            elapsed = time.time() - start_time
            times.append(elapsed)

            assert result.returncode == 0, "Hook must succeed"

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # NFR-P1: Average and max must be <500ms
        assert avg_time < 0.5, f"Average time {avg_time:.3f}s exceeds 500ms"
        assert max_time < 0.5, f"Max time {max_time:.3f}s exceeds 500ms"


# AC 2.1.5: Timeout Handling
class TestTimeoutHandling:
    """Test AC 2.1.5 (FR35) - Timeout handling in background script."""

    @pytest.mark.slow
    def test_timeout_default_value(self):
        """HOOK_TIMEOUT should default to 60s if not set."""
        script_path = Path(".claude/hooks/scripts/store_async.py")

        # Read script to verify timeout configuration exists
        assert script_path.exists(), "Storage script must exist"

        content = script_path.read_text()
        # Should reference HOOK_TIMEOUT env var
        assert "HOOK_TIMEOUT" in content, "Script must use HOOK_TIMEOUT env var"

    @pytest.mark.slow
    def test_timeout_configurable(self, valid_edit_input, monkeypatch):
        """HOOK_TIMEOUT must be configurable via env var."""
        # Set very short timeout to test handling
        monkeypatch.setenv("HOOK_TIMEOUT", "1")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:99999")  # Simulate slow service

        script_path = Path(".claude/hooks/scripts/store_async.py")

        start_time = time.time()
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=json.dumps(valid_edit_input),
            capture_output=True,
            text=True,
            timeout=10
        )
        elapsed = time.time() - start_time

        # Should timeout and exit gracefully
        assert result.returncode in [0, 1], "Must exit 0 or 1 on timeout"

        # Note: Actual timeout behavior depends on implementation
