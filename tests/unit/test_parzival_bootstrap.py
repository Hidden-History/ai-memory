"""Unit tests for Parzival session bootstrap and GitHub enrichment (SPEC-016).

Tests cover:
- Enhanced Tier 1 bootstrap with agent_id=parzival filter
- Fallback to generic query when parzival_enabled=False
- GitHub enrichment date filtering, caps, and skip conditions
- Graceful degradation when Qdrant is unavailable

TD-174: parzival_enabled is read in injection.py (retrieve_bootstrap_context), NOT in
session_start.py. session_start.py calls injection.py which handles the parzival logic.
"""

from unittest.mock import MagicMock

from memory.config import COLLECTION_GITHUB, MemoryConfig
from memory.injection import _build_github_enrichment, retrieve_bootstrap_context
from memory.qdrant_client import QdrantUnavailable


class TestParzivalBootstrap:
    """Test Parzival-aware Tier 1 bootstrap queries."""

    def test_parzival_bootstrap_uses_agent_id(self):
        """When parzival_enabled=True, bootstrap queries include agent_id='parzival'."""
        mock_search = MagicMock()
        mock_search.search.return_value = []
        mock_search.get_recent.return_value = []

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = True
        config.github_sync_enabled = False

        retrieve_bootstrap_context(mock_search, "test-project", config)

        # Handoff now uses get_recent with agent_id="parzival"
        handoff_calls = [
            call
            for call in mock_search.get_recent.call_args_list
            if call.kwargs.get("agent_id") == "parzival"
        ]
        assert len(handoff_calls) >= 1
        assert handoff_calls[0].kwargs["memory_type"] == ["agent_handoff"]
        assert handoff_calls[0].kwargs["limit"] == 1

        # Insights use search with agent_id="parzival"
        parzival_search_calls = [
            call
            for call in mock_search.search.call_args_list
            if call.kwargs.get("agent_id") == "parzival"
        ]
        assert len(parzival_search_calls) == 1
        assert parzival_search_calls[0].kwargs["memory_type"] == ["agent_insight"]
        assert parzival_search_calls[0].kwargs["limit"] == 3

    def test_parzival_disabled_uses_generic_query(self):
        """When parzival_enabled=False, bootstrap uses generic agent context query."""
        mock_search = MagicMock()
        mock_search.search.return_value = []

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = False

        retrieve_bootstrap_context(mock_search, "test-project", config)

        # Should NOT have any calls with agent_id="parzival"
        parzival_calls = [
            call
            for call in mock_search.search.call_args_list
            if call.kwargs.get("agent_id") == "parzival"
        ]
        assert len(parzival_calls) == 0

        # Should have a generic agent context call with memory_type including agent_handoff
        generic_calls = [
            call
            for call in mock_search.search.call_args_list
            if "agent_handoff" in (call.kwargs.get("memory_type") or [])
            and call.kwargs.get("agent_id") is None
        ]
        assert len(generic_calls) >= 1

    def test_parzival_bootstrap_skips_github_when_disabled(self):
        """GitHub enrichment skipped when github_sync_enabled=False."""
        mock_search = MagicMock()

        handoff_result = {
            "content": "Session handoff",
            "timestamp": "2026-02-10T00:00:00Z",
            "score": 0.9,
        }

        def search_side_effect(**kwargs):
            if kwargs.get("memory_type") == ["agent_handoff"]:
                return [handoff_result]
            return []

        mock_search.search.side_effect = search_side_effect

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = True
        config.github_sync_enabled = False

        retrieve_bootstrap_context(mock_search, "test-project", config)

        # Should NOT have any calls with source="github"
        github_calls = [
            call
            for call in mock_search.search.call_args_list
            if call.kwargs.get("source") == "github"
        ]
        assert len(github_calls) == 0

    def test_parzival_bootstrap_full_qdrant_down(self):
        """Bootstrap returns empty when ALL queries fail (full Qdrant outage)."""
        mock_search = MagicMock()
        mock_search.search.side_effect = QdrantUnavailable("Connection refused")
        mock_search.get_recent.side_effect = QdrantUnavailable("Connection refused")

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = True
        config.github_sync_enabled = False

        results = retrieve_bootstrap_context(mock_search, "test-project", config)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_parzival_bootstrap_graceful_degradation(self):
        """When Qdrant fails during Parzival queries, returns empty without crash."""
        mock_search = MagicMock()
        mock_search.get_recent.return_value = []

        def side_effect(**kwargs):
            if kwargs.get("agent_id") == "parzival":
                raise QdrantUnavailable("Qdrant unavailable")
            return []

        mock_search.search.side_effect = side_effect

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = True
        config.github_sync_enabled = False

        # Should not raise
        results = retrieve_bootstrap_context(mock_search, "test-project", config)
        assert isinstance(results, list)

    def test_parzival_bootstrap_includes_github_enrichment(self):
        """When parzival_enabled and handoff exists, GitHub enrichment is called."""
        mock_search = MagicMock()

        handoff_result = {
            "content": "Session handoff",
            "timestamp": "2026-02-10T00:00:00Z",
            "score": 0.9,
        }

        github_result = {
            "content": "PR #42 merged",
            "timestamp": "2026-02-12T00:00:00Z",
            "score": 0.7,
        }

        # Handoff now uses get_recent, not search
        def get_recent_side_effect(**kwargs):
            if kwargs.get("memory_type") == ["agent_handoff"]:
                return [handoff_result]
            return []

        def search_side_effect(**kwargs):
            if kwargs.get("source") == "github":
                return [github_result]
            return []

        mock_search.get_recent.side_effect = get_recent_side_effect
        mock_search.search.side_effect = search_side_effect

        config = MagicMock(spec=MemoryConfig)
        config.parzival_enabled = True
        config.github_sync_enabled = True

        results = retrieve_bootstrap_context(mock_search, "test-project", config)

        # Should contain both the handoff and the github result
        assert handoff_result in results
        assert github_result in results


