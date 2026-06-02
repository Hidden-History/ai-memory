"""Tests for aim-parzival-constraints/scripts/constraints.py.

Script loaded via importlib.util.spec_from_file_location, fresh per test.
memory.* modules mocked via monkeypatch.setitem(sys.modules) — no real package needed.
AI_MEMORY_PROJECT_ID unset; plugin-free.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import ANY, MagicMock

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "_ai-memory/pov/skills/aim-parzival-constraints/scripts/constraints.py"
)


def _exec_constraints(monkeypatch, argv, load_return_value):
    """Exec constraints.py with controlled argv and mocked memory.* modules.

    Returns (mock_load, mock_push, mock_emit).
    """
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

    mock_load = MagicMock(return_value=load_return_value)
    mock_push = MagicMock()
    mock_emit = MagicMock()

    mem_injection = MagicMock()
    mem_injection.load_parzival_constraints = mock_load

    mem_metrics = MagicMock()
    mem_metrics.push_skill_metrics_async = mock_push

    mem_trace = MagicMock()
    mem_trace.emit_trace_event = mock_emit

    monkeypatch.setitem(sys.modules, "memory", MagicMock())
    monkeypatch.setitem(sys.modules, "memory.injection", mem_injection)
    monkeypatch.setitem(sys.modules, "memory.metrics_push", mem_metrics)
    monkeypatch.setitem(sys.modules, "memory.trace_buffer", mem_trace)

    spec = importlib.util.spec_from_file_location("constraints", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return mock_load, mock_push, mock_emit


class TestKnownPhase:
    """Case 1: --phase <value> → load called with that phase, stdout shows constraints."""

    def test_known_phase_passed_to_load(self, monkeypatch):
        mock_load, _, _ = _exec_constraints(
            monkeypatch,
            argv=["constraints.py", "--phase", "init"],
            load_return_value="## Constraint A\n## Constraint B",
        )
        mock_load.assert_called_once_with(ANY, phase="init")

    def test_known_phase_output_printed(self, monkeypatch, capsys):
        _exec_constraints(
            monkeypatch,
            argv=["constraints.py", "--phase", "init"],
            load_return_value="## Constraint A\n## Constraint B",
        )
        out = capsys.readouterr().out
        assert "## Constraint A" in out
        assert "## Constraint B" in out


class TestNoPhase:
    """Case 2: no --phase → phase=None, graceful handling of empty result."""

    def test_no_phase_passes_none_to_load(self, monkeypatch):
        mock_load, _, _ = _exec_constraints(
            monkeypatch,
            argv=["constraints.py"],
            load_return_value="",
        )
        mock_load.assert_called_once_with(ANY, phase=None)

    def test_empty_constraints_prints_not_found(self, monkeypatch, capsys):
        _exec_constraints(
            monkeypatch,
            argv=["constraints.py"],
            load_return_value="",
        )
        out = capsys.readouterr().out
        assert "No constraint files found" in out

    def test_empty_constraints_metric_label_empty(self, monkeypatch):
        _, mock_push, mock_emit = _exec_constraints(
            monkeypatch,
            argv=["constraints.py"],
            load_return_value="",
        )
        mock_push.assert_called_once_with("aim-parzival-constraints", "empty", ANY)
        mock_emit.assert_called_once()


class TestTelemetryShim:
    """Case 3: telemetry shim integration — callables invoked with exact args."""

    def test_push_metrics_success_label(self, monkeypatch):
        _, mock_push, _ = _exec_constraints(
            monkeypatch,
            argv=["constraints.py"],
            load_return_value="## Some constraint",
        )
        mock_push.assert_called_once_with("aim-parzival-constraints", "success", ANY)

    def test_emit_trace_event_kwargs(self, monkeypatch, capsys):
        _, _, mock_emit = _exec_constraints(
            monkeypatch,
            argv=["constraints.py"],
            load_return_value="## Some constraint",
        )
        mock_emit.assert_called_once_with(
            event_type="skill_execution",
            data={
                "input": "Skill: aim-parzival-constraints"[:10000],
                "output": "Result: completed"[:10000],
                "metadata": {"skill_name": "aim-parzival-constraints"},
            },
            session_id=ANY,
            tags=["skill"],
        )


class TestImportError:
    """Safety-critical early-exit: ImportError on memory.injection → exit 0 + Unavailable message."""

    def test_import_error_exits_zero_with_unavailable_message(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(sys, "argv", ["constraints.py"])
        monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)

        # Mark memory.injection absent via the None sentinel — Python raises ImportError
        # immediately without any filesystem lookup, regardless of sys.path.
        monkeypatch.setitem(sys.modules, "memory.injection", None)

        spec = importlib.util.spec_from_file_location(
            "constraints_importerror", SCRIPT_PATH
        )
        module = importlib.util.module_from_spec(spec)

        with pytest.raises(SystemExit) as exc_info:
            spec.loader.exec_module(module)

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "**Unavailable**" in out
