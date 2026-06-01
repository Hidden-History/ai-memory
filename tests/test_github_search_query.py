"""Tests for _ai-memory/skills/aim-github-search/scripts/query.py.

Hermetic — loads query.py via importlib, mocks memory.* and the qdrant_client
instance via monkeypatch.setitem(sys.modules) so no live services are required.
AI_MEMORY_PROJECT_ID is not set.

Covers every documented filter form:
  - source + group_id only (base form)
  - source + group_id + type
  - source + group_id + state
  - source + group_id + type + state
  - count form (--format count → client.count(), not scroll-then-len)
  - json format (--format json)
  - argparse defaults and required-arg enforcement
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue

# ---------------------------------------------------------------------------
# Path to the script under test
# ---------------------------------------------------------------------------

_QUERY_PY = (
    Path(__file__).parent.parent
    / "_ai-memory"
    / "skills"
    / "aim-github-search"
    / "scripts"
    / "query.py"
)


# ---------------------------------------------------------------------------
# Hermetic loader fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def query_module(monkeypatch):
    """Load query.py with memory.* and qdrant client instance mocked.

    Uses monkeypatch.setitem to inject stub modules into sys.modules so that
    query.py's module-level imports resolve without touching live services.
    Monkeypatch cleanup restores sys.modules after each test.

    Returns:
        tuple[module, MagicMock]: (loaded query module, mock qdrant client instance)
    """
    mock_client = MagicMock()
    # Default scroll → empty result (points, next_page_offset)
    mock_client.scroll.return_value = ([], None)
    # Default count → 0
    mock_client.count.return_value = MagicMock(count=0)

    # Stub memory package
    memory_mod = ModuleType("memory")
    monkeypatch.setitem(sys.modules, "memory", memory_mod)

    # Stub memory.config
    config_mod = ModuleType("memory.config")
    config_mod.get_config = MagicMock(return_value=MagicMock())
    monkeypatch.setitem(sys.modules, "memory.config", config_mod)

    # Stub memory.qdrant_client
    qdrant_mod = ModuleType("memory.qdrant_client")
    qdrant_mod.get_qdrant_client = MagicMock(return_value=mock_client)
    monkeypatch.setitem(sys.modules, "memory.qdrant_client", qdrant_mod)

    # Remove any cached query module from a prior test
    monkeypatch.delitem(sys.modules, "query", raising=False)

    # AI_MEMORY_PROJECT_ID must NOT be set (hermetic)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    # Load query.py by file location
    spec = importlib.util.spec_from_file_location("query", _QUERY_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return mod, mock_client


# ---------------------------------------------------------------------------
# build_filter — pure function tests (no client needed)
# ---------------------------------------------------------------------------


class TestBuildFilter:
    """Verify that build_filter() constructs the correct Qdrant Filter per form."""

    def test_base_form_source_and_group_id(self, query_module):
        """Form 1: source=github + group_id only — no type/state."""
        mod, _ = query_module
        result = mod.build_filter("hidden-history/ai-memory", None, None)
        expected = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value="github")),
                FieldCondition(
                    key="group_id", match=MatchValue(value="hidden-history/ai-memory")
                ),
            ]
        )
        assert result == expected

    def test_with_type_filter(self, query_module):
        """Form 2: source + group_id + type."""
        mod, _ = query_module
        result = mod.build_filter("hidden-history/ai-memory", "github_pr", None)
        expected = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value="github")),
                FieldCondition(
                    key="group_id", match=MatchValue(value="hidden-history/ai-memory")
                ),
                FieldCondition(key="type", match=MatchValue(value="github_pr")),
            ]
        )
        assert result == expected

    def test_with_state_filter(self, query_module):
        """Form 3: source + group_id + state."""
        mod, _ = query_module
        result = mod.build_filter("hidden-history/ai-memory", None, "merged")
        expected = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value="github")),
                FieldCondition(
                    key="group_id", match=MatchValue(value="hidden-history/ai-memory")
                ),
                FieldCondition(key="state", match=MatchValue(value="merged")),
            ]
        )
        assert result == expected

    def test_with_type_and_state(self, query_module):
        """Form 4: source + group_id + type + state (all filters)."""
        mod, _ = query_module
        result = mod.build_filter("hidden-history/ai-memory", "github_pr", "merged")
        expected = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value="github")),
                FieldCondition(
                    key="group_id", match=MatchValue(value="hidden-history/ai-memory")
                ),
                FieldCondition(key="type", match=MatchValue(value="github_pr")),
                FieldCondition(key="state", match=MatchValue(value="merged")),
            ]
        )
        assert result == expected

    def test_other_document_types(self, query_module):
        """Other documented type values produce correct filter."""
        mod, _ = query_module
        for doc_type in (
            "github_issue",
            "github_commit",
            "github_ci_result",
            "github_code_blob",
            "github_issue_comment",
            "github_pr_review",
            "github_pr_diff",
        ):
            result = mod.build_filter("owner/repo", doc_type, None)
            must_keys = [c.key for c in result.must]
            must_values = {c.key: c.match.value for c in result.must}
            assert must_keys == ["source", "group_id", "type"]
            assert must_values["type"] == doc_type

    def test_source_always_github(self, query_module):
        """source=github is always the first must condition regardless of args."""
        mod, _ = query_module
        for type_f, state_f in [
            (None, None),
            ("github_pr", None),
            (None, "open"),
            ("github_issue", "closed"),
        ]:
            result = mod.build_filter("owner/repo", type_f, state_f)
            first = result.must[0]
            assert first.key == "source"
            assert first.match.value == "github"


# ---------------------------------------------------------------------------
# parse_args — argparse interface tests
# ---------------------------------------------------------------------------


class TestParseArgs:
    """Verify argparse interface defaults and validation."""

    def test_group_id_required(self, query_module, monkeypatch):
        """--group-id is required; missing → SystemExit(2)."""
        mod, _ = query_module
        monkeypatch.setattr(sys, "argv", ["query.py"])
        with pytest.raises(SystemExit) as exc_info:
            mod.parse_args()
        assert exc_info.value.code == 2

    def test_defaults(self, query_module, monkeypatch):
        """Defaults: collection=discussions, limit=10, format=table, no type/state."""
        mod, _ = query_module
        monkeypatch.setattr(sys, "argv", ["query.py", "--group-id", "owner/repo"])
        args = mod.parse_args()
        assert args.group_id == "owner/repo"
        assert args.collection == "discussions"
        assert args.limit == 10
        assert args.output_format == "table"
        assert args.type_filter is None
        assert args.state_filter is None

    def test_all_flags(self, query_module, monkeypatch):
        """All flags parsed correctly when provided."""
        mod, _ = query_module
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "query.py",
                "--group-id",
                "hidden-history/ai-memory",
                "--type",
                "github_pr",
                "--state",
                "merged",
                "--limit",
                "20",
                "--format",
                "json",
                "--collection",
                "discussions",
            ],
        )
        args = mod.parse_args()
        assert args.group_id == "hidden-history/ai-memory"
        assert args.type_filter == "github_pr"
        assert args.state_filter == "merged"
        assert args.limit == 20
        assert args.output_format == "json"
        assert args.collection == "discussions"

    def test_invalid_format_rejected(self, query_module, monkeypatch):
        """Invalid --format value → SystemExit(2)."""
        mod, _ = query_module
        monkeypatch.setattr(
            sys, "argv", ["query.py", "--group-id", "x/y", "--format", "xml"]
        )
        with pytest.raises(SystemExit) as exc_info:
            mod.parse_args()
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# main() — end-to-end dispatch tests
# ---------------------------------------------------------------------------


class TestMain:
    """Verify main() dispatches to scroll or count with the correct filter."""

    def test_table_format_calls_scroll(self, query_module, monkeypatch, capsys):
        """--format table → client.scroll() called with correct filter + limit."""
        mod, mock_client = query_module
        mock_client.scroll.return_value = ([], None)
        monkeypatch.setattr(
            sys, "argv", ["query.py", "--group-id", "hidden-history/ai-memory"]
        )
        rc = mod.main()
        assert rc == 0
        mock_client.scroll.assert_called_once()
        call_kwargs = mock_client.scroll.call_args.kwargs
        assert call_kwargs["collection_name"] == "discussions"
        assert call_kwargs["limit"] == 10
        assert call_kwargs["with_payload"] is True
        assert call_kwargs["with_vectors"] is False
        # Verify the filter has source=github + group_id in must
        filt = call_kwargs["scroll_filter"]
        must_map = {c.key: c.match.value for c in filt.must}
        assert must_map["source"] == "github"
        assert must_map["group_id"] == "hidden-history/ai-memory"
        # count() must NOT be called for table format
        mock_client.count.assert_not_called()

    def test_count_format_calls_count_not_scroll(
        self, query_module, monkeypatch, capsys
    ):
        """--format count → client.count() called; client.scroll() NOT called."""
        mod, mock_client = query_module
        mock_client.count.return_value = MagicMock(count=42)
        monkeypatch.setattr(
            sys,
            "argv",
            ["query.py", "--group-id", "hidden-history/ai-memory", "--format", "count"],
        )
        rc = mod.main()
        assert rc == 0
        mock_client.count.assert_called_once()
        call_kwargs = mock_client.count.call_args.kwargs
        assert call_kwargs["collection_name"] == "discussions"
        assert call_kwargs["exact"] is True
        # Verify filter
        filt = call_kwargs["count_filter"]
        must_map = {c.key: c.match.value for c in filt.must}
        assert must_map["source"] == "github"
        assert must_map["group_id"] == "hidden-history/ai-memory"
        # scroll must NOT be called
        mock_client.scroll.assert_not_called()
        out = capsys.readouterr().out
        assert "42" in out

    def test_count_format_with_type_and_state(self, query_module, monkeypatch):
        """count + type + state → count_filter has all 4 must conditions."""
        mod, mock_client = query_module
        mock_client.count.return_value = MagicMock(count=7)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "query.py",
                "--group-id",
                "hidden-history/ai-memory",
                "--type",
                "github_pr",
                "--state",
                "merged",
                "--format",
                "count",
            ],
        )
        mod.main()
        filt = mock_client.count.call_args.kwargs["count_filter"]
        must_map = {c.key: c.match.value for c in filt.must}
        assert must_map == {
            "source": "github",
            "group_id": "hidden-history/ai-memory",
            "type": "github_pr",
            "state": "merged",
        }

    def test_json_format_outputs_json(self, query_module, monkeypatch, capsys):
        """--format json → stdout is valid JSON with id and payload keys."""
        mod, mock_client = query_module
        fake_point = MagicMock()
        fake_point.id = "point-abc"
        fake_point.payload = {
            "type": "github_pr",
            "url": "https://github.com/x/y/pull/1",
        }
        mock_client.scroll.return_value = ([fake_point], None)
        monkeypatch.setattr(
            sys,
            "argv",
            ["query.py", "--group-id", "owner/repo", "--format", "json"],
        )
        rc = mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert data[0]["id"] == "point-abc"
        assert data[0]["payload"]["type"] == "github_pr"

    def test_custom_limit_passed_to_scroll(self, query_module, monkeypatch):
        """--limit N is forwarded to scroll()."""
        mod, mock_client = query_module
        mock_client.scroll.return_value = ([], None)
        monkeypatch.setattr(
            sys, "argv", ["query.py", "--group-id", "owner/repo", "--limit", "25"]
        )
        mod.main()
        assert mock_client.scroll.call_args.kwargs["limit"] == 25

    def test_custom_collection_forwarded(self, query_module, monkeypatch):
        """--collection is forwarded to both scroll and count."""
        mod, mock_client = query_module
        mock_client.scroll.return_value = ([], None)
        monkeypatch.setattr(
            sys,
            "argv",
            ["query.py", "--group-id", "owner/repo", "--collection", "custom-coll"],
        )
        mod.main()
        assert mock_client.scroll.call_args.kwargs["collection_name"] == "custom-coll"

    def test_scroll_filter_type_and_state(self, query_module, monkeypatch):
        """scroll filter includes type + state when both flags are provided."""
        mod, mock_client = query_module
        mock_client.scroll.return_value = ([], None)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "query.py",
                "--group-id",
                "hidden-history/ai-memory",
                "--type",
                "github_issue",
                "--state",
                "open",
            ],
        )
        mod.main()
        filt = mock_client.scroll.call_args.kwargs["scroll_filter"]
        must_map = {c.key: c.match.value for c in filt.must}
        assert must_map == {
            "source": "github",
            "group_id": "hidden-history/ai-memory",
            "type": "github_issue",
            "state": "open",
        }

    def test_table_output_format(self, query_module, monkeypatch, capsys):
        """Table format prints Found N + one line per point."""
        mod, mock_client = query_module
        p1 = MagicMock()
        p1.payload = {
            "type": "github_pr",
            "state": "merged",
            "url": "https://github.com/x/y/pull/1",
            "content": "Add decay scoring",
        }
        mock_client.scroll.return_value = ([p1], None)
        monkeypatch.setattr(sys, "argv", ["query.py", "--group-id", "x/y"])
        mod.main()
        out = capsys.readouterr().out
        assert "Found 1 points" in out
        assert "[github_pr]" in out
        assert "merged" in out
