"""Unit tests for graceful degradation utilities.

Test suite for src/memory/graceful.py - Exit codes, decorator, helper functions.
Follows 2025 best practices for decorator testing and exception handling.
"""

import logging

import pytest

from src.memory.graceful import (
    EXIT_BLOCKING,
    EXIT_NON_BLOCKING,
    EXIT_SUCCESS,
    exit_graceful,
    exit_success,
    graceful_hook,
)


class TestExitCodeConstants:
    """Test exit code constants match project-context.md specification."""

    def test_exit_success_value(self):
        """EXIT_SUCCESS should be 0."""
        assert EXIT_SUCCESS == 0

    def test_exit_non_blocking_value(self):
        """EXIT_NON_BLOCKING should be 1."""
        assert EXIT_NON_BLOCKING == 1

    def test_exit_blocking_value(self):
        """EXIT_BLOCKING should be 2."""
        assert EXIT_BLOCKING == 2


class TestGracefulHookDecorator:
    """Test @graceful_hook decorator with various exception scenarios."""

    def test_successful_function(self):
        """Decorator should pass through successful function calls."""

        @graceful_hook
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_successful_function_with_args(self):
        """Decorator should pass through args and kwargs."""

        @graceful_hook
        def func_with_args(a, b, keyword=None):
            return f"{a}-{b}-{keyword}"

        result = func_with_args("one", "two", keyword="three")
        assert result == "one-two-three"

    def test_preserves_function_metadata(self):
        """Decorator should preserve __name__ and __doc__ using functools.wraps."""

        @graceful_hook
        def documented_func():
            """This is a docstring."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a docstring."

    def test_catches_value_error(self):
        """Decorator should catch ValueError and exit with code 1."""

        @graceful_hook
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(SystemExit) as exc_info:
            failing_func()

        assert exc_info.value.code == EXIT_NON_BLOCKING

    def test_catches_runtime_error(self):
        """Decorator should catch RuntimeError and exit with code 1."""

        @graceful_hook
        def failing_func():
            raise RuntimeError("Runtime failure")

        with pytest.raises(SystemExit) as exc_info:
            failing_func()

        assert exc_info.value.code == EXIT_NON_BLOCKING

    def test_catches_generic_exception(self):
        """Decorator should catch any Exception and exit with code 1."""

        @graceful_hook
        def failing_func():
            raise Exception("Generic failure")

        with pytest.raises(SystemExit) as exc_info:
            failing_func()

        assert exc_info.value.code == EXIT_NON_BLOCKING

    def test_logs_error_with_structured_extras(self, caplog):
        """Decorator should log errors using structured logging with extras dict."""
        caplog.set_level(logging.ERROR)

        @graceful_hook
        def failing_func():
            raise RuntimeError("Test failure")

        with pytest.raises(SystemExit):
            failing_func()

        # Verify structured logging was used
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "ERROR"
        assert record.message == "hook_failed"

        # Verify extras dict contains expected fields
        assert hasattr(record, "hook")
        assert record.hook == "failing_func"
        assert hasattr(record, "error")
        assert "Test failure" in record.error
        assert hasattr(record, "error_type")
        assert record.error_type == "RuntimeError"

    def test_logs_different_exception_types(self, caplog):
        """Decorator should log different error_type for different exceptions."""
        caplog.set_level(logging.ERROR)

        @graceful_hook
        def value_error_func():
            raise ValueError("Value error")

        with pytest.raises(SystemExit):
            value_error_func()

        record = caplog.records[0]
        assert record.error_type == "ValueError"
        assert "Value error" in record.error


class TestExitHelpers:
    """Test exit_success() and exit_graceful() helper functions."""

    def test_exit_success(self):
        """exit_success() should exit with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            exit_success()

        assert exc_info.value.code == EXIT_SUCCESS

    def test_exit_graceful_without_message(self):
        """exit_graceful() should exit with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            exit_graceful()

        assert exc_info.value.code == EXIT_NON_BLOCKING

    def test_exit_graceful_with_message(self, caplog):
        """exit_graceful() should log message if provided."""
        caplog.set_level(logging.WARNING)

        with pytest.raises(SystemExit) as exc_info:
            exit_graceful("Test graceful exit")

        assert exc_info.value.code == EXIT_NON_BLOCKING

        # Verify structured logging
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "WARNING"
        assert record.message == "graceful_exit"
        assert hasattr(record, "reason")
        assert record.reason == "Test graceful exit"

    def test_exit_graceful_message_in_extras(self, caplog):
        """exit_graceful() message should be in extras dict as 'reason'."""
        caplog.set_level(logging.WARNING)

        with pytest.raises(SystemExit):
            exit_graceful("Custom exit message")

        record = caplog.records[0]
        # The extras dict should contain the reason (not "message" - reserved)
        assert hasattr(record, "reason")
        assert record.reason == "Custom exit message"


class TestRealWorldScenarios:
    """Test realistic hook scenarios."""

    def test_hook_with_network_timeout(self):
        """Simulate network timeout in hook."""

        @graceful_hook
        def network_hook():
            raise TimeoutError("Connection timed out")

        with pytest.raises(SystemExit) as exc_info:
            network_hook()

        assert exc_info.value.code == EXIT_NON_BLOCKING

    def test_hook_with_file_not_found(self):
        """Simulate file operation failure in hook."""

        @graceful_hook
        def file_hook():
            raise FileNotFoundError("Config file missing")

        with pytest.raises(SystemExit) as exc_info:
            file_hook()

        assert exc_info.value.code == EXIT_NON_BLOCKING

    def test_hook_with_nested_function_calls(self):
        """Decorator should catch exceptions from nested calls."""

        def inner_func():
            raise ValueError("Inner failure")

        @graceful_hook
        def outer_func():
            inner_func()

        with pytest.raises(SystemExit) as exc_info:
            outer_func()

        assert exc_info.value.code == EXIT_NON_BLOCKING
