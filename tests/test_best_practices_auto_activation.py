"""Unit tests for best_practices_retrieval.py auto-activation (WP-5).

Tests cover:
- Error-triggered auto-activation (§4.3 R-BP, §6.2 Rule 1)
- Struggling pattern detection (3+ edits to same file)
- Confidence gate (best_score > 0.6 threshold)
- No false triggers (normal edits don't fire)
- Edit count tracking across hook calls
- File path matching logic
"""

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup path to import the hook script
HOOK_SCRIPT_DIR = Path(__file__).parent.parent / ".claude" / "hooks" / "scripts"
SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(HOOK_SCRIPT_DIR))
sys.path.insert(0, str(SRC_DIR))

# Import the functions under test (after sys.path setup above)
from best_practices_retrieval import (
    AUTO_ACTIVATION_CONFIDENCE_THRESHOLD,
    STRUGGLING_EDIT_THRESHOLD,
    _check_auto_activation,
    _file_paths_match,
    _get_edit_counts_path,
    _increment_edit_count,
    main,
)


class TestFilePathsMatch:
    """Test _file_paths_match() for various path comparison scenarios."""

    def test_exact_match(self):
        assert _file_paths_match("/src/foo.py", "/src/foo.py") is True

    def test_basename_match(self):
        assert _file_paths_match("/a/b/foo.py", "/c/d/foo.py") is True

    def test_basename_match_relative_vs_absolute(self):
        assert _file_paths_match("/project/src/foo.py", "src/foo.py") is True

    def test_basename_match_absolute_vs_relative(self):
        assert _file_paths_match("src/foo.py", "/project/src/foo.py") is True

    def test_no_match(self):
        assert _file_paths_match("/src/foo.py", "/src/bar.py") is False

    def test_no_false_positive_shared_suffix(self):
        """'/project/foobar.py' must NOT match 'bar.py' (segment-aware, not string endswith)."""
        assert _file_paths_match("/project/foobar.py", "bar.py") is False

    def test_empty_paths(self):
        assert _file_paths_match("", "") is False  # Empty paths never match
        assert _file_paths_match("foo.py", "") is False
        assert _file_paths_match("", "foo.py") is False

    # L-3: Tests for full path suffix comparison before basename fallback
    def test_suffix_match_relative_trailing(self):
        """Shorter relative path matches as trailing segment of absolute path."""
        assert (
            _file_paths_match("/project/src/utils/foo.py", "src/utils/foo.py") is True
        )

    def test_suffix_match_longer_relative(self):
        """Multi-segment relative path matches trailing segments."""
        assert _file_paths_match("utils/foo.py", "/project/src/utils/foo.py") is True

    def test_basename_collision_different_dirs(self):
        """Two files with same basename in different dirs — basename match (known limitation)."""
        # This tests the current behavior: basename match still returns True
        # because basename fallback is kept for robustness. The L-3 fix adds
        # suffix matching as a HIGHER priority check, not replaces basename.
        assert _file_paths_match("/a/utils.py", "/b/utils.py") is True


class TestEditCountTracking:
    """Test edit count tracking per file per session."""

    def setup_method(self):
        """Use a unique session ID for each test to avoid interference."""
        self._session_id = f"test-edit-{id(self)}"
        self._cleanup()

    def teardown_method(self):
        self._cleanup()

    def _cleanup(self):
        path = _get_edit_counts_path(self._session_id)
        if path.exists():
            path.unlink()

    def test_first_edit_returns_1(self):
        count = _increment_edit_count("/src/foo.py", self._session_id)
        assert count == 1

    def test_increments_on_same_file(self):
        _increment_edit_count("/src/foo.py", self._session_id)
        _increment_edit_count("/src/foo.py", self._session_id)
        count = _increment_edit_count("/src/foo.py", self._session_id)
        assert count == 3

    def test_tracks_files_independently(self):
        _increment_edit_count("/src/foo.py", self._session_id)
        _increment_edit_count("/src/foo.py", self._session_id)
        count_bar = _increment_edit_count("/src/bar.py", self._session_id)
        assert count_bar == 1  # Different file, fresh count

    def test_unknown_session_returns_1(self):
        count = _increment_edit_count("/src/foo.py", "unknown")
        assert count == 1

    def test_persists_across_calls(self):
        """Verify counts survive across separate function calls (file-backed)."""
        _increment_edit_count("/src/foo.py", self._session_id)
        _increment_edit_count("/src/foo.py", self._session_id)
        # Verify file exists
        path = _get_edit_counts_path(self._session_id)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["/src/foo.py"] == 2


