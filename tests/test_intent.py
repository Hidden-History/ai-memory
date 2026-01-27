"""Tests for intent detection module.

Tests intent detection, collection mapping, and type filtering for V2.0 cascading search.
"""

import pytest

from src.memory.intent import (
    IntentType,
    detect_intent,
    get_target_collection,
    get_target_types,
)
from src.memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
)


class TestDetectIntent:
    """Tests for detect_intent() function."""

    def test_detect_intent_none_input(self):
        """None input returns UNKNOWN."""
        assert detect_intent(None) == IntentType.UNKNOWN

    def test_detect_intent_empty_string(self):
        """Empty string returns UNKNOWN."""
        assert detect_intent("") == IntentType.UNKNOWN
        assert detect_intent("   ") == IntentType.UNKNOWN

    def test_detect_intent_how_queries(self):
        """HOW queries detected correctly."""
        how_queries = [
            "how do I implement authentication",
            "how to configure the database",
            "implement a retry mechanism",
            "build an error handler",
            "create a singleton pattern",
            "fix the connection issue",
        ]
        for query in how_queries:
            assert detect_intent(query) == IntentType.HOW, f"Failed for: {query}"

    def test_detect_intent_what_queries(self):
        """WHAT queries detected correctly."""
        what_queries = [
            "what is the naming convention",
            "what port does the database use",
            "which framework should I use",
            "convention for imports",
            "standard for error messages",
            "rule for variable names",
        ]
        for query in what_queries:
            assert detect_intent(query) == IntentType.WHAT, f"Failed for: {query}"

    def test_detect_intent_why_queries(self):
        """WHY queries detected correctly."""
        why_queries = [
            "why did we choose PostgreSQL",
            "why do we use this pattern",
            "decision about the architecture",
            "rationale for using microservices",
            "reason for this approach",
            "decided to use async",
        ]
        for query in why_queries:
            assert detect_intent(query) == IntentType.WHY, f"Failed for: {query}"

    def test_detect_intent_unknown_queries(self):
        """Ambiguous queries return UNKNOWN."""
        unknown_queries = [
            "hello world",
            "test query",
            "random text here",
            "foo bar baz",
        ]
        for query in unknown_queries:
            assert detect_intent(query) == IntentType.UNKNOWN, f"Failed for: {query}"

    def test_detect_intent_case_insensitive(self):
        """Intent detection is case-insensitive."""
        assert detect_intent("HOW DO I IMPLEMENT") == IntentType.HOW
        assert detect_intent("What Port") == IntentType.WHAT
        assert detect_intent("WHY DID we decide") == IntentType.WHY


class TestGetTargetCollection:
    """Tests for get_target_collection() function."""

    def test_how_maps_to_code_patterns(self):
        """HOW intent maps to code-patterns collection."""
        assert get_target_collection(IntentType.HOW) == COLLECTION_CODE_PATTERNS

    def test_what_maps_to_conventions(self):
        """WHAT intent maps to conventions collection."""
        assert get_target_collection(IntentType.WHAT) == COLLECTION_CONVENTIONS

    def test_why_maps_to_discussions(self):
        """WHY intent maps to discussions collection."""
        assert get_target_collection(IntentType.WHY) == COLLECTION_DISCUSSIONS

    def test_unknown_maps_to_discussions(self):
        """UNKNOWN intent defaults to discussions collection."""
        assert get_target_collection(IntentType.UNKNOWN) == COLLECTION_DISCUSSIONS


class TestGetTargetTypes:
    """Tests for get_target_types() function."""

    def test_how_returns_implementation_types(self):
        """HOW intent returns implementation-related types."""
        types = get_target_types(IntentType.HOW)
        assert isinstance(types, list)
        assert len(types) > 0
        # Should include implementation-related types
        expected_types = ["implementation", "error_fix", "refactor", "file_pattern"]
        for expected in expected_types:
            assert expected in types, f"Missing type: {expected}"

    def test_what_returns_convention_types(self):
        """WHAT intent returns convention-related types."""
        types = get_target_types(IntentType.WHAT)
        assert isinstance(types, list)
        assert len(types) > 0
        # Should include convention-related types
        expected_types = ["rule", "guideline", "port", "naming"]
        for expected in expected_types:
            assert expected in types, f"Missing type: {expected}"

    def test_why_returns_discussion_types(self):
        """WHY intent returns discussion-related types."""
        types = get_target_types(IntentType.WHY)
        assert isinstance(types, list)
        assert len(types) > 0
        # Should include discussion-related types
        expected_types = ["decision", "session", "blocker", "preference"]
        for expected in expected_types:
            assert expected in types, f"Missing type: {expected}"

    def test_unknown_returns_empty_list(self):
        """UNKNOWN intent returns empty list (no type filter)."""
        types = get_target_types(IntentType.UNKNOWN)
        assert types == []
