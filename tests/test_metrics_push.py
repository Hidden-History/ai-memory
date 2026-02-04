"""Tests for metrics push functions.

Tests verify async fork pattern and graceful degradation.
Note: PUSHGATEWAY_ENABLED tests require env var set before import.
"""

import os
import sys
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.metrics_push import (
    VALID_STATUSES,
    _validate_label,
    push_capture_metrics_async,
    push_context_injection_metrics_async,
    push_embedding_metrics_async,
    push_failure_metrics_async,
    push_retrieval_metrics_async,
    push_token_metrics_async,
    push_trigger_metrics_async,
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
            push_context_injection_metrics_async(
                "SessionStart", "discussions", "test-project", 500
            )
            mock_popen.assert_called_once()

    def test_project_label_included_in_metrics(self):
        """Verify project label is passed to subprocess (BUG-046 fix verification)."""
        with patch("subprocess.Popen") as mock_popen:
            push_context_injection_metrics_async(
                "SessionStart", "code-patterns", "my-project", 1500
            )

            # Verify subprocess was called
            assert mock_popen.called

            # Extract the command passed to subprocess
            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]  # [sys.executable, '-c', '<script>']

            # Verify the metrics data dict includes all required fields
            assert '"hook_type": "SessionStart"' in inline_script
            assert '"collection": "code-patterns"' in inline_script
            assert '"project": "my-project"' in inline_script
            assert '"token_count": 1500' in inline_script


class TestPushCaptureMetrics:
    """Tests for capture metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used (CRIT-1 fix verification)."""
        with patch("subprocess.Popen") as mock_popen:
            push_capture_metrics_async(
                "PostToolUse", "success", "test-project", "code-patterns", 1
            )
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
                status="success", embedding_type="dense", duration_seconds=0.5
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
                duration_seconds=0.5,
            )
            assert "unexpected_label_value" in caplog.text

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            # Should not raise exception
            push_embedding_metrics_async(
                status="success", embedding_type="dense", duration_seconds=0.5
            )
            assert "metrics_fork_failed" in caplog.text


class TestPushRetrievalMetrics:
    """Tests for retrieval metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used."""
        with patch("subprocess.Popen") as mock_popen:
            push_retrieval_metrics_async(
                collection="code-patterns", status="success", duration_seconds=0.3
            )
            mock_popen.assert_called_once()

    def test_validates_collection(self, caplog):
        """Test collection validation warns on unexpected value."""
        with patch("subprocess.Popen"):
            push_retrieval_metrics_async(
                collection="unknown-collection",  # Not in VALID_COLLECTIONS
                status="success",
                duration_seconds=0.3,
            )
            assert "unexpected_label_value" in caplog.text

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            push_retrieval_metrics_async(
                collection="code-patterns", status="success", duration_seconds=0.3
            )
            assert "metrics_fork_failed" in caplog.text


class TestPushFailureMetrics:
    """Tests for failure metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used."""
        with patch("subprocess.Popen") as mock_popen:
            push_failure_metrics_async(
                component="embedding", error_code="EMBEDDING_TIMEOUT"
            )
            mock_popen.assert_called_once()

    def test_validates_component(self, caplog):
        """Test component validation warns on unexpected value."""
        with patch("subprocess.Popen"):
            push_failure_metrics_async(
                component="unknown_component",  # Not in VALID_COMPONENTS
                error_code="EMBEDDING_TIMEOUT",
            )
            assert "unexpected_label_value" in caplog.text

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            push_failure_metrics_async(
                component="embedding", error_code="EMBEDDING_TIMEOUT"
            )
            assert "metrics_fork_failed" in caplog.text


# ==============================================================================
# NEW NFR PUSH FUNCTION TESTS (MED-3)
# ==============================================================================


class TestPushHookMetricsWithProject:
    """Tests for hook metrics push with project label (CRIT-1 fix)."""

    def test_async_push_includes_project(self):
        """Verify project label is passed to subprocess."""
        from memory.metrics_push import push_hook_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_hook_metrics_async(
                hook_name="session_start",
                duration_seconds=0.3,
                success=True,
                project="test-project",
            )
            mock_popen.assert_called_once()

            # Extract the command passed to subprocess
            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]  # [sys.executable, '-c', '<script>']

            # Verify the metrics data dict includes project
            assert '"project": "test-project"' in inline_script
            assert '["hook_type", "status", "project"]' in inline_script

    def test_default_project_is_unknown(self):
        """Verify default project is 'unknown' when not specified."""
        from memory.metrics_push import push_hook_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_hook_metrics_async(
                hook_name="session_start",
                duration_seconds=0.3,
                success=True,
            )
            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]
            assert '"project": "unknown"' in inline_script


