"""Tests for Streamlit V2.0 type system (TECH-DEBT-014-D).

Validates that the Streamlit dashboard's COLLECTION_TYPES constant correctly
matches the canonical MemoryType enum from src/memory/models.py.

C3: Zero test coverage for Wave 2 features (fixed).
"""

import os
import sys

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from memory.models import MemoryType

# Import COLLECTION_TYPES from Streamlit app - handle import failures gracefully
try:
    sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "..", "docker", "streamlit")
    )
    from app import COLLECTION_NAMES, COLLECTION_TYPES

    STREAMLIT_IMPORTED = True
except ImportError as e:
    STREAMLIT_IMPORTED = False
    IMPORT_ERROR = str(e)


class TestCollectionTypesValidation:
    """Tests for COLLECTION_TYPES constant validation."""

    @pytest.mark.skipif(
        not STREAMLIT_IMPORTED,
        reason=f"Cannot import Streamlit app: {IMPORT_ERROR if not STREAMLIT_IMPORTED else ''}",
    )
    def test_collection_types_match_memory_type_enum(self):
        """Verify all COLLECTION_TYPES values exist in MemoryType enum.

        C3.1: Ensure no typos or drift between UI and backend type definitions.
        """
        valid_types = {t.value for t in MemoryType}

        for collection, types in COLLECTION_TYPES.items():
            for mem_type in types:
                assert mem_type in valid_types, (
                    f"Type '{mem_type}' in collection '{collection}' "
                    f"not found in MemoryType enum. Valid types: {valid_types}"
                )

    @pytest.mark.skipif(not STREAMLIT_IMPORTED, reason="Cannot import Streamlit app")
    def test_all_collections_have_types(self):
        """Verify all collections have type definitions.

        C3.2: Detect missing collection configuration (L2 validation).
        """
        for collection in COLLECTION_NAMES:
            assert (
                collection in COLLECTION_TYPES
            ), f"Collection '{collection}' missing from COLLECTION_TYPES"
            assert (
                len(COLLECTION_TYPES[collection]) > 0
            ), f"Collection '{collection}' has empty type list"

    @pytest.mark.skipif(not STREAMLIT_IMPORTED, reason="Cannot import Streamlit app")
    def test_no_duplicate_types_across_collections(self):
        """Verify types are not duplicated across collections.

        C3.3: V2.0 spec requires each type to belong to exactly one collection.
        """
        seen = {}
        for collection, types in COLLECTION_TYPES.items():
            for mem_type in types:
                if mem_type in seen:
                    pytest.fail(
                        f"Type '{mem_type}' appears in both "
                        f"'{seen[mem_type]}' and '{collection}' collections. "
                        f"V2.0 spec requires types to be unique per collection."
                    )
                seen[mem_type] = collection

    def test_memory_type_enum_coverage(self):
        """Verify all MemoryType values are assigned to a collection.

        C3.4: Detect if new types are added to enum but not to UI.
        """
        if not STREAMLIT_IMPORTED:
            pytest.skip("Cannot import Streamlit app")

        all_assigned = set()
        for types in COLLECTION_TYPES.values():
            all_assigned.update(types)

        all_enum_values = {t.value for t in MemoryType}
        missing = all_enum_values - all_assigned

        assert not missing, (
            f"MemoryType enum values not assigned to any collection: {missing}. "
            f"Update COLLECTION_TYPES in docker/streamlit/app.py"
        )

    @pytest.mark.skipif(not STREAMLIT_IMPORTED, reason="Cannot import Streamlit app")
    def test_expected_collection_structure(self):
        """Verify V2.0 collection structure (3 collections with specific types).

        C3.5: Validate the exact V2.0 spec structure.
        """
        assert set(COLLECTION_TYPES.keys()) == {
            "code-patterns",
            "conventions",
            "discussions",
        }, "V2.0 spec requires exactly 3 collections: code-patterns, conventions, discussions"

        # V2.0 spec type counts per collection
        assert (
            len(COLLECTION_TYPES["code-patterns"]) == 4
        ), "code-patterns should have 4 types"
        assert (
            len(COLLECTION_TYPES["conventions"]) == 5
        ), "conventions should have 5 types"
        assert (
            len(COLLECTION_TYPES["discussions"]) == 6
        ), "discussions should have 6 types"

    @pytest.mark.skipif(not STREAMLIT_IMPORTED, reason="Cannot import Streamlit app")
    def test_code_patterns_types(self):
        """Verify code-patterns collection has correct types.

        C3.6: Validate code-patterns collection (HOW things are built).
        """
        expected = {"implementation", "error_fix", "refactor", "file_pattern"}
        actual = set(COLLECTION_TYPES["code-patterns"])

        assert (
            actual == expected
        ), f"code-patterns types mismatch. Expected: {expected}, Got: {actual}"

    @pytest.mark.skipif(not STREAMLIT_IMPORTED, reason="Cannot import Streamlit app")
    def test_conventions_types(self):
        """Verify conventions collection has correct types.

        C3.7: Validate conventions collection (WHAT rules to follow).
        """
        expected = {"rule", "guideline", "port", "naming", "structure"}
        actual = set(COLLECTION_TYPES["conventions"])

        assert (
            actual == expected
        ), f"conventions types mismatch. Expected: {expected}, Got: {actual}"

    @pytest.mark.skipif(not STREAMLIT_IMPORTED, reason="Cannot import Streamlit app")
    def test_discussions_types(self):
        """Verify discussions collection has correct types.

        C3.8: Validate discussions collection (WHY things were decided).
        """
        expected = {
            "decision",
            "session",
            "blocker",
            "preference",
            "user_message",
            "agent_response",
        }
        actual = set(COLLECTION_TYPES["discussions"])

        assert (
            actual == expected
        ), f"discussions types mismatch. Expected: {expected}, Got: {actual}"


class TestMemoryTypeEnumStructure:
    """Tests for MemoryType enum structure (baseline validation)."""

    def test_memory_type_enum_exists(self):
        """Verify MemoryType enum is importable."""
        assert MemoryType is not None
        assert hasattr(MemoryType, "IMPLEMENTATION")
        assert hasattr(MemoryType, "RULE")
        assert hasattr(MemoryType, "DECISION")

    def test_memory_type_enum_has_15_types(self):
        """Verify MemoryType enum has exactly 15 types (V2.0 spec).

        4 code-patterns + 5 conventions + 6 discussions = 15 total
        """
        all_types = list(MemoryType)
        assert (
            len(all_types) == 15
        ), f"MemoryType enum should have 15 types (V2.0 spec), got {len(all_types)}"

    def test_memory_type_values_are_lowercase_snake_case(self):
        """Verify all MemoryType values use lowercase snake_case.

        Ensures consistency with Qdrant payload schema.
        """
        for mem_type in MemoryType:
            value = mem_type.value
            assert value.islower(), f"Type value '{value}' should be lowercase"
            assert " " not in value, f"Type value '{value}' should not contain spaces"
            # Allow underscores for multi-word types (error_fix, user_message, etc.)
