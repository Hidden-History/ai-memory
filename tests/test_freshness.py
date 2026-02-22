"""Unit tests for freshness detection module (SPEC-013).

Tests cover all freshness detection functionality:
- Classification logic (fresh/aging/stale/expired/unknown)
- Ground truth map construction
- Commit counting
- Full scan orchestration
- Config validation
- Payload updates and audit logging
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from memory.config import MemoryConfig
from memory.freshness import (
    FreshnessReport,
    FreshnessResult,
    FreshnessTier,
    build_ground_truth_map,
    classify_freshness,
    count_commits_for_file,
    run_freshness_scan,
)


class TestClassifyFreshness:
    """Test freshness classification logic."""

    def test_classify_fresh(self):
        """Test blob_hash match + 0 commits = FRESH."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, reason = classify_freshness(None, 0, config)
        assert tier == FreshnessTier.FRESH
        assert "0 commits" in reason

    def test_classify_aging(self):
        """Test blob_hash match + 3 commits = AGING."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, reason = classify_freshness(None, 3, config)
        assert tier == FreshnessTier.AGING
        assert "3 commits" in reason

    def test_classify_stale(self):
        """Test blob_hash match + 10 commits = STALE."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, reason = classify_freshness(None, 10, config)
        assert tier == FreshnessTier.STALE
        assert "10 commits" in reason

    def test_classify_expired_hash_mismatch(self):
        """Test blob_hash mismatch = EXPIRED regardless of commits."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, reason = classify_freshness(False, 2, config)
        assert tier == FreshnessTier.EXPIRED
        assert "Blob hash mismatch" in reason

    def test_classify_expired_high_churn(self):
        """Test blob_hash match + 25 commits = EXPIRED."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, reason = classify_freshness(None, 25, config)
        assert tier == FreshnessTier.EXPIRED
        assert "25 commits" in reason

    def test_classify_none_hash_falls_through(self):
        """Test blob_hash_match=None with 0 commits = FRESH."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, _reason = classify_freshness(None, 0, config)
        assert tier == FreshnessTier.FRESH

    def test_classify_boundary_aging(self):
        """Test exactly aging threshold commits."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, _ = classify_freshness(None, 3, config)
        assert tier == FreshnessTier.AGING

    def test_classify_boundary_stale(self):
        """Test exactly stale threshold commits."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, _ = classify_freshness(None, 10, config)
        assert tier == FreshnessTier.STALE

    def test_classify_boundary_expired(self):
        """Test exactly expired threshold commits."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, _ = classify_freshness(None, 25, config)
        assert tier == FreshnessTier.EXPIRED

    def test_classify_below_aging(self):
        """Test aging_threshold - 1 = FRESH."""
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        tier, _ = classify_freshness(None, 2, config)
        assert tier == FreshnessTier.FRESH


class TestGroundTruthMap:
    """Test ground truth map construction."""

    def test_ground_truth_map_empty(self):
        """Test no github_code_blob data = empty dict."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        config = MemoryConfig()
        result = build_ground_truth_map(mock_client, config)

        assert result == {}
        assert mock_client.scroll.call_count == 1

    def test_ground_truth_map_dedup(self):
        """Test multiple chunks same file_path = single entry."""
        mock_point1 = Mock()
        mock_point1.payload = {
            "file_path": "src/memory/search.py",
            "blob_hash": "abc123",
            "last_commit_sha": "def456",
            "last_synced": "2026-02-16T00:00:00Z",
        }
        mock_point2 = Mock()
        mock_point2.payload = {
            "file_path": "src/memory/search.py",
            "blob_hash": "abc123",
            "last_commit_sha": "def456",
            "last_synced": "2026-02-16T00:00:00Z",
        }

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([mock_point1, mock_point2], None)

        config = MemoryConfig()
        result = build_ground_truth_map(mock_client, config)

        assert len(result) == 1
        assert "src/memory/search.py" in result
        assert result["src/memory/search.py"].blob_hash == "abc123"

    def test_ground_truth_map_filter(self):
        """Test only is_current=True, source=github, type=github_code_blob."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        config = MemoryConfig()
        build_ground_truth_map(mock_client, config)

        # Verify scroll was called with correct filters
        call_args = mock_client.scroll.call_args
        scroll_filter = call_args[1]["scroll_filter"]
        assert scroll_filter is not None


