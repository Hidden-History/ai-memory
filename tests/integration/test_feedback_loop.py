"""Integration tests for the post-sync freshness feedback loop.

Tests _trigger_freshness_for_merged_pr() method on GitHubSyncEngine.
These tests mock the Qdrant client to verify correct behavior without
requiring a running Qdrant instance.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root / "src"))


def _make_mock_point(point_id, payload=None):
    """Create a mock Qdrant point."""
    point = MagicMock()
    point.id = point_id
    point.payload = payload or {}
    return point


@pytest.fixture
def mock_sync_engine():
    """Create a GitHubSyncEngine with mocked dependencies."""
    with (
        patch("memory.connectors.github.sync.get_config") as mock_config,
        patch("memory.connectors.github.sync.get_qdrant_client") as mock_qdrant,
        patch("memory.connectors.github.sync.GitHubClient"),
        patch("memory.connectors.github.sync.MemoryStorage"),
    ):
        config = MagicMock()
        config.github_sync_enabled = True
        config.github_token.get_secret_value.return_value = "fake-token"
        config.github_repo = "test-owner/test-repo"
        config.github_branch = "main"
        config.project_path = str(_project_root)
        mock_config.return_value = config

        qdrant = MagicMock()
        mock_qdrant.return_value = qdrant

        from memory.connectors.github.sync import GitHubSyncEngine

        engine = GitHubSyncEngine(config=config)
        engine.qdrant = qdrant

        yield engine, qdrant


class TestTriggerFreshnessForMergedPR:
    """Tests for _trigger_freshness_for_merged_pr."""

    def test_merged_pr_flags_matching_code_patterns(self, mock_sync_engine):
        """Merged PR flags affected code-patterns as stale."""
        engine, qdrant = mock_sync_engine

        # Setup: one code-pattern point matching src/auth.py
        point = _make_mock_point("point-1", {"freshness_status": "fresh"})
        qdrant.scroll.return_value = ([point], None)

        flagged = engine._trigger_freshness_for_merged_pr(["src/auth.py"])

        assert flagged == 1
        qdrant.set_payload.assert_called_once()

        # Verify payload contains correct freshness fields
        call_kwargs = qdrant.set_payload.call_args
        payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        if payload is None:
            payload = call_kwargs[0][0] if call_kwargs[0] else {}
            # Try positional args
            for arg in call_kwargs[0]:
                if isinstance(arg, dict):
                    payload = arg
                    break
        # Access via kwargs
        actual_call = qdrant.set_payload.call_args
        assert actual_call.kwargs["payload"]["freshness_status"] == "stale"
        assert (
            actual_call.kwargs["payload"]["freshness_trigger"] == "post_sync_pr_merge"
        )
        assert "freshness_checked_at" in actual_call.kwargs["payload"]

    def test_no_matching_files_returns_zero(self, mock_sync_engine):
        """Trigger with files that have no matching code-patterns."""
        engine, qdrant = mock_sync_engine
        qdrant.scroll.return_value = ([], None)

        flagged = engine._trigger_freshness_for_merged_pr(["src/other.py"])

        assert flagged == 0
        qdrant.set_payload.assert_not_called()

    def test_empty_files_list_returns_zero(self, mock_sync_engine):
        """Empty files_changed returns 0 immediately."""
        engine, qdrant = mock_sync_engine

        flagged = engine._trigger_freshness_for_merged_pr([])

        assert flagged == 0
        qdrant.scroll.assert_not_called()

    def test_multiple_files_flagged(self, mock_sync_engine):
        """Multiple files each flag their matching code-patterns."""
        engine, qdrant = mock_sync_engine

        point1 = _make_mock_point("point-1")
        point2 = _make_mock_point("point-2")

        # First file has one point, second has one point
        qdrant.scroll.side_effect = [
            ([point1], None),
            ([point2], None),
        ]

        flagged = engine._trigger_freshness_for_merged_pr(["src/a.py", "src/b.py"])

        assert flagged == 2
        assert qdrant.set_payload.call_count == 2

    def test_fail_open_on_set_payload_error(self, mock_sync_engine):
        """Flagging failure doesn't abort - returns 0, no exception."""
        engine, qdrant = mock_sync_engine

        point = _make_mock_point("point-1")
        qdrant.scroll.return_value = ([point], None)
        qdrant.set_payload.side_effect = Exception("Qdrant connection failed")

        # Should NOT raise - fail-open pattern
        flagged = engine._trigger_freshness_for_merged_pr(["src/auth.py"])

        assert flagged == 0

    def test_pagination_handles_multiple_pages(self, mock_sync_engine):
        """Scroll pagination works when next_offset is returned."""
        engine, qdrant = mock_sync_engine

        point1 = _make_mock_point("point-1")
        point2 = _make_mock_point("point-2")

        # First scroll returns page 1 with next_offset, second returns page 2
        qdrant.scroll.side_effect = [
            ([point1], "offset-2"),
            ([point2], None),
        ]

        flagged = engine._trigger_freshness_for_merged_pr(["src/auth.py"])

        assert flagged == 2
        assert qdrant.scroll.call_count == 2

    def test_group_id_filter_applied(self, mock_sync_engine):
        """Scroll filter includes group_id for tenant isolation."""
        engine, qdrant = mock_sync_engine
        qdrant.scroll.return_value = ([], None)

        engine._trigger_freshness_for_merged_pr(["src/auth.py"])

        # Verify scroll was called with group_id filter
        call_kwargs = qdrant.scroll.call_args.kwargs
        scroll_filter = call_kwargs["scroll_filter"]
        # Should have 2 must conditions: file_path + group_id
        assert len(scroll_filter.must) == 2

        # Check group_id filter (search by key, not position, to avoid fragility)
        group_filter = next(f for f in scroll_filter.must if f.key == "group_id")
        assert group_filter.key == "group_id"

    def test_code_patterns_collection_used(self, mock_sync_engine):
        """Scroll targets code-patterns collection, NOT discussions."""
        engine, qdrant = mock_sync_engine
        qdrant.scroll.return_value = ([], None)

        engine._trigger_freshness_for_merged_pr(["src/auth.py"])

        call_kwargs = qdrant.scroll.call_args.kwargs
        assert call_kwargs["collection_name"] == "code-patterns"
