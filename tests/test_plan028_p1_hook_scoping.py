"""Regression tests for PLAN-028 P1 — conventions hook project-scoping.

These tests pin the FIX-1 / FIX-4 behaviour so it cannot silently regress:
every active hook that searches the project-scoped `conventions` collection
must pass `group_id=project_name`, never `group_id=None`.

Coverage:
- FIX-5: new_file_trigger.py conventions search is project-scoped
- FIX-5: best_practices_retrieval.py conventions search is project-scoped
- FIX-4: context_injection_tier2.py conventions route search is project-scoped

PLAN-028 P1 (W-01 / DEC-PM298-D4): conventions is project-scoped — a None
group_id re-introduces the cross-project leak P1 exists to eliminate.
"""

import contextlib
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Hook scripts live outside the importable package — add their dir + src to path.
_HOOK_SCRIPT_DIR = Path(__file__).parent.parent / ".claude" / "hooks" / "scripts"
_SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_HOOK_SCRIPT_DIR))
sys.path.insert(0, str(_SRC_DIR))

import best_practices_retrieval  # noqa: E402
import context_injection_tier2  # noqa: E402
import new_file_trigger  # noqa: E402

from memory.injection import RouteTarget  # noqa: E402

_PROJECT = "test-project"


def _empty_search_instance():
    """Return a mock MemorySearch whose search() returns no results."""
    mock = MagicMock()
    mock.search.return_value = []
    mock.close.return_value = None
    # tier-2 computes a topic-drift embedding after the search loop
    mock.embedding_client.embed.return_value = [[0.0] * 8]
    return mock


# ---------------------------------------------------------------------------
# FIX-5: new_file_trigger.py — conventions search is project-scoped
# ---------------------------------------------------------------------------


class TestNewFileTriggerConventionsScoping:
    """new_file_trigger.py must pass group_id=project_name (FIX-1 regression)."""

    def test_new_file_conventions_search_uses_project_group_id(self, monkeypatch):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", _PROJECT)
        stdin = io.StringIO(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/proj/src/widget.py"},
                    "session_id": "sess-nf-1",
                    "cwd": "/proj",
                }
            )
        )
        mock_search = _empty_search_instance()

        with (
            patch("sys.stdin", stdin),
            patch("new_file_trigger.track_hook_duration", contextlib.nullcontext),
            patch("new_file_trigger.log_to_activity", lambda *a, **k: None),
            patch("memory.triggers.is_new_file", return_value=True),
            patch.dict(
                "memory.triggers.TRIGGER_CONFIG",
                {
                    "new_file": {
                        "enabled": True,
                        "max_results": 2,
                        "type_filter": ["naming", "structure"],
                    }
                },
                clear=False,
            ),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.health.check_qdrant_health", return_value=True),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch("memory.project.detect_project", return_value=_PROJECT),
            patch("memory.search.MemorySearch", return_value=mock_search),
            patch(
                "memory.metrics_push.push_trigger_metrics_async",
                lambda *a, **k: None,
            ),
        ):
            rc = new_file_trigger.main()

        assert rc == 0
        mock_search.search.assert_called_once()
        kwargs = mock_search.search.call_args[1]
        assert kwargs["collection"] == "conventions"
        assert kwargs["group_id"] == _PROJECT, (
            "new_file_trigger conventions search must pass group_id=project_name, "
            f"got {kwargs['group_id']!r} (FIX-1 regression)"
        )


# ---------------------------------------------------------------------------
# FIX-5: best_practices_retrieval.py — conventions search is project-scoped
# ---------------------------------------------------------------------------


class TestBestPracticesRetrievalConventionsScoping:
    """best_practices_retrieval.py must pass group_id=project_name (FIX-1 regression)."""

    def teardown_method(self):
        path = Path("/tmp/ai-memory-sess-bp-1-edit-counts.json")
        if path.exists():
            path.unlink()

    def test_best_practices_conventions_search_uses_project_group_id(self, monkeypatch):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", _PROJECT)
        stdin = io.StringIO(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/proj/src/service.py"},
                    "session_id": "sess-bp-1",
                    "cwd": "/proj",
                }
            )
        )
        mock_search = _empty_search_instance()

        with (
            patch("sys.stdin", stdin),
            patch("memory.health.check_qdrant_health", return_value=True),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.project.detect_project", return_value=_PROJECT),
            patch("memory.search.MemorySearch", return_value=mock_search),
            patch("best_practices_retrieval.push_retrieval_metrics_async", None),
            patch("best_practices_retrieval.push_hook_metrics_async", None),
            patch("best_practices_retrieval.emit_trace_event", None),
            patch(
                "best_practices_retrieval._check_auto_activation",
                return_value="struggling_pattern",
            ),
        ):
            rc = best_practices_retrieval.main()

        assert rc == 0
        mock_search.search.assert_called_once()
        kwargs = mock_search.search.call_args[1]
        assert kwargs["collection"] == "conventions"
        assert kwargs["group_id"] == _PROJECT, (
            "best_practices_retrieval conventions search must pass "
            f"group_id=project_name, got {kwargs['group_id']!r} (FIX-1 regression)"
        )


# ---------------------------------------------------------------------------
# FIX-4: context_injection_tier2.py — conventions route search is project-scoped
# ---------------------------------------------------------------------------


class TestTier2ConventionsScoping:
    """Tier-2 hook must scope a conventions route to the detected project."""

    def test_tier2_conventions_route_uses_project_group_id(self, monkeypatch):
        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", _PROJECT)
        stdin = io.StringIO(
            json.dumps(
                {
                    "prompt": "what are the best practices for Python logging?",
                    "session_id": "sess-t2-1",
                    "cwd": "/proj",
                }
            )
        )
        mock_search = _empty_search_instance()

        with (
            patch("sys.stdin", stdin),
            patch("context_injection_tier2.resolve_project_id", return_value=_PROJECT),
            patch("context_injection_tier2.check_qdrant_health", return_value=True),
            patch(
                "context_injection_tier2.get_qdrant_client", return_value=MagicMock()
            ),
            patch("context_injection_tier2.MemorySearch", return_value=mock_search),
            patch(
                "context_injection_tier2.route_collections",
                return_value=[RouteTarget("conventions")],
            ),
            patch("context_injection_tier2.log_injection_event", lambda *a, **k: None),
        ):
            rc = context_injection_tier2.main()

        assert rc == 0
        # Exactly one routed collection (conventions) → exactly one search call.
        mock_search.search.assert_called_once()
        kwargs = mock_search.search.call_args[1]
        assert kwargs["collection"] == "conventions"
        assert kwargs["group_id"] == _PROJECT, (
            "tier-2 conventions route must search with group_id=project_name, "
            f"got {kwargs['group_id']!r} — RouteTarget.shared must stay False (FIX-4)"
        )
