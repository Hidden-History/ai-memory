"""Unit tests for memory.hooks_common module.

Covers all 9 public functions and 2 constants exported by hooks_common.
hooks_common provides shared utilities for all Claude Code hook scripts;
setup_python_path is the entry point for all memory capture hooks.

TD-361: First-pass test coverage (zero coverage existed before this file).
"""

import builtins
import json
import logging
import os
import random
import sys
from unittest.mock import MagicMock

import pytest

from memory.hooks_common import (
    LANGUAGE_MAP,
    PREVIEW_MAX_CHARS,
    _rotate_log_if_needed,
    extract_error_signature,
    get_hook_timeout,
    get_metrics,
    get_token_metrics,
    get_trigger_metrics,
    log_to_activity,
    read_transcript,
    setup_hook_logging,
    setup_python_path,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def restore_sys_path():
    """Save and restore sys.path around setup_python_path calls.

    Prevents sys.path state leaking between tests (BUG-234 pattern).
    """
    original = sys.path.copy()
    yield
    sys.path[:] = original


# ---------------------------------------------------------------------------
# Constants: LANGUAGE_MAP
# ---------------------------------------------------------------------------


class TestLanguageMap:
    """Tests for the LANGUAGE_MAP constant."""

    def test_language_map_has_minimum_14_extensions(self):
        """LANGUAGE_MAP contains at least 14 extension entries."""
        assert len(LANGUAGE_MAP) >= 14

    def test_language_map_v4_minimum_extensions_present(self):
        """LANGUAGE_MAP includes the 5 V4-required extensions: .py .js .ts .go .rs."""
        required = {".py", ".js", ".ts", ".go", ".rs"}
        assert required.issubset(LANGUAGE_MAP.keys())

    def test_language_map_python_value(self):
        """LANGUAGE_MAP maps .py to 'Python'."""
        assert LANGUAGE_MAP[".py"] == "Python"

    def test_language_map_yaml_both_extensions(self):
        """LANGUAGE_MAP maps both .yaml and .yml to 'YAML'."""
        assert LANGUAGE_MAP[".yaml"] == "YAML"
        assert LANGUAGE_MAP[".yml"] == "YAML"


# ---------------------------------------------------------------------------
# Constants: PREVIEW_MAX_CHARS
# ---------------------------------------------------------------------------


class TestPreviewMaxChars:
    """Tests for the PREVIEW_MAX_CHARS constant."""

    def test_preview_max_chars_value(self):
        """PREVIEW_MAX_CHARS equals 400 as required by the V4 fix spec."""
        assert PREVIEW_MAX_CHARS == 400


# ---------------------------------------------------------------------------
# setup_python_path
# ---------------------------------------------------------------------------


class TestSetupPythonPath:
    """Tests for setup_python_path()."""

    def test_env_var_path_inserted_in_sys_path(self, monkeypatch, restore_sys_path):
        """setup_python_path inserts {AI_MEMORY_INSTALL_DIR}/src at sys.path[0]."""
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", "/tmp/test_install_dir")
        setup_python_path()
        assert sys.path[0] == "/tmp/test_install_dir/src"

    def test_env_var_returned_as_install_dir(self, monkeypatch, restore_sys_path):
        """setup_python_path returns the AI_MEMORY_INSTALL_DIR value."""
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", "/tmp/test_install_return")
        result = setup_python_path()
        assert result == "/tmp/test_install_return"

    def test_default_fallback_when_env_var_unset(self, monkeypatch, restore_sys_path):
        """setup_python_path defaults to ~/.ai-memory when AI_MEMORY_INSTALL_DIR is unset."""
        monkeypatch.delenv("AI_MEMORY_INSTALL_DIR", raising=False)
        result = setup_python_path()
        expected = os.path.expanduser("~/.ai-memory")
        assert result == expected
        assert sys.path[0] == os.path.join(expected, "src")

    def test_duplicate_path_inserted_on_repeated_call(
        self, monkeypatch, restore_sys_path
    ):
        """setup_python_path called twice inserts the src path twice (no dedup guard).

        Documents current unguarded behavior: the path appears at the front of
        sys.path once per call. Future dedup work would change this count to 1.
        """
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", "/tmp/test_dedup_pypath")
        setup_python_path()
        setup_python_path()
        src_path = "/tmp/test_dedup_pypath/src"
        assert sys.path.count(src_path) == 2


# ---------------------------------------------------------------------------
# setup_hook_logging
# ---------------------------------------------------------------------------


class TestSetupHookLogging:
    """Tests for setup_hook_logging()."""

    def test_returns_logger_instance(self):
        """setup_hook_logging returns a logging.Logger."""
        logger = setup_hook_logging("ai_memory.td361_returns_logger")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_matches_argument(self):
        """setup_hook_logging uses the provided logger_name."""
        logger = setup_hook_logging("ai_memory.td361_name_arg")
        assert logger.name == "ai_memory.td361_name_arg"

    def test_default_logger_name(self):
        """setup_hook_logging defaults to 'ai_memory.hooks' when no name given."""
        logger = setup_hook_logging()
        assert logger.name == "ai_memory.hooks"

    def test_logger_level_is_info(self):
        """setup_hook_logging sets the logger level to INFO."""
        logger = setup_hook_logging("ai_memory.td361_info_level")
        assert logger.level == logging.INFO

    def test_propagate_is_false(self):
        """setup_hook_logging sets propagate=False to prevent duplicate log output."""
        logger = setup_hook_logging("ai_memory.td361_propagate_false")
        assert logger.propagate is False

    def test_has_stream_handler(self):
        """setup_hook_logging adds at least one StreamHandler to the logger."""
        logger = setup_hook_logging("ai_memory.td361_stream_handler")
        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) >= 1

    def test_handler_uses_structured_formatter(self):
        """setup_hook_logging attaches a StructuredFormatter to the StreamHandler."""
        from memory.logging_config import StructuredFormatter

        logger = setup_hook_logging("ai_memory.td361_structured_fmt")
        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) >= 1
        assert isinstance(stream_handlers[-1].formatter, StructuredFormatter)

    def test_handler_accumulation_on_repeated_call(self):
        """setup_hook_logging called twice with the same name adds a second handler.

        Current behavior (unguarded): each call appends a new StreamHandler, so
        two calls yield two handlers on the same logger. TD-427 tracks a future
        dedup guard in hooks_common.py; this test documents the current state.
        """
        logger_name = "ai_memory.test_dedup_logger"
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        try:
            setup_hook_logging(logger_name)
            setup_hook_logging(logger_name)
            assert len(logger.handlers) == 2
        finally:
            logger.handlers.clear()


