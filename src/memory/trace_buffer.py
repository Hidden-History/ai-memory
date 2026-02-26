"""Fire-and-forget trace event buffer for hook scripts.

Writes JSON trace events to a buffer directory. A separate
trace-flush-worker reads and sends these to Langfuse.

Overhead: ~5-10ms per event (atomic file write).

SPEC-020 §4 / PLAN-008
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

TRACE_BUFFER_DIR = (
    Path(os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")))
    / "trace_buffer"
)

# Max buffer size guard (MB-based, per DEC-PLAN008-004)
BUFFER_MAX_MB = int(os.environ.get("LANGFUSE_TRACE_BUFFER_MAX_MB", "100"))

# Buffer size tracked incrementally to avoid O(n) directory scan on every emit call.
# Initialized from actual directory size on first write; updated on each successful write.
_buffer_size_bytes: int = -1  # -1 = not yet calibrated


def _calibrate_buffer_size() -> int:
    """Scan buffer directory once to initialize _buffer_size_bytes. O(n) — call only on startup."""
    try:
        return sum(f.stat().st_size for f in TRACE_BUFFER_DIR.glob("*.json"))
    except OSError:
        return 0


def emit_trace_event(
    event_type: str,
    data: dict,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    as_type: str | None = None,
) -> bool:
    """Write a trace event to the buffer directory.

    Args:
        event_type: Span name (e.g., "1_capture", "5_chunk", "7_store", "9_classify")
        data: Event payload (inputs, outputs, metadata). For generation type, may include
              "model", "usage" ({"input": N, "output": N}) keys alongside "input"/"output".
        trace_id: Langfuse trace ID (shared across pipeline steps)
        span_id: Unique span ID for this event
        parent_span_id: Parent span ID (for nesting)
        session_id: Claude Code session ID (for Tier 1 linking)
        project_id: AI Memory project ID (from detect_project)
        start_time: Span start time (default: now). Capture before doing work.
        end_time: Span end time (default: now). Enables Langfuse latency visualization.
        as_type: Observation type override. "generation" creates a Langfuse generation
                 (with model name + token usage) instead of the default span. None = span.

    Returns:
        True if event was written, False if skipped (disabled or buffer full).
    """
    global _buffer_size_bytes

    # Check kill-switch without importing langfuse
    if os.environ.get("LANGFUSE_ENABLED", "false").lower() != "true":
        return False
    if os.environ.get("LANGFUSE_TRACE_HOOKS", "true").lower() != "true":
        return False

    TRACE_BUFFER_DIR.mkdir(parents=True, exist_ok=True)

    # Calibrate buffer size once on first call (avoids O(n) scan on every emit).
    if _buffer_size_bytes < 0:
        _buffer_size_bytes = _calibrate_buffer_size()

    # Buffer overflow guard: MB-based (DEC-PLAN008-004).
    buffer_size_mb = _buffer_size_bytes / (1024 * 1024)
    if buffer_size_mb >= BUFFER_MAX_MB:
        return False

    now = datetime.now(tz=timezone.utc)
    event = {
        "timestamp": time.time(),
        "event_type": event_type,
        "trace_id": (
            trace_id or os.environ.get("LANGFUSE_TRACE_ID", uuid4().hex)
        ).replace("-", ""),
        "span_id": span_id or uuid4().hex,
        "parent_span_id": parent_span_id,
        "session_id": session_id,
        "project_id": project_id or os.environ.get("AI_MEMORY_PROJECT_ID", ""),
        "data": {
            **data,
            "start_time": (start_time or now).isoformat(),
            "end_time": (end_time or now).isoformat(),
        },
    }
    # Wave 1H: Include observation type when explicitly specified (e.g., "generation")
    if as_type:
        event["as_type"] = as_type

    # Atomic write via temp file + rename (prevents partial reads)
    tmp_path = TRACE_BUFFER_DIR / f".tmp_{uuid4().hex}"
    final_path = TRACE_BUFFER_DIR / f"{uuid4().hex}.json"

    try:
        serialized = json.dumps(event, default=str)
        tmp_path.write_text(serialized)
        tmp_path.rename(final_path)
        # Increment running counter so next call needs no directory scan
        _buffer_size_bytes += len(serialized.encode())
        return True
    except OSError:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        return False
