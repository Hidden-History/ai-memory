"""Regression tests: parzival-save-* scripts pass explicit group_id (PLAN-028 P1B / W-09).

PLAN-028 P1B / W-09 (DEC-PM302-D1): ``store_agent_memory`` requires ``group_id``
as a required keyword-only argument. Before this fix each skill called
``store_agent_memory`` without ``group_id``, raising ``TypeError`` on every
invocation and silently breaking the handoff→L1, insights→L3, and
decisions→L2 emit paths via the try/except wrapper.

Each test: loads the externalized backing script via importlib, runs it with
mocked ``memory.*`` modules (no live Qdrant writes), and asserts
``store_agent_memory`` was invoked with a non-empty ``group_id`` kwarg.
The assertion fails if ``group_id`` is absent — demonstrating the TypeError
that would occur against the real W-09 signature.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts" / "memory"

_DECISION_SCRIPT = _SCRIPTS / "parzival_save_decision.py"
_HANDOFF_SCRIPT = _SCRIPTS / "parzival_save_handoff.py"
_INSIGHT_SCRIPT = _SCRIPTS / "parzival_save_insight.py"


def _load_module(script_path: Path, module_name: str):
    """Load a backing script fresh via importlib, evicting any prior cached version."""
    for key in list(sys.modules.keys()):
        if module_name in key or "parzival_save_common" in key:
            del sys.modules[key]
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_memory_modules(
    monkeypatch, mock_storage_instance: MagicMock, group_id: str
) -> None:
    """Inject fake ``memory.*`` modules so scripts never touch live services."""
    fake_config = MagicMock()
    fake_config.parzival_enabled = True

    memory_pkg = types.ModuleType("memory")
    cfg_mod = types.ModuleType("memory.config")
    cfg_mod.get_config = MagicMock(return_value=fake_config)
    storage_mod = types.ModuleType("memory.storage")
    storage_mod.MemoryStorage = MagicMock(return_value=mock_storage_instance)
    project_mod = types.ModuleType("memory.project")
    project_mod.detect_project = lambda _cwd: group_id
    project_mod.resolve_project_id = lambda _cwd=None, *, explicit=None: group_id
    metrics_mod = types.ModuleType("memory.metrics_push")
    metrics_mod.push_skill_metrics_async = MagicMock()
    trace_mod = types.ModuleType("memory.trace_buffer")
    trace_mod.emit_trace_event = MagicMock()

    for name, mod in [
        ("memory", memory_pkg),
        ("memory.config", cfg_mod),
        ("memory.storage", storage_mod),
        ("memory.project", project_mod),
        ("memory.metrics_push", metrics_mod),
        ("memory.trace_buffer", trace_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Clear ambient AI_MEMORY_PROJECT_ID so tests control scope explicitly."""
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)


class TestDecisionSkillGroupId:
    """parzival_save_decision.py passes group_id to store_agent_memory."""

    def test_store_called_with_group_id(self, monkeypatch, tmp_path):
        """store_agent_memory receives group_id from env; fails assertion without fix."""
        group_id = "test-decision-project"
        mock_store = MagicMock()
        mock_store.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "abc001xyz",
        }

        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", group_id)
        _patch_memory_modules(monkeypatch, mock_store, group_id)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "parzival_save_decision.py",
                "--dec-id",
                "PM999-D1",
                "--content",
                "Decision: test fix",
            ],
        )
        monkeypatch.chdir(tmp_path)

        mod = _load_module(_DECISION_SCRIPT, "parzival_save_decision_under_test")
        mod.main()

        mock_store.store_agent_memory.assert_called_once()
        kwargs = mock_store.store_agent_memory.call_args.kwargs
        assert "group_id" in kwargs, (
            "group_id missing from store_agent_memory call — "
            "would raise TypeError against W-09 real signature"
        )
        assert kwargs["group_id"] == group_id


class TestHandoffSkillGroupId:
    """parzival_save_handoff.py passes group_id to store_agent_memory."""

    def test_store_called_with_group_id(self, monkeypatch, tmp_path):
        """store_agent_memory receives group_id from env; fails assertion without fix."""
        group_id = "test-handoff-project"
        mock_store = MagicMock()
        mock_store.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "abc002xyz",
        }

        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", group_id)
        _patch_memory_modules(monkeypatch, mock_store, group_id)
        monkeypatch.setattr(
            sys, "argv", ["parzival_save_handoff.py", "PM999 handoff content"]
        )
        monkeypatch.chdir(tmp_path)

        mod = _load_module(_HANDOFF_SCRIPT, "parzival_save_handoff_under_test")
        mod.main()

        mock_store.store_agent_memory.assert_called_once()
        kwargs = mock_store.store_agent_memory.call_args.kwargs
        assert "group_id" in kwargs, (
            "group_id missing from store_agent_memory call — "
            "would raise TypeError against W-09 real signature"
        )
        assert kwargs["group_id"] == group_id


class TestInsightSkillGroupId:
    """parzival_save_insight.py passes group_id to store_agent_memory."""

    def test_store_called_with_group_id(self, monkeypatch, tmp_path):
        """store_agent_memory receives group_id from env; fails assertion without fix."""
        group_id = "test-insight-project"
        mock_store = MagicMock()
        mock_store.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "abc003xyz",
        }

        monkeypatch.setenv("AI_MEMORY_PROJECT_ID", group_id)
        _patch_memory_modules(monkeypatch, mock_store, group_id)
        monkeypatch.setattr(
            sys, "argv", ["parzival_save_insight.py", "Test insight content"]
        )
        monkeypatch.chdir(tmp_path)

        mod = _load_module(_INSIGHT_SCRIPT, "parzival_save_insight_under_test")
        mod.main()

        mock_store.store_agent_memory.assert_called_once()
        kwargs = mock_store.store_agent_memory.call_args.kwargs
        assert "group_id" in kwargs, (
            "group_id missing from store_agent_memory call — "
            "would raise TypeError against W-09 real signature"
        )
        assert kwargs["group_id"] == group_id
