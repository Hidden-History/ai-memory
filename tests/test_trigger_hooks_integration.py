"""Integration tests for Phase 3 trigger hook scripts.

Tests the actual hook scripts with mocked dependencies to verify:
- JSON input parsing
- Error handling
- Graceful degradation
- TRIGGER_CONFIG validation
"""

import json
import os
import subprocess
import sys

import pytest


def _qdrant_available() -> bool:
    """Check if Qdrant is available for integration tests.

    Returns:
        True if Qdrant is reachable, False otherwise.
    """
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url="http://localhost:6333", timeout=1.0)
        client.get_collections()
        return True
    except Exception:
        return False


class TestNewFileTriggerHook:
    """Integration tests for new_file_trigger.py hook."""

    @pytest.fixture
    def hook_script(self):
        """Path to new_file_trigger.py."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(project_root, ".claude/hooks/scripts/new_file_trigger.py")

    def test_hook_handles_malformed_json(self, hook_script):
        """Hook gracefully degrades on malformed JSON input."""
        result = subprocess.run(
            [sys.executable, hook_script],
            input="not valid json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_missing_file_path(self, hook_script):
        """Hook handles missing file_path in tool_input."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {},  # No file_path
            "cwd": "/tmp",
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_wrong_tool(self, hook_script):
        """Hook ignores non-Write tools."""
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "cwd": "/tmp",
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (not this hook's concern)
        assert result.returncode == 0
        # Should not output anything to stdout
        assert result.stdout.strip() == ""


class TestFirstEditTriggerHook:
    """Integration tests for first_edit_trigger.py hook."""

    @pytest.fixture
    def hook_script(self):
        """Path to first_edit_trigger.py."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(project_root, ".claude/hooks/scripts/first_edit_trigger.py")

    def test_hook_handles_malformed_json(self, hook_script):
        """Hook gracefully degrades on malformed JSON input."""
        result = subprocess.run(
            [sys.executable, hook_script],
            input="not valid json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_missing_session_id(self, hook_script):
        """Hook handles missing session_id."""
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "cwd": "/tmp",
            # Missing session_id
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_wrong_tool(self, hook_script):
        """Hook ignores non-Edit tools."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py"},
            "cwd": "/tmp",
            "session_id": "test_session",
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (not this hook's concern)
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestUnifiedKeywordTriggerHook:
    """Integration tests for unified_keyword_trigger.py hook (TECH-DEBT-062)."""

    @pytest.fixture
    def hook_script(self):
        """Path to unified_keyword_trigger.py (consolidated trigger)."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(
            project_root, ".claude/hooks/scripts/unified_keyword_trigger.py"
        )

    def test_hook_handles_malformed_json(self, hook_script):
        """Hook gracefully degrades on malformed JSON input."""
        result = subprocess.run(
            [sys.executable, hook_script],
            input="not valid json",
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_missing_prompt(self, hook_script):
        """Hook handles missing prompt."""
        hook_input = {
            "cwd": "/tmp"
            # Missing prompt
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_no_keywords(self, hook_script):
        """Hook handles prompts without decision keywords."""
        hook_input = {
            "prompt": "How do I implement authentication?",  # Unified trigger uses "prompt" not "user_input"
            "cwd": "/tmp",
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit 0 (no keywords detected)
        assert result.returncode == 0
        # Should not output anything
        assert result.stdout.strip() == ""


class TestHooksGracefulDegradation:
    """Test that all hooks handle errors gracefully."""

    @pytest.fixture(
        params=[
            ".claude/hooks/scripts/new_file_trigger.py",
            ".claude/hooks/scripts/first_edit_trigger.py",
            ".claude/hooks/scripts/unified_keyword_trigger.py",  # TECH-DEBT-062: Consolidated trigger
        ]
    )
    def hook_script(self, request):
        """Parametrized fixture for all trigger hooks."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(project_root, request.param)

    def test_hook_exits_zero_on_empty_input(self, hook_script):
        """All hooks exit 0 on empty stdin."""
        result = subprocess.run(
            [sys.executable, hook_script],
            input="",
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    @pytest.mark.skipif(
        os.environ.get("CI") == "true" or not _qdrant_available(),
        reason="Requires running Qdrant instance (skipped in CI or when Qdrant unavailable)",
    )
    def test_hook_completes_within_timeout(self, hook_script):
        """All hooks complete within reasonable time."""
        hook_input = {"cwd": "/tmp"}
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=2,  # 2 second timeout (matching settings.json)
        )
        # Should complete without timeout
        assert result.returncode == 0
