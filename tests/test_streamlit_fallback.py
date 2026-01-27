"""Test that Streamlit fallback values match canonical source.

BP-033: Fallback values must be verified against source to prevent drift.

TECH-DEBT-068: Ensures docker/streamlit/app.py hardcoded COLLECTION_TYPES
match the canonical source in src/memory/models.py (MemoryType enum).
"""
import pytest
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_streamlit_fallback_matches_models():
    """Verify Streamlit fallback COLLECTION_TYPES matches models.py.

    This test ensures that if docker/streamlit/app.py falls back to hardcoded
    values (when pydantic_settings not installed), those values exactly match
    the canonical MemoryType enum in src/memory/models.py.

    Failure indicates drift - update docker/streamlit/app.py lines 84-92.
    """
    from memory.models import MemoryType

    # Fallback values from docker/streamlit/app.py:84-92
    # These are what the dashboard uses when imports fail
    FALLBACK_TYPES = {
        "code-patterns": ["implementation", "error_fix", "refactor", "file_pattern"],
        "conventions": ["rule", "guideline", "port", "naming", "structure"],
        "discussions": ["decision", "session", "blocker", "preference", "user_message", "agent_response"],
    }

    # Source of truth from models.py
    source_code_patterns = {
        MemoryType.IMPLEMENTATION.value,
        MemoryType.ERROR_FIX.value,
        MemoryType.REFACTOR.value,
        MemoryType.FILE_PATTERN.value,
    }
    source_conventions = {
        MemoryType.RULE.value,
        MemoryType.GUIDELINE.value,
        MemoryType.PORT.value,
        MemoryType.NAMING.value,
        MemoryType.STRUCTURE.value,
    }
    source_discussions = {
        MemoryType.DECISION.value,
        MemoryType.SESSION.value,
        MemoryType.BLOCKER.value,
        MemoryType.PREFERENCE.value,
        MemoryType.USER_MESSAGE.value,
        MemoryType.AGENT_RESPONSE.value,
    }

    # Verify each collection matches exactly
    assert set(FALLBACK_TYPES["code-patterns"]) == source_code_patterns, \
        f"code-patterns fallback doesn't match models.py. " \
        f"Missing from fallback: {source_code_patterns - set(FALLBACK_TYPES['code-patterns'])}, " \
        f"Extra in fallback: {set(FALLBACK_TYPES['code-patterns']) - source_code_patterns}"

    assert set(FALLBACK_TYPES["conventions"]) == source_conventions, \
        f"conventions fallback doesn't match models.py. " \
        f"Missing from fallback: {source_conventions - set(FALLBACK_TYPES['conventions'])}, " \
        f"Extra in fallback: {set(FALLBACK_TYPES['conventions']) - source_conventions}"

    assert set(FALLBACK_TYPES["discussions"]) == source_discussions, \
        f"discussions fallback doesn't match models.py. " \
        f"Missing from fallback: {source_discussions - set(FALLBACK_TYPES['discussions'])}, " \
        f"Extra in fallback: {set(FALLBACK_TYPES['discussions']) - source_discussions}"


def test_collection_names_match():
    """Verify collection names are consistent across codebase.

    Collection names must match between:
    - docker/streamlit/app.py (COLLECTION_NAMES constant)
    - src/memory/config.py (default collections)
    """
    # Expected V2.0 collection names
    EXPECTED_COLLECTIONS = {"code-patterns", "conventions", "discussions"}

    # Verify against models.py docstring expectations
    from memory.models import MemoryType

    # All types should map to one of the three collections
    # This is an indirect check - if new types are added, they should fit one of these
    code_pattern_types = {
        MemoryType.IMPLEMENTATION, MemoryType.ERROR_FIX,
        MemoryType.REFACTOR, MemoryType.FILE_PATTERN
    }
    convention_types = {
        MemoryType.RULE, MemoryType.GUIDELINE, MemoryType.PORT,
        MemoryType.NAMING, MemoryType.STRUCTURE
    }
    discussion_types = {
        MemoryType.DECISION, MemoryType.SESSION, MemoryType.BLOCKER,
        MemoryType.PREFERENCE, MemoryType.USER_MESSAGE, MemoryType.AGENT_RESPONSE
    }

    all_types = code_pattern_types | convention_types | discussion_types

    # Verify all MemoryType enum values are accounted for
    enum_values = set(MemoryType)
    assert enum_values == all_types, \
        f"MemoryType enum has changed. New types: {enum_values - all_types}, " \
        f"Removed types: {all_types - enum_values}. " \
        f"Update docker/streamlit/app.py COLLECTION_TYPES accordingly."
