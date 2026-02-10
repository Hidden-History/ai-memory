"""Unit tests for Jira search module.

Tests search_jira and lookup_issue with:
- group_id filter validation (REQUIRED for tenant isolation)
- All filter combinations
- Issue lookup mode
- Result formatting (badges, URLs, snippets)
- Error handling
"""

import pytest
from unittest.mock import Mock, patch

from src.memory.connectors.jira.search import (
    search_jira,
    lookup_issue,
    JiraSearchError,
    _format_jira_url,
    _format_badges,
    _truncate_content,
)
from src.memory.models import MemoryType


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestFormatJiraUrl:
    """Test _format_jira_url helper."""

    def test_issue_url(self):
        """Format issue URL."""
        url = _format_jira_url("company.atlassian.net", "PROJ-123")
        assert url == "https://company.atlassian.net/browse/PROJ-123"

    def test_comment_url(self):
        """Format comment URL with focusedCommentId."""
        url = _format_jira_url("company.atlassian.net", "PROJ-123", "10001")
        assert url == "https://company.atlassian.net/browse/PROJ-123?focusedCommentId=10001"

    def test_url_without_comment_id(self):
        """URL without comment ID."""
        url = _format_jira_url("test.atlassian.net", "TEST-1", None)
        assert url == "https://test.atlassian.net/browse/TEST-1"


class TestFormatBadges:
    """Test _format_badges helper."""

    def test_issue_badges(self):
        """Format badges for issue."""
        payload = {
            "type": "jira_issue",
            "jira_issue_type": "Bug",
            "jira_status": "In Progress",
            "jira_priority": "High",
            "jira_reporter": "Alice",
        }
        badges = _format_badges(payload)

        assert "[Type: Bug]" in badges
        assert "[Status: In Progress]" in badges
        assert "[Priority: High]" in badges
        assert "[Reporter: Alice]" in badges

    def test_comment_badges(self):
        """Format badges for comment."""
        payload = {
            "type": "jira_comment",
            "jira_issue_type": "Story",
            "jira_status": "Done",
            "jira_priority": "Medium",
            "jira_author": "Bob",
        }
        badges = _format_badges(payload)

        assert "[Type: Story]" in badges
        assert "[Status: Done]" in badges
        assert "[Priority: Medium]" in badges
        assert "[Author: Bob]" in badges

    def test_nullable_priority(self):
        """Nullable priority handled gracefully."""
        payload = {
            "type": "jira_issue",
            "jira_issue_type": "Task",
            "jira_status": "Open",
            "jira_priority": None,
        }
        badges = _format_badges(payload)

        # Priority not included if None
        assert "Priority" not in badges


class TestTruncateContent:
    """Test _truncate_content helper."""

    def test_short_content(self):
        """Short content not truncated."""
        content = "Short text"
        result = _truncate_content(content, max_length=300)
        assert result == "Short text"

    def test_long_content_truncated(self):
        """Long content truncated with ellipsis."""
        content = "A" * 400
        result = _truncate_content(content, max_length=300)
        assert len(result) == 303  # 300 + "..."
        assert result.endswith("...")

    def test_exact_length(self):
        """Content exactly at max_length not truncated."""
        content = "B" * 300
        result = _truncate_content(content, max_length=300)
        assert result == content
        assert not result.endswith("...")


# =============================================================================
# group_id Filter Validation
# =============================================================================


