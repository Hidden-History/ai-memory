"""Trace buffer flush daemon — reads JSON events from disk and sends to Langfuse.

Runs as a long-lived process (docker-compose trace-flush-worker service).
Flushes the on-disk trace buffer to Langfuse on a configurable interval.

SPEC-020 §5 / PLAN-008 / DEC-PLAN008-004
"""

import contextlib
import json
import logging
import os
import signal
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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

from memory.langfuse_config import get_langfuse_client  # noqa: E402


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
    """Create an OTel context for linking spans to a trace and optional parent."""
    if not OTEL_AVAILABLE:
        return None
    trace_id_int = int(trace_id_hex, 16)
    parent_span_id_int = 0
    if parent_span_id_hex:
        parent_span_id_int = int(parent_span_id_hex[:16], 16)
    span_context = SpanContext(
        trace_id=trace_id_int,
        span_id=parent_span_id_int if parent_span_id_int else otel_trace_api.INVALID_SPAN_ID,
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

shutdown_requested = False


def _handle_signal(signum, frame):
    global shutdown_requested
    logger.info("Received signal %s — shutting down gracefully", signum)
    shutdown_requested = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


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
            otel_span.set_attribute("langfuse.trace.session_id", event["session_id"])
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
        otel_span.set_attribute(
            "langfuse.trace.metadata",
            json.dumps({"project_id": event.get("project_id"), "source": "trace_buffer"}),
        )

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

    if as_type == "generation":
        observation = langfuse.start_generation(
            trace_context={"trace_id": trace_id},
            name=event_type,
        )
        observation.update(
            input=data.get("input"),
            output=data.get("output"),
            metadata=span_metadata,
            model=data.get("model"),
            usage_details=data.get("usage"),
        )
    else:
        observation = langfuse.start_span(
            trace_context={"trace_id": trace_id},
            name=event_type,
        )
        observation.update(
            input=data.get("input"),
            output=data.get("output"),
            metadata=span_metadata,
        )

    # ISSUE-185: Only set trace-level I/O on root events
    is_root = event_type == "1_capture" or not parent_span_id
    trace_kwargs = {
        "name": f"hook_pipeline_{event.get('project_id', 'unknown')}",
        "session_id": event.get("session_id"),
        "metadata": {
            "project_id": event.get("project_id"),
            "source": "trace_buffer",
        },
    }
    if is_root:
        trace_kwargs["input"] = data.get("input")
        trace_kwargs["output"] = data.get("output")
    observation.update_trace(**trace_kwargs)

    if data.get("end_time"):
        observation.end(end_time=_dt_to_ns(data["end_time"]))
    else:
        observation.end()


def process_buffer_files(langfuse) -> tuple[int, int]:
    """Read *.json files from buffer dir, create Langfuse traces+spans, delete processed.

    Uses raw OTel spans when available (ISSUE-183: accurate timing via start_time).
    Falls back to Langfuse SDK when OTel is not installed.

    Returns:
        Tuple of (processed_count, error_count).
    """
    if not BUFFER_DIR.exists():
        return 0, 0

    processed = 0
    errors = 0

    for json_file in list(BUFFER_DIR.glob("*.json")):
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
            json_file.unlink()
            processed += 1
        except Exception as e:
            logger.error("Failed to process buffer file %s: %s", json_file.name, e)
            errors += 1

    return processed, errors


def main():
    """Main flush loop: evict → process → flush → push metrics → sleep."""
    global shutdown_requested

    langfuse = get_langfuse_client()
    if langfuse is None:
        logger.warning("Langfuse client unavailable — trace flush worker exiting")
        sys.exit(1)

    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Trace flush worker started (buffer=%s, interval=%ss, max_buffer=%sMB)",
        BUFFER_DIR,
        FLUSH_INTERVAL,
        MAX_BUFFER_MB,
    )

    total_processed = 0
    total_errors = 0

    while not shutdown_requested:
        evicted = evict_oldest_traces()
        processed, errors = process_buffer_files(langfuse)

        total_errors += errors
        if processed > 0:
            try:
                langfuse.flush()
            except Exception as e:
                logger.warning("Langfuse flush failed: %s", e)
            total_processed += processed
            logger.info("Flushed %s events (%s errors)", processed, errors)

        # Push metrics
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

        # TD-182: Touch heartbeat file for Docker healthcheck (file-based liveness probe)
        with contextlib.suppress(OSError):
            HEARTBEAT_FILE.touch()

        time.sleep(FLUSH_INTERVAL)

    # Graceful shutdown — flush remaining buffer
    logger.info(
        "Shutdown requested — flushing remaining buffer (%s total processed)",
        total_processed,
    )
    evict_oldest_traces()
    processed, errors = process_buffer_files(langfuse)
    total_errors += errors
    if processed > 0:
        try:
            langfuse.flush()
        except Exception as e:
            logger.warning("Langfuse flush failed during shutdown: %s", e)
        total_processed += processed

    logger.info(
        "Trace flush worker stopped (total_processed=%s, total_errors=%s)",
        total_processed,
        total_errors,
    )
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
