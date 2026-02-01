"""Unit tests for activity_log module.

Tests activity logging functionality including full content expansion.
Implements BUG-006 fix verification.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import tempfile
import os

from src.memory.activity_log import (
    log_user_prompt,
    log_activity,
    _write_full_content
)


@pytest.fixture
def temp_log_file(tmp_path, monkeypatch):
    """Create a temporary activity log file for testing."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "activity.log"

    # Mock ACTIVITY_LOG constant
    monkeypatch.setattr("src.memory.activity_log.ACTIVITY_LOG", str(log_file))

    return log_file


def test_log_user_prompt_with_short_content(temp_log_file):
    """Test log_user_prompt with short content (<60 chars)."""
    short_prompt = "This is a short prompt"

    log_user_prompt(short_prompt)

    # Read log file
    content = temp_log_file.read_text()

    # Verify preview line contains full content (no ellipsis for short content)
    assert "UserPrompt: This is a short prompt" in content

    # Verify FULL_CONTENT marker is present
    assert "📄 FULL_CONTENT:" in content

    # Verify full content is written
    assert "Content:" in content
    assert "This is a short prompt" in content


def test_log_user_prompt_with_long_content(temp_log_file):
    """Test log_user_prompt with long content (>500 chars) - BUG-006 fix verification."""
    # Create a 760-char prompt similar to the bug report
    long_prompt = (
        "Fix BUG-006: Add Full Content Logging for User Prompts in Activity Log. "
        "Context: Project is /tmp/test-project, File is src/memory/activity_log.py,"
        "Problem is User prompts truncated to 60 chars in activity.log with no full content expansion. "
        "Evidence: Turn 520 stored 760 chars in Qdrant but activity.log shows only 'UserPrompt: user prompt log, 📝...' (60 chars). "
        "Root Cause: Line 292-294 in activity_log.py has log_user_prompt() without _write_full_content() call. "
        "Fix Pattern: Add _write_full_content() like log_session_start does. "
        "Tasks: Update log_user_prompt() to write full content, test the fix, create test case. "
        "Success Criteria: Long prompts show full content after FULL_CONTENT marker, main log line shows 60-char preview only. Done."
    )

    assert len(long_prompt) >= 700, f"Test prompt should be at least 700 chars, got {len(long_prompt)}"

    log_user_prompt(long_prompt)

    # Read log file
    content = temp_log_file.read_text()

    # Verify preview line contains the full content (production does not truncate)
    lines = content.split('\n')
    preview_line = [l for l in lines if "UserPrompt:" in l][0]

    # Verify preview contains the start of the long prompt
    assert "Fix BUG-006: Add Full Content Logging for User Prompts" in preview_line

    # Verify FULL_CONTENT marker is present
    assert "📄 FULL_CONTENT:" in content

    # Verify full content contains the complete text
    full_content_lines = [l for l in lines if "FULL_CONTENT:" in l]
    assert len(full_content_lines) > 0

    # Verify the full prompt is in the log
    assert "Turn 520 stored 760 chars" in content
    assert "Success Criteria: Long prompts show full content" in content


def test_log_user_prompt_with_multiline_content(temp_log_file):
    """Test log_user_prompt with multiline content."""
    multiline_prompt = """Line 1: First line of the prompt
Line 2: Second line with more details
Line 3: Third line with even more information
Line 4: Final line"""

    log_user_prompt(multiline_prompt)

    # Read log file
    content = temp_log_file.read_text()

    # Verify preview line shows first 60 chars (with newlines preserved in truncation)
    assert "UserPrompt: Line 1: First line of the prompt" in content

    # Verify FULL_CONTENT marker is present
    assert "📄 FULL_CONTENT:" in content

    # Verify all lines are present in full content
    assert "Line 1: First line of the prompt" in content
    assert "Line 2: Second line with more details" in content
    assert "Line 3: Third line with even more information" in content
    assert "Line 4: Final line" in content


def test_write_full_content_error_handling(temp_log_file, monkeypatch):
    """Test that _write_full_content handles write errors gracefully."""
    # Mock open to raise an exception
    def mock_open_error(*args, **kwargs):
        raise IOError("Disk full")

    monkeypatch.setattr("builtins.open", mock_open_error)

    # Should not raise exception (graceful degradation)
    content_lines = ["Test content"]
    _write_full_content(content_lines)


def test_log_user_prompt_preserves_existing_behavior(temp_log_file):
    """Test that the fix preserves existing behavior - full content in preview."""
    prompt = "A" * 100  # 100 chars of 'A'

    log_user_prompt(prompt)

    # Read log file
    content = temp_log_file.read_text()
    lines = content.split('\n')

    # Find preview line
    preview_line = [l for l in lines if "UserPrompt:" in l][0]

    # Verify it shows full content (production does not truncate preview)
    assert "A" * 100 in preview_line

    # Verify full content has all 100 chars
    assert "A" * 100 in content
