"""Graceful degradation tests for retrieval system.

Validates that the memory system degrades gracefully when:
- No memories exist for a project (empty project)
- SessionStart receives malformed input
- Edge cases and error conditions

Critical Requirements (FR30, NFR-R1, NFR-R4):
- Always exit 0 (never block Claude)
- Empty context when services down or no results
- Errors logged to stderr only (never stdout)
- Claude can continue working without memory

References:
- FR30: Never block Claude
- NFR-R1: Graceful degradation on service failure
- NFR-R4: Error handling requirements
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

# Hook script path for SessionStart
SESSION_START = (
    Path(__file__).parent.parent.parent
    / ".claude"
    / "hooks"
    / "scripts"
    / "session_start.py"
)


def get_python_exe():
    """Get the Python executable to use for subprocess calls."""
    project_root = Path(__file__).parent.parent.parent
    venv_python = project_root / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def get_test_env():
    """Get environment variables for subprocess calls."""
    env = os.environ.copy()
    env["EMBEDDING_READ_TIMEOUT"] = "60.0"  # CPU mode needs 20-30s
    env["QDRANT_URL"] = "http://localhost:26350"
    env["SIMILARITY_THRESHOLD"] = "0.4"  # Production threshold (TECH-DEBT-002)

    # Add project src/ to PYTHONPATH for development mode
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"
    env["PYTHONPATH"] = str(src_dir) + ":" + env.get("PYTHONPATH", "")

    return env


@pytest.mark.integration
class TestRetrievalGracefulDegradation:
    """SessionStart must never fail, even with edge cases."""

    def test_sessionstart_handles_empty_results(self):
        """SessionStart returns empty context gracefully when no memories found.

        Validates:
        - New projects don't cause errors
        - Empty context returned (not error message)
        - Hook exits 0 (graceful degradation per NFR-R1)
        - Claude can work without memory (FR30)
        """
        # Use unique project name guaranteed to have no memories
        unique_project = f"brand-new-project-{uuid.uuid4().hex[:8]}"

        hook_input = {
            "cwd": f"/tmp/{unique_project}",
            "session_id": f"new-project-session-{uuid.uuid4().hex[:8]}",
        }

        print(f"\n[EMPTY PROJECT TEST] Project: {unique_project}")

        proc = subprocess.run(
            [get_python_exe(), str(SESSION_START)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=150,
            env=get_test_env(),
        )

        # MUST exit 0 even with no results (FR30: never block Claude)
        assert proc.returncode == 0, (
            f"Hook failed on new project (exit {proc.returncode})!\n"
            f"Should gracefully return empty context.\n"
            f"stderr: {proc.stderr}"
        )

        context = proc.stdout

        # Empty or minimal context acceptable
        # Should NOT contain error messages
        assert "Error" not in context and "Exception" not in context, (
            f"Error message in context! Should be silent graceful degradation.\n"
            f"Context: {context[:500]}"
        )

        print("✓ New project handled gracefully (exit 0, no errors)")
        print(f"  Context length: {len(context)} chars")

    def test_sessionstart_handles_malformed_input(self):
        """SessionStart handles malformed JSON gracefully.

        Validates:
        - Malformed input doesn't crash hook
        - Hook exits 0 (FR30, NFR-R4)
        - No error in stdout (errors go to stderr only)
        """
        print("\n[MALFORMED INPUT TEST]")

        proc = subprocess.run(
            [get_python_exe(), str(SESSION_START)],
            input="not valid json {{{",
            capture_output=True,
            text=True,
            timeout=150,
            env=get_test_env(),
        )

        # MUST exit 0 (FR30, NFR-R4: graceful degradation)
        assert proc.returncode == 0, (
            f"Hook crashed on malformed input (exit {proc.returncode})!\n"
            f"Should handle gracefully.\n"
            f"stderr: {proc.stderr}"
        )

        # Context should be empty or minimal (no error propagated to Claude)
        context = proc.stdout
        assert "Error" not in context and "Exception" not in context, (
            f"Error leaked into context!\n" f"Context: {context}"
        )

        print("✓ Malformed input handled gracefully (exit 0)")
        print(f"  Context length: {len(context)} chars")
        print(f"  Errors logged to stderr: {len(proc.stderr)} chars")

    def test_sessionstart_handles_missing_fields(self):
        """SessionStart handles missing required fields gracefully.

        Validates:
        - Missing cwd or session_id doesn't crash
        - Hook exits 0 with graceful degradation
        - Empty context returned
        """
        print("\n[MISSING FIELDS TEST]")

        # Test with missing cwd
        hook_input = {
            "session_id": f"test-session-{uuid.uuid4().hex[:8]}",
            # cwd missing!
        }

        proc = subprocess.run(
            [get_python_exe(), str(SESSION_START)],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=150,
            env=get_test_env(),
        )

        # MUST exit 0 (graceful degradation)
        assert proc.returncode == 0, (
            f"Hook crashed on missing cwd (exit {proc.returncode})!\n"
            f"stderr: {proc.stderr}"
        )

        context = proc.stdout
        assert "Error" not in context and "Exception" not in context, (
            f"Error in context!\n" f"Context: {context}"
        )

        print("✓ Missing cwd handled gracefully (exit 0)")
        print(f"  Context length: {len(context)} chars")
