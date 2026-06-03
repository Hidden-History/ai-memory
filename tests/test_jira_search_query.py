"""Tests for _ai-memory/skills/aim-jira-search/scripts/query.py.

Hermetic — no live Qdrant, no real memory.config values, AI_MEMORY_PROJECT_ID unset.
Uses importlib.util.spec_from_file_location to load the script and
monkeypatch.setitem to replace memory.* in sys.modules before execution.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

_QUERY_PY = (
    Path(__file__).parent.parent
    / "_ai-memory"
    / "skills"
    / "aim-jira-search"
    / "scripts"
    / "query.py"
)


@pytest.fixture()
def qmod(monkeypatch):
    """Load query.py with memory.* mocked.

    Yields:
        tuple[module, MagicMock]: (loaded query module, mock qdrant client)
    """
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mock_config = MagicMock()
    mock_client = MagicMock()
    mock_get_config = MagicMock(return_value=mock_config)
    mock_get_qdrant_client = MagicMock(return_value=mock_client)

    # Stub memory.config
    mem_config_mod = ModuleType("memory.config")
    mem_config_mod.get_config = mock_get_config
    mem_config_mod.COLLECTION_JIRA_DATA = "jira-data"

    # Stub memory.qdrant_client
    mem_qdrant_mod = ModuleType("memory.qdrant_client")
    mem_qdrant_mod.get_qdrant_client = mock_get_qdrant_client

    monkeypatch.setitem(sys.modules, "memory.config", mem_config_mod)
    monkeypatch.setitem(sys.modules, "memory.qdrant_client", mem_qdrant_mod)

    # Fresh load each test
    monkeypatch.delitem(sys.modules, "aim_jira_search_query", raising=False)
    spec = importlib.util.spec_from_file_location("aim_jira_search_query", _QUERY_PY)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "aim_jira_search_query", mod)
    spec.loader.exec_module(mod)

    # Default scroll response: single mock point
    mock_point = MagicMock()
    mock_point.id = "abc-111"
    mock_point.payload = {
        "jira_issue_key": "BMAD-42",
        "type": "jira_issue",
        "jira_status": "Done",
        "content": "Test issue content for hermetic unit tests",
    }
    mock_client.scroll.return_value = ([mock_point], None)

    # Default count response (client.count form — F-3 fix)
    mock_count_result = MagicMock()
    mock_count_result.count = 99
    mock_client.count.return_value = mock_count_result

    return mod, mock_client


# ---------------------------------------------------------------------------
# build_filter unit tests — assert correct FieldCondition must-list per form
# ---------------------------------------------------------------------------


def test_build_filter_no_args(qmod):
    """No args → None (no filter)."""
    mod, _ = qmod
    assert mod.build_filter() is None


def test_build_filter_project_only(qmod):
    """--project BMAD → must=[FieldCondition(jira_project=BMAD)]."""
    mod, _ = qmod
    f = mod.build_filter(project="BMAD")
    assert f is not None
    assert len(f.must) == 1
    assert f.must[0].key == "jira_project"
    assert f.must[0].match.value == "BMAD"


def test_build_filter_project_issue_type_status(qmod):
    """--project + --issue-type + --status → 3-condition must list."""
    mod, _ = qmod
    f = mod.build_filter(project="BMAD", issue_type="Bug", status="Done")
    assert f is not None
    assert len(f.must) == 3
    by_key = {c.key: c.match.value for c in f.must}
    assert by_key == {
        "jira_project": "BMAD",
        "jira_issue_type": "Bug",
        "jira_status": "Done",
    }


def test_build_filter_issue_key_and_doc_type(qmod):
    """--issue-key + --doc-type → 2-condition must list (all-comments form)."""
    mod, _ = qmod
    f = mod.build_filter(issue_key="BMAD-42", doc_type="jira_comment")
    assert f is not None
    assert len(f.must) == 2
    by_key = {c.key: c.match.value for c in f.must}
    assert by_key == {"jira_issue_key": "BMAD-42", "type": "jira_comment"}


def test_build_filter_all_flags(qmod):
    """All named flags → 5-condition must list."""
    mod, _ = qmod
    f = mod.build_filter(
        project="PROJ",
        issue_type="Story",
        status="In Progress",
        issue_key="PROJ-7",
        doc_type="jira_issue",
    )
    assert len(f.must) == 5
    by_key = {c.key: c.match.value for c in f.must}
    assert by_key["jira_project"] == "PROJ"
    assert by_key["jira_issue_type"] == "Story"
    assert by_key["jira_status"] == "In Progress"
    assert by_key["jira_issue_key"] == "PROJ-7"
    assert by_key["type"] == "jira_issue"


# ---------------------------------------------------------------------------
# --count mode
# ---------------------------------------------------------------------------


def test_count_mode(qmod, capsys):
    """--count calls client.count() (exact=True) and prints 'Points: N'."""
    mod, mock_client = qmod
    mod.main(["--count"])

    mock_client.count.assert_called_once_with(collection_name="jira-data", exact=True)
    mock_client.scroll.assert_not_called()

    out = capsys.readouterr().out.strip()
    assert out == "Points: 99"


def test_count_mode_custom_collection(qmod, capsys):
    """--count --collection custom-col uses the specified collection."""
    mod, mock_client = qmod
    mod.main(["--count", "--collection", "custom-col"])
    mock_client.count.assert_called_once_with(collection_name="custom-col", exact=True)
    out = capsys.readouterr().out.strip()
    assert out == "Points: 99"


# ---------------------------------------------------------------------------
# scroll mode — CLI flag → scroll() call args
# ---------------------------------------------------------------------------


def test_scroll_no_flags(qmod):
    """No filter flags → scroll_filter=None."""
    mod, mock_client = qmod
    mod.main(["--limit", "5"])
    kw = mock_client.scroll.call_args.kwargs
    assert kw["scroll_filter"] is None
    assert kw["limit"] == 5
    assert kw["collection_name"] == "jira-data"
    assert kw["with_payload"] is True
    assert kw["with_vectors"] is False


def test_scroll_project_flag(qmod):
    """--project PROJ → scroll with Filter(must=[jira_project=PROJ])."""
    mod, mock_client = qmod
    mod.main(["--project", "PROJ", "--limit", "10"])
    f = mock_client.scroll.call_args.kwargs["scroll_filter"]
    assert len(f.must) == 1
    assert f.must[0].key == "jira_project"
    assert f.must[0].match.value == "PROJ"


def test_scroll_project_issue_type_status(qmod):
    """Three named flags → scroll with 3-condition Filter."""
    mod, mock_client = qmod
    mod.main(["--project", "BMAD", "--issue-type", "Bug", "--status", "Done"])
    f = mock_client.scroll.call_args.kwargs["scroll_filter"]
    assert len(f.must) == 3
    by_key = {c.key: c.match.value for c in f.must}
    assert by_key["jira_project"] == "BMAD"
    assert by_key["jira_issue_type"] == "Bug"
    assert by_key["jira_status"] == "Done"


def test_scroll_issue_key_doc_type(qmod):
    """--issue-key + --doc-type → scroll with 2-condition Filter."""
    mod, mock_client = qmod
    mod.main(["--issue-key", "BMAD-42", "--doc-type", "jira_comment", "--limit", "50"])
    f = mock_client.scroll.call_args.kwargs["scroll_filter"]
    by_key = {c.key: c.match.value for c in f.must}
    assert by_key == {"jira_issue_key": "BMAD-42", "type": "jira_comment"}
    assert mock_client.scroll.call_args.kwargs["limit"] == 50


# ---------------------------------------------------------------------------
# --format output
# ---------------------------------------------------------------------------


def test_format_table(qmod, capsys):
    """Default --format table prints human-readable lines (inline format).

    Asserts the exact inline strings restored by DEC-105:
      Found {n} points
      {jira_issue_key} [{type}] - {jira_status} - {content[:80]}...
    """
    mod, _ = qmod
    mod.main(["--project", "BMAD"])
    out = capsys.readouterr().out
    assert "Found 1 points" in out
    assert "BMAD-42" in out
    assert " - Done - " in out
    assert "..." in out


def test_format_json(qmod, capsys):
    """--format json prints a JSON array with id + payload keys."""
    mod, _ = qmod
    mod.main(["--project", "BMAD", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert data[0]["payload"]["jira_issue_key"] == "BMAD-42"


def test_format_default_is_table(qmod, capsys):
    """No --format flag → table (not JSON)."""
    mod, _ = qmod
    mod.main([])
    out = capsys.readouterr().out
    assert "Found" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------


def test_default_collection(qmod):
    """Default --collection is jira-data."""
    mod, mock_client = qmod
    mod.main([])
    assert mock_client.scroll.call_args.kwargs["collection_name"] == "jira-data"


def test_no_score_threshold_flag(qmod):
    """--score-threshold flag does not exist in the named-flag interface."""
    mod, _ = qmod
    with pytest.raises(SystemExit):
        mod.main(["--score-threshold", "0.7"])
