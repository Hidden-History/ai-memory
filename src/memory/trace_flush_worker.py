"""Trace buffer flush daemon — reads JSON events from disk and sends to Langfuse.

Runs as a long-lived process (docker-compose trace-flush-worker service).
Flushes the on-disk trace buffer to Langfuse on a configurable interval.

SPEC-020 §5 / PLAN-008 / DEC-PLAN008-004
"""

# LANGFUSE: Trace flush worker. See LANGFUSE-INTEGRATION-SPEC.md §7.6
# SDK VERSION: V4. Do NOT use start_span() or start_generation().
# TD-372: OTel scope "ai-memory.flush-worker" requires should_export_span in langfuse_config.py.
# OTel path (_process_event_otel): Uses raw OTel spans — DO NOT change attribute names.
# SDK path (_process_event_sdk): Fallback when OTel unavailable — uses start_observation().

import contextlib
import json
import logging
import os
import random
import signal
import socket
import stat
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from opentelemetry import trace as otel_trace_api
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Bootstrap: allow running as `python -m memory.trace_flush_worker` from src/
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

try:
    from langfuse import propagate_attributes as _langfuse_propagate_attributes
except ImportError:  # pragma: no cover
    _langfuse_propagate_attributes = None  # type: ignore[assignment]

from memory.langfuse_config import get_langfuse_client


def _dt_to_ns(iso_str: str) -> int:
    """Convert ISO datetime string to nanoseconds since epoch.

    Langfuse SDK v3 uses OpenTelemetry internally, which requires
    end_time/start_time as nanoseconds (int), not datetime objects.
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1e9)


def _make_parent_context(trace_id_hex: str, parent_span_id_hex: str | None = None):
    """Create an OTel context for linking spans to a trace and optional parent.

    When parent_span_id_hex is None (root span), generates a random valid span_id
    so the SpanContext passes is_valid() and OTel inherits the trace_id.
    INVALID_SPAN_ID would make is_valid() return False, causing OTel to create
    a new trace with a random trace_id — breaking trace linking.
    """
    if not OTEL_AVAILABLE:
        return None
    trace_id_int = int(trace_id_hex, 16)
    if parent_span_id_hex:
        parent_span_id_int = int(parent_span_id_hex[:16], 16)
    else:
        # Generate a valid synthetic span_id (is_remote=True means OTel won't
        # look for this span locally). This ensures SpanContext.is_valid() == True
        # so the new span inherits our trace_id.
        parent_span_id_int = random.getrandbits(64)
    span_context = SpanContext(
        trace_id=trace_id_int,
        span_id=parent_span_id_int,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return otel_trace_api.set_span_in_context(NonRecordingSpan(span_context))


try:
    from memory.metrics_push import (
        push_langfuse_buffer_metrics_async as _push_metrics_fn,
    )

    push_metrics_fn = _push_metrics_fn
except ImportError:
    push_metrics_fn = None

logger = logging.getLogger(__name__)

BUFFER_DIR = Path(INSTALL_DIR) / "trace_buffer"
FLUSH_INTERVAL = int(os.environ.get("LANGFUSE_FLUSH_INTERVAL", "5"))
MAX_BUFFER_MB = int(os.environ.get("LANGFUSE_TRACE_BUFFER_MAX_MB", "100"))
HEARTBEAT_FILE = BUFFER_DIR / ".heartbeat"

# BUG-315: bound the per-iteration drain so one slow flush cannot wedge an
# unbounded pass over a large backlog. Aligned with LANGFUSE_FLUSH_AT (max events
# the SDK batches per send) so each pass enqueues at most one batch before the
# loop cycles (refreshing the heartbeat and re-checking connectivity).
FLUSH_BATCH_MAX = int(os.environ.get("LANGFUSE_FLUSH_AT", "500"))

# Backend the worker flushes to. flush() blocks (never throws) when this is
# unreachable, so the loop preflights a TCP probe here and skips the flush when
# it cannot connect (the container has no wget/curl).
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "http://langfuse-web:3000")
PREFLIGHT_TIMEOUT_SECONDS = float(
    os.environ.get("LANGFUSE_PREFLIGHT_TIMEOUT_SECONDS", "3")
)

# BUG-315: stall watchdog. If the main loop makes no forward progress (completes
# no full iteration) for this long, it is considered wedged and the process
# self-exits so Docker (restart: unless-stopped) restarts it into a draining
# state — an "unhealthy" healthcheck alone does NOT trigger a restart. Derived
# from FLUSH_INTERVAL with a wide margin so a slow-but-progressing backlog drain
# (each bounded batch advances the progress marker) never trips it.
STALL_DEADLINE_SECONDS = int(
    os.environ.get(
        "LANGFUSE_STALL_DEADLINE_SECONDS", str(max(FLUSH_INTERVAL * 12, 120))
    )
)

shutdown_requested = False

# Monotonic timestamp of the last completed main-loop iteration. The watchdog
# thread reads this to detect a wedged loop. Updated at the bottom of each
# iteration so it reflects drain progress, not raw wall-clock spent inside flush.
_last_loop_progress = 0.0

# Watchdog wakeup — lets the watchdog wait on its own cadence (not time.sleep, so
# it stays independent of the main loop's pacing) and be woken promptly on exit.
_watchdog_wakeup = threading.Event()


def _handle_signal(signum, frame):
    global shutdown_requested
    logger.info("Received signal %s — shutting down gracefully", signum)
    shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _backend_reachable() -> bool:
    """Return True if a TCP connection to the Langfuse backend can be opened.

    The worker container ships without wget/curl, so connectivity is probed with
    a short-timeout socket connect. flush() blocks (and never throws) against an
    unreachable backend, so the loop uses this to skip the flush and keep cycling
    (evict + heartbeat) instead of wedging inside a doomed retry (BUG-315).
    """
    parsed = urlparse(LANGFUSE_BASE_URL)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=PREFLIGHT_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _resolve_user_id(span_metadata: dict) -> str:
    """Map a buffered event's agent identity to a Langfuse user_id (BP-169 §2.3).

    Convention: ``agent:<name>`` for agent-attributable events (the capture-time
    CLAUDE_AGENT_NAME, already in data["metadata"]); ``system:unknown`` when the
    buffered event carries no identity. The flush worker's own service spans use
    ``system:trace-flush-worker`` — but the events processed here are relayed
    agent events, so they carry their real identity, not the worker's.
    """
    agent_name = span_metadata.get("agent_name")
    if agent_name:
        return f"agent:{agent_name}"[:200]
    return "system:unknown"


def _resolve_role_tag(span_metadata: dict) -> str | None:
    """Return a ``role:<role>`` tag from the buffered event's agent_role, or None."""
    agent_role = span_metadata.get("agent_role")
    if agent_role:
        return f"role:{agent_role}"[:200]
    return None


