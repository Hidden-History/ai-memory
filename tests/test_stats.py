"""Unit tests for collection statistics module.

Tests:
- CollectionStats dataclass initialization and validation
- get_collection_stats() with mocked Qdrant client
- get_unique_field_values() returns unique projects
- calculate_disk_size() calculates correctly from segments
- get_last_updated() returns latest timestamp
- Edge cases: empty collections, zero projects, missing fields

Complies with:
- AC 6.6.1: Statistics Endpoint requirements
- pytest best practices: fixtures, mocking, parametrize
- project-context.md: test naming, structure
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
from dataclasses import asdict

from memory.stats import (
    CollectionStats,
    get_collection_stats,
    get_unique_field_values,
    calculate_disk_size,
    get_last_updated,
)


class TestCollectionStatsDataclass:
    """Test CollectionStats dataclass initialization."""

    def test_collection_stats_initialization(self):
        """CollectionStats initializes with all required fields."""
        stats = CollectionStats(
            collection_name="implementations",
            total_points=1000,
            indexed_points=950,
            segments_count=3,
            disk_size_bytes=5242880,
            last_updated="2026-01-13T10:00:00Z",
            projects=["project-a", "project-b"],
            points_by_project={"project-a": 600, "project-b": 400},
        )

        assert stats.collection_name == "implementations"
        assert stats.total_points == 1000
        assert stats.indexed_points == 950
        assert stats.segments_count == 3
        assert stats.disk_size_bytes == 5242880
        assert stats.last_updated == "2026-01-13T10:00:00Z"
        assert stats.projects == ["project-a", "project-b"]
        assert stats.points_by_project == {"project-a": 600, "project-b": 400}

    def test_collection_stats_optional_last_updated(self):
        """CollectionStats allows None for last_updated."""
        stats = CollectionStats(
            collection_name="best_practices",
            total_points=0,
            indexed_points=0,
            segments_count=0,
            disk_size_bytes=0,
            last_updated=None,
            projects=[],
            points_by_project={},
        )

        assert stats.last_updated is None


class TestGetCollectionStats:
    """Test get_collection_stats() function."""

    def test_get_collection_stats_success(self):
        """get_collection_stats() returns complete stats for collection."""
        # Mock Qdrant client
        mock_client = Mock()

        # Mock collection info (Qdrant 1.16+ API structure)
        mock_collection_info = Mock()
        mock_collection_info.points_count = 1500
        mock_collection_info.indexed_vectors_count = 1450
        mock_collection_info.segments_count = 2

        mock_client.get_collection.return_value = mock_collection_info

        # Mock unique projects
        mock_client.scroll.return_value = (
            [
                Mock(payload={"group_id": "proj-a"}),
                Mock(payload={"group_id": "proj-b"}),
                Mock(payload={"group_id": "proj-a"}),  # duplicate
            ],
            None,
        )

        # Mock per-project counts
        mock_client.count.side_effect = [
            Mock(count=900),  # proj-a
            Mock(count=600),  # proj-b
        ]

        # Execute
        stats = get_collection_stats(mock_client, "implementations")

        # Verify
        assert stats.collection_name == "implementations"
        assert stats.total_points == 1500
        assert stats.indexed_points == 1450
        assert stats.segments_count == 2
        assert stats.disk_size_bytes == 0  # Not available via API
        assert len(stats.projects) == 2
        assert "proj-a" in stats.projects
        assert "proj-b" in stats.projects
        assert stats.points_by_project == {"proj-a": 900, "proj-b": 600}

    def test_get_collection_stats_empty_collection(self):
        """get_collection_stats() handles empty collection."""
        mock_client = Mock()

        mock_collection_info = Mock()
        mock_collection_info.points_count = 0
        mock_collection_info.indexed_vectors_count = 0
        mock_collection_info.segments_count = 0

        mock_client.get_collection.return_value = mock_collection_info
        mock_client.scroll.return_value = ([], None)

        stats = get_collection_stats(mock_client, "implementations")

        assert stats.total_points == 0
        assert stats.indexed_points == 0
        assert stats.segments_count == 0
        assert stats.disk_size_bytes == 0
        assert stats.projects == []
        assert stats.points_by_project == {}


class TestGetUniqueFieldValues:
    """Test get_unique_field_values() helper function."""

    def test_get_unique_field_values_extracts_unique_projects(self):
        """get_unique_field_values() returns sorted unique values."""
        mock_client = Mock()
        mock_client.scroll.return_value = (
            [
                Mock(payload={"group_id": "project-c"}),
                Mock(payload={"group_id": "project-a"}),
                Mock(payload={"group_id": "project-b"}),
                Mock(payload={"group_id": "project-a"}),  # duplicate
            ],
            None,
        )

        projects = get_unique_field_values(
            mock_client, "implementations", "group_id"
        )

        assert projects == ["project-a", "project-b", "project-c"]  # sorted

    def test_get_unique_field_values_empty_collection(self):
        """get_unique_field_values() returns empty list for empty collection."""
        mock_client = Mock()
        mock_client.scroll.return_value = ([], None)

        projects = get_unique_field_values(
            mock_client, "implementations", "group_id"
        )

        assert projects == []

    def test_get_unique_field_values_missing_field(self):
        """get_unique_field_values() handles missing field in payload."""
        mock_client = Mock()
        mock_client.scroll.return_value = (
            [
                Mock(payload={"group_id": "project-a"}),
                Mock(payload={}),  # missing group_id
                Mock(payload={"group_id": "project-b"}),
            ],
            None,
        )

        projects = get_unique_field_values(
            mock_client, "implementations", "group_id"
        )

        assert projects == ["project-a", "project-b"]


class TestCalculateDiskSize:
    """Test calculate_disk_size() helper function."""

    def test_calculate_disk_size_returns_zero(self):
        """calculate_disk_size() returns 0 (not available via API)."""
        mock_collection_info = Mock()
        mock_collection_info.segments_count = 3

        total_size = calculate_disk_size(mock_collection_info)

        # API doesn't expose disk size, returns 0 as placeholder
        assert total_size == 0

    def test_calculate_disk_size_empty_collection(self):
        """calculate_disk_size() returns 0 for empty collection."""
        mock_collection_info = Mock()
        mock_collection_info.segments_count = 0

        total_size = calculate_disk_size(mock_collection_info)

        assert total_size == 0


class TestGetLastUpdated:
    """Test get_last_updated() helper function."""

    def test_get_last_updated_returns_latest_timestamp(self):
        """get_last_updated() returns most recent timestamp."""
        mock_client = Mock()
        mock_client.scroll.return_value = (
            [
                Mock(
                    payload={
                        "timestamp": "2026-01-13T09:00:00Z"
                    }
                )
            ],
            None,
        )

        last_updated = get_last_updated(mock_client, "implementations")

        assert last_updated == "2026-01-13T09:00:00Z"

    def test_get_last_updated_no_timestamps(self):
        """get_last_updated() returns None if no timestamp field."""
        mock_client = Mock()
        mock_client.scroll.return_value = ([], None)

        last_updated = get_last_updated(mock_client, "implementations")

        assert last_updated is None

    def test_get_last_updated_missing_timestamp_field(self):
        """get_last_updated() handles missing timestamp field gracefully."""
        mock_client = Mock()
        mock_client.scroll.return_value = (
            [Mock(payload={"group_id": "project-a"})],  # no timestamp
            None,
        )

        last_updated = get_last_updated(mock_client, "implementations")

        assert last_updated is None
