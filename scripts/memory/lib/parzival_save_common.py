"""Shared helpers for parzival-save-* backing scripts.

Provides store_with_metrics() and emit_trace() — the two call-site primitives
shared across parzival_save_decision.py, parzival_save_handoff.py, and
parzival_save_insight.py.

Per-script names (get_config, MemoryStorage, push_skill_metrics_async,
resolve_project_id, _DEC_PREFIX_RE) stay in each backing script so that
test patches on the loaded module objects (monkeypatch.setattr / patch.object)
continue to bind correctly.
"""

from __future__ import annotations

import os


def store_with_metrics(
    *,
    storage,
    content: str,
    memory_type: str,
    group_id: str,
    agent_id: str,
    **extra_store_kwargs,
) -> dict:
    """Wrap storage.store_agent_memory, injecting cwd=os.getcwd().

    Returns the result dict.  Raises on storage exception — the caller is
    responsible for pushing error metrics and printing the per-script message.
    """
    return storage.store_agent_memory(
        content=content,
        memory_type=memory_type,
        agent_id=agent_id,
        cwd=os.getcwd(),
        group_id=group_id,
        **extra_store_kwargs,
    )


def emit_trace(*, session_id: str, data: dict, tags: list | None = None) -> None:
    """Best-effort trace emit via memory.trace_buffer.  No-op on any exception."""
    try:
        from memory.trace_buffer import emit_trace_event

        emit_trace_event(
            event_type="skill_execution",
            data=data,
            session_id=session_id,
            tags=tags or ["skill"],
        )
    except Exception:
        pass