class TestPushDedupDurationMetrics:
    """Tests for NFR-P4 dedup duration metric push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used for dedup duration."""
        from memory.metrics_push import push_dedup_duration_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_dedup_duration_metrics_async(
                collection="code-patterns",
                project="test-project",
                duration_seconds=0.05,
            )
            mock_popen.assert_called_once()

    def test_includes_collection_and_project_labels(self):
        """Verify collection and project labels are passed."""
        from memory.metrics_push import push_dedup_duration_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_dedup_duration_metrics_async(
                collection="discussions",
                project="my-project",
                duration_seconds=0.08,
            )

            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]

            assert '"collection": "discussions"' in inline_script
            assert '"project": "my-project"' in inline_script
            assert "aimemory_dedup_check_duration_seconds" in inline_script

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        from memory.metrics_push import push_dedup_duration_metrics_async

        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            push_dedup_duration_metrics_async(
                collection="code-patterns",
                project="test-project",
                duration_seconds=0.05,
            )
            assert "metrics_fork_failed" in caplog.text


class TestPushSessionInjectionMetrics:
    """Tests for NFR-P3 session injection duration metric push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used for session injection."""
        from memory.metrics_push import push_session_injection_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_session_injection_metrics_async(
                project="test-project",
                duration_seconds=1.5,
            )
            mock_popen.assert_called_once()

    def test_includes_project_label(self):
        """Verify project label is passed to subprocess."""
        from memory.metrics_push import push_session_injection_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_session_injection_metrics_async(
                project="my-project",
                duration_seconds=2.0,
            )

            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]

            assert '"project": "my-project"' in inline_script
            assert "aimemory_session_injection_duration_seconds" in inline_script

    def test_fork_failure_logged(self, caplog):
        """Verify fork failures are logged gracefully."""
        from memory.metrics_push import push_session_injection_metrics_async

        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            push_session_injection_metrics_async(
                project="test-project",
                duration_seconds=1.5,
            )
            assert "metrics_fork_failed" in caplog.text


class TestPushDeduplicationMetrics:
    """Tests for deduplication event counter push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used for deduplication events."""
        from memory.metrics_push import push_deduplication_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_deduplication_metrics_async(
                action="skipped_duplicate",
                collection="code-patterns",
                project="test-project",
            )
            mock_popen.assert_called_once()

    def test_includes_action_collection_project_labels(self):
        """Verify all three labels are passed."""
        from memory.metrics_push import push_deduplication_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_deduplication_metrics_async(
                action="stored",
                collection="discussions",
                project="my-project",
            )

            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]

            assert '"action": "stored"' in inline_script
            assert '"collection": "discussions"' in inline_script
            assert '"project": "my-project"' in inline_script


class TestPushQueueMetrics:
    """Tests for queue size gauge push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used for queue metrics."""
        from memory.metrics_push import push_queue_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_queue_metrics_async(
                pending_count=5,
                exhausted_count=2,
                ready_count=3,
            )
            mock_popen.assert_called_once()


class TestPushSkillMetrics:
    """Tests for skill invocation metrics push."""

    def test_async_push_uses_subprocess(self):
        """Verify fork pattern is used for skill metrics."""
        from memory.metrics_push import push_skill_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_skill_metrics_async(
                skill_name="search-memory",
                status="success",
                duration_seconds=1.2,
            )
            mock_popen.assert_called_once()

    def test_includes_skill_name_and_status(self):
        """Verify skill_name and status labels are passed."""
        from memory.metrics_push import push_skill_metrics_async

        with patch("subprocess.Popen") as mock_popen:
            push_skill_metrics_async(
                skill_name="memory-status",
                status="empty",
                duration_seconds=0.5,
            )

            call_args = mock_popen.call_args[0][0]
            inline_script = call_args[2]

            assert '"skill_name": "memory-status"' in inline_script
            assert '"status": "empty"' in inline_script
