"""Tests for content significance checking.

TECH-DEBT-069: LLM-based memory classification system tests.
"""

import pytest
from src.memory.classifier.significance import check_significance
from src.memory.classifier.config import Significance


class TestSignificance:
    """Test content significance checking."""

    def test_skip_short_content(self):
        """Test that very short content is marked as SKIP."""
        assert check_significance("ok") == Significance.SKIP
        assert check_significance("yes") == Significance.SKIP
        assert check_significance("no") == Significance.SKIP
        assert check_significance("  ") == Significance.SKIP

    def test_skip_empty_content(self):
        """Test that empty content is marked as SKIP."""
        assert check_significance("") == Significance.SKIP
        assert check_significance(None) == Significance.SKIP

    def test_skip_acknowledgment_patterns(self):
        """Test that acknowledgment patterns are marked as SKIP."""
        acknowledgments = [
            "ok",
            "okay",
            "yes",
            "no",
            "sure",
            "thanks",
            "thank you",
            "got it",
            "done",
            "yep",
            "nope",
        ]
        for ack in acknowledgments:
            result = check_significance(ack)
            assert result == Significance.SKIP, f"'{ack}' should be SKIP"

    def test_skip_emoji_only(self):
        """Test that emoji-only content is marked as SKIP."""
        # Unicode emoji range
        assert check_significance("👍") == Significance.SKIP
        assert check_significance("✅") == Significance.SKIP
        assert check_significance("🚀") == Significance.SKIP

    def test_low_significance_patterns(self):
        """Test that simple responses are marked as LOW."""
        # Note: Responses must be >= MIN_CONTENT_LENGTH (20 chars) to be evaluated
        low_responses = [
            "sounds good, I'll work on that",
            "will do that right away",
            "on it, starting implementation",
            "understood, proceeding with the plan",
            "acknowledged, will implement this",
        ]
        for response in low_responses:
            result = check_significance(response)
            assert result == Significance.LOW, f"'{response}' should be LOW"

    def test_high_significance_decision(self):
        """Test that decision references are marked as HIGH."""
        decision_texts = [
            "DEC-031 decided to use PostgreSQL",
            "After analysis, we chose option A (see dec-042)",
            "The decision was made in DEC-001",
        ]
        for text in decision_texts:
            result = check_significance(text)
            assert result == Significance.HIGH, f"'{text}' should be HIGH"

    def test_high_significance_blocker(self):
        """Test that blocker references are marked as HIGH."""
        blocker_texts = [
            "BLK-015 is blocking progress",
            "Waiting on external API (blk-023)",
        ]
        for text in blocker_texts:
            result = check_significance(text)
            assert result == Significance.HIGH, f"'{text}' should be HIGH"

    def test_high_significance_error(self):
        """Test that error content is marked as HIGH."""
        error_texts = [
            "Got TypeError: Cannot read property 'map' of undefined",
            "Exception occurred during processing",
            "Traceback shows the issue is in line 42",
        ]
        for text in error_texts:
            result = check_significance(text)
            assert result == Significance.HIGH, f"'{text}' should be HIGH"

    def test_high_significance_rule(self):
        """Test that rule content (MUST/NEVER) is marked as HIGH."""
        rule_texts = [
            "MUST use snake_case for all functions",
            "NEVER commit directly to main branch",
            "ALWAYS validate user input",
            "REQUIRED to add tests for new features",
            "SHALL NOT use deprecated APIs",
        ]
        for text in rule_texts:
            result = check_significance(text)
            assert result == Significance.HIGH, f"'{text}' should be HIGH"

    def test_medium_significance_default(self):
        """Test that normal content defaults to MEDIUM."""
        normal_texts = [
            "After discussing options, we implemented the feature using React",
            "The API endpoint is configured to handle 1000 requests per second",
            "Created new component for user authentication",
            "Updated documentation to reflect recent changes",
        ]
        for text in normal_texts:
            result = check_significance(text)
            assert result == Significance.MEDIUM, f"'{text}' should be MEDIUM"

    def test_whitespace_handling(self):
        """Test that leading/trailing whitespace is handled correctly."""
        assert check_significance("  ok  ") == Significance.SKIP
        assert check_significance("\n\nyes\n\n") == Significance.SKIP
        assert (
            check_significance("  This is meaningful content  ")
            == Significance.MEDIUM
        )