def _is_stalled(last_progress: float, now: float) -> bool:
    """Return True if the loop has made no progress within STALL_DEADLINE_SECONDS."""
    return (now - last_progress) > STALL_DEADLINE_SECONDS


def _watchdog_loop() -> None:
    """Background watchdog: hard-exit the process if the main loop wedges.

    Measures drain progress via ``_last_loop_progress`` (advanced at the bottom of
    every main-loop iteration), so a slow-but-progressing backlog drain is never
    killed — only a loop stuck inside a blocking flush/process pass trips it.

    Uses ``os._exit`` (not ``sys.exit``): when the main thread is wedged in a
    blocking flush, a SystemExit raised in this thread cannot terminate the
    process, so a hard exit is the only way to let Docker restart the container.
    """
    while not shutdown_requested:
        if _last_loop_progress and _is_stalled(_last_loop_progress, time.monotonic()):
            logger.warning(
                "Trace flush loop stalled — no progress for >%ss (wedged flush?). "
                "Self-exiting so Docker restarts the worker into a draining state.",
                STALL_DEADLINE_SECONDS,
            )
            os._exit(1)
        _watchdog_wakeup.wait(min(FLUSH_INTERVAL or 1, 5))


def evict_oldest_traces() -> int:
    """Evict oldest trace files when buffer exceeds MAX_BUFFER_MB.

    Uses a single stat() call per file (not 2-3). Sorts by mtime.
    Returns number of files evicted.
    """
    if not BUFFER_DIR.exists():
        return 0

    try:
        # Single stat call per file via os.scandir for efficiency
        entries = []
        with os.scandir(BUFFER_DIR) as it:
            for entry in it:
                st = entry.stat()
                if stat.S_ISREG(st.st_mode) and entry.name.endswith(".json"):
                    entries.append((st.st_mtime, st.st_size, Path(entry.path)))
    except OSError as e:
        logger.warning("Failed to scan buffer dir: %s", e)
        return 0

    total_bytes = sum(size for _, size, _ in entries)
    max_bytes = MAX_BUFFER_MB * 1024 * 1024

    if total_bytes <= max_bytes:
        return 0

    # Sort oldest first
    entries.sort(key=lambda x: x[0])

    evicted = 0
    for _mtime, size, path in entries:
        if total_bytes <= max_bytes:
            break
        try:
            path.unlink()
            total_bytes -= size
            evicted += 1
        except OSError as e:
            logger.warning("Failed to evict %s: %s", path.name, e)

    if evicted > 0:
        logger.warning(
            "Langfuse trace buffer exceeded %sMB, evicting %s oldest traces. Is Langfuse running?",
            MAX_BUFFER_MB,
            evicted,
        )

    return evicted


