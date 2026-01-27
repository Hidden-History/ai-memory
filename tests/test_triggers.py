"""Tests for Memory System V2.0 Phase 3 Trigger System.

Tests automatic trigger detection functions:
- Error signal detection
- Decision keyword detection
- New file detection
- First edit tracking with session isolation
"""

import os
import tempfile
from pathlib import Path

import pytest

from memory.triggers import (
    detect_error_signal,
    detect_decision_keywords,
    is_new_file,
    is_first_edit_in_session,
    _session_edited_files,
    _session_lock,
    MAX_SESSIONS,
    TRIGGER_CONFIG,
)


class TestErrorSignalDetection:
    """Test error signal detection from text."""

    def test_detect_error_with_error_colon(self):
        """Detect 'Error:' pattern."""
        text = "Error: Connection refused on port 26350"
        result = detect_error_signal(text)
        assert result is not None
        assert "Connection refused" in result

    def test_detect_error_with_exception(self):
        """Detect 'Exception:' pattern."""
        text = "Exception: TypeError in module authentication"
        result = detect_error_signal(text)
        assert result is not None
        assert "TypeError" in result

    def test_detect_error_with_traceback(self):
        """Detect 'Traceback' pattern."""
        text = "Traceback (most recent call last):\n  File test.py"
        result = detect_error_signal(text)
        assert result is not None

    def test_detect_error_with_failed_uppercase(self):
        """Detect 'FAILED:' structured pattern."""
        text = "FAILED: assertion error in test_auth.py"
        result = detect_error_signal(text)
        assert result is not None
        assert "assertion error" in result.lower()

    def test_no_false_positive_on_error_word(self):
        """Don't trigger on 'error' in normal conversation."""
        text = "I prefer error handling with try/catch blocks"
        result = detect_error_signal(text)
        assert result is None, "Should not trigger on conversational use of 'error'"

    def test_no_error_signal_in_normal_text(self):
        """Return None for text without error patterns."""
        text = "Everything is working fine. All tests pass."
        result = detect_error_signal(text)
        assert result is None

    def test_no_error_signal_empty_text(self):
        """Return None for empty text."""
        result = detect_error_signal("")
        assert result is None

    def test_no_error_signal_none_text(self):
        """Return None for None input."""
        result = detect_error_signal(None)
        assert result is None

    def test_error_signature_truncated_at_200_chars(self):
        """Error signature is truncated at 200 characters."""
        long_error = "Error: " + "x" * 300
        result = detect_error_signal(long_error)
        assert result is not None
        assert len(result) <= 200

    def test_error_signature_stops_at_newline(self):
        """Error signature extracts only first line."""
        text = "Error: First line\nSecond line\nThird line"
        result = detect_error_signal(text)
        assert result is not None
        assert "First line" in result
        assert "Second line" not in result

    def test_exception_type_extraction(self):
        """Verify exception types are extracted from structured errors."""
        # Should include exception type in result
        result = detect_error_signal("TypeError: expected str, got int")
        assert result is not None, "Should detect TypeError"
        assert "TypeError" in result, f"Expected TypeError in '{result}'"

        result = detect_error_signal("ValueError: invalid literal")
        assert result is not None, "Should detect ValueError"
        assert "ValueError" in result, f"Expected ValueError in '{result}'"

        result = detect_error_signal("KeyError: 'missing_key'")
        assert result is not None, "Should detect KeyError"
        assert "KeyError" in result, f"Expected KeyError in '{result}'"

    def test_traceback_extracts_exception(self):
        """Verify traceback extracts the actual exception."""
        traceback = """Traceback (most recent call last):
  File "test.py", line 10, in <module>
    foo()
  File "test.py", line 5, in foo
    raise ValueError("bad value")
ValueError: bad value"""

        result = detect_error_signal(traceback)
        assert result is not None, "Should detect traceback"
        assert "ValueError" in result, f"Expected ValueError in '{result}'"