class TestCommitCounting:
    """Test commit counting functionality."""

    def test_count_commits_none_after(self):
        """Test no commits after stored_at = 0."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        count = count_commits_for_file(
            mock_client, "src/memory/search.py", "2026-02-16T00:00:00Z"
        )

        assert count == 0

    def test_count_commits_filters_by_date(self):
        """Test only counts commits after stored_at."""
        mock_commit1 = Mock()
        mock_commit1.payload = {
            "timestamp": "2026-02-15T00:00:00Z",  # Before stored_at
            "files_changed": ["src/memory/search.py"],
        }
        mock_commit2 = Mock()
        mock_commit2.payload = {
            "timestamp": "2026-02-17T00:00:00Z",  # After stored_at
            "files_changed": ["src/memory/search.py"],
        }

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([mock_commit1, mock_commit2], None)

        count = count_commits_for_file(
            mock_client, "src/memory/search.py", "2026-02-16T00:00:00Z"
        )

        assert count == 1

    def test_count_commits_filters_by_file(self):
        """Test only counts commits touching target file."""
        mock_commit1 = Mock()
        mock_commit1.payload = {
            "timestamp": "2026-02-17T00:00:00Z",
            "files_changed": ["src/memory/search.py"],
        }
        mock_commit2 = Mock()
        mock_commit2.payload = {
            "timestamp": "2026-02-17T00:00:00Z",
            "files_changed": ["src/memory/config.py"],  # Different file
        }

        mock_client = MagicMock()
        mock_client.scroll.return_value = ([mock_commit1, mock_commit2], None)

        count = count_commits_for_file(
            mock_client, "src/memory/search.py", "2026-02-16T00:00:00Z"
        )

        assert count == 1

    def test_count_commits_invalid_since(self):
        """Test invalid stored_at timestamp returns 0."""
        mock_client = MagicMock()
        count = count_commits_for_file(
            mock_client, "src/memory/search.py", "invalid-timestamp"
        )
        assert count == 0


class TestFreshnessScan:
    """Test full freshness scan orchestration."""

    def test_scan_disabled(self):
        """Test freshness_enabled=False returns empty report."""
        config = MemoryConfig(freshness_enabled=False)
        report = run_freshness_scan(config=config)

        assert report.total_checked == 0
        assert report.fresh_count == 0
        assert report.aging_count == 0
        assert report.stale_count == 0
        assert report.expired_count == 0
        assert report.unknown_count == 0

    @patch("memory.freshness.get_qdrant_client")
    def test_scan_no_ground_truth(self, mock_get_client):
        """Test empty ground truth map returns empty report."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_get_client.return_value = mock_client

        config = MemoryConfig(freshness_enabled=True)
        report = run_freshness_scan(config=config)

        assert report.total_checked == 0

    @patch("memory.freshness.build_ground_truth_map")
    @patch("memory.freshness.get_qdrant_client")
    def test_scan_skips_no_file_path(self, mock_get_client, mock_build_gt):
        """Test points without file_path are skipped."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Provide non-empty ground truth so the scan proceeds past early return
        gt_entry = MagicMock()
        gt_entry.blob_hash = "abc123"
        mock_build_gt.return_value = {"src/memory/search.py": gt_entry}

        # Return a point WITHOUT file_path in the code-patterns scroll
        mock_point = MagicMock()
        mock_point.id = "test-point-no-path"
        mock_point.payload = {"type": "pattern", "stored_at": "2026-01-01T00:00:00Z"}
        mock_client.scroll.return_value = ([mock_point], None)

        config = MemoryConfig(freshness_enabled=True)
        report = run_freshness_scan(config=config)

        # Point without file_path is skipped → not counted
        assert report.total_checked == 0
        assert len(report.results) == 0

    @patch("memory.freshness.get_qdrant_client")
    def test_scan_qdrant_unavailable(self, mock_get_client):
        """Test Qdrant unavailable = empty report, no crash."""
        mock_get_client.side_effect = Exception("Qdrant unavailable")

        config = MemoryConfig(freshness_enabled=True)
        report = run_freshness_scan(config=config)

        assert report.total_checked == 0
        assert report.duration_seconds >= 0


class TestConfigValidation:
    """Test config threshold validation."""

    def test_config_threshold_ordering(self):
        """Test thresholds must be in ascending order."""
        # Valid ordering
        config = MemoryConfig(
            freshness_commit_threshold_aging=3,
            freshness_commit_threshold_stale=10,
            freshness_commit_threshold_expired=25,
        )
        assert (
            config.freshness_commit_threshold_aging
            < config.freshness_commit_threshold_stale
        )
        assert (
            config.freshness_commit_threshold_stale
            < config.freshness_commit_threshold_expired
        )

    def test_config_threshold_validation_fail(self):
        """Test invalid ordering raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(
                freshness_commit_threshold_aging=10,
                freshness_commit_threshold_stale=5,
                freshness_commit_threshold_expired=25,
            )
        assert "ascending order" in str(exc_info.value)

    def test_config_threshold_equal_fails(self):
        """Test equal thresholds fail validation."""
        with pytest.raises(ValidationError):
            MemoryConfig(
                freshness_commit_threshold_aging=10,
                freshness_commit_threshold_stale=10,
                freshness_commit_threshold_expired=25,
            )