def _process_event_otel(event: dict, data: dict) -> None:
    """Process a single trace event using raw OTel spans for accurate timing.

    ISSUE-183: Uses OTel tracer from global TracerProvider (where Langfuse
    auto-registers its span processor) so spans flow through Langfuse.
    """
    tracer = otel_trace_api.get_tracer("ai-memory.flush-worker")

    raw_trace_id = event.get("trace_id", "")
    trace_id = raw_trace_id.replace("-", "") if raw_trace_id else None
    parent_span_id = event.get("parent_span_id")
    event_type = event.get("event_type", "unknown")
    as_type = event.get("as_type")

    parent_ctx = _make_parent_context(trace_id, parent_span_id) if trace_id else None

    start_ns = _dt_to_ns(data["start_time"]) if data.get("start_time") else None
    end_ns = _dt_to_ns(data["end_time"]) if data.get("end_time") else None

    span_kwargs = {}
    if parent_ctx is not None:
        span_kwargs["context"] = parent_ctx
    if start_ns is not None:
        span_kwargs["start_time"] = start_ns

    otel_span = tracer.start_span(name=event_type, **span_kwargs)

    if data.get("input") is not None:
        val = data["input"]
        otel_span.set_attribute(
            "langfuse.observation.input",
            json.dumps(val) if not isinstance(val, str) else val,
        )
    if data.get("output") is not None:
        val = data["output"]
        otel_span.set_attribute(
            "langfuse.observation.output",
            json.dumps(val) if not isinstance(val, str) else val,
        )
    if as_type == "generation":
        otel_span.set_attribute("langfuse.observation.type", "generation")
        if data.get("model"):
            otel_span.set_attribute("langfuse.observation.model.name", data["model"])
        if data.get("usage"):
            otel_span.set_attribute(
                "langfuse.observation.usage_details",
                json.dumps(data["usage"]),
            )
    elif as_type in ("retriever", "agent", "tool", "chain"):
        # G3 (BP-169): agent/tool/chain make the agent-graph view trigger; the
        # graph renders only when a trace has an observation whose type is not
        # span/event/generation.
        otel_span.set_attribute("langfuse.observation.type", as_type)

    span_metadata = dict(data.get("metadata") or {})
    if data.get("start_time"):
        span_metadata["original_start_time"] = data["start_time"]
    if parent_span_id:
        span_metadata["parent_span_id"] = parent_span_id
    if span_metadata:
        otel_span.set_attribute(
            "langfuse.observation.metadata", json.dumps(span_metadata)
        )
        for k, v in span_metadata.items():
            otel_span.set_attribute(f"langfuse.observation.metadata.{k}", str(v))

    # ISSUE-185: Only set trace-level attributes on root events
    is_root = event_type == "1_capture" or not parent_span_id
    if is_root:
        otel_span.set_attribute(
            "langfuse.trace.name",
            f"hook_pipeline_{event.get('project_id', 'unknown')}",
        )
        if event.get("session_id"):
            # Langfuse SDK v4 expects "session.id" (not "langfuse.trace.session_id")
            otel_span.set_attribute("session.id", event["session_id"])
        # G1 (BP-169): agent identity comes from the buffered event, not a
        # hardcoded "system" — agent:<name> for agent-attributable events,
        # system:unknown when the event carries none.
        otel_span.set_attribute("user.id", _resolve_user_id(span_metadata))
        if data.get("input") is not None:
            val = data["input"]
            otel_span.set_attribute(
                "langfuse.trace.input",
                json.dumps(val) if not isinstance(val, str) else val,
            )
        if data.get("output") is not None:
            val = data["output"]
            otel_span.set_attribute(
                "langfuse.trace.output",
                json.dumps(val) if not isinstance(val, str) else val,
            )
        trace_metadata = {
            "project_id": event.get("project_id"),
            "source": "trace_buffer",
        }
        # G2 (BP-169): role is propagated trace-level metadata (+ a role:<role>
        # tag below), not identity.
        if span_metadata.get("agent_role"):
            trace_metadata["agent_role"] = str(span_metadata["agent_role"])[:200]
        otel_span.set_attribute("langfuse.trace.metadata", json.dumps(trace_metadata))
        trace_tags = list(event.get("tags") or [])
        role_tag = _resolve_role_tag(span_metadata)
        if role_tag:
            trace_tags.append(role_tag)
        if trace_tags:
            otel_span.set_attribute("langfuse.trace.tags", trace_tags)

    if end_ns is not None:
        otel_span.end(end_time=end_ns)
    else:
        otel_span.end()


