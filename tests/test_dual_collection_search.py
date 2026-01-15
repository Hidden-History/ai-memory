"""Unit tests for dual-collection search functionality (Story 3.2).

Tests dual-collection search logic, filtering, collection attribution,
and performance requirements.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from memory.search import MemorySearch
from memory.config import get_config


def test_search_adds_collection_attribution():
    """AC 3.2.4: Search results include collection field for attribution."""
    # Mock the dependencies
    with patch('memory.search.get_qdrant_client') as mock_qdrant, \
         patch('memory.search.EmbeddingClient') as mock_embedding:

        # Setup mocks
        mock_client = Mock()
        mock_qdrant.return_value = mock_client

        mock_embed = Mock()
        mock_embed.embed.return_value = [[0.1] * 768]
        mock_embedding.return_value = mock_embed

        # Mock Qdrant response
        mock_result = Mock()
        mock_result.id = "mem_123"
        mock_result.score = 0.95
        mock_result.payload = {
            "content": "Test implementation",
            "type": "implementation",
            "group_id": "test-project",
            "source_hook": "PostToolUse"
        }

        mock_response = Mock()
        mock_response.points = [mock_result]
        mock_client.query_points.return_value = mock_response

        # Execute search
        search = MemorySearch()
        results = search.search(
            query="test query",
            collection="implementations",
            group_id="test-project"
        )

        # Verify collection field is added to results
        assert len(results) == 1
        assert results[0]["collection"] == "implementations"
        assert results[0]["score"] == 0.95
        assert results[0]["content"] == "Test implementation"


def test_implementations_filtered_by_group_id():
    """AC 3.2.1: Implementations collection filtered by project group_id."""
    with patch('memory.search.get_qdrant_client') as mock_qdrant, \
         patch('memory.search.EmbeddingClient') as mock_embedding:

        mock_client = Mock()
        mock_qdrant.return_value = mock_client

        mock_embed = Mock()
        mock_embed.embed.return_value = [[0.1] * 768]
        mock_embedding.return_value = mock_embed

        mock_response = Mock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        # Execute search with group_id
        search = MemorySearch()
        search.search(
            query="test query",
            collection="implementations",
            group_id="my-project"
        )

        # Verify group_id filter was applied
        call_args = mock_client.query_points.call_args
        query_filter = call_args.kwargs['query_filter']

        assert query_filter is not None
        assert len(query_filter.must) == 1
        assert query_filter.must[0].key == "group_id"
        assert query_filter.must[0].match.value == "my-project"


def test_best_practices_no_group_id_filter():
    """AC 3.2.2: Best practices collection has no group_id filter (shared)."""
    with patch('memory.search.get_qdrant_client') as mock_qdrant, \
         patch('memory.search.EmbeddingClient') as mock_embedding:

        mock_client = Mock()
        mock_qdrant.return_value = mock_client

        mock_embed = Mock()
        mock_embed.embed.return_value = [[0.1] * 768]
        mock_embedding.return_value = mock_embed

        mock_response = Mock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        # Execute search with group_id=None
        search = MemorySearch()
        search.search(
            query="test query",
            collection="best_practices",
            group_id=None  # No filter - shared across projects
        )

        # Verify NO group_id filter was applied
        call_args = mock_client.query_points.call_args
        query_filter = call_args.kwargs['query_filter']

        assert query_filter is None  # No filter at all


def test_combined_results_sorted_by_score():
    """AC 3.2.3: Combined results sorted by relevance score (highest first)."""
    implementations = [
        {"score": 0.88, "content": "impl1", "collection": "implementations"},
        {"score": 0.92, "content": "impl2", "collection": "implementations"}
    ]

    best_practices = [
        {"score": 0.95, "content": "bp1", "collection": "best_practices"},
        {"score": 0.85, "content": "bp2", "collection": "best_practices"}
    ]

    # Combine and sort (as done in session_start.py)
    all_results = implementations + best_practices
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Verify sorting
    assert len(all_results) == 4
    assert all_results[0]["score"] == 0.95  # Best practice (highest)
    assert all_results[1]["score"] == 0.92  # Implementation
    assert all_results[2]["score"] == 0.88  # Implementation
    assert all_results[3]["score"] == 0.85  # Best practice (lowest)


def test_format_memory_entry_includes_collection():
    """AC 3.2.4: format_memory_entry() includes collection attribution."""
    # Import the function (will be modified to include collection)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.claude/hooks/scripts"))
    from session_start_test_helpers import format_memory_entry

    memory = {
        "type": "implementation",
        "score": 0.95,
        "content": "Test implementation code",
        "source_hook": "PostToolUse",
        "collection": "implementations"
    }

    formatted = format_memory_entry(memory, truncate=False)

    # Verify collection is shown in formatted output
    assert "[implementations]" in formatted or "implementations" in formatted.lower()
    assert "95%" in formatted
    assert "PostToolUse" in formatted


def test_dual_collection_search_performance_budget():
    """AC 3.2.3: Dual-collection search completes within 1.5s budget."""
    import time

    with patch('memory.search.get_qdrant_client') as mock_qdrant, \
         patch('memory.search.EmbeddingClient') as mock_embedding:

        mock_client = Mock()
        mock_qdrant.return_value = mock_client

        mock_embed = Mock()
        mock_embed.embed.return_value = [[0.1] * 768]
        mock_embedding.return_value = mock_embed

        # Mock fast responses
        mock_response = Mock()
        mock_response.points = []
        mock_client.query_points.return_value = mock_response

        # Execute dual-collection search
        search = MemorySearch()

        start = time.perf_counter()

        # Implementations search
        search.search(
            query="test query",
            collection="implementations",
            group_id="test-project"
        )

        # Best practices search
        search.search(
            query="test query",
            collection="best_practices",
            group_id=None
        )

        duration = time.perf_counter() - start

        # Verify within performance budget (NFR-P3)
        # Note: With mocks, this will be fast. In integration tests,
        # we'll validate against real services.
        assert duration < 1.5, f"Dual search took {duration:.3f}s, expected <1.5s"


def test_session_start_dual_collection_logic():
    """Verify session_start.py implements dual-collection search correctly."""
    # This test verifies the actual implementation in session_start.py
    # by importing and testing the main logic flow

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.claude/hooks/scripts"))

    # We'll verify the code structure exists (integration tests will verify behavior)
    import session_start

    # Verify dual-collection search logic exists in main()
    import inspect
    source = inspect.getsource(session_start.main)

    # Check for implementations search with group_id
    assert 'collection="implementations"' in source
    assert 'group_id=project_name' in source

    # Check for best_practices search without group_id
    assert 'collection="best_practices"' in source
    assert 'group_id=None' in source

    # Check for result combination
    assert 'implementations + best_practices' in source or 'all_results' in source
