#!/usr/bin/env python3
"""Integration tests for manual_save_memory hook (BUG-044 fix).

Tests that verify:
- Python path setup works correctly
- Script can import memory modules
- /save-memory command executes successfully
- Graceful degradation when path is invalid

Run with: pytest tests/integration/test_manual_save_memory.py -v
Requires Docker services running (Qdrant, Embedding Service).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Test configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent
MANUAL_SAVE_SCRIPT = PROJECT_ROOT / ".claude/hooks/scripts/manual_save_memory.py"
INSTALL_DIR = os.environ.get('BMAD_INSTALL_DIR', os.path.expanduser('~/.bmad-memory'))


def test_manual_save_script_exists():
    """Verify manual_save_memory.py exists."""
    assert MANUAL_SAVE_SCRIPT.exists(), f"Script not found: {MANUAL_SAVE_SCRIPT}"


def test_manual_save_imports_successfully():
    """Test that the script can import memory modules (BUG-044 fix verification)."""
    # This tests that sys.path setup happens before imports
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, '{PROJECT_ROOT}'); "
         f"exec(open('{MANUAL_SAVE_SCRIPT}').read())"],
        env={**os.environ, 'BMAD_INSTALL_DIR': INSTALL_DIR},
        capture_output=True,
        timeout=5
    )

    # Script should import successfully (will fail at runtime without args, but imports work)
    assert result.returncode in [0, 1], f"Import failed: {result.stderr.decode()}"
    assert b"ModuleNotFoundError" not in result.stderr, "BUG-044 not fixed: ModuleNotFoundError"


def test_manual_save_syntax_valid():
    """Verify Python syntax is valid."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(MANUAL_SAVE_SCRIPT)],
        capture_output=True
    )
    assert result.returncode == 0, f"Syntax error: {result.stderr.decode()}"


def test_manual_save_executes_with_description():
    """Test /save-memory command executes successfully with description."""
    result = subprocess.run(
        [sys.executable, str(MANUAL_SAVE_SCRIPT), "Test session save"],
        env={
            **os.environ,
            'BMAD_INSTALL_DIR': INSTALL_DIR,
            'CLAUDE_SESSION_ID': 'test_session_123'
        },
        capture_output=True,
        timeout=10,
        cwd=str(PROJECT_ROOT)
    )

    # Should succeed (exit 0) or queue (also exit 0 per graceful degradation)
    assert result.returncode == 0, f"Execution failed: {result.stderr.decode()}"

    # Should print success or queue message
    output = result.stdout.decode()
    assert "saved to memory" in output.lower() or "queued" in output.lower(), \
        f"Unexpected output: {output}"


def test_manual_save_graceful_degradation_invalid_path():
    """Test graceful degradation when BMAD_INSTALL_DIR is invalid (F2 fix)."""
    result = subprocess.run(
        [sys.executable, str(MANUAL_SAVE_SCRIPT)],
        env={
            **os.environ,
            'BMAD_INSTALL_DIR': '/nonexistent/path/to/memory',
            'CLAUDE_SESSION_ID': 'test_session_456'
        },
        capture_output=True,
        timeout=5,
        cwd=str(PROJECT_ROOT)
    )

    # Should exit 1 (non-blocking error) per graceful degradation
    assert result.returncode == 1, "Should exit 1 for invalid path"

    # Should print warning message
    stderr = result.stderr.decode()
    assert "Memory module not found" in stderr, f"Missing warning message: {stderr}"


def test_manual_save_path_validation():
    """Test that path validation happens before imports (F1 fix)."""
    # Run with invalid path - should fail fast with clear error
    result = subprocess.run(
        [sys.executable, str(MANUAL_SAVE_SCRIPT)],
        env={
            **os.environ,
            'BMAD_INSTALL_DIR': '/tmp/invalid_bmad_dir_12345',
            'CLAUDE_SESSION_ID': 'test_validation'
        },
        capture_output=True,
        timeout=5,
        cwd=str(PROJECT_ROOT)
    )

    assert result.returncode == 1, "Should exit 1 for missing src directory"
    stderr = result.stderr.decode()
    assert "Memory module not found" in stderr
    assert "/tmp/invalid_bmad_dir_12345" in stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