class TestCheckAutoActivation:
    """Test _check_auto_activation() trigger detection."""

    def setup_method(self):
        self._session_id = f"test-auto-{id(self)}"
        self._cleanup()

    def teardown_method(self):
        self._cleanup()

    def _cleanup(self):
        # Clean up edit counts
        path = _get_edit_counts_path(self._session_id)
        if path.exists():
            path.unlink()
        # Clean up injection state
        state_path = Path(f"/tmp/ai-memory-{self._session_id}-injection-state.json")
        if state_path.exists():
            state_path.unlink()

    def _set_error_state(self, error_file: str, error_group_id: str = "err-123"):
        """Write injection session state with error_state in WP-6 nested format.

        C-1 FIX: error_pattern_capture.py stores nested dicts keyed by error_group_id:
        {egid: {"error_group_id": egid, "file_path": path, ...}}
        """
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            error_group_id: {
                "error_group_id": error_group_id,
                "file_path": error_file,
                "exception_type": "TestError",
            }
        }
        state.save()

    def test_error_triggered_exact_match(self):
        """Auto-activates when error_state file matches edit file exactly."""
        self._set_error_state("/src/foo.py")
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result == "error_triggered"

    def test_error_triggered_basename_match(self):
        """Auto-activates when error_state file matches by basename."""
        self._set_error_state("foo.py")
        result = _check_auto_activation("/project/src/foo.py", self._session_id, 1)
        assert result == "error_triggered"

    def test_error_triggered_relative_path_match(self):
        """Auto-activates when error_state relative path matches edit file's trailing segments."""
        self._set_error_state("src/foo.py")
        result = _check_auto_activation("/project/src/foo.py", self._session_id, 1)
        assert result == "error_triggered"

    def test_no_error_state_no_trigger(self):
        """No trigger when error_state is None (no error detected)."""
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None

    def test_error_on_different_file_no_trigger(self):
        """No trigger when error_state file doesn't match edit file."""
        self._set_error_state("/src/bar.py")
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None

    def test_struggling_pattern_at_threshold(self):
        """Auto-activates when edit_count reaches threshold (3)."""
        result = _check_auto_activation(
            "/src/foo.py", self._session_id, STRUGGLING_EDIT_THRESHOLD
        )
        assert result == "struggling_pattern"

    def test_struggling_pattern_above_threshold(self):
        """Auto-activates when edit_count exceeds threshold."""
        result = _check_auto_activation("/src/foo.py", self._session_id, 5)
        assert result == "struggling_pattern"

    def test_no_struggling_below_threshold(self):
        """No trigger when edit_count is below threshold."""
        result = _check_auto_activation("/src/foo.py", self._session_id, 2)
        assert result is None

    def test_error_takes_priority_over_struggling(self):
        """Error trigger fires first even when struggling threshold is met."""
        self._set_error_state("/src/foo.py")
        result = _check_auto_activation(
            "/src/foo.py", self._session_id, STRUGGLING_EDIT_THRESHOLD
        )
        assert result == "error_triggered"

    def test_unknown_session_no_error_trigger(self):
        """Unknown session ID doesn't trigger error-based activation."""
        result = _check_auto_activation("/src/foo.py", "unknown", 1)
        assert result is None

    def test_empty_error_state_no_trigger(self):
        """Empty dict error_state doesn't trigger."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {}
        state.save()
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None

    def test_error_state_missing_file_path_key_no_trigger(self):
        """error_state entry without 'file_path' key doesn't trigger."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "abc": {
                "error_group_id": "abc",
                # No 'file_path' key
            }
        }
        state.save()
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None

    def test_multiple_error_entries_matches_second(self):
        """C-1: Multiple nested error entries — matches the second one."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "egid-1": {
                "error_group_id": "egid-1",
                "file_path": "/src/bar.py",
                "exception_type": "ImportError",
            },
            "egid-2": {
                "error_group_id": "egid-2",
                "file_path": "/src/foo.py",
                "exception_type": "TypeError",
            },
        }
        state.save()
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result == "error_triggered"

    def test_internal_key_skipped(self):
        """C-1: Internal keys like _last_fix_injected are skipped."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "_last_fix_injected": {
                "error_group_id": "egid-1",
                "fix_point_id": "fp-1",
            },
        }
        state.save()
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None