class TestDecisionKeywordDetection:
    """Test decision keyword detection from user prompts."""

    def test_detect_why_did_we_pattern(self):
        """Detect 'why did we' pattern."""
        text = "Why did we choose port 26350 for Qdrant?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert "choose port 26350" in result.lower()

    def test_detect_why_do_we_pattern(self):
        """Detect 'why do we' pattern."""
        text = "Why do we use semantic search instead of keyword search?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert "use semantic search" in result.lower()

    def test_detect_what_was_decided_pattern(self):
        """Detect 'what was decided' pattern."""
        text = "What was decided about the authentication approach?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert "about the authentication" in result.lower()

    def test_detect_what_did_we_decide_pattern(self):
        """Detect 'what did we decide' pattern."""
        text = "What did we decide on the collection architecture?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert "on the collection" in result.lower()

    def test_detect_remember_when_pattern(self):
        """Detect 'remember when' pattern."""
        text = "Remember when we discussed the hook system design?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert "we discussed" in result.lower()

    def test_detect_remember_the_decision_pattern(self):
        """Detect 'remember the decision' pattern."""
        text = "Remember the decision about multi-tenancy?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert "about multi-tenancy" in result.lower()

    def test_no_decision_keywords_in_normal_question(self):
        """Return None for questions without decision keywords."""
        text = "How do I implement authentication?"
        result = detect_decision_keywords(text)
        assert result is None

    def test_no_decision_keywords_empty_text(self):
        """Return None for empty text."""
        result = detect_decision_keywords("")
        assert result is None

    def test_no_decision_keywords_none_text(self):
        """Return None for None input."""
        result = detect_decision_keywords(None)
        assert result is None

    def test_decision_topic_strips_question_mark(self):
        """Remove trailing question mark from extracted topic."""
        text = "Why did we choose this approach?"
        result = detect_decision_keywords(text)
        assert result is not None
        assert not result.endswith("?")

    def test_decision_topic_case_insensitive(self):
        """Detection is case-insensitive."""
        text = "WHY DID WE choose this?"
        result = detect_decision_keywords(text)
        assert result is not None

    def test_decision_keywords_empty_topic_fallback(self):
        """Use full text as fallback when topic extraction fails."""
        text = "What was decided"
        result = detect_decision_keywords(text)
        assert result is not None
        assert result == "What was decided"


class TestNewFileDetection:
    """Test new file detection."""

    def test_new_file_does_not_exist(self):
        """Return True for non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_file = os.path.join(tmpdir, "new_file.py")
            assert is_new_file(new_file) is True

    def test_existing_file(self):
        """Return False for existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"content")
            tmp.flush()
            try:
                assert is_new_file(tmp.name) is False
            finally:
                os.unlink(tmp.name)

    def test_new_file_empty_path(self):
        """Return False for empty file path."""
        assert is_new_file("") is False

    def test_new_file_none_path(self):
        """Return False for None file path."""
        assert is_new_file(None) is False

    def test_new_file_in_non_existent_directory(self):
        """Return True for file in non-existent directory."""
        non_existent = "/non/existent/path/file.py"
        # Assuming this path doesn't exist
        assert is_new_file(non_existent) is True


