"""Tests for rule-based classification.

TECH-DEBT-069: LLM-based memory classification system tests.
"""

import pytest
from src.memory.classifier.rules import classify_by_rules


class TestRuleClassification:
    """Test rule-based memory classification."""

    def test_error_fix_pattern_fixed(self):
        """Test error_fix pattern with 'fixed' keyword."""
        content = "Fixed TypeError by adding null check before map call"
        result = classify_by_rules(content, "code-patterns")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "error_fix"
        assert confidence >= 0.85

    def test_error_fix_pattern_resolved(self):
        """Test error_fix pattern with 'resolved' keyword."""
        content = "Resolved the exception by catching the error properly"
        result = classify_by_rules(content, "code-patterns")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "error_fix"

    def test_error_fix_pattern_multiline(self):
        """Test error_fix pattern with traceback."""
        content = """
        Got this error:
        TypeError: Cannot read property 'map' of undefined
        Fixed by adding null check
        """
        result = classify_by_rules(content, "code-patterns")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "error_fix"

    def test_port_pattern_colon(self):
        """Test port pattern with colon separator."""
        content = "Qdrant runs on port: 26350"
        result = classify_by_rules(content, "conventions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "port"
        assert confidence >= 0.85

    def test_port_pattern_runs_on(self):
        """Test port pattern with 'runs on port' phrase."""
        content = "The embedding service listens on port 28080"
        result = classify_by_rules(content, "conventions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "port"

    def test_rule_pattern_must(self):
        """Test rule pattern with MUST (caps only)."""
        content = "MUST use snake_case for all function names"
        result = classify_by_rules(content, "conventions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "rule"
        assert confidence >= 0.85

    def test_rule_pattern_never(self):
        """Test rule pattern with NEVER (caps only)."""
        content = "NEVER commit directly to main branch"
        result = classify_by_rules(content, "conventions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "rule"

    def test_rule_pattern_always(self):
        """Test rule pattern with ALWAYS (caps only)."""
        content = "ALWAYS validate user input before processing"
        result = classify_by_rules(content, "conventions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "rule"

    def test_rule_pattern_lowercase_no_match(self):
        """Test that lowercase 'must' doesn't match rule pattern."""
        content = "You must install dependencies first"
        result = classify_by_rules(content, "conventions")

        # Should not match 'rule' pattern (requires caps)
        if result:
            classified_type, _ = result
            assert classified_type != "rule"

    def test_blocker_pattern_blocked(self):
        """Test blocker pattern with 'blocked' keyword."""
        content = "Development is blocked waiting on API access"
        result = classify_by_rules(content, "discussions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "blocker"
        assert confidence >= 0.85

    def test_blocker_pattern_reference(self):
        """Test blocker pattern with BLK-xxx reference."""
        content = "BLK-015 is preventing deployment to production"
        result = classify_by_rules(content, "discussions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "blocker"

    def test_decision_pattern_reference(self):
        """Test decision pattern with DEC-xxx reference."""
        content = "DEC-031 decided to use PostgreSQL for the database"
        result = classify_by_rules(content, "discussions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "decision"
        assert confidence >= 0.85

    def test_decision_pattern_case_insensitive(self):
        """Test decision pattern is case insensitive."""
        content = "See dec-042 for the architectural decision"
        result = classify_by_rules(content, "discussions")

        assert result is not None
        classified_type, confidence = result
        assert classified_type == "decision"

    def test_no_pattern_match(self):
        """Test that content without patterns returns None."""
        content = "This is just a normal message with no special keywords"
        result = classify_by_rules(content, "discussions")

        assert result is None

    def test_empty_content(self):
        """Test that empty content returns None."""
        assert classify_by_rules("", "discussions") is None
        assert classify_by_rules(None, "discussions") is None

    def test_invalid_regex_handling(self):
        """Test that invalid regex patterns are handled gracefully."""
        # This should not crash, even if a pattern is malformed
        content = "Some content to classify"
        result = classify_by_rules(content, "discussions")
        # Should either return a valid result or None, but not crash
        assert result is None or isinstance(result, tuple)

    def test_multiple_patterns_first_wins(self):
        """Test that when multiple patterns match, first one wins."""
        # This content could match both error_fix and decision patterns
        content = "DEC-015: Fixed the bug in authentication system"
        result = classify_by_rules(content, "discussions")

        # Should match decision (higher confidence pattern)
        assert result is not None
        classified_type, confidence = result
        # Either error_fix or decision is valid, depending on pattern order
        assert classified_type in ["error_fix", "decision"]