class TestConfidenceGate:
    """Test confidence gating constants and threshold behavior."""

    def test_threshold_value(self):
        """Confidence threshold is 0.6 per §4.3 R-BP."""
        assert AUTO_ACTIVATION_CONFIDENCE_THRESHOLD == 0.6

    def test_struggling_threshold_value(self):
        """Struggling pattern threshold is 3 per §4.3 R-BP."""
        assert STRUGGLING_EDIT_THRESHOLD == 3


class TestNoFalseTriggers:
    """Verify normal coding patterns don't trigger auto-activation."""

    def setup_method(self):
        self._session_id = f"test-nofalse-{id(self)}"
        self._cleanup()

    def teardown_method(self):
        self._cleanup()

    def _cleanup(self):
        path = _get_edit_counts_path(self._session_id)
        if path.exists():
            path.unlink()
        state_path = Path(f"/tmp/ai-memory-{self._session_id}-injection-state.json")
        if state_path.exists():
            state_path.unlink()

    def test_single_edit_no_trigger(self):
        """Single edit to a file should not trigger."""
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None

    def test_two_edits_no_trigger(self):
        """Two edits to same file should not trigger."""
        result = _check_auto_activation("/src/foo.py", self._session_id, 2)
        assert result is None

    def test_no_error_no_struggling_no_trigger(self):
        """Clean session with few edits produces no trigger."""
        result = _check_auto_activation("/src/foo.py", self._session_id, 1)
        assert result is None

    def test_error_on_unrelated_file_no_trigger(self):
        """Error on a different file doesn't trigger for current edit."""
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "db-err": {
                "error_group_id": "db-err",
                "file_path": "/src/database.py",
                "exception_type": "DBError",
            }
        }
        state.save()
        result = _check_auto_activation("/src/api.py", self._session_id, 1)
        assert result is None


class TestEditCountsPath:
    """Test _get_edit_counts_path sanitization."""

    def test_sanitizes_special_chars(self):
        path = _get_edit_counts_path("test/../../../etc/passwd")
        # Path traversal chars (/ and .) are stripped by the sanitizer
        assert ".." not in path.name
        assert "/" not in path.stem.replace("ai-memory-", "")

    def test_handles_empty_session(self):
        path = _get_edit_counts_path("")
        assert "unknown" in str(path)

    def test_truncates_long_session_id(self):
        long_id = "a" * 200
        path = _get_edit_counts_path(long_id)
        assert len(long_id) > 64  # Verify our test input is actually long
        # Extract safe_id: strip "ai-memory-" prefix and "-edit-counts.json" suffix
        safe_id = path.name.removeprefix("ai-memory-").removesuffix("-edit-counts.json")
        assert len(safe_id) == 64