# ---------------------------------------------------------------------------
# log_to_activity
# ---------------------------------------------------------------------------


class TestLogToActivity:
    """Tests for log_to_activity()."""

    def test_writes_message_to_activity_log(self, tmp_path):
        """log_to_activity appends the message to {install_dir}/logs/activity.log."""
        log_to_activity("hello activity", install_dir=str(tmp_path))
        log_file = tmp_path / "logs" / "activity.log"
        assert log_file.exists()
        assert "hello activity" in log_file.read_text()

    def test_creates_logs_directory_if_missing(self, tmp_path):
        """log_to_activity creates the logs/ subdirectory when it does not exist."""
        fresh_dir = tmp_path / "fresh"
        log_to_activity("dir creation test", install_dir=str(fresh_dir))
        assert (fresh_dir / "logs").is_dir()

    def test_iso8601_timestamp_prefix(self, tmp_path):
        """log_to_activity prefixes each entry with an ISO 8601 timestamp."""
        import re

        log_to_activity("timestamped", install_dir=str(tmp_path))
        content = (tmp_path / "logs" / "activity.log").read_text()
        assert re.search(r"\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\]", content)

    def test_newlines_escaped_to_literal_backslash_n(self, tmp_path):
        """log_to_activity replaces newlines with \\n so each entry stays on one line."""
        log_to_activity("line one\nline two", install_dir=str(tmp_path))
        content = (tmp_path / "logs" / "activity.log").read_text()
        assert "line one\\nline two" in content
        # The written entry should not contain a bare newline mid-message
        lines = content.strip().split("\n")
        assert len(lines) == 1

    def test_graceful_on_write_error(self, monkeypatch, tmp_path):
        """log_to_activity does not raise when the file write fails (graceful degradation)."""
        original_open = builtins.open

        def failing_open(path, *args, **kwargs):
            if "activity.log" in str(path) and args and args[0] == "a":
                raise OSError("simulated disk full")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", failing_open)
        # Should complete without raising
        log_to_activity("no raise test", install_dir=str(tmp_path))

    def test_uses_env_var_when_install_dir_not_provided(self, monkeypatch, tmp_path):
        """log_to_activity reads install_dir from AI_MEMORY_INSTALL_DIR when argument omitted."""
        monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
        log_to_activity("env detection")
        log_file = tmp_path / "logs" / "activity.log"
        assert log_file.exists()
        assert "env detection" in log_file.read_text()


# ---------------------------------------------------------------------------
# get_hook_timeout
# ---------------------------------------------------------------------------


