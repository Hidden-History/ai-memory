"""Import-outcome parity tests for scripts/memory/lib/optional_telemetry.py.

Verifies all 4 rows of the BASELINE behavior matrix (item-3-optional_telemetry):
  - both deps present  → both names truthy
  - only metrics_push  → push truthy, trace None
  - only trace_buffer  → push None, trace truthy
  - both absent        → both names None

Uses importlib spec-load + sys.modules injection so the tests are hermetic:
no real ai-memory package install required.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_HELPER = _REPO / "scripts" / "memory" / "lib" / "optional_telemetry.py"

# Truthy sentinel that stands in for a real imported callable.
_SENTINEL = object()


def _make_metrics_mod() -> types.ModuleType:
    m = types.ModuleType("memory.metrics_push")
    m.push_skill_metrics_async = _SENTINEL
    return m


def _make_trace_mod() -> types.ModuleType:
    m = types.ModuleType("memory.trace_buffer")
    m.emit_trace_event = _SENTINEL
    return m


def _load_helper(
    monkeypatch, *, metrics_present: bool, trace_present: bool
) -> types.ModuleType:
    """Load optional_telemetry.py fresh with fully controlled sys.modules state.

    For "present" deps: inject a fake module that has the expected attribute.
    For "absent" deps: inject an empty module stub — `from X import Y` on a
    module that has no Y raises ImportError (cannot import name), which the
    helper's try/except catches and assigns None.
    """
    # Clear any cached copy of the helper module itself.
    monkeypatch.delitem(sys.modules, "optional_telemetry", raising=False)

    # Ensure the `memory` parent package stub is present so Python's import
    # machinery can resolve submodule path lookups without hitting the filesystem.
    if "memory" not in sys.modules:
        monkeypatch.setitem(sys.modules, "memory", types.ModuleType("memory"))

    # memory.metrics_push
    if metrics_present:
        monkeypatch.setitem(sys.modules, "memory.metrics_push", _make_metrics_mod())
    else:
        # Empty stub → `from memory.metrics_push import push_skill_metrics_async`
        # raises ImportError (no such attribute), caught by the helper's except.
        monkeypatch.setitem(
            sys.modules,
            "memory.metrics_push",
            types.ModuleType("memory.metrics_push"),
        )

    # memory.trace_buffer
    if trace_present:
        monkeypatch.setitem(sys.modules, "memory.trace_buffer", _make_trace_mod())
    else:
        monkeypatch.setitem(
            sys.modules,
            "memory.trace_buffer",
            types.ModuleType("memory.trace_buffer"),
        )

    spec = importlib.util.spec_from_file_location("optional_telemetry", _HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOptionalTelemetryParity:
    """BASELINE behavior matrix — all 4 rows (item-3-optional_telemetry)."""

    def test_both_present(self, monkeypatch):
        """Both deps present → both names are truthy."""
        mod = _load_helper(monkeypatch, metrics_present=True, trace_present=True)
        assert mod.push_skill_metrics_async is not None
        assert mod.emit_trace_event is not None

    def test_only_metrics_present(self, monkeypatch):
        """Only metrics_push present → push truthy, trace None."""
        mod = _load_helper(monkeypatch, metrics_present=True, trace_present=False)
        assert mod.push_skill_metrics_async is not None
        assert mod.emit_trace_event is None

    def test_only_trace_present(self, monkeypatch):
        """Only trace_buffer present → push None, trace truthy."""
        mod = _load_helper(monkeypatch, metrics_present=False, trace_present=True)
        assert mod.push_skill_metrics_async is None
        assert mod.emit_trace_event is not None

    def test_both_absent(self, monkeypatch):
        """Both deps absent → both names are None."""
        mod = _load_helper(monkeypatch, metrics_present=False, trace_present=False)
        assert mod.push_skill_metrics_async is None
        assert mod.emit_trace_event is None