def _process_event_sdk(event: dict, data: dict, langfuse) -> None:
    """Process a single trace event using the Langfuse SDK (fallback path).

    Used when OTel is not available. Root-only trace data applied (ISSUE-185).
    Parent-child hierarchy stored in metadata only; true nesting requires OTel
    path (ISSUE-184).
    """
    raw_trace_id = event.get("trace_id", "")
    trace_id = raw_trace_id.replace("-", "") if raw_trace_id else None
    event_type = event.get("event_type", "unknown")
    as_type = event.get("as_type")
    parent_span_id = event.get("parent_span_id")

    span_metadata = dict(data.get("metadata") or {})
    if data.get("start_time"):
        span_metadata["original_start_time"] = data["start_time"]
    if parent_span_id:
        span_metadata["parent_span_id"] = parent_span_id

    # Set trace-level attributes via propagate_attributes (V4 pattern).
    # Falls back to nullcontext if langfuse not installed (degraded mode).
    # G1/G2 (BP-169): identity → user_id (agent:<name>/system:unknown);
    # role → propagated metadata.agent_role + a role:<role> tag.
    trace_metadata = {"project_id": event.get("project_id"), "source": "trace_buffer"}
    if span_metadata.get("agent_role"):
        trace_metadata["agent_role"] = str(span_metadata["agent_role"])[:200]
    trace_tags = list(event.get("tags") or [])
    role_tag = _resolve_role_tag(span_metadata)
    if role_tag:
        trace_tags.append(role_tag)
    _prop_ctx = (
        _langfuse_propagate_attributes(
            trace_name=f"hook_pipeline_{event.get('project_id', 'unknown')}",
            session_id=event.get("session_id") or None,
            user_id=_resolve_user_id(span_metadata),
            metadata=trace_metadata,
            tags=trace_tags or None,
        )
        if _langfuse_propagate_attributes is not None
        else contextlib.nullcontext()
    )
    with _prop_ctx:
        observation = langfuse.start_observation(
            name=event_type,
            # G3 (BP-169): pass agent/tool/chain through so the agent-graph view
            # triggers; unknown types still fall back to span.
            as_type=(
                as_type
                if as_type
                in ("generation", "span", "retriever", "agent", "tool", "chain")
                else "span"
            ),
            trace_context={"trace_id": trace_id} if trace_id else None,
        )
        observation.update(
            input=data.get("input"),
            output=data.get("output"),
            metadata=span_metadata,
            model=data.get("model") if as_type == "generation" else None,
            usage_details=data.get("usage") if as_type == "generation" else None,
        )

        if data.get("end_time"):
            try:
                observation.end(end_time=_dt_to_ns(data["end_time"]))
            except TypeError:
                # V4 SDK wrapper may not accept end_time kwarg — fall back to plain end
                logger.warning(
                    "V4 SDK rejected end_time kwarg — trace duration may be inaccurate"
                )
                observation.end()
        else:
            observation.end()


def process_buffer_files(langfuse, limit: int = FLUSH_BATCH_MAX) -> tuple[int, int]:
    """Drain up to ``limit`` *.json buffer files to Langfuse, deleting processed.

    Uses raw OTel spans when available (ISSUE-183: accurate timing via start_time).
    Falls back to Langfuse SDK when OTel is not installed.

    BUG-315: the batch is bounded (``limit``) so one slow flush cannot wedge an
    unbounded pass over a large backlog — the caller loops, refreshing the
    heartbeat and re-checking connectivity between batches. The drain is
    loss-safe: a file is unlinked only AFTER ``flush()`` confirms the batch is
    enqueued. A crash between enqueue and unlink replays the batch on restart
    (at-least-once; a duplicate is preferred over a dropped trace).

    Returns:
        Tuple of (processed_count, error_count).
    """
    if not BUFFER_DIR.exists():
        return 0, 0

    processed = 0
    errors = 0
    enqueued: list[Path] = []

    for json_file in list(BUFFER_DIR.glob("*.json"))[:limit]:
        try:
            with open(json_file) as f:
                event = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "Malformed or unreadable buffer file %s: %s", json_file.name, e
            )
            with contextlib.suppress(OSError):
                json_file.unlink()
            errors += 1
            continue

        try:
            data = event.get("data", {})
            if OTEL_AVAILABLE:
                _process_event_otel(event, data)
            else:
                _process_event_sdk(event, data, langfuse)
            enqueued.append(json_file)
        except Exception as e:
            logger.error("Failed to process buffer file %s: %s", json_file.name, e)
            errors += 1

    # Loss-safe: flush the batch before unlinking so files are removed only once
    # their spans are confirmed enqueued (flush() blocks until queues drain).
    if enqueued:
        try:
            langfuse.flush()
        except Exception as e:
            logger.warning("Langfuse flush failed: %s", e)
        for json_file in enqueued:
            with contextlib.suppress(OSError):
                json_file.unlink()
            processed += 1

    return processed, errors