class TestGroupIdValidation:
    """Test group_id filter requirement."""

    def test_group_id_none_raises(self):
        """group_id=None raises ValueError."""
        with pytest.raises(ValueError, match="group_id is required"):
            search_jira(query="test", group_id=None)

    def test_group_id_empty_raises(self):
        """group_id='' raises ValueError."""
        with pytest.raises(ValueError, match="group_id is required"):
            search_jira(query="test", group_id="")

    def test_group_id_required_in_filter(self):
        """group_id included in Qdrant filter."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    config=mock_config,
                )

        # Verify filter includes group_id
        call_args = mock_qdrant.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]
        filter_conditions = query_filter.must

        # Find group_id condition
        group_id_conditions = [c for c in filter_conditions if hasattr(c, "key") and c.key == "group_id"]
        assert len(group_id_conditions) == 1
        assert group_id_conditions[0].match.value == "company.atlassian.net"


# =============================================================================
# Filter Combinations
# =============================================================================


class TestFilterCombinations:
    """Test all filter combinations."""

    def test_no_optional_filters(self):
        """Search with only group_id filter."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    config=mock_config,
                )

        # Only group_id filter present
        call_args = mock_qdrant.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]
        assert len(query_filter.must) == 1

    def test_project_filter(self):
        """Search with project filter."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    project="PROJ",
                    config=mock_config,
                )

        # group_id + project filters
        call_args = mock_qdrant.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]
        assert len(query_filter.must) == 2

    def test_all_filters(self):
        """Search with all filters."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    project="PROJ",
                    memory_type="jira_issue",
                    issue_type="Bug",
                    status="In Progress",
                    priority="High",
                    author="Alice",
                    config=mock_config,
                )

        # 7 filters total (group_id + 6 optional)
        call_args = mock_qdrant.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]
        assert len(query_filter.must) == 7

    def test_multiple_optional_filters(self):
        """Search with multiple optional filters."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    project="PROJ",
                    status="Open",
                    priority="Critical",
                    config=mock_config,
                )

        # group_id + project + status + priority = 4 filters
        call_args = mock_qdrant.query_points.call_args
        query_filter = call_args.kwargs["query_filter"]
        assert len(query_filter.must) == 4


# =============================================================================
# Issue Lookup Mode
# =============================================================================


class TestIssueLookup:
    """Test lookup_issue function."""

    def test_lookup_issue_found(self):
        """Issue and comments retrieved successfully."""
        mock_config = Mock()

        mock_issue_point = Mock()
        mock_issue_point.id = "issue-id"
        mock_issue_point.payload = {
            "type": "jira_issue",
            "content": "Issue content",
            "jira_issue_key": "PROJ-123",
        }

        mock_comment_point = Mock()
        mock_comment_point.id = "comment-id"
        mock_comment_point.payload = {
            "type": "jira_comment",
            "content": "Comment content",
            "jira_issue_key": "PROJ-123",
            "jira_comment_id": "10001",
            "jira_updated": "2026-02-07T00:00:00Z",
        }

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.scroll = Mock(return_value=([mock_issue_point, mock_comment_point], None))
            mock_qdrant_fn.return_value = mock_qdrant

            result = lookup_issue("PROJ-123", "company.atlassian.net", config=mock_config)

        # Verify result structure
        assert result["issue"] is not None
        assert len(result["comments"]) == 1
        assert result["total_count"] == 2

    def test_lookup_issue_not_found(self):
        """Issue not found returns None."""
        mock_config = Mock()

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.scroll = Mock(return_value=([], None))
            mock_qdrant_fn.return_value = mock_qdrant

            result = lookup_issue("PROJ-999", "company.atlassian.net", config=mock_config)

        # No issue found
        assert result["issue"] is None
        assert result["comments"] == []
        assert result["total_count"] == 0

    def test_lookup_comments_sorted_chronologically(self):
        """Comments sorted by jira_updated."""
        mock_config = Mock()

        mock_issue = Mock()
        mock_issue.id = "issue-id"
        mock_issue.payload = {
            "type": "jira_issue",
            "content": "Issue",
            "jira_issue_key": "PROJ-123",
        }

        # Comments in wrong order
        mock_comment1 = Mock()
        mock_comment1.id = "c1"
        mock_comment1.payload = {
            "type": "jira_comment",
            "content": "Second comment",
            "jira_updated": "2026-02-07T00:00:00Z",
        }

        mock_comment2 = Mock()
        mock_comment2.id = "c2"
        mock_comment2.payload = {
            "type": "jira_comment",
            "content": "First comment",
            "jira_updated": "2026-02-01T00:00:00Z",
        }

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.scroll = Mock(return_value=([mock_issue, mock_comment1, mock_comment2], None))
            mock_qdrant_fn.return_value = mock_qdrant

            result = lookup_issue("PROJ-123", "company.atlassian.net", config=mock_config)

        # Comments sorted chronologically
        assert len(result["comments"]) == 2
        assert result["comments"][0]["content"] == "First comment"
        assert result["comments"][1]["content"] == "Second comment"

    def test_lookup_group_id_required(self):
        """lookup_issue requires group_id."""
        with pytest.raises(ValueError, match="group_id is required"):
            lookup_issue("PROJ-123", None)

        with pytest.raises(ValueError, match="group_id is required"):
            lookup_issue("PROJ-123", "")

    def test_lookup_issue_key_required(self):
        """lookup_issue requires issue_key."""
        with pytest.raises(ValueError, match="issue_key is required"):
            lookup_issue("", "company.atlassian.net")


# =============================================================================
# Result Formatting
# =============================================================================


class TestResultFormatting:
    """Test search result formatting."""

    def test_result_fields_present(self):
        """All required fields present in results."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        mock_point = Mock()
        mock_point.id = "mem-123"
        mock_point.score = 0.85
        mock_point.payload = {
            "content": "Issue content here",
            "jira_issue_key": "PROJ-123",
            "jira_comment_id": None,
            "type": "jira_issue",
            "jira_issue_type": "Bug",
            "jira_status": "Open",
            "jira_priority": "High",
        }

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[mock_point]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                results = search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    config=mock_config,
                )

        # Verify required fields
        assert len(results) == 1
        result = results[0]
        assert result["id"] == "mem-123"
        assert result["score"] == 0.85
        assert result["jira_url"] is not None
        assert result["badges"] is not None
        assert result["snippet"] is not None
        assert result["content"] == "Issue content here"

    def test_url_formatting_in_results(self):
        """Jira URL formatted correctly in results."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        mock_point = Mock()
        mock_point.id = "mem-123"
        mock_point.score = 0.85
        mock_point.payload = {
            "content": "Content",
            "jira_issue_key": "PROJ-456",
            "jira_comment_id": "10001",
        }

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[mock_point]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                results = search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    config=mock_config,
                )

        # URL includes comment ID
        result = results[0]
        assert "PROJ-456" in result["jira_url"]
        assert "focusedCommentId=10001" in result["jira_url"]

    def test_content_truncation(self):
        """Long content truncated in snippet."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        long_content = "A" * 500

        mock_point = Mock()
        mock_point.id = "mem-123"
        mock_point.score = 0.85
        mock_point.payload = {
            "content": long_content,
            "jira_issue_key": "PROJ-123",
        }

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(return_value=Mock(points=[mock_point]))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                results = search_jira(
                    query="test",
                    group_id="company.atlassian.net",
                    config=mock_config,
                )

        result = results[0]
        # Snippet truncated to 300 chars + "..."
        assert len(result["snippet"]) == 303
        assert result["snippet"].endswith("...")
        # Full content still available
        assert len(result["content"]) == 500