class TestGetHookTimeout:
    """Tests for get_hook_timeout()."""

    def test_valid_env_var_returned_as_int(self, monkeypatch):
        """get_hook_timeout returns int(HOOK_TIMEOUT) when env var is a valid number."""
        monkeypatch.setenv("HOOK_TIMEOUT", "120")
        assert get_hook_timeout() == 120

    def test_default_60_when_env_var_unset(self, monkeypatch):
        """get_hook_timeout returns 60 when HOOK_TIMEOUT is not set."""
        monkeypatch.delenv("HOOK_TIMEOUT", raising=False)
        assert get_hook_timeout() == 60

    def test_invalid_env_var_returns_60_not_raises(self, monkeypatch):
        """get_hook_timeout returns 60 (not raises) when HOOK_TIMEOUT is non-numeric."""
        monkeypatch.setenv("HOOK_TIMEOUT", "not_a_number")
        result = get_hook_timeout()
        assert result == 60

    def test_return_type_is_always_int(self, monkeypatch):
        """get_hook_timeout always returns an int, never a string."""
        monkeypatch.setenv("HOOK_TIMEOUT", "45")
        assert isinstance(get_hook_timeout(), int)


# ---------------------------------------------------------------------------
# get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    """Tests for get_metrics()."""

    def test_returns_three_none_tuple_on_import_error(self, monkeypatch):
        """get_metrics returns (None, None, None) when memory.metrics is unavailable."""
        monkeypatch.setitem(sys.modules, "memory.metrics", None)
        result = get_metrics()
        assert result == (None, None, None)

    def test_returns_three_tuple_when_metrics_available(self, monkeypatch):
        """get_metrics returns a 3-tuple with the correct metric objects in order."""
        mock_mod = MagicMock()
        monkeypatch.setitem(sys.modules, "memory.metrics", mock_mod)
        result = get_metrics()
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] is mock_mod.memory_retrievals_total
        assert result[1] is mock_mod.retrieval_duration_seconds
        assert result[2] is mock_mod.hook_duration_seconds


# ---------------------------------------------------------------------------
# get_trigger_metrics
# ---------------------------------------------------------------------------


class TestGetTriggerMetrics:
    """Tests for get_trigger_metrics()."""

    def test_returns_two_none_tuple_on_import_error(self, monkeypatch):
        """get_trigger_metrics returns (None, None) when memory.metrics is unavailable."""
        monkeypatch.setitem(sys.modules, "memory.metrics", None)
        result = get_trigger_metrics()
        assert result == (None, None)

    def test_returns_two_tuple_when_metrics_available(self, monkeypatch):
        """get_trigger_metrics returns a 2-tuple with the correct metric objects in order."""
        mock_mod = MagicMock()
        monkeypatch.setitem(sys.modules, "memory.metrics", mock_mod)
        result = get_trigger_metrics()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is mock_mod.trigger_fires_total
        assert result[1] is mock_mod.trigger_results_returned


# ---------------------------------------------------------------------------
# get_token_metrics
# ---------------------------------------------------------------------------


class TestGetTokenMetrics:
    """Tests for get_token_metrics()."""

    def test_returns_two_none_tuple_on_import_error(self, monkeypatch):
        """get_token_metrics returns (None, None) when memory.metrics is unavailable."""
        monkeypatch.setitem(sys.modules, "memory.metrics", None)
        result = get_token_metrics()
        assert result == (None, None)

    def test_returns_two_tuple_when_metrics_available(self, monkeypatch):
        """get_token_metrics returns a 2-tuple with the correct metric objects in order."""
        mock_mod = MagicMock()
        monkeypatch.setitem(sys.modules, "memory.metrics", mock_mod)
        result = get_token_metrics()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is mock_mod.tokens_consumed_total
        assert result[1] is mock_mod.context_injection_tokens


# ---------------------------------------------------------------------------
# extract_error_signature
# ---------------------------------------------------------------------------


