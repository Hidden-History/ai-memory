"""Unit tests for search module.

Tests MemorySearch class with mocked dependencies following 2025 best practices.
All tests use pytest and follow PEP 8 naming conventions.

Architecture Reference: architecture.md:747-863 (Search Module)
"""

import logging

import pytest
from unittest.mock import Mock, MagicMock, patch
from qdrant_client.models import Filter, FieldCondition, MatchValue

from src.memory.search import MemorySearch
from src.memory.embeddings import EmbeddingError
from src.memory.qdrant_client import QdrantUnavailable


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration for search tests."""
    mock_cfg = Mock()
    mock_cfg.max_retrievals = 5
    mock_cfg.similarity_threshold = 0.7
    monkeypatch.setattr("src.memory.search.get_config", lambda: mock_cfg)
    return mock_cfg


@pytest.fixture
def mock_qdrant_client(monkeypatch):
    """Mock Qdrant client with query_points results.

    Updated for qdrant-client 1.16.2+ API: uses query_points() which returns
    a response object with .points attribute (not direct list from search()).
    """
    mock_client = Mock()

    # Mock search result point
    mock_result = Mock()
    mock_result.id = "mem-123"
    mock_result.score = 0.95
    mock_result.payload = {
        "content": "Test implementation pattern",
        "group_id": "test-project",
        "type": "implementation",
        "source_hook": "PostToolUse",
    }

    # Mock response with .points attribute (query_points API)
    mock_response = Mock()
    mock_response.points = [mock_result]

    mock_client.query_points = Mock(return_value=mock_response)
    monkeypatch.setattr(
        "src.memory.search.get_qdrant_client", lambda x: mock_client
    )
    return mock_client


@pytest.fixture
def mock_embedding_client(monkeypatch):
    """Mock embedding client."""
    mock_ec = Mock()
    mock_ec.embed = Mock(return_value=[[0.1] * 768])  # DEC-010: 768 dimensions
    monkeypatch.setattr("src.memory.search.EmbeddingClient", lambda x: mock_ec)
    return mock_ec


class TestMemorySearchInit:
    """Test MemorySearch initialization."""

    def test_init_with_default_config(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test initialization uses get_config() by default."""
        search = MemorySearch()

        assert search.config is not None
        assert search.client is not None
        assert search.embedding_client is not None