def main():
    """Main flush loop: heartbeat → evict → preflight → drain batch → metrics → sleep.

    BUG-315: the heartbeat is touched at the TOP of each iteration (liveness =
    loop cycling, decoupled from a blocking flush); a TCP preflight skips the
    drain when the backend is unreachable; and a watchdog thread hard-exits the
    process if the loop wedges so Docker restarts it.
    """
    global shutdown_requested, _last_loop_progress

    langfuse = get_langfuse_client()
    degraded = langfuse is None

    BUFFER_DIR.mkdir(parents=True, exist_ok=True)

    if degraded:
        logger.warning(
            "Langfuse client unavailable — trace flush worker running in degraded mode "
            "(evict + heartbeat only, no flushing)"
        )
    else:
        logger.info(
            "Trace flush worker started (buffer=%s, interval=%ss, max_buffer=%sMB, batch=%s)",
            BUFFER_DIR,
            FLUSH_INTERVAL,
            MAX_BUFFER_MB,
            FLUSH_BATCH_MAX,
        )

    # Start the stall watchdog (BUG-315). Daemon thread so it never blocks exit.
    _last_loop_progress = time.monotonic()
    threading.Thread(target=_watchdog_loop, name="flush-watchdog", daemon=True).start()

    total_processed = 0
    total_errors = 0

    while not shutdown_requested:
        # TD-182 / BUG-315: heartbeat at the TOP of the loop so liveness reflects
        # the loop cycling, not a long/blocking flush completing.
        with contextlib.suppress(OSError):
            HEARTBEAT_FILE.touch()

        evicted = evict_oldest_traces()

        processed = 0
        errors = 0
        if not degraded:
            # Preflight: flush() blocks (never throws) on an unreachable backend,
            # so skip the drain when it cannot connect and keep cycling.
            if _backend_reachable():
                processed, errors = process_buffer_files(langfuse)
                total_errors += errors
                total_processed += processed
                if processed > 0:
                    logger.info("Flushed %s events (%s errors)", processed, errors)
            else:
                logger.debug(
                    "Langfuse backend unreachable (%s) — skipping flush this cycle",
                    LANGFUSE_BASE_URL,
                )

        # Push metrics regardless of degraded state (M-1: keep observability when
        # Langfuse is down — evictions still happen and buffer still grows)
        try:
            buffer_size_bytes = sum(f.stat().st_size for f in BUFFER_DIR.glob("*.json"))
        except OSError:
            buffer_size_bytes = 0

        if push_metrics_fn:
            push_metrics_fn(
                evictions=evicted,
                buffer_size_bytes=buffer_size_bytes,
                events_processed=processed,
                flush_errors=errors,
            )

        # Mark forward progress (a full iteration completed) for the stall
        # watchdog — a loop wedged inside flush never reaches this point.
        _last_loop_progress = time.monotonic()

        time.sleep(FLUSH_INTERVAL)

    # Wake the watchdog so it re-checks shutdown_requested and exits promptly.
    _watchdog_wakeup.set()

    # Graceful shutdown — flush remaining buffer
    logger.info(
        "Shutdown requested — flushing remaining buffer (%s total processed)",
        total_processed,
    )

    # Best-effort bounded drain on shutdown (loss-safe: process_buffer_files
    # flushes before unlinking; any remainder persists for the next start).
    if not degraded and _backend_reachable():
        evict_oldest_traces()
        processed, errors = process_buffer_files(langfuse)
        total_errors += errors
        total_processed += processed

    logger.info(
        "Trace flush worker stopped (total_processed=%s, total_errors=%s)",
        total_processed,
        total_errors,
    )

    if not degraded:
        try:
            langfuse.shutdown()
        except Exception as e:
            logger.warning("Langfuse shutdown error: %s", e)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    main()