class TestExtractErrorSignature:
    """Tests for extract_error_signature()."""

    def test_returns_first_line_with_error_keyword(self):
        """extract_error_signature returns the first line containing an error keyword."""
        output = "Starting\nError: bad path /foo\nDone"
        assert extract_error_signature(output) == "Error: bad path /foo"

    def test_fallback_to_last_non_empty_line_when_no_keywords(self):
        """extract_error_signature falls back to the last non-empty line when no keywords match."""
        output = "line one\nline two\nlast line"
        assert extract_error_signature(output) == "last line"

    def test_fallback_string_on_empty_output(self):
        """extract_error_signature returns the sentinel string when output is empty."""
        assert extract_error_signature("") == "Error detected in command output"

    def test_fallback_string_on_whitespace_only_output(self):
        """extract_error_signature returns the sentinel string when output is all whitespace."""
        assert (
            extract_error_signature("   \n  \n  ") == "Error detected in command output"
        )

    def test_max_length_truncates_long_line(self):
        """extract_error_signature truncates result to max_length characters."""
        long_error = "Error: " + "x" * 300
        result = extract_error_signature(long_error, max_length=50)
        assert len(result) <= 50

    def test_default_max_length_is_200(self):
        """extract_error_signature applies a 200-character ceiling by default."""
        long_error = "Exception: " + "a" * 300
        result = extract_error_signature(long_error)
        assert len(result) <= 200

    def test_exception_keyword_matches(self):
        """extract_error_signature recognises the 'exception' keyword."""
        output = "ok\nException: NullPointerException\ndone"
        result = extract_error_signature(output)
        assert "Exception" in result

    def test_traceback_keyword_matches(self):
        """extract_error_signature recognises the 'traceback' keyword."""
        output = "Traceback (most recent call last):\n  foo.py\nValueError: bad"
        result = extract_error_signature(output)
        assert "Traceback" in result

    def test_keyword_match_is_case_insensitive(self):
        """extract_error_signature keyword detection is case-insensitive."""
        output = "good line\nFATAL: system crash\nother"
        result = extract_error_signature(output)
        assert "FATAL" in result


# ---------------------------------------------------------------------------
# read_transcript
# ---------------------------------------------------------------------------


class TestReadTranscript:
    """Tests for read_transcript()."""

    def test_valid_jsonl_returns_list_of_dicts(self, tmp_path):
        """read_transcript parses a valid JSONL file into a list of dicts."""
        jsonl_file = tmp_path / "valid.jsonl"
        entries = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        jsonl_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        assert read_transcript(str(jsonl_file)) == entries

    def test_nonexistent_file_returns_empty_list(self, tmp_path):
        """read_transcript returns [] when the file does not exist."""
        assert read_transcript(str(tmp_path / "missing.jsonl")) == []

    def test_tilde_expansion_in_path(self, monkeypatch, tmp_path):
        """read_transcript expands ~ before opening the file."""
        jsonl_file = tmp_path / "tilde.jsonl"
        jsonl_file.write_text(json.dumps({"tilde": True}) + "\n")
        real_expanduser = os.path.expanduser
        monkeypatch.setattr(
            os.path,
            "expanduser",
            lambda p: str(jsonl_file) if p == "~/tilde.jsonl" else real_expanduser(p),
        )
        result = read_transcript("~/tilde.jsonl")
        assert result == [{"tilde": True}]

    def test_malformed_json_lines_skipped_valid_lines_returned(self, tmp_path):
        """read_transcript skips malformed JSON lines and returns valid entries."""
        jsonl_file = tmp_path / "mixed.jsonl"
        jsonl_file.write_text('{"good": 1}\n' "not valid {{{ json\n" '{"good": 2}\n')
        result = read_transcript(str(jsonl_file))
        assert result == [{"good": 1}, {"good": 2}]

    def test_empty_lines_skipped(self, tmp_path):
        """read_transcript ignores blank lines without raising."""
        jsonl_file = tmp_path / "blank_lines.jsonl"
        jsonl_file.write_text('{"n": 1}\n\n{"n": 2}\n')
        result = read_transcript(str(jsonl_file))
        assert len(result) == 2

    def test_graceful_on_read_error(self, monkeypatch, tmp_path):
        """read_transcript returns [] when an unexpected read error occurs (graceful degradation)."""
        jsonl_file = tmp_path / "error.jsonl"
        jsonl_file.write_text('{"ok": true}\n')
        original_open = builtins.open

        def failing_open(path, *args, **kwargs):
            if str(path) == str(jsonl_file):
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", failing_open)
        assert read_transcript(str(jsonl_file)) == []


# ---------------------------------------------------------------------------
# _rotate_log_if_needed
# ---------------------------------------------------------------------------


class TestRotateLogIfNeeded:
    """Tests for _rotate_log_if_needed()."""

    def test_rotates_file_exceeding_max_lines(self, tmp_path, monkeypatch):
        """_rotate_log_if_needed truncates an oversized log to keep_lines lines.

        Monkeypatches random.random to 0.01 to force execution past the
        probabilistic skip gate (threshold is 0.02).
        """
        log_file = tmp_path / "activity.log"
        # Write 510 lines — exceeds the default max_lines of 500
        log_file.write_text("\n".join(f"line {i}" for i in range(510)) + "\n")
        monkeypatch.setattr(random, "random", lambda: 0.01)
        _rotate_log_if_needed(log_file)
        lines = log_file.read_text().splitlines()
        assert len(lines) == 450  # default keep_lines
