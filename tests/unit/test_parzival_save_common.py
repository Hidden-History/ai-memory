"""Unit tests for scripts/memory/lib/parzival_save_common.py.

DEC-109 CI conventions: in-process, mocked memory.*, AI_MEMORY_PROJECT_ID unset.
No Qdrant, no external services.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# Add lib/ to sys.path so parzival_save_common is importable without install.
_LIB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "memory", "lib")
)
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from parzival_save_common import emit_trace, store_with_metrics  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Clear ambient AI_MEMORY_PROJECT_ID per DEC-109 CI conventions."""
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)


class TestStoreWithMetrics:
    def test_returns_storage_result(self):
        """Returns the dict from storage.store_agent_memory unchanged."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "abc123xyz",
        }

        result = store_with_metrics(
            storage=mock_storage,
            content="test content",
            memory_type="agent_insight",
            group_id="proj-a",
            agent_id="parzival",
        )

        assert result == {"status": "stored", "memory_id": "abc123xyz"}
        mock_storage.store_agent_memory.assert_called_once()

    def test_injects_cwd(self, tmp_path, monkeypatch):
        """cwd=os.getcwd() is always passed to store_agent_memory."""
        monkeypatch.chdir(tmp_path)
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "x",
        }

        store_with_metrics(
            storage=mock_storage,
            content="content",
            memory_type="agent_handoff",
            group_id="proj-b",
            agent_id="parzival",
        )

        kwargs = mock_storage.store_agent_memory.call_args.kwargs
        assert kwargs["cwd"] == str(tmp_path)

    def test_forwards_required_kwargs(self):
        """content, memory_type, group_id, agent_id are passed through."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "y",
        }

        store_with_metrics(
            storage=mock_storage,
            content="body text",
            memory_type="decision",
            group_id="proj-c",
            agent_id="parzival",
        )

        kwargs = mock_storage.store_agent_memory.call_args.kwargs
        assert kwargs["content"] == "body text"
        assert kwargs["memory_type"] == "decision"
        assert kwargs["group_id"] == "proj-c"
        assert kwargs["agent_id"] == "parzival"

    def test_forwards_extra_kwargs(self):
        """Per-script extras (session_id, metadata) are forwarded unchanged."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.return_value = {
            "status": "stored",
            "memory_id": "z",
        }
        meta = {
            "dec_id": "DEC-001",
            "pm_number": 99,
            "decision_summary": "test",
            "rationale_text": None,
        }

        store_with_metrics(
            storage=mock_storage,
            content="decision body",
            memory_type="decision",
            group_id="proj-d",
            agent_id="parzival",
            session_id="sess-xyz",
            metadata=meta,
        )

        kwargs = mock_storage.store_agent_memory.call_args.kwargs
        assert kwargs["session_id"] == "sess-xyz"
        assert kwargs["metadata"] == meta

    def test_raises_on_storage_exception(self):
        """Exceptions from store_agent_memory propagate to the caller."""
        mock_storage = MagicMock()
        mock_storage.store_agent_memory.side_effect = RuntimeError("qdrant down")

        with pytest.raises(RuntimeError, match="qdrant down"):
            store_with_metrics(
                storage=mock_storage,
                content="content",
                memory_type="agent_insight",
                group_id="proj-e",
                agent_id="parzival",
            )


class TestEmitTrace:
    def test_calls_emit_trace_event(self, monkeypatch):
        """Dispatches emit_trace_event with correct args when module is available."""
        mock_emit = MagicMock()
        fake_mod = types.ModuleType("memory.trace_buffer")
        fake_mod.emit_trace_event = mock_emit
        monkeypatch.setitem(sys.modules, "memory.trace_buffer", fake_mod)

        data = {
            "input": "Skill: parzival-save-insight"[:10000],
            "output": "Result: stored"[:10000],
            "metadata": {"skill_name": "parzival-save-insight"},
        }
        emit_trace(session_id="sess-001", data=data, tags=["skill"])

        mock_emit.assert_called_once_with(
            event_type="skill_execution",
            data=data,
            session_id="sess-001",
            tags=["skill"],
        )

    def test_default_tags_is_skill(self, monkeypatch):
        """Tags default to ['skill'] when not provided."""
        mock_emit = MagicMock()
        fake_mod = types.ModuleType("memory.trace_buffer")
        fake_mod.emit_trace_event = mock_emit
        monkeypatch.setitem(sys.modules, "memory.trace_buffer", fake_mod)

        emit_trace(
            session_id="sess-002",
            data={"input": "x", "output": "y", "metadata": {}},
        )

        assert mock_emit.call_args.kwargs["tags"] == ["skill"]

    def test_swallows_import_error(self, monkeypatch):
        """No-op when emit_trace_event is missing from the module (ImportError)."""
        empty_mod = types.ModuleType("memory.trace_buffer")
        # emit_trace_event deliberately absent — import will raise ImportError
        monkeypatch.setitem(sys.modules, "memory.trace_buffer", empty_mod)

        # Must not raise
        emit_trace(
            session_id="sess-003",
            data={"input": "x", "output": "y", "metadata": {}},
        )

    def test_swallows_runtime_exception(self, monkeypatch):
        """Swallows any exception raised by emit_trace_event."""
        crashing_mod = types.ModuleType("memory.trace_buffer")
        crashing_mod.emit_trace_event = MagicMock(
            side_effect=ConnectionError("langfuse down")
        )
        monkeypatch.setitem(sys.modules, "memory.trace_buffer", crashing_mod)

        # Must not raise
        emit_trace(
            session_id="sess-004",
            data={"input": "x", "output": "y", "metadata": {}},
        )
