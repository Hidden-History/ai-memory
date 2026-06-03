"""Optional telemetry helpers — shared import-guard.

Re-exports push_skill_metrics_async and emit_trace_event with graceful-degrade
fallback to None when the underlying packages are unavailable.

Used by aim-parzival-bootstrap and aim-parzival-constraints skills.
Both names are always defined after import; callers must guard on truthiness.
"""

try:
    from memory.metrics_push import push_skill_metrics_async  # type: ignore
except ImportError:
    push_skill_metrics_async = None  # type: ignore

try:
    from memory.trace_buffer import emit_trace_event  # type: ignore
except ImportError:
    emit_trace_event = None  # type: ignore
