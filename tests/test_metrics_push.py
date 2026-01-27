"""Tests for metrics push functions.

Tests verify async fork pattern and graceful degradation.
Note: PUSHGATEWAY_ENABLED tests require env var set before import.
"""

import sys
import os
import pytest
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory.metrics_push import (
    push_trigger_metrics_async,
    push_token_metrics_async,
    push_context_injection_metrics_async,
    push_capture_metrics_async,
    push_embedding_metrics_async,
    push_retrieval_metrics_async,
    push_failure_metrics_async,
    _validate_label,
    VALID_STATUSES,
    VALID_EMBEDDING_TYPES,
    VALID_COLLECTIONS,
    VALID_COMPONENTS,
)


class TestPushTriggerMetrics:
    """Tests for trigger metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used (CRIT-1 fix verification)."""
        with patch("subprocess.Popen") as mock_popen:
            push_trigger_metrics_async("decision", "success", "test-project", 2)
            mock_popen.assert_called_once()

            # Verify subprocess args contain python executable and -c flag
            call_args = mock_popen.call_args
            assert sys.executable in call_args[0][0]
            assert "-c" in call_args[0][0]
            # Verify fire-and-forget (stdout/stderr devnull)
            assert call_args[1]["stdout"] == -3  # subprocess.DEVNULL
            assert call_args[1]["stderr"] == -3

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully (CRIT-2 fix verification)."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            # Should not raise exception
            push_trigger_metrics_async("decision", "success", "test-project", 2)
            assert "metrics_fork_failed" in caplog.text


class TestPushTokenMetrics:
    """Tests for token metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used (CRIT-1 fix verification)."""
        with patch("subprocess.Popen") as mock_popen:
            push_token_metrics_async("injection", "output", "test-project", 1000)
            mock_popen.assert_called_once()


class TestPushContextInjectionMetrics:
    """Tests for context injection metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used (CRIT-1 fix verification)."""
        with patch("subprocess.Popen") as mock_popen:
            push_context_injection_metrics_async("SessionStart", "discussions", 500)
            mock_popen.assert_called_once()


class TestPushCaptureMetrics:
    """Tests for capture metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used (CRIT-1 fix verification)."""
        with patch("subprocess.Popen") as mock_popen:
            push_capture_metrics_async("PostToolUse", "success", "test-project", "code-patterns", 1)
            mock_popen.assert_called_once()


class TestValidateLabel:
    """Tests for label validation helper (HIGH-1 fix verification)."""

    def test_valid_label_unchanged(self):
        """Valid labels pass through unchanged."""
        result = _validate_label("success", "status", VALID_STATUSES)
        assert result == "success"

    def test_invalid_type_returns_unknown(self, caplog):
        """Non-string values return 'unknown'."""
        result = _validate_label(None, "status", VALID_STATUSES)
        assert result == "unknown"
        assert "invalid_label_value" in caplog.text

    def test_unexpected_value_logged(self, caplog):
        """Unexpected values are logged but allowed."""
        result = _validate_label("weird_status", "status", VALID_STATUSES)
        assert result == "weird_status"  # Still allowed
        assert "unexpected_label_value" in caplog.text

    def test_no_allowed_set_skips_validation(self):
        """Validation skipped when no allowed set provided."""
        result = _validate_label("any-value", "param")
        assert result == "any-value"


class TestPushEmbeddingMetrics:
    """Tests for embedding metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used."""
        with patch("subprocess.Popen") as mock_popen:
            push_embedding_metrics_async(
                status="success",
                embedding_type="dense",
                duration_seconds=0.5
            )
            mock_popen.assert_called_once()

            # Verify subprocess args contain python executable and -c flag
            call_args = mock_popen.call_args
            assert sys.executable in call_args[0][0]
            assert "-c" in call_args[0][0]
            # Verify fire-and-forget (stdout/stderr devnull)
            assert call_args[1]["stdout"] == -3  # subprocess.DEVNULL
            assert call_args[1]["stderr"] == -3

    def test_validates_embedding_type(self, caplog):
        """Test embedding_type validation warns on unexpected value."""
        with patch("subprocess.Popen"):
            push_embedding_metrics_async(
                status="success",
                embedding_type="unknown_type",  # Not in VALID_EMBEDDING_TYPES
                duration_seconds=0.5
            )
            assert "unexpected_label_value" in caplog.text

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            # Should not raise exception
            push_embedding_metrics_async(
                status="success",
                embedding_type="dense",
                duration_seconds=0.5
            )
            assert "metrics_fork_failed" in caplog.text


class TestPushRetrievalMetrics:
    """Tests for retrieval metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used."""
        with patch("subprocess.Popen") as mock_popen:
            push_retrieval_metrics_async(
                collection="code-patterns",
                status="success",
                duration_seconds=0.3
            )
            mock_popen.assert_called_once()

    def test_validates_collection(self, caplog):
        """Test collection validation warns on unexpected value."""
        with patch("subprocess.Popen"):
            push_retrieval_metrics_async(
                collection="unknown-collection",  # Not in VALID_COLLECTIONS
                status="success",
                duration_seconds=0.3
            )
            assert "unexpected_label_value" in caplog.text

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            push_retrieval_metrics_async(
                collection="code-patterns",
                status="success",
                duration_seconds=0.3
            )
            assert "metrics_fork_failed" in caplog.text


class TestPushFailureMetrics:
    """Tests for failure metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used."""
        with patch("subprocess.Popen") as mock_popen:
            push_failure_metrics_async(
                component="embedding",
                error_code="EMBEDDING_TIMEOUT"
            )
            mock_popen.assert_called_once()

    def test_validates_component(self, caplog):
        """Test component validation warns on unexpected value."""
        with patch("subprocess.Popen"):
            push_failure_metrics_async(
                component="unknown_component",  # Not in VALID_COMPONENTS
                error_code="EMBEDDING_TIMEOUT"
            )
            assert "unexpected_label_value" in caplog.text

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            push_failure_metrics_async(
                component="embedding",
                error_code="EMBEDDING_TIMEOUT"
            )
            assert "metrics_fork_failed" in caplog.text
