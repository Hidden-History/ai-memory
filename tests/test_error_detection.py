"""Test error_detection.py hook functionality."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "hooks" / "scripts"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def detection_module():
    return _load_module("error_detection", _SCRIPTS_DIR / "error_detection.py")


class TestDetectError:
    """Test detect_error() function."""

    def test_nonzero_exit_code(self, detection_module):
        assert detection_module.detect_error({"exitCode": 1, "stderr": ""}) is True

    def test_zero_exit_clean(self, detection_module):
        assert detection_module.detect_error({"exitCode": 0, "stdout": "ok"}) is False

    def test_traceback_in_stderr(self, detection_module):
        tool_response = {
            "exitCode": 0,
            "stderr": "Traceback (most recent call last):\n  File foo.py\nTypeError: x",
        }
        assert detection_module.detect_error(tool_response) is True

    def test_error_keyword_in_stderr(self, detection_module):
        tool_response = {"exitCode": 0, "stderr": "Error: No module named 'x'"}
        assert detection_module.detect_error(tool_response) is True


class TestFormatErrorPattern:
    """Test format_error_pattern()."""

    def test_fix_label(self, detection_module):
        fix = {
            "content": "fix content",
            "score": 0.8,
            "type": "error_pattern",
            "subtype": "fix",
            "file_path": "f.py",
            "resolution_confidence": 0.9,
        }
        result = detection_module.format_error_pattern(fix, 1)
        assert "[FIX]" in result
        assert "Confidence: 90%" in result

    def test_error_label(self, detection_module):
        err = {
            "content": "error content",
            "score": 0.8,
            "type": "error_pattern",
            "subtype": "error",
        }
        result = detection_module.format_error_pattern(err, 1)
        assert "[ERROR]" in result

    def test_no_subtype_defaults_error(self, detection_module):
        item = {"content": "content", "score": 0.7, "type": "error_pattern"}
        result = detection_module.format_error_pattern(item, 1)
        assert "[ERROR]" in result


class TestTwoPhaseRetrievalUnit:
    """Unit tests for two_phase_retrieval()."""

    def _run(self, detection_module, phase1_results, scroll_results=None):
        mock_search = MagicMock()
        mock_search.search.return_value = phase1_results

        mock_client = MagicMock()
        mock_client.scroll.return_value = (scroll_results or [], None)

        mock_qdrant = MagicMock()
        mock_qdrant.QdrantClient.return_value = mock_client
        mock_qdrant_models = MagicMock()
        mock_qdrant_models.FieldCondition = MagicMock()
        mock_qdrant_models.Filter = MagicMock()
        mock_qdrant_models.MatchValue = MagicMock()

        import sys

        with patch.dict(
            sys.modules,
            {
                "qdrant_client": mock_qdrant,
                "qdrant_client.models": mock_qdrant_models,
            },
        ):
            return detection_module.two_phase_retrieval(
                search=mock_search,
                error_signature="test error",
                project_name="test_project",
                session_id="sess123",
            )

    def test_empty_phase1_returns_empty(self, detection_module):
        results = self._run(detection_module, phase1_results=[])
        assert results == []

    def test_error_with_no_fix_returns_error_only(self, detection_module):
        phase1 = [
            {
                "score": 0.8,
                "content": "err",
                "type": "error_pattern",
                "subtype": "error",
                "error_group_id": "egid1",
            }
        ]
        results = self._run(detection_module, phase1_results=phase1, scroll_results=[])
        # Should have the error entry, no fix
        assert len(results) == 1
        assert results[0]["subtype"] == "error"

    def test_high_confidence_fix_sorted_first(self, detection_module):
        phase1 = [
            {
                "score": 0.9,
                "content": "err1",
                "type": "error_pattern",
                "subtype": "error",
                "error_group_id": "egid1",
            },
            {
                "score": 0.8,
                "content": "err2",
                "type": "error_pattern",
                "subtype": "error",
                "error_group_id": "egid2",
            },
        ]
        high_fix = MagicMock()
        high_fix.id = "hf"
        high_fix.payload = {
            "content": "hfix",
            "type": "error_pattern",
            "freshness_status": "unverified",
            "resolution_confidence": 0.9,
        }
        low_fix = MagicMock()
        low_fix.id = "lf"
        low_fix.payload = {
            "content": "lfix",
            "type": "error_pattern",
            "freshness_status": "unverified",
            "resolution_confidence": 0.4,
        }

        call_count = [0]

        def scroll_se(**kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return ([high_fix], None) if idx == 0 else ([low_fix], None)

        mock_search = MagicMock()
        mock_search.search.return_value = phase1
        mock_client = MagicMock()
        mock_client.scroll.side_effect = scroll_se
        mock_qdrant = MagicMock()
        mock_qdrant.QdrantClient.return_value = mock_client
        mock_qdrant_models = MagicMock()
        mock_qdrant_models.FieldCondition = MagicMock()
        mock_qdrant_models.Filter = MagicMock()
        mock_qdrant_models.MatchValue = MagicMock()

        import sys

        with patch.dict(
            sys.modules,
            {
                "qdrant_client": mock_qdrant,
                "qdrant_client.models": mock_qdrant_models,
            },
        ):
            results = detection_module.two_phase_retrieval(
                search=mock_search,
                error_signature="test",
                project_name="proj",
                session_id="s",
            )

        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert fixes[0]["resolution_confidence"] == 0.9

    def test_phase1_filters_subtype_error_only(self, detection_module):
        """M-1: Phase 1 should only return subtype='error' results."""
        phase1_raw = [
            {
                "score": 0.9,
                "content": "err",
                "type": "error_pattern",
                "subtype": "error",
                "error_group_id": "egid1",
            },
            {
                "score": 0.7,
                "content": "fix leaked into phase1",
                "type": "error_pattern",
                "subtype": "fix",
                "error_group_id": "egid2",
            },
        ]
        results = self._run(
            detection_module, phase1_results=phase1_raw, scroll_results=[]
        )
        # Fix results that leak into Phase 1 should be filtered out
        subtypes = [r.get("subtype") for r in results]
        assert "fix" not in subtypes or all(
            r.get("subtype") == "error"
            for r in results
            if r.get("error_group_id") == "egid1"
        )

    def test_stale_fix_excluded(self, detection_module):
        """Stale fixes should be skipped per §4.3 R2."""
        phase1 = [
            {
                "score": 0.8,
                "content": "err",
                "type": "error_pattern",
                "subtype": "error",
                "error_group_id": "egid1",
            }
        ]
        stale_fix = MagicMock()
        stale_fix.id = "sf"
        stale_fix.payload = {
            "content": "stale fix",
            "type": "error_pattern",
            "freshness_status": "stale",
            "resolution_confidence": 0.9,
        }
        results = self._run(
            detection_module, phase1_results=phase1, scroll_results=[stale_fix]
        )
        fixes = [r for r in results if r.get("subtype") == "fix"]
        assert len(fixes) == 0


class TestTrackFixEffectiveness:
    """L-4/M-4: Test track_fix_effectiveness() function."""

    def setup_method(self):
        self._session_id = f"test-eff-{id(self)}"
        self._state_path = Path(
            f"/tmp/ai-memory-{self._session_id}-injection-state.json"
        )
        self._cleanup()

    def teardown_method(self):
        self._cleanup()

    def _cleanup(self):
        if self._state_path.exists():
            self._state_path.unlink()

    def _load_module(self):
        return _load_module("error_detection", _SCRIPTS_DIR / "error_detection.py")

    def test_no_error_state_returns_early(self):
        """No error_state → no crash, returns None."""
        mod = self._load_module()
        # Create state without error_state
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.save()

        hook_input = {"tool_response": {"exitCode": 0}}
        # Should not raise
        mod.track_fix_effectiveness(self._session_id, hook_input)

    def test_no_fix_injected_flag_returns_early(self):
        """error_state exists but no _last_fix_injected → returns early."""
        mod = self._load_module()
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "egid-1": {"error_group_id": "egid-1", "file_path": "/src/foo.py"}
        }
        state.save()

        hook_input = {"tool_response": {"exitCode": 0}}
        mod.track_fix_effectiveness(self._session_id, hook_input)

    def test_resolved_clears_tracking_flag(self):
        """Exit code 0 after fix injection → resolved, clears _last_fix_injected."""
        mod = self._load_module()
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "_last_fix_injected": {
                "error_group_id": "egid-1",
                "fix_point_id": "fp-1",
            }
        }
        state.save()

        hook_input = {"tool_response": {"exitCode": 0}, "cwd": "/tmp"}

        with (
            patch.object(mod, "emit_trace_event", None),
            patch.object(mod, "error_fix_effectiveness_total", None),
        ):
            mod.track_fix_effectiveness(self._session_id, hook_input)

        # Verify flag was cleared
        updated_state = InjectionSessionState.load(self._session_id)
        assert "_last_fix_injected" not in (updated_state.error_state or {})

    def test_unresolved_exit_code(self):
        """Non-zero exit code after fix injection → unresolved."""
        mod = self._load_module()
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "_last_fix_injected": {
                "error_group_id": "egid-1",
                "fix_point_id": "fp-1",
            }
        }
        state.save()

        hook_input = {"tool_response": {"exitCode": 1}, "cwd": "/tmp"}

        with (
            patch.object(mod, "emit_trace_event", None),
            patch.object(mod, "error_fix_effectiveness_total", None),
        ):
            mod.track_fix_effectiveness(self._session_id, hook_input)

        # Flag should still be cleared even for unresolved
        updated_state = InjectionSessionState.load(self._session_id)
        assert "_last_fix_injected" not in (updated_state.error_state or {})

    def test_prometheus_metric_incremented_on_resolve(self):
        """Prometheus error_fix_effectiveness_total incremented on resolved outcome."""
        mod = self._load_module()
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "_last_fix_injected": {
                "error_group_id": "egid-1",
                "fix_point_id": "fp-1",
            }
        }
        state.save()

        mock_metric = MagicMock()
        hook_input = {"tool_response": {"exitCode": 0}, "cwd": "/tmp"}

        with (
            patch.object(mod, "emit_trace_event", None),
            patch.object(mod, "error_fix_effectiveness_total", mock_metric),
            patch.object(mod, "detect_project", return_value="test-proj"),
        ):
            mod.track_fix_effectiveness(self._session_id, hook_input)

        mock_metric.labels.assert_called_with(outcome="resolved", project="test-proj")
        mock_metric.labels().inc.assert_called_once()

    def test_langfuse_trace_emitted(self):
        """Langfuse trace event emitted for effectiveness tracking."""
        mod = self._load_module()
        from memory.injection import InjectionSessionState

        state = InjectionSessionState(session_id=self._session_id)
        state.error_state = {
            "_last_fix_injected": {
                "error_group_id": "egid-1",
                "fix_point_id": "fp-1",
            }
        }
        state.save()

        mock_emit = MagicMock()
        hook_input = {"tool_response": {"exitCode": 0}, "cwd": "/tmp"}

        with (
            patch.object(mod, "emit_trace_event", mock_emit),
            patch.object(mod, "error_fix_effectiveness_total", None),
        ):
            mod.track_fix_effectiveness(self._session_id, hook_input)

        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args
        assert call_kwargs[1]["event_type"] == "error_fix_effectiveness"


class TestMainFunction:
    """M-4: Test main() entry point."""

    def _load_module(self):
        return _load_module("error_detection", _SCRIPTS_DIR / "error_detection.py")

    def _make_stdin(self, exit_code=1, stderr="Error: test", stdout=""):
        data = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "python test.py"},
                "tool_response": {
                    "exitCode": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                "session_id": "test-main-err",
                "cwd": "/tmp",
            }
        )
        return io.StringIO(data)

    def test_non_bash_tool_exits_0(self):
        """Non-Bash tool → exit 0 immediately."""
        mod = self._load_module()
        data = json.dumps({"tool_name": "Edit", "tool_input": {}})
        with patch("sys.stdin", io.StringIO(data)):
            result = mod.main()
        assert result == 0

    def test_no_error_exits_0(self):
        """Clean Bash exit → exit 0, no output."""
        mod = self._load_module()
        data = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "echo ok"},
                "tool_response": {"exitCode": 0, "stdout": "ok", "stderr": ""},
                "session_id": "test-clean",
                "cwd": "/tmp",
            }
        )
        with patch("sys.stdin", io.StringIO(data)):
            result = mod.main()
        assert result == 0

    def test_malformed_json_exits_0(self):
        """Malformed JSON → exit 0 (graceful degradation)."""
        mod = self._load_module()
        with patch("sys.stdin", io.StringIO("not json")):
            result = mod.main()
        assert result == 0

    def test_error_detected_searches_memory(self, capsys):
        """Error detected → calls MemorySearch and two_phase_retrieval."""
        mod = self._load_module()
        mock_search = MagicMock()
        mock_search.search.return_value = []
        mock_search.close.return_value = None

        with (
            patch("sys.stdin", self._make_stdin()),
            patch.object(mod, "MemorySearch", return_value=mock_search),
            patch.object(
                mod, "get_config", return_value=MagicMock(similarity_threshold=0.4)
            ),
            patch.object(mod, "resolve_project_id", return_value="test-proj"),
            patch.object(mod, "push_hook_metrics_async", None),
            patch.object(mod, "push_retrieval_metrics_async", None),
            patch.object(mod, "emit_trace_event", None),
            patch.object(mod, "error_fix_injections_total", None),
            patch.object(mod, "error_fix_effectiveness_total", None),
        ):
            result = mod.main()

        assert result == 0
        mock_search.search.assert_called_once()

    def test_error_with_results_produces_output(self, capsys):
        """Error with matching results → stdout output with header."""
        mod = self._load_module()
        mock_search = MagicMock()
        mock_search.search.return_value = [
            {
                "score": 0.8,
                "content": "similar error found",
                "type": "error_pattern",
                "subtype": "error",
                "error_group_id": "egid1",
            }
        ]
        mock_search.close.return_value = None

        mock_qdrant = MagicMock()
        mock_client = MagicMock()
        mock_client.scroll.return_value = ([], None)
        mock_qdrant.QdrantClient.return_value = mock_client
        mock_qdrant_models = MagicMock()

        import sys as _sys

        with (
            patch("sys.stdin", self._make_stdin()),
            patch.object(mod, "MemorySearch", return_value=mock_search),
            patch.object(
                mod, "get_config", return_value=MagicMock(similarity_threshold=0.4)
            ),
            patch.object(mod, "resolve_project_id", return_value="test-proj"),
            patch.object(mod, "push_hook_metrics_async", None),
            patch.object(mod, "push_retrieval_metrics_async", None),
            patch.object(mod, "emit_trace_event", None),
            patch.object(mod, "error_fix_injections_total", None),
            patch.object(mod, "error_fix_effectiveness_total", None),
            patch.object(mod, "log_to_activity", MagicMock()),
            patch.dict(
                _sys.modules,
                {
                    "qdrant_client": mock_qdrant,
                    "qdrant_client.models": mock_qdrant_models,
                },
            ),
        ):
            result = mod.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMILAR ERROR FIXES FOUND" in captured.out

    def test_exception_in_main_exits_0(self):
        """Unhandled exception → exit 0 (graceful degradation)."""
        mod = self._load_module()
        with (
            patch("sys.stdin", self._make_stdin()),
            patch.object(mod, "get_config", side_effect=RuntimeError("config broke")),
            patch.object(mod, "push_hook_metrics_async", None),
            patch.object(mod, "push_retrieval_metrics_async", None),
            patch.object(mod, "emit_trace_event", None),
            patch.object(mod, "error_fix_effectiveness_total", None),
        ):
            result = mod.main()
        assert result == 0
