"""Unit tests for collection threshold warnings module.

Tests:
- check_collection_thresholds() with WARNING threshold (10K default)
- check_collection_thresholds() with CRITICAL threshold (50K default)
- Per-project warnings triggered correctly
- Environment variable threshold configuration
- Structured logging output format
- Empty collections return no warnings

Complies with:
- AC 6.6.2: Threshold Warning Implementation (FR46a)
- pytest best practices: fixtures, mocking, parametrize
- project-context.md: structured logging patterns
"""

import sys
from unittest.mock import patch

import pytest

from memory.stats import CollectionStats
from memory.warnings import (
    COLLECTION_SIZE_CRITICAL,
    COLLECTION_SIZE_WARNING,
    check_collection_thresholds,
)

# Skip tests that use module-level patching on Python 3.10 due to import order issues
_skip_py310 = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="Python 3.10 module patching incompatibility - TECH-DEBT-094",
)


class TestCheckCollectionThresholds:
    """Test check_collection_thresholds() function."""

    def test_no_warnings_below_threshold(self, caplog):
        """check_collection_thresholds() returns no warnings below WARNING threshold."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=5000,  # Below 10K WARNING
            indexed_points=5000,
            segments_count=1,
            disk_size_bytes=1024000,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a"],
            points_by_project={"proj-a": 5000},
        )

        warnings = check_collection_thresholds(stats)

        assert warnings == []
        assert len(caplog.records) == 0

    @_skip_py310
    def test_warning_at_threshold(self, caplog):
        """check_collection_thresholds() logs WARNING at 10K default."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=10000,  # Exactly at WARNING
            indexed_points=10000,
            segments_count=2,
            disk_size_bytes=2048000,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a"],
            points_by_project={"proj-a": 10000},
        )

        with patch("memory.warnings.logger") as mock_logger:
            warnings = check_collection_thresholds(stats)

            # Verify warnings returned (collection + per-project)
            assert len(warnings) == 2
            assert any(
                "WARNING" in w and "code-patterns" in w and "10000" in w
                for w in warnings
            )
            assert any("proj-a" in w for w in warnings)

            # Verify structured logging (2 calls: collection + project)
            assert mock_logger.warning.call_count == 2
            calls = mock_logger.warning.call_args_list
            assert calls[0][0][0] == "collection_size_warning"
            assert calls[0][1]["extra"]["collection"] == "code-patterns"

    @_skip_py310
    def test_critical_at_threshold(self, caplog):
        """check_collection_thresholds() logs CRITICAL at 50K default."""
        stats = CollectionStats(
            collection_name="conventions",
            total_points=50000,  # At CRITICAL
            indexed_points=50000,
            segments_count=5,
            disk_size_bytes=10240000,
            last_updated="2026-01-13T10:00:00Z",
            projects=["global"],
            points_by_project={"global": 50000},
        )

        with patch("memory.warnings.logger") as mock_logger:
            warnings = check_collection_thresholds(stats)

            # Verify warnings returned (CRITICAL + per-project WARNING)
            assert len(warnings) == 2
            assert any("CRITICAL" in w and "conventions" in w for w in warnings)
            assert any("global" in w for w in warnings)

            # Verify structured logging with ERROR level for collection
            mock_logger.error.assert_called_once_with(
                "collection_size_critical",
                extra={
                    "collection": "conventions",
                    "size": 50000,
                    "threshold": 50000,
                },
            )
            # Also WARNING for per-project
            mock_logger.warning.assert_called_once()

    @_skip_py310
    def test_critical_takes_precedence_over_warning(self):
        """check_collection_thresholds() returns CRITICAL not WARNING if both apply."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=55000,  # Above both WARNING and CRITICAL
            indexed_points=55000,
            segments_count=6,
            disk_size_bytes=12288000,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a"],
            points_by_project={"proj-a": 55000},
        )

        with patch("memory.warnings.logger") as mock_logger:
            warnings = check_collection_thresholds(stats)

            # CRITICAL for collection + WARNING for project
            assert len(warnings) == 2
            assert any("CRITICAL" in w and "code-patterns" in w for w in warnings)
            assert any("WARNING" in w and "proj-a" in w for w in warnings)

            # Error logged for collection, warning for project
            mock_logger.error.assert_called_once()
            mock_logger.warning.assert_called_once()

    @_skip_py310
    def test_per_project_warnings(self):
        """check_collection_thresholds() warns about individual projects over threshold."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=15000,  # Above WARNING
            indexed_points=15000,
            segments_count=3,
            disk_size_bytes=3072000,
            last_updated="2026-01-13T10:00:00Z",
            projects=["proj-a", "proj-b", "proj-c"],
            points_by_project={
                "proj-a": 12000,  # Above WARNING
                "proj-b": 2000,  # Below WARNING
                "proj-c": 1000,  # Below WARNING
            },
        )

        with patch("memory.warnings.logger") as mock_logger:
            warnings = check_collection_thresholds(stats)

            # Collection WARNING + per-project WARNING for proj-a
            assert len(warnings) == 2
            assert any("code-patterns" in w and "15000" in w for w in warnings)
            assert any("proj-a" in w and "12000" in w for w in warnings)

            # Verify both structured logs
            assert mock_logger.warning.call_count == 2

    def test_empty_collection_no_warnings(self):
        """check_collection_thresholds() returns no warnings for empty collection."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=0,
            indexed_points=0,
            segments_count=0,
            disk_size_bytes=0,
            last_updated=None,
            projects=[],
            points_by_project={},
        )

        warnings = check_collection_thresholds(stats)

        assert warnings == []


class TestEnvironmentVariableConfiguration:
    """Test threshold configuration via environment variables."""

    def test_default_warning_threshold(self):
        """WARNING threshold defaults to 10000."""
        # Test default value without reloading
        assert COLLECTION_SIZE_WARNING == 10000

    def test_default_critical_threshold(self):
        """CRITICAL threshold defaults to 50000."""
        # Test default value without reloading
        assert COLLECTION_SIZE_CRITICAL == 50000


@_skip_py310
class TestStructuredLoggingFormat:
    """Test structured logging format compliance."""

    def test_warning_uses_extra_dict_not_fstring(self):
        """Warnings use structured logging with extra dict, not f-strings."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=10000,
            indexed_points=10000,
            segments_count=1,
            disk_size_bytes=1024000,
            last_updated="2026-01-13T10:00:00Z",
            projects=[],
            points_by_project={},
        )

        with patch("memory.warnings.logger") as mock_logger:
            check_collection_thresholds(stats)

            # Verify logger.warning called with message and extra dict
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args

            # First arg is message string (not f-string)
            assert call_args[0][0] == "collection_size_warning"

            # Second arg (keyword) is extra dict with context
            assert "extra" in call_args[1]
            assert isinstance(call_args[1]["extra"], dict)
            assert "collection" in call_args[1]["extra"]
            assert "size" in call_args[1]["extra"]
            assert "threshold" in call_args[1]["extra"]

    def test_critical_uses_logger_error(self):
        """CRITICAL warnings use logger.error, not logger.warning."""
        stats = CollectionStats(
            collection_name="code-patterns",
            total_points=50000,
            indexed_points=50000,
            segments_count=5,
            disk_size_bytes=10240000,
            last_updated="2026-01-13T10:00:00Z",
            projects=[],
            points_by_project={},
        )

        with patch("memory.warnings.logger") as mock_logger:
            check_collection_thresholds(stats)

            # Verify logger.error called, not logger.warning
            mock_logger.error.assert_called_once()
            mock_logger.warning.assert_not_called()

            # Verify error message format
            call_args = mock_logger.error.call_args
            assert call_args[0][0] == "collection_size_critical"
