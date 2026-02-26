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


def process_buffer_files(langfuse) -> tuple[int, int]:
    """Read *.json files from buffer dir, create Langfuse traces+spans, delete processed.

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
            raw_trace_id = event.get("trace_id", "")
            # Langfuse requires 32 lowercase hex chars (no hyphens).
            # Our trace IDs are UUID4 format — strip hyphens to comply.
            trace_id = raw_trace_id.replace("-", "") if raw_trace_id else None
            data = event.get("data", {})
            event_type = event.get("event_type", "unknown")
            as_type = event.get(
                "as_type"
            )  # Wave 1H: "generation" or None (default = span)

            span_metadata = data.get("metadata", {})
            if data.get("start_time"):
                span_metadata["original_start_time"] = data["start_time"]
            if event.get("parent_span_id"):
                span_metadata["parent_span_id"] = event.get("parent_span_id")

            # Wave 1H: Create GENERATION observation for LLM calls (e.g., 9_classify),
            # plain SPAN for all other pipeline steps.
            if as_type == "generation":
                # Build generation kwargs — model and usage are in data payload
                gen_kwargs = {
                    "trace_context": {"trace_id": trace_id},
                    "name": event_type,
                    "input": data.get("input"),
                    "metadata": span_metadata,
                }
                if data.get("model"):
                    gen_kwargs["model"] = data["model"]
                if data.get("usage"):
                    gen_kwargs["usage"] = data["usage"]
                if data.get("start_time"):
                    gen_kwargs["start_time"] = _dt_to_ns(data["start_time"])
                observation = langfuse.start_generation(**gen_kwargs)
            else:
                span_kwargs = {
                    "trace_context": {"trace_id": trace_id},
                    "name": event_type,
                    "input": data.get("input"),
                    "metadata": span_metadata,
                }
                if data.get("start_time"):
                    span_kwargs["start_time"] = _dt_to_ns(data["start_time"])
                observation = langfuse.start_span(**span_kwargs)

            # BUG-152: Root spans (no parent_span_id) must set input/output
            # on update_trace() so Langfuse v3 derives trace-level I/O.
            trace_kwargs = {
                "name": f"hook_pipeline_{event.get('project_id', 'unknown')}",
                "session_id": event.get("session_id"),
                "metadata": {
                    "project_id": event.get("project_id"),
                    "source": "trace_buffer",
                },
            }
            if not event.get("parent_span_id"):
                trace_kwargs["input"] = data.get("input")
                trace_kwargs["output"] = data.get("output")
            observation.update_trace(**trace_kwargs)

            # BUG-154: Set output on observation before ending — start_span/start_generation()
            # does not persist output, must use observation.update().
            if data.get("output") is not None:
                observation.update(output=data.get("output"))

            if data.get("end_time"):
                observation.end(end_time=_dt_to_ns(data["end_time"]))
            else:
                observation.end()
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
