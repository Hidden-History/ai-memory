"""Unit tests for Prometheus metrics integration with collection statistics.

Tests:
- update_collection_metrics() updates gauges correctly
- Gauge values set correctly for "all" project
- Gauge values set correctly per-project
- Multiple collections update independently

Complies with:
- AC 6.6.3: Prometheus Gauge Updates
- pytest best practices: fixtures, mocking
- project-context.md: test naming
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from memory.stats import CollectionStats


class TestUpdateCollectionMetrics:
    """Test update_collection_metrics() function."""

    def test_update_collection_metrics_sets_overall_gauge(self):
        """update_collection_metrics() sets gauge for overall collection."""
        stats = CollectionStats(
            collection_name="implementations",
            total_points=1500,
            indexed_points=1450,
            segments_count=3,
            disk_size_bytes=3145728,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a", "proj-b"],
            points_by_project={"proj-a": 900, "proj-b": 600},
        )

        with patch("memory.metrics.collection_size") as mock_gauge:
            from memory.metrics import update_collection_metrics

            update_collection_metrics(stats)

            # Verify overall collection gauge set
            mock_gauge.labels.assert_any_call(
                collection="implementations", project="all"
            )
            mock_gauge.labels.return_value.set.assert_any_call(1500)

    def test_update_collection_metrics_sets_per_project_gauges(self):
        """update_collection_metrics() sets gauges for each project."""
        stats = CollectionStats(
            collection_name="implementations",
            total_points=1500,
            indexed_points=1450,
            segments_count=3,
            disk_size_bytes=3145728,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a", "proj-b"],
            points_by_project={"proj-a": 900, "proj-b": 600},
        )

        with patch("memory.metrics.collection_size") as mock_gauge:
            from memory.metrics import update_collection_metrics

            update_collection_metrics(stats)

            # Verify per-project gauges set
            mock_gauge.labels.assert_any_call(
                collection="implementations", project="proj-a"
            )
            mock_gauge.labels.assert_any_call(
                collection="implementations", project="proj-b"
            )

    def test_update_collection_metrics_multiple_collections(self):
        """update_collection_metrics() handles multiple collections independently."""
        stats_impl = CollectionStats(
            collection_name="implementations",
            total_points=1500,
            indexed_points=1450,
            segments_count=3,
            disk_size_bytes=3145728,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a"],
            points_by_project={"proj-a": 1500},
        )

        stats_best = CollectionStats(
            collection_name="best_practices",
            total_points=500,
            indexed_points=500,
            segments_count=1,
            disk_size_bytes=1048576,
            last_updated="2026-01-13T10:00:00Z",
            projects=["global"],
            points_by_project={"global": 500},
        )

        with patch("memory.metrics.collection_size") as mock_gauge:
            from memory.metrics import update_collection_metrics

            # Update both collections
            update_collection_metrics(stats_impl)
            update_collection_metrics(stats_best)

            # Verify both collections updated with correct labels
            mock_gauge.labels.assert_any_call(
                collection="implementations", project="all"
            )
            mock_gauge.labels.assert_any_call(
                collection="best_practices", project="all"
            )

    def test_update_collection_metrics_empty_collection(self):
        """update_collection_metrics() handles empty collection (0 points)."""
        stats = CollectionStats(
            collection_name="implementations",
            total_points=0,
            indexed_points=0,
            segments_count=0,
            disk_size_bytes=0,
            last_updated=None,
            projects=[],
            points_by_project={},
        )

        with patch("memory.metrics.collection_size") as mock_gauge:
            from memory.metrics import update_collection_metrics

            update_collection_metrics(stats)

            # Verify gauge set to 0
            mock_gauge.labels.assert_called_once_with(
                collection="implementations", project="all"
            )
            mock_gauge.labels.return_value.set.assert_called_once_with(0)