# =============================================================================
# Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling."""

    def test_embedding_error_raises(self):
        """Embedding generation error raises JiraSearchError."""
        mock_config = Mock()

        with patch("src.memory.connectors.jira.search.get_qdrant_client"):
            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                from src.memory.embeddings import EmbeddingError

                mock_embed = Mock()
                mock_embed.embed = Mock(side_effect=EmbeddingError("Embedding failed"))
                mock_embed_cls.return_value = mock_embed

                with pytest.raises(JiraSearchError, match="Embedding generation failed"):
                    search_jira(
                        query="test",
                        group_id="company.atlassian.net",
                        config=mock_config,
                    )

    def test_qdrant_error_raises(self):
        """Qdrant query error raises JiraSearchError."""
        mock_config = Mock()
        mock_config.similarity_threshold = 0.7
        mock_config.hnsw_ef_accurate = 128

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.query_points = Mock(side_effect=Exception("Qdrant error"))
            mock_qdrant_fn.return_value = mock_qdrant

            with patch("src.memory.connectors.jira.search.EmbeddingClient") as mock_embed_cls:
                mock_embed = Mock()
                mock_embed.embed = Mock(return_value=[[0.1] * 768])
                mock_embed_cls.return_value = mock_embed

                with pytest.raises(JiraSearchError, match="Qdrant search failed"):
                    search_jira(
                        query="test",
                        group_id="company.atlassian.net",
                        config=mock_config,
                    )

    def test_lookup_qdrant_error_raises(self):
        """lookup_issue Qdrant error raises JiraSearchError."""
        mock_config = Mock()

        with patch("src.memory.connectors.jira.search.get_qdrant_client") as mock_qdrant_fn:
            mock_qdrant = Mock()
            mock_qdrant.scroll = Mock(side_effect=Exception("Scroll error"))
            mock_qdrant_fn.return_value = mock_qdrant

            with pytest.raises(JiraSearchError, match="Issue lookup failed"):
                lookup_issue("PROJ-123", "company.atlassian.net", config=mock_config)