class TestGitHubEnrichment:
    """Test _build_github_enrichment function."""

    def test_github_enrichment_filters_by_date(self):
        """Only items after last_session_date are returned."""
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {"content": "PR old", "timestamp": "2026-02-10T00:00:00Z"},
            {"content": "PR new", "timestamp": "2026-02-15T00:00:00Z"},
        ]

        config = MagicMock(spec=MemoryConfig)
        config.github_sync_enabled = True

        result = _build_github_enrichment(
            mock_search, config, "test-project", "2026-02-12T00:00:00Z"
        )

        assert len(result) == 1
        assert result[0]["content"] == "PR new"

    def test_github_enrichment_skips_when_disabled(self):
        """Returns empty when github_sync_enabled=False."""
        mock_search = MagicMock()
        config = MagicMock(spec=MemoryConfig)
        config.github_sync_enabled = False

        result = _build_github_enrichment(
            mock_search, config, "test-project", "2026-02-10T00:00:00Z"
        )
        assert result == []
        mock_search.search.assert_not_called()

    def test_github_enrichment_no_baseline(self):
        """Returns empty when last_session_date is None."""
        mock_search = MagicMock()
        config = MagicMock(spec=MemoryConfig)
        config.github_sync_enabled = True

        result = _build_github_enrichment(mock_search, config, "test-project", None)
        assert result == []
        mock_search.search.assert_not_called()

    def test_github_enrichment_capped_at_10(self):
        """Returns at most 10 results even if more match."""
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {
                "content": f"PR #{i}",
                "timestamp": f"2026-02-{15 + (i % 10):02d}T00:00:00Z",
            }
            for i in range(15)
        ]

        config = MagicMock(spec=MemoryConfig)
        config.github_sync_enabled = True

        result = _build_github_enrichment(
            mock_search, config, "test-project", "2026-02-01T00:00:00Z"
        )
        assert len(result) <= 10

    def test_github_enrichment_empty_timestamps_excluded(self):
        """Items with empty or missing timestamps are excluded."""
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {"content": "PR with timestamp", "timestamp": "2026-02-15T00:00:00Z"},
            {"content": "PR no timestamp", "timestamp": ""},
            {"content": "PR missing timestamp"},
        ]

        config = MagicMock(spec=MemoryConfig)
        config.github_sync_enabled = True

        result = _build_github_enrichment(
            mock_search, config, "test-project", "2026-02-10T00:00:00Z"
        )
        assert len(result) == 1
        assert result[0]["content"] == "PR with timestamp"

    def test_github_enrichment_queries_correct_types(self):
        """GitHub enrichment searches for github_pr, github_issue, github_commit."""
        mock_search = MagicMock()
        mock_search.search.return_value = []

        config = MagicMock(spec=MemoryConfig)
        config.github_sync_enabled = True

        _build_github_enrichment(
            mock_search, config, "test-project", "2026-02-10T00:00:00Z"
        )

        call_kwargs = mock_search.search.call_args.kwargs
        assert call_kwargs["collection"] == COLLECTION_GITHUB
        assert call_kwargs["source"] == "github"
        assert set(call_kwargs["memory_type"]) == {
            "github_pr",
            "github_issue",
            "github_commit",
        }
        assert call_kwargs["group_id"] == "test-project"
