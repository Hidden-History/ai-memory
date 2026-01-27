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
from unittest import mock

import pytest


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
            timeout=5
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_missing_file_path(self, hook_script):
        """Hook handles missing file_path in tool_input."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {},  # No file_path
            "cwd": "/tmp"
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_wrong_tool(self, hook_script):
        """Hook ignores non-Write tools."""
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "cwd": "/tmp"
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5
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
            timeout=5
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_missing_session_id(self, hook_script):
        """Hook handles missing session_id."""
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "cwd": "/tmp"
            # Missing session_id
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_wrong_tool(self, hook_script):
        """Hook ignores non-Edit tools."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test.py"},
            "cwd": "/tmp",
            "session_id": "test_session"
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (not this hook's concern)
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestDecisionKeywordTriggerHook:
    """Integration tests for decision_keyword_trigger.py hook."""

    @pytest.fixture
    def hook_script(self):
        """Path to decision_keyword_trigger.py."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(project_root, ".claude/hooks/scripts/decision_keyword_trigger.py")

    def test_hook_handles_malformed_json(self, hook_script):
        """Hook gracefully degrades on malformed JSON input."""
        result = subprocess.run(
            [sys.executable, hook_script],
            input="not valid json",
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_missing_user_input(self, hook_script):
        """Hook handles missing user_input."""
        hook_input = {
            "cwd": "/tmp"
            # Missing user_input
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (graceful degradation)
        assert result.returncode == 0

    def test_hook_handles_no_keywords(self, hook_script):
        """Hook handles prompts without decision keywords."""
        hook_input = {
            "user_input": "How do I implement authentication?",
            "cwd": "/tmp"
        }
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=5
        )
        # Should exit 0 (no keywords detected)
        assert result.returncode == 0
        # Should not output anything
        assert result.stdout.strip() == ""


class TestHooksGracefulDegradation:
    """Test that all hooks handle errors gracefully."""

    @pytest.fixture(params=[
        ".claude/hooks/scripts/new_file_trigger.py",
        ".claude/hooks/scripts/first_edit_trigger.py",
        ".claude/hooks/scripts/decision_keyword_trigger.py"
    ])
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
            timeout=5
        )
        assert result.returncode == 0

    def test_hook_completes_within_timeout(self, hook_script):
        """All hooks complete within reasonable time."""
        hook_input = {"cwd": "/tmp"}
        result = subprocess.run(
            [sys.executable, hook_script],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            timeout=2  # 2 second timeout (matching settings.json)
        )
        # Should complete without timeout
        assert result.returncode == 0
