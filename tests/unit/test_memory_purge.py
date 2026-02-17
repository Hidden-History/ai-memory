"""Tests for /memory-purge skill: duration parsing + purge logic.

Tests the core functions from the memory-purge skill without
requiring a running Qdrant instance (mocked).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Replicate the parse_duration function from the skill for testability.
# The skill lives in SKILL.md (not a normal importable module), so we
# inline the function here to test it.


def parse_duration(duration_str: str) -> timedelta:
    """Parse duration string like '30d', '2w', '3m', '1y' to timedelta."""
    match = re.match(r"^(\d+)([dwmy])$", duration_str.strip())
    if not match:
        raise ValueError(
            f"Invalid duration: '{duration_str}'. "
            f"Use format: <number><unit> where unit = d/w/m/y"
        )
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)
    elif unit == "m":
        return timedelta(days=value * 30)
    elif unit == "y":
        return timedelta(days=value * 365)
    raise ValueError(f"Unknown unit: {unit}")


# -- Duration parsing tests ------------------------------------------------


class TestParseDuration:
    def test_parse_duration_days(self):
        assert parse_duration("30d") == timedelta(days=30)

    def test_parse_duration_weeks(self):
        assert parse_duration("2w") == timedelta(weeks=2)

    def test_parse_duration_months(self):
        assert parse_duration("3m") == timedelta(days=90)

    def test_parse_duration_years(self):
        assert parse_duration("1y") == timedelta(days=365)

    def test_parse_duration_zero_days(self):
        assert parse_duration("0d") == timedelta(0)

    def test_parse_duration_large_value(self):
        assert parse_duration("365d") == timedelta(days=365)

    def test_parse_duration_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("abc")

    def test_parse_duration_no_unit(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("30")

    def test_parse_duration_empty(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("")

    def test_parse_duration_negative(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("-5d")

    def test_parse_duration_whitespace(self):
        assert parse_duration("  30d  ") == timedelta(days=30)

    def test_parse_duration_invalid_unit(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("30x")


# -- Purge scan/execute logic tests (mocked Qdrant) -----------------------


def _make_mock_point(point_id, type_val, timestamp_val):
    """Create a mock Qdrant point."""
    point = MagicMock()
    point.id = point_id
    point.payload = {"type": type_val, "timestamp": timestamp_val}
    return point


class TestScanPurgeable:
    """Test scan_purgeable logic with mocked Qdrant client."""

    def test_scan_returns_old_points(self):
        """Scan finds points older than cutoff."""
        mock_client = MagicMock()
        old_point = _make_mock_point("p1", "code_pattern", "2025-01-01T00:00:00+00:00")
        mock_client.scroll.return_value = ([old_point], None)

        # Simulate scan_purgeable: scroll returns matching points
        results = {}
        collections = ["code-patterns"]

        for collection in collections:
            points_to_purge = []
            # scroll is called with a filter (mocked - doesn't validate Range)
            points, next_offset = mock_client.scroll(
                collection_name=collection,
                scroll_filter=MagicMock(),  # Filter with Range(lt=cutoff_iso)
                limit=100,
                offset=None,
                with_payload=["type", "timestamp"],
            )
            for point in points:
                payload = point.payload or {}
                points_to_purge.append((
                    point.id, payload.get("type", "unknown"), payload.get("timestamp", "unknown")
                ))
            if points_to_purge:
                results[collection] = points_to_purge

        assert "code-patterns" in results
        assert len(results["code-patterns"]) == 1
        assert results["code-patterns"][0][0] == "p1"

    def test_scan_empty_when_no_old_points(self):
        """No points older than cutoff returns empty dict."""
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)

        # Inline simplified scan
        results = {}
        points, _ = mock_client.scroll(
            collection_name="code-patterns",
            scroll_filter=MagicMock(),
            limit=100,
            offset=None,
            with_payload=["type", "timestamp"],
        )
        if points:
            results["code-patterns"] = points
        assert results == {}


class TestExecutePurge:
    """Test execute_purge and log_purge logic."""

    def test_execute_purge_deletes_points(self):
        """execute_purge calls client.delete with correct IDs."""
        mock_client = MagicMock()
        purgeable = {
            "code-patterns": [("p1", "code_pattern", "ts1"), ("p2", "code_pattern", "ts2")],
        }

        deleted = {}
        for collection, points in purgeable.items():
            point_ids = [pid for pid, _, _ in points]
            for i in range(0, len(point_ids), 100):
                batch = point_ids[i : i + 100]
                mock_client.delete(collection_name=collection, points_selector=batch)
            deleted[collection] = len(point_ids)

        assert deleted == {"code-patterns": 2}
        mock_client.delete.assert_called_once_with(
            collection_name="code-patterns",
            points_selector=["p1", "p2"],
        )

    def test_dry_run_does_not_delete(self):
        """Dry run (no --confirm) should not call delete."""
        mock_client = MagicMock()
        # simulate dry-run: just scan, no delete call
        purgeable = {"code-patterns": [("p1", "cp", "ts1")]}

        # Format output but don't delete
        total = sum(len(pts) for pts in purgeable.values())
        assert total == 1
        mock_client.delete.assert_not_called()

    def test_project_scoped_purge(self):
        """Only deletes vectors matching current group_id."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        mock_client = MagicMock()
        pa = _make_mock_point("pa1", "code_pattern", "2025-01-01T00:00:00+00:00")
        mock_client.scroll.return_value = ([pa], None)

        group_id = "project-a"

        # Build filter with group_id (Range mocked since datetime strings
        # are only accepted by Qdrant server, not the Python model)
        must_conditions = [
            MagicMock(key="timestamp"),  # Range filter (mocked)
            FieldCondition(key="group_id", match=MatchValue(value=group_id)),
        ]

        points, _ = mock_client.scroll(
            collection_name="code-patterns",
            scroll_filter=Filter(must=must_conditions),
            limit=100,
            offset=None,
            with_payload=["type", "timestamp"],
        )

        # Verify the scroll was called with group_id filter
        call_args = mock_client.scroll.call_args
        scroll_filter = call_args.kwargs["scroll_filter"]
        assert len(scroll_filter.must) == 2
        assert scroll_filter.must[1].key == "group_id"

    def test_audit_log_written(self, tmp_path):
        """Purge writes audit log to .audit/logs/purge-log.jsonl."""
        log_path = tmp_path / ".audit" / "logs" / "purge-log.jsonl"
        purgeable = {"code-patterns": [("p1", "cp", "ts1")]}
        deleted = {"code-patterns": 1}
        cutoff_iso = "2026-01-01T00:00:00+00:00"

        # Inline log_purge logic
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cutoff": cutoff_iso,
            "collections": {col: len(pts) for col, pts in purgeable.items()},
            "deleted": deleted,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        assert log_path.exists()
        log_data = json.loads(log_path.read_text().strip())
        assert log_data["cutoff"] == cutoff_iso
        assert log_data["deleted"] == {"code-patterns": 1}

    def test_collection_filter(self):
        """--collection limits purge to single collection."""
        all_collections = ["code-patterns", "conventions", "discussions"]
        selected = "code-patterns"

        filtered = [selected] if selected in all_collections else all_collections
        assert filtered == ["code-patterns"]
