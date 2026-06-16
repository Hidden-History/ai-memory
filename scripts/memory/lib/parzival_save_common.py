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

# D4 F-1 write-side caps (DEC-PM338-D4.1, bounded-lead + pointer).
# HANDOFF_MAX_LINES/HANDOFF_MAX_BYTES mirror the D3 handoff file cap (60 lines /
# 8 KB); kept as local constants because the D3 gate lives in a file-disjoint
# lane and cannot be imported here. A bounded handoff (<= 8 KB ~= 2000 tokens)
# stays under the chunker's 3000-token whole-store threshold, so it persists as
# ONE vector instead of fan-chunking into 20+ injectable points.
HANDOFF_MAX_LINES = 60
HANDOFF_MAX_BYTES = 8192  # 8 KB

# Chunker AGENT_RESPONSE whole-store threshold: a body at or under this token
# count persists as ONE vector; over it, the chunker fan-chunks. The byte cap
# already keeps the char-estimate (len/4) under this, but token-dense bodies
# (code/JSON ~2.7 ch/tok) can pack more real tokens per byte, so we verify the
# bounded lead's ACTUAL token count and tighten the byte budget if needed.
HANDOFF_SINGLE_VECTOR_MAX_TOKENS = 3000

# INSIGHT_MAX_TOKENS ~= 512 tokens; at 4 chars/token that is 2048 chars, the
# ProseChunker single-chunk boundary, so a bounded insight is ONE vector.
INSIGHT_MAX_TOKENS = 512
_CHARS_PER_TOKEN = 4
INSIGHT_MAX_CHARS = INSIGHT_MAX_TOKENS * _CHARS_PER_TOKEN  # 2048

_INSIGHT_TRUNCATION_MARKER = " [truncated]"


def bound_handoff_content(content: str, *, source_path: str | None = None) -> str:
    """Return a write-bounded handoff body (D4 F-1).

    A compliant handoff (<= HANDOFF_MAX_LINES lines AND <= HANDOFF_MAX_BYTES
    bytes AND <= HANDOFF_SINGLE_VECTOR_MAX_TOKENS real tokens) is returned
    unchanged. An over-cap handoff is reduced to a bounded lead (front-loaded
    Exec-Summary / Status / Next sections) plus a pointer to the full file on
    disk. The full handoff stays whole on the filesystem (lossless); only the
    injectable vector is bounded.

    The binding single-vector guarantee is the byte/token cap, NOT the line
    count: the appended pointer adds its own newlines, so the returned body's
    total line count may exceed HANDOFF_MAX_LINES by a few lines. That is
    intentional — the byte budget reserves room for the pointer, and the token
    check below guarantees the result stays under the chunker's whole-store
    threshold regardless of token density.
    """
    over_lines = content.count("\n") + 1 > HANDOFF_MAX_LINES
    over_bytes = len(content.encode("utf-8")) > HANDOFF_MAX_BYTES
    over_tokens = _count_tokens(content) > HANDOFF_SINGLE_VECTOR_MAX_TOKENS
    if not (over_lines or over_bytes or over_tokens):
        return content

    pointer = (
        f"\n\n[truncated — full handoff: {source_path}]"
        if source_path
        else "\n\n[truncated — full handoff retained on disk]"
    )
    # Reserve room for the pointer so the stored vector stays within the cap.
    budget = HANDOFF_MAX_BYTES - len(pointer.encode("utf-8"))
    lead_src = "\n".join(content.splitlines()[:HANDOFF_MAX_LINES])
    # Tighten the byte budget until the bounded lead's ACTUAL token count is
    # under the chunker's whole-store threshold. Token-dense content (code/JSON)
    # can exceed the threshold at the byte cap even though the char-estimate
    # (len/4) does not; the geometric shrink converges quickly and the budget
    # floor guarantees termination.
    while True:
        lead = _trim_to_bytes(lead_src, budget)
        result = lead.rstrip() + pointer
        if _count_tokens(result) <= HANDOFF_SINGLE_VECTOR_MAX_TOKENS or budget <= 0:
            return result
        budget = int(budget * 0.9)


def _count_tokens(text: str) -> int:
    """Real (tiktoken) token count via the shared chunker utility.

    Imported lazily so this module stays importable on the insight path, which
    never needs it and may run before ``src`` is on sys.path.
    """
    from memory.chunking import count_tokens

    return count_tokens(text)


def bound_insight_content(content: str) -> str:
    """Return a write-bounded insight body (D4 F-1).

    A compliant insight (<= INSIGHT_MAX_CHARS) is returned unchanged. An
    over-cap insight is truncated to a bounded lead plus a truncation marker,
    kept within INSIGHT_MAX_CHARS so it stores as a single vector.
    """
    if len(content) <= INSIGHT_MAX_CHARS:
        return content
    budget = INSIGHT_MAX_CHARS - len(_INSIGHT_TRUNCATION_MARKER)
    return content[:budget].rstrip() + _INSIGHT_TRUNCATION_MARKER


def _trim_to_bytes(text: str, max_bytes: int) -> str:
    """Trim text to at most max_bytes UTF-8 bytes without splitting a char."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


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