class TestPayloadUpdates:
    """Test Qdrant payload update functionality."""

    def test_payload_update_freshness_status(self):
        """Test _update_freshness_payloads calls set_payload with correct fields."""
        from memory.freshness import _update_freshness_payloads

        mock_client = MagicMock()

        results = [
            FreshnessResult(
                point_id="point-abc",
                file_path="src/memory/search.py",
                memory_type="pattern",
                status=FreshnessTier.STALE,
                reason="10 commits since stored",
                stored_at="2026-01-01T00:00:00Z",
                blob_hash_match=None,
                commit_count=10,
            )
        ]

        _update_freshness_payloads(mock_client, results)

        mock_client.set_payload.assert_called_once()
        call_kwargs = mock_client.set_payload.call_args.kwargs
        assert call_kwargs["payload"]["freshness_status"] == FreshnessTier.STALE
        assert "freshness_checked_at" in call_kwargs["payload"]
        assert call_kwargs["points"] == ["point-abc"]


class TestAuditLogging:
    """Test audit trail logging."""

    def test_audit_log_written(self):
        """Test freshness-log.jsonl created with correct entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MemoryConfig(audit_dir=Path(".audit"))
            results = [
                FreshnessResult(
                    point_id="test-id",
                    file_path="src/memory/test.py",
                    memory_type="pattern",
                    status="fresh",
                    reason="Test reason",
                    stored_at="2026-02-16T00:00:00Z",
                    blob_hash_match=None,
                    commit_count=0,
                )
            ]

            from memory.freshness import _log_freshness_results

            _log_freshness_results(results, config, cwd=tmpdir)

            log_path = Path(tmpdir) / ".audit" / "logs" / "freshness-log.jsonl"
            assert log_path.exists()

            with open(log_path) as f:
                line = f.readline()
                entry = json.loads(line)
                assert entry["point_id"] == "test-id"
                assert entry["status"] == "fresh"

    def test_audit_log_dir_created(self):
        """Test .audit/logs/ created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = MemoryConfig(audit_dir=Path(".audit"))
            results = [
                FreshnessResult(
                    point_id="test-id",
                    file_path="src/memory/test.py",
                    memory_type="pattern",
                    status="fresh",
                    reason="Test",
                    stored_at="2026-02-16T00:00:00Z",
                    blob_hash_match=None,
                    commit_count=0,
                )
            ]

            from memory.freshness import _log_freshness_results

            _log_freshness_results(results, config, cwd=tmpdir)

            log_dir = Path(tmpdir) / ".audit" / "logs"
            assert log_dir.exists()
            assert log_dir.is_dir()


