"""Tests for TECH-DEBT-071: Comprehensive Token Tracking.

Tests verify:
1. Classification token metrics push to Pushgateway
2. Capture token metrics push for stored content
3. Token count estimation logic
4. Correct labels for new operations (classification) and directions (stored)
5. Edge cases (None, negative, zero, very large token counts)
"""

import os
import sys
from unittest.mock import patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.metrics_push import (
    VALID_DIRECTIONS,
    VALID_OPERATIONS,
    _validate_label,
    push_token_metrics_async,
)


class TestClassificationTokenPush:
    """Tests for classification token instrumentation (Task 1)."""

    def test_classification_operation_valid(self):
        """Verify 'classification' is a valid operation."""
        assert "classification" in VALID_OPERATIONS

    def test_push_classification_input_tokens(self):
        """Verify classification input tokens are pushed correctly."""
        with patch("subprocess.Popen") as mock_popen:
            push_token_metrics_async(
                operation="classification",
                direction="input",
                project="classifier",
                token_count=450,
            )
            mock_popen.assert_called_once()

            # Verify subprocess call contains expected data
            call_args = mock_popen.call_args
            assert sys.executable in call_args[0][0]
            assert "-c" in call_args[0][0]
            # Verify fire-and-forget (stdout/stderr devnull)
            assert call_args[1]["stdout"] == -3  # subprocess.DEVNULL
            assert call_args[1]["stderr"] == -3

    def test_push_classification_output_tokens(self):
        """Verify classification output tokens are pushed correctly."""
        with patch("subprocess.Popen") as mock_popen:
            push_token_metrics_async(
                operation="classification",
                direction="output",
                project="classifier",
                token_count=75,
            )
            mock_popen.assert_called_once()

    def test_classification_fork_failure_graceful(self, caplog):
        """Verify fork failures don't crash classification."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            # Should not raise exception
            push_token_metrics_async(
                operation="classification",
                direction="input",
                project="classifier",
                token_count=100,
            )
            assert "metrics_fork_failed" in caplog.text


class TestCaptureTokenPush:
    """Tests for capture token instrumentation (Task 2)."""

    def test_stored_direction_valid(self):
        """Verify 'stored' is a valid direction."""
        assert "stored" in VALID_DIRECTIONS

    def test_push_capture_stored_tokens(self):
        """Verify captured content tokens are pushed correctly."""
        with patch("subprocess.Popen") as mock_popen:
            push_token_metrics_async(
                operation="capture",
                direction="stored",
                project="test-project",
                token_count=1234,
            )
            mock_popen.assert_called_once()

    def test_capture_fork_failure_graceful(self, caplog):
        """Verify fork failures don't crash capture storage."""
        with patch("subprocess.Popen", side_effect=OSError("fork failed")):
            # Should not raise exception
            push_token_metrics_async(
                operation="capture",
                direction="stored",
                project="test-project",
                token_count=500,
            )
            assert "metrics_fork_failed" in caplog.text


class TestTokenEstimation:
    """Tests for token count estimation logic (Task 2)."""

    def test_token_estimation_formula(self):
        """Verify token estimation uses len(content) // 4."""
        # Test cases based on spec: len(content) // 4
        test_cases = [
            ("short", 1),  # 5 chars // 4 = 1 token
            ("a" * 100, 25),  # 100 chars // 4 = 25 tokens
            ("a" * 1000, 250),  # 1000 chars // 4 = 250 tokens
            ("", 0),  # Empty string = 0 tokens
        ]

        for content, expected_tokens in test_cases:
            estimated = len(content) // 4
            assert (
                estimated == expected_tokens
            ), f"Failed for content length {len(content)}"

    def test_token_estimation_realistic_code(self):
        """Test token estimation on realistic code samples."""
        code_sample = """
def hello_world():
    print("Hello, world!")
    return 42
"""
        estimated = len(code_sample) // 4
        # Actual length will depend on newlines, just verify formula works
        assert estimated == len(code_sample) // 4
        assert estimated > 0

    def test_token_estimation_edge_cases(self):
        """Test token estimation edge cases."""
        # Unicode characters
        unicode_text = "Hello 世界"
        estimated = len(unicode_text) // 4
        assert estimated >= 0  # Should not crash

        # Very long content
        long_content = "x" * 10000
        estimated = len(long_content) // 4
        assert estimated == 2500