class TestFirstEditTracking:
    """Test first edit per file per session tracking."""

    def setup_method(self):
        """Clear session state before each test."""
        _session_edited_files.clear()

    def test_first_edit_to_file(self):
        """Return True for first edit to a file in session."""
        result = is_first_edit_in_session("/src/main.py", "sess_123")
        assert result is True

    def test_second_edit_to_same_file(self):
        """Return False for second edit to same file in same session."""
        is_first_edit_in_session("/src/main.py", "sess_123")
        result = is_first_edit_in_session("/src/main.py", "sess_123")
        assert result is False

    def test_first_edit_different_session(self):
        """Return True for same file in different session."""
        is_first_edit_in_session("/src/main.py", "sess_123")
        result = is_first_edit_in_session("/src/main.py", "sess_456")
        assert result is True

    def test_first_edit_different_file_same_session(self):
        """Return True for different file in same session."""
        is_first_edit_in_session("/src/main.py", "sess_123")
        result = is_first_edit_in_session("/src/utils.py", "sess_123")
        assert result is True

    def test_session_isolation(self):
        """Sessions track edits independently."""
        # Session 1: Edit file A then file B
        assert is_first_edit_in_session("/src/main.py", "sess_1") is True
        assert is_first_edit_in_session("/src/utils.py", "sess_1") is True

        # Session 2: Edit file A (should be first for this session)
        assert is_first_edit_in_session("/src/main.py", "sess_2") is True

        # Session 1: Edit file A again (should be second)
        assert is_first_edit_in_session("/src/main.py", "sess_1") is False

    def test_first_edit_tracks_file_in_session(self):
        """First edit adds file to session's tracking set."""
        session_id = "sess_123"
        file_path = "/src/main.py"

        # Initially, session not tracked
        assert session_id not in _session_edited_files

        # First edit
        is_first_edit_in_session(file_path, session_id)

        # Now session is tracked and contains the file
        assert session_id in _session_edited_files
        assert file_path in _session_edited_files[session_id]

    def test_multiple_files_in_same_session(self):
        """Track multiple files edited in same session."""
        session_id = "sess_123"
        files = ["/src/main.py", "/src/utils.py", "/src/config.py"]

        # Edit all files
        for file_path in files:
            is_first_edit_in_session(file_path, session_id)

        # All files tracked for this session
        assert len(_session_edited_files[session_id]) == 3
        for file_path in files:
            assert file_path in _session_edited_files[session_id]

    def test_first_edit_empty_file_path(self):
        """Return False for empty file path."""
        result = is_first_edit_in_session("", "sess_123")
        assert result is False

    def test_first_edit_empty_session_id(self):
        """Return False for empty session ID."""
        result = is_first_edit_in_session("/src/main.py", "")
        assert result is False

    def test_first_edit_none_inputs(self):
        """Return False for None inputs."""
        assert is_first_edit_in_session(None, "sess_123") is False
        assert is_first_edit_in_session("/src/main.py", None) is False

    def test_session_cleanup_enforces_exact_max(self):
        """Verify exactly MAX_SESSIONS allowed, not MAX+1."""
        # Clear existing state
        with _session_lock:
            _session_edited_files.clear()

        # Add MAX_SESSIONS + 10 sessions
        for i in range(MAX_SESSIONS + 10):
            is_first_edit_in_session('/tmp/test.py', f'sess_{i}')

        # Must be exactly MAX_SESSIONS or fewer
        assert len(_session_edited_files) <= MAX_SESSIONS, \
            f"Expected <= {MAX_SESSIONS}, got {len(_session_edited_files)}"


class TestTriggerConfiguration:
    """Test trigger configuration structure."""

    def test_trigger_config_has_all_triggers(self):
        """TRIGGER_CONFIG contains all 4 trigger types."""
        assert "error_detection" in TRIGGER_CONFIG
        assert "new_file" in TRIGGER_CONFIG
        assert "first_edit" in TRIGGER_CONFIG
        assert "decision_keywords" in TRIGGER_CONFIG

    def test_error_detection_config(self):
        """Error detection config has required fields."""
        config = TRIGGER_CONFIG["error_detection"]
        assert config["enabled"] is True
        assert isinstance(config["patterns"], list)
        assert len(config["patterns"]) > 0
        assert config["collection"] == "code-patterns"
        assert config["type_filter"] == "error_fix"
        assert config["max_results"] == 3

    def test_new_file_config(self):
        """New file config has required fields."""
        config = TRIGGER_CONFIG["new_file"]
        assert config["enabled"] is True
        assert config["collection"] == "conventions"
        assert isinstance(config["type_filter"], list)
        assert "naming" in config["type_filter"]
        assert "structure" in config["type_filter"]
        assert config["max_results"] == 2

    def test_first_edit_config(self):
        """First edit config has required fields."""
        config = TRIGGER_CONFIG["first_edit"]
        assert config["enabled"] is True
        assert config["collection"] == "code-patterns"
        assert config["type_filter"] is None  # Search all types - implementation patterns relevant to first edits
        assert config["max_results"] == 3

    def test_decision_keywords_config(self):
        """Decision keywords config has required fields."""
        config = TRIGGER_CONFIG["decision_keywords"]
        assert config["enabled"] is True
        assert isinstance(config["patterns"], list)
        assert len(config["patterns"]) > 0
        assert config["collection"] == "discussions"
        # Search ALL discussion types (decision, session, blocker, preference, user_message, agent_response)
        # This allows "do you remember what errors you made" to find agent_response memories
        assert config["type_filter"] is None
        assert config["max_results"] == 3