class TestMainIntegration:
    """Integration tests for main() using mocked dependencies."""

    def teardown_method(self):
        """Remove edit count file left by tests using session_id 'test-main-123'."""
        path = Path("/tmp/ai-memory-test-main-123-edit-counts.json")
        if path.exists():
            path.unlink()

    def _make_stdin(
        self, file_path="/src/foo.py", tool_name="Edit", session_id="test-main-123"
    ):
        """Return a StringIO representing hook JSON input."""
        data = json.dumps(
            {
                "tool_name": tool_name,
                "tool_input": {"file_path": file_path},
                "session_id": session_id,
                "cwd": "/project",
            }
        )
        return io.StringIO(data)

    def _mock_search_instance(self, scores):
        """Return a mock MemorySearch instance with results at given scores."""
        results = [
            {
                "score": s,
                "content": f"practice content {i}",
                "component": "general",
                "tags": [],
            }
            for i, s in enumerate(scores)
        ]
        mock = MagicMock()
        mock.search.return_value = results
        mock.close.return_value = None
        return mock

    def test_auto_activation_below_confidence_gate_no_output(self, capsys):
        """Auto-activation fires but score 0.3 ≤ 0.6 threshold → silent exit, no stdout."""
        mock_search = self._mock_search_instance([0.3])
        with (
            patch("sys.stdin", self._make_stdin()),
            patch.dict(
                os.environ,
                {
                    "AI_MEMORY_AGENT_TYPE": "",
                    "AI_MEMORY_BEST_PRACTICES_EXPLICIT": "false",
                },
                clear=False,
            ),
            patch("memory.health.check_qdrant_health", return_value=True),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.project.detect_project", return_value="test-project"),
            patch("memory.search.MemorySearch", return_value=mock_search),
            patch("best_practices_retrieval.push_retrieval_metrics_async", None),
            patch("best_practices_retrieval.push_hook_metrics_async", None),
            patch("best_practices_retrieval.emit_trace_event", None),
            patch(
                "best_practices_retrieval._check_auto_activation",
                return_value="struggling_pattern",
            ),
        ):
            result = main()
        captured = capsys.readouterr()
        assert result == 0
        assert captured.out == ""

    def test_auto_activation_above_confidence_gate_produces_output(self, capsys):
        """Auto-activation fires and score 0.8 > 0.6 threshold → stdout output produced."""
        mock_search = self._mock_search_instance([0.8])
        with (
            patch("sys.stdin", self._make_stdin()),
            patch.dict(
                os.environ,
                {
                    "AI_MEMORY_AGENT_TYPE": "",
                    "AI_MEMORY_BEST_PRACTICES_EXPLICIT": "false",
                },
                clear=False,
            ),
            patch("memory.health.check_qdrant_health", return_value=True),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.project.detect_project", return_value="test-project"),
            patch("memory.search.MemorySearch", return_value=mock_search),
            patch("best_practices_retrieval.push_retrieval_metrics_async", None),
            patch("best_practices_retrieval.push_hook_metrics_async", None),
            patch("best_practices_retrieval.emit_trace_event", None),
            patch(
                "best_practices_retrieval._check_auto_activation",
                return_value="struggling_pattern",
            ),
        ):
            result = main()
        captured = capsys.readouterr()
        assert result == 0
        assert "BEST PRACTICES" in captured.out

    def test_explicit_mode_bypasses_confidence_gate(self, capsys):
        """Explicit mode outputs regardless of score (confidence gate skipped entirely)."""
        mock_search = self._mock_search_instance(
            [0.3]
        )  # Low score — filtered in auto mode
        with (
            patch("sys.stdin", self._make_stdin()),
            patch.dict(
                os.environ, {"AI_MEMORY_BEST_PRACTICES_EXPLICIT": "true"}, clear=False
            ),
            patch("memory.health.check_qdrant_health", return_value=True),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.project.detect_project", return_value="test-project"),
            patch("memory.search.MemorySearch", return_value=mock_search),
            patch("best_practices_retrieval.push_retrieval_metrics_async", None),
            patch("best_practices_retrieval.push_hook_metrics_async", None),
            patch("best_practices_retrieval.emit_trace_event", None),
        ):
            result = main()
        captured = capsys.readouterr()
        assert result == 0
        assert "BEST PRACTICES" in captured.out

    def test_auto_activation_at_confidence_boundary_no_output(self, capsys):
        """Auto-activation fires but score=0.6 exactly is rejected by exclusive <= 0.6 threshold → no output."""
        mock_search = self._mock_search_instance([0.6])
        with (
            patch("sys.stdin", self._make_stdin()),
            patch.dict(
                os.environ,
                {
                    "AI_MEMORY_AGENT_TYPE": "",
                    "AI_MEMORY_BEST_PRACTICES_EXPLICIT": "false",
                },
                clear=False,
            ),
            patch("memory.health.check_qdrant_health", return_value=True),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.project.detect_project", return_value="test-project"),
            patch("memory.search.MemorySearch", return_value=mock_search),
            patch("best_practices_retrieval.push_retrieval_metrics_async", None),
            patch("best_practices_retrieval.push_hook_metrics_async", None),
            patch("best_practices_retrieval.emit_trace_event", None),
            patch(
                "best_practices_retrieval._check_auto_activation",
                return_value="struggling_pattern",
            ),
        ):
            result = main()
        captured = capsys.readouterr()
        assert result == 0
        assert captured.out == ""

    def test_qdrant_down_graceful_degradation(self, capsys):
        """Qdrant unavailable → exit 0, no crash, no stdout output."""
        with (
            patch("sys.stdin", self._make_stdin()),
            patch.dict(
                os.environ, {"AI_MEMORY_BEST_PRACTICES_EXPLICIT": "true"}, clear=False
            ),
            patch("memory.health.check_qdrant_health", return_value=False),
            patch("memory.qdrant_client.get_qdrant_client", return_value=MagicMock()),
            patch(
                "memory.config.get_config",
                return_value=MagicMock(similarity_threshold=0.4),
            ),
            patch("memory.project.detect_project", return_value="test-project"),
            patch("best_practices_retrieval.push_retrieval_metrics_async", None),
            patch("best_practices_retrieval.push_hook_metrics_async", None),
            patch("best_practices_retrieval.emit_trace_event", None),
        ):
            result = main()
        captured = capsys.readouterr()
        assert result == 0
        assert captured.out == ""