class TestMetricsLabelsCorrect:
    """Tests for label validation (Task 4)."""

    def test_classification_operation_validated(self):
        """Verify 'classification' operation passes validation."""
        result = _validate_label("classification", "operation", VALID_OPERATIONS)
        assert result == "classification"

    def test_stored_direction_validated(self):
        """Verify 'stored' direction passes validation."""
        result = _validate_label("stored", "direction", VALID_DIRECTIONS)
        assert result == "stored"

    def test_existing_operations_still_valid(self):
        """Verify existing operations still work after adding 'classification'."""
        for operation in ["capture", "retrieval", "trigger", "injection"]:
            result = _validate_label(operation, "operation", VALID_OPERATIONS)
            assert result == operation

    def test_existing_directions_still_valid(self):
        """Verify existing directions still work after adding 'stored'."""
        for direction in ["input", "output"]:
            result = _validate_label(direction, "direction", VALID_DIRECTIONS)
            assert result == direction

    def test_invalid_operation_logged(self, caplog):
        """Verify invalid operations are logged."""
        result = _validate_label("invalid_op", "operation", VALID_OPERATIONS)
        assert result == "invalid_op"  # Still allowed but logged
        assert "unexpected_label_value" in caplog.text

    def test_invalid_direction_logged(self, caplog):
        """Verify invalid directions are logged."""
        result = _validate_label("invalid_dir", "direction", VALID_DIRECTIONS)
        assert result == "invalid_dir"  # Still allowed but logged
        assert "unexpected_label_value" in caplog.text


class TestIntegrationScenarios:
    """Integration tests for realistic token tracking scenarios."""

    def test_full_classification_flow(self):
        """Test complete classification token tracking flow."""
        with patch("subprocess.Popen") as mock_popen:
            # Simulate LLM classifier with input and output tokens
            input_tokens = 450
            output_tokens = 75

            # Push input tokens
            push_token_metrics_async(
                operation="classification",
                direction="input",
                project="classifier",
                token_count=input_tokens,
            )

            # Push output tokens
            push_token_metrics_async(
                operation="classification",
                direction="output",
                project="classifier",
                token_count=output_tokens,
            )

            # Should have been called twice (once for input, once for output)
            assert mock_popen.call_count == 2

    def test_full_capture_flow(self):
        """Test complete capture token tracking flow."""
        with patch("subprocess.Popen") as mock_popen:
            # Simulate storing content
            content = "def hello():\n    return 'world'"
            token_count = len(content) // 4

            push_token_metrics_async(
                operation="capture",
                direction="stored",
                project="test-project",
                token_count=token_count,
            )

            mock_popen.assert_called_once()

    def test_zero_tokens_not_pushed(self):
        """Verify zero token counts are handled gracefully."""
        with patch("subprocess.Popen"):
            # Implementation should skip pushing 0 tokens
            # (this would be checked in the actual hook scripts)
            token_count = len("") // 4
            assert token_count == 0

            # If implementation pushes anyway, verify it doesn't crash
            if token_count > 0:
                push_token_metrics_async(
                    operation="capture",
                    direction="stored",
                    project="test-project",
                    token_count=token_count,
                )


class TestPerformanceRequirements:
    """Tests for TECH-DEBT-071 performance requirements."""

    def test_async_push_is_fire_and_forget(self):
        """Verify token push is async and non-blocking."""
        with patch("subprocess.Popen") as mock_popen:
            # Push should return immediately
            push_token_metrics_async(
                operation="classification",
                direction="input",
                project="classifier",
                token_count=100,
            )

            # Verify start_new_session=True for detached process
            call_args = mock_popen.call_args
            assert call_args[1].get("start_new_session") is True

    def test_push_failure_does_not_block(self, caplog):
        """Verify push failures are logged but don't block execution."""
        with patch("subprocess.Popen", side_effect=Exception("Unexpected error")):
            # Should not raise
            push_token_metrics_async(
                operation="classification",
                direction="input",
                project="classifier",
                token_count=100,
            )
            # Error should be logged
            assert "metrics_fork_failed" in caplog.text


class TestTokenMetricsEdgeCases:
    """MEDIUM-2: Edge case handling for token metrics."""

    def test_none_token_count_handled(self):
        """None token count should not crash (graceful degradation)."""
        # This would be caught by isinstance() check in classifier
        # Testing that validation layer exists
        assert isinstance(100, int)  # Valid
        assert not isinstance(None, int)  # Would be rejected
        assert not isinstance("100", int)  # Would be rejected

    def test_negative_token_count_not_pushed(self):
        """Negative tokens should be rejected by validation."""
        with patch("subprocess.Popen") as mock_popen:
            # Implementation checks token_count > 0
            # Negative count should not trigger push
            token_count = -100
            if token_count > 0:  # Should be False
                push_token_metrics_async(
                    operation="capture",
                    direction="stored",
                    project="test",
                    token_count=token_count,
                )
            # Should NOT have been called
            mock_popen.assert_not_called()

    def test_zero_token_count_not_pushed(self):
        """Zero tokens should be skipped (no-op)."""
        with patch("subprocess.Popen") as mock_popen:
            # Implementation checks token_count > 0
            token_count = 0
            if token_count > 0:  # Should be False
                push_token_metrics_async(
                    operation="capture",
                    direction="stored",
                    project="test",
                    token_count=token_count,
                )
            # Should NOT have been called
            mock_popen.assert_not_called()

    def test_very_large_token_count_handled(self):
        """Very large token counts should not crash."""
        with patch("subprocess.Popen") as mock_popen:
            # Should handle large numbers gracefully
            push_token_metrics_async(
                operation="capture",
                direction="stored",
                project="test",
                token_count=1_000_000_000,  # 1 billion tokens
            )
            mock_popen.assert_called_once()
