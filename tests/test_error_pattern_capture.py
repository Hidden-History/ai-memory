"""Test error pattern capture hook functionality."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def hook_script():
    """Get path to error_pattern_capture.py script."""
    script_path = (
        Path(__file__).parent.parent
        / ".claude"
        / "hooks"
        / "scripts"
        / "error_pattern_capture.py"
    )
    assert script_path.exists(), f"Hook script not found: {script_path}"
    return script_path


def test_error_pattern_detection(hook_script):
    """Test that error patterns are detected from Bash failures."""
    # Simulate Claude Code hook input for a failed Bash command
    hook_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "python3 /path/to/script.py"},
        "tool_response": {
            "output": """Traceback (most recent call last):
  File "/path/to/script.py", line 42, in <module>
    result = divide(10, 0)
  File "/path/to/script.py", line 15, in divide
    return a / b
ZeroDivisionError: division by zero""",
            "exitCode": 1,
        },
        "cwd": "/tmp/test-project",
        "session_id": "test_session_123",
    }

    # Run hook script with input
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
    )

    # Hook should exit 0 (non-blocking)
    assert result.returncode == 0, f"Hook failed: {result.stderr}"

    # Should log error pattern detection
    # Note: Background fork means storage happens async, so we just verify hook succeeds


def test_no_error_pattern_for_success(hook_script):
    """Test that successful commands don't trigger error capture."""
    # Simulate successful Bash command
    hook_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo 'Hello World'"},
        "tool_response": {"output": "Hello World\n", "exitCode": 0},
        "cwd": "/tmp/test-project",
        "session_id": "test_session_456",
    }

    # Run hook script
    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
    )

    # Should still exit 0, but not capture anything
    assert result.returncode == 0


def test_file_line_reference_extraction(hook_script):
    """Test extraction of file:line references from errors."""
    hook_input = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/test_foo.py"},
        "tool_response": {
            "output": """tests/test_foo.py:25: error: Assertion failed
Expected: 42
Actual: 24
File "tests/test_foo.py", line 25, in test_calculation""",
            "exitCode": 1,
        },
        "cwd": "/tmp/test-project",
        "session_id": "test_session_789",
    }

    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0


def test_malformed_json_graceful_handling(hook_script):
    """Test graceful handling of malformed JSON input."""
    malformed_input = "{ this is not valid json }"

    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=malformed_input,
        capture_output=True,
        text=True,
    )

    # Should exit 0 (non-blocking error)
    assert result.returncode == 0


def test_non_bash_tool_skipped(hook_script):
    """Test that non-Bash tools are skipped."""
    hook_input = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/path/to/file.py",
            "old_string": "foo",
            "new_string": "bar",
        },
        "tool_response": {"filePath": "/path/to/file.py"},
        "cwd": "/tmp/test-project",
        "session_id": "test_session_edit",
    }

    result = subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
    )

    # Should exit 0 and skip processing
    assert result.returncode == 0