class TestMemorySearchBasic:
    """Test basic search functionality."""

    def test_search_success(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test successful search returns results with scores."""
        search = MemorySearch()

        results = search.search(
            query="test query",
            collection="implementations",
            group_id="test-project",
        )

        # Verify results structure
        assert len(results) == 1
        assert results[0]["id"] == "mem-123"
        assert results[0]["score"] == 0.95
        assert results[0]["content"] == "Test implementation pattern"
        assert results[0]["group_id"] == "test-project"
        assert results[0]["type"] == "implementation"

        # Verify embedding was called
        mock_embedding_client.embed.assert_called_once_with(["test query"])

        # Verify Qdrant search was called
        mock_qdrant_client.query_points.assert_called_once()

    def test_search_uses_config_defaults(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search uses config defaults for limit and threshold."""
        search = MemorySearch()

        search.search(query="test")

        # Verify defaults from config were used
        call_args = mock_qdrant_client.query_points.call_args
        assert call_args.kwargs["limit"] == 5  # mock_config.max_retrievals
        assert call_args.kwargs["score_threshold"] == 0.7  # mock_config.similarity_threshold

    def test_search_overrides_limit_and_threshold(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search can override limit and score_threshold."""
        search = MemorySearch()

        search.search(query="test", limit=10, score_threshold=0.85)

        call_args = mock_qdrant_client.query_points.call_args
        assert call_args.kwargs["limit"] == 10
        assert call_args.kwargs["score_threshold"] == 0.85


class TestMemorySearchFiltering:
    """Test search filtering capabilities."""

    def test_search_with_group_id_filter(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search applies group_id filter."""
        search = MemorySearch()

        search.search(query="test", group_id="project-123")

        # Verify Filter was constructed with group_id
        call_args = mock_qdrant_client.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]

        assert query_filter is not None
        assert len(query_filter.must) == 1
        # Verify it's a FieldCondition for group_id
        assert query_filter.must[0].key == "group_id"

    def test_search_with_memory_type_filter(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search applies memory_type filter."""
        search = MemorySearch()

        search.search(query="test", memory_type="implementation")

        call_args = mock_qdrant_client.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]

        assert query_filter is not None
        assert len(query_filter.must) == 1
        assert query_filter.must[0].key == "type"

    def test_search_with_both_filters(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search combines group_id and memory_type filters."""
        search = MemorySearch()

        search.search(
            query="test", group_id="project-123", memory_type="pattern"
        )

        call_args = mock_qdrant_client.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]

        # Both filters should be present
        assert len(query_filter.must) == 2

    def test_search_without_filters(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search with no filters passes None to Qdrant."""
        search = MemorySearch()

        search.search(query="test")

        call_args = mock_qdrant_client.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]

        assert query_filter is None


class TestMemorySearchDualCollection:
    """Test dual-collection search functionality."""

    def test_search_both_collections(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search_both_collections calls search twice."""
        search = MemorySearch()

        results = search.search_both_collections(
            query="test query", group_id="test-project", limit=5
        )

        # Verify structure
        assert "implementations" in results
        assert "best_practices" in results
        assert isinstance(results["implementations"], list)
        assert isinstance(results["best_practices"], list)

        # Should call search twice (once per collection)
        assert mock_qdrant_client.query_points.call_count == 2

    def test_search_both_collections_filters_implementations_only(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test implementations filtered by group_id, best_practices not."""
        search = MemorySearch()

        # Track query_points calls
        search_calls = []
        original_query_points = mock_qdrant_client.query_points

        def track_query_points(*args, **kwargs):
            search_calls.append(kwargs)
            return original_query_points(*args, **kwargs)

        mock_qdrant_client.query_points = Mock(side_effect=track_query_points)

        search.search_both_collections(
            query="test", group_id="test-project", limit=3
        )

        # First call should be implementations with group_id
        impl_call = search_calls[0]
        assert impl_call["collection_name"] == "implementations"
        assert impl_call["query_filter"] is not None

        # Second call should be best_practices without group_id
        bp_call = search_calls[1]
        assert bp_call["collection_name"] == "best_practices"
        assert bp_call["query_filter"] is None


class TestMemorySearchTieredFormatting:
    """Test tiered results formatting."""

    def test_format_tiered_results_categorizes_by_score(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test format_tiered_results creates high and medium tiers."""
        search = MemorySearch()

        results = [
            {"score": 0.95, "type": "implementation", "content": "High relevance"},
            {"score": 0.85, "type": "pattern", "content": "Medium relevance"},
            {"score": 0.45, "type": "decision", "content": "Below threshold"},  # DEC-009: Below 50% excluded
        ]

        formatted = search.format_tiered_results(results)

        # High relevance tier should exist
        assert "## High Relevance Memories (>90%)" in formatted
        assert "95%" in formatted
        assert "High relevance" in formatted

        # Medium relevance tier should exist
        assert "## Medium Relevance Memories (50-90%)" in formatted
        assert "85%" in formatted
        assert "Medium relevance" in formatted

        # Below threshold should be excluded
        assert "Below threshold" not in formatted

    def test_format_tiered_results_truncates_medium_tier(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test medium tier content is truncated to 500 chars."""
        search = MemorySearch()

        long_content = "x" * 600
        results = [
            {"score": 0.85, "type": "pattern", "content": long_content},
        ]

        formatted = search.format_tiered_results(results)

        # Should be truncated to 500 chars + "..."
        assert "x" * 500 + "..." in formatted
        assert len(formatted.split("x" * 500)[1]) < 20  # Just "..." and formatting

    def test_format_tiered_results_shows_full_content_high_tier(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test high tier shows full content without truncation."""
        search = MemorySearch()

        long_content = "y" * 600
        results = [
            {"score": 0.95, "type": "implementation", "content": long_content},
        ]

        formatted = search.format_tiered_results(results)

        # Full content should be present (no "...")
        assert "y" * 600 in formatted
        assert "..." not in formatted

    def test_format_tiered_results_custom_thresholds(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test format_tiered_results accepts custom thresholds."""
        search = MemorySearch()

        results = [
            {"score": 0.85, "type": "implementation", "content": "High by custom"},
            {"score": 0.70, "type": "pattern", "content": "Medium by custom"},
        ]

        # Custom: high >= 0.80, medium >= 0.65
        formatted = search.format_tiered_results(
            results, high_threshold=0.80, medium_threshold=0.65
        )

        assert "## High Relevance Memories" in formatted
        assert "High by custom" in formatted
        assert "## Medium Relevance Memories" in formatted
        assert "Medium by custom" in formatted


class TestMemorySearchErrorHandling:
    """Test graceful degradation and error handling."""

    def test_search_embedding_failure_raises_error(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search propagates EmbeddingError when embedding fails."""
        mock_embedding_client.embed.side_effect = EmbeddingError("Service down")

        search = MemorySearch()

        with pytest.raises(EmbeddingError, match="Service down"):
            search.search(query="test")

    def test_search_qdrant_failure_raises_qdrant_unavailable(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search raises QdrantUnavailable when Qdrant fails (AC 1.6.4)."""
        mock_qdrant_client.query_points.side_effect = Exception("Connection refused")

        search = MemorySearch()

        with pytest.raises(QdrantUnavailable, match="Search failed"):
            search.search(query="test")

    def test_search_logs_on_success(
        self, mock_config, mock_qdrant_client, mock_embedding_client, caplog
    ):
        """Test search logs successful operation with structured extras."""
        caplog.set_level(logging.INFO)  # Required for caplog to capture INFO level
        search = MemorySearch()

        search.search(query="test", collection="implementations", group_id="proj")

        # Verify structured logging occurred
        assert any("search_completed" in record.message for record in caplog.records)


class TestMemorySearchIntegration:
    """Test search integration patterns."""

    def test_search_returns_payload_data(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search returns all payload fields in results."""
        search = MemorySearch()

        results = search.search(query="test")

        # All payload fields should be present
        assert "content" in results[0]
        assert "group_id" in results[0]
        assert "type" in results[0]
        assert "source_hook" in results[0]

    def test_search_includes_id_and_score(
        self, mock_config, mock_qdrant_client, mock_embedding_client
    ):
        """Test search includes id and score from Qdrant result."""
        search = MemorySearch()

        results = search.search(query="test")

        assert "id" in results[0]
        assert "score" in results[0]
        assert results[0]["id"] == "mem-123"
        assert results[0]["score"] == 0.95