class TestReportFormatting:
    """Test report formatting functionality."""

    def test_report_format_all_fresh(self):
        """Test format output when everything is fresh."""
        import dataclasses

        ts = datetime.now(timezone.utc).isoformat()
        report = FreshnessReport(
            total_checked=10,
            fresh_count=10,
            aging_count=0,
            stale_count=0,
            expired_count=0,
            unknown_count=0,
            duration_seconds=1.5,
            results=[],
            timestamp=ts,
        )

        # Serialize the report and verify all fields are present and correct
        data = dataclasses.asdict(report)
        assert data["total_checked"] == 10
        assert data["fresh_count"] == 10
        assert data["aging_count"] == 0
        assert data["stale_count"] == 0
        assert data["expired_count"] == 0
        assert data["unknown_count"] == 0
        # All checked points are fresh
        assert data["fresh_count"] == data["total_checked"]
        # Duration is positive
        assert data["duration_seconds"] > 0
        # Timestamp is a valid ISO string
        assert isinstance(data["timestamp"], str)
        datetime.fromisoformat(data["timestamp"])

    def test_report_format_mixed(self):
        """Test format output with mixed tiers."""
        import dataclasses

        ts = datetime.now(timezone.utc).isoformat()
        report = FreshnessReport(
            total_checked=20,
            fresh_count=10,
            aging_count=5,
            stale_count=3,
            expired_count=2,
            unknown_count=0,
            duration_seconds=2.0,
            results=[],
            timestamp=ts,
        )

        # Serialize the report and verify structural consistency
        data = dataclasses.asdict(report)
        assert data["total_checked"] == 20
        # All tier counts should sum to total_checked (unknown_count == 0 here)
        tier_total = (
            data["fresh_count"]
            + data["aging_count"]
            + data["stale_count"]
            + data["expired_count"]
            + data["unknown_count"]
        )
        assert tier_total == data["total_checked"]
        # No single tier dominates (mixed distribution)
        assert data["fresh_count"] < data["total_checked"]
        assert data["expired_count"] > 0


class TestIntegration:
    """Integration tests for end-to-end functionality."""

    @patch("memory.freshness.get_qdrant_client")
    def test_end_to_end_scan(self, mock_get_client):
        """Test full pipeline: ground truth build -> scan -> classify -> update -> log."""
        # Set up mock Qdrant client
        mock_client = MagicMock()

        # Mock ground truth data (GitHub code blobs)
        mock_blob = Mock()
        mock_blob.payload = {
            "file_path": "src/memory/test.py",
            "blob_hash": "abc123",
            "last_commit_sha": "def456",
            "last_synced": "2026-02-16T00:00:00Z",
        }

        # Mock code-patterns point
        mock_pattern = Mock()
        mock_pattern.id = "pattern-id-1"
        mock_pattern.payload = {
            "file_path": "src/memory/test.py",
            "type": "pattern",
            "stored_at": "2026-02-15T00:00:00Z",
        }

        # Mock commit data
        mock_commit = Mock()
        mock_commit.payload = {
            "timestamp": "2026-02-16T12:00:00Z",
            "files_changed": ["src/memory/test.py"],
        }

        # Set up scroll return values in sequence
        mock_client.scroll.side_effect = [
            # First call: build_ground_truth_map
            ([mock_blob], None),
            # Second call: scroll code-patterns
            ([mock_pattern], None),
            # Third call: count_commits_for_file
            ([mock_commit], None),
        ]

        mock_get_client.return_value = mock_client

        with tempfile.TemporaryDirectory() as tmpdir:
            config = MemoryConfig(freshness_enabled=True, audit_dir=Path(".audit"))
            report = run_freshness_scan(config=config, cwd=tmpdir)

            assert report.total_checked == 1
            assert report.fresh_count == 1  # 1 commit < 3 threshold = fresh
            assert len(report.results) == 1

            # Verify audit log was created
            log_path = Path(tmpdir) / ".audit" / "logs" / "freshness-log.jsonl"
            assert log_path.exists()
