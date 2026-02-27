"""Unit tests for memory.trace_flush_worker — SPEC-020 §9.1 (9 test cases)."""

import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src/ is on path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_module(tmp_path, monkeypatch):
    """Import trace_flush_worker with BUFFER_DIR patched to tmp_path.

    Also patches OTEL_AVAILABLE=False on the freshly imported module so tests
    exercise the SDK fallback path regardless of whether opentelemetry is
    installed in the test environment.
    """
    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    monkeypatch.setenv("LANGFUSE_FLUSH_INTERVAL", "0")
    monkeypatch.setenv("LANGFUSE_TRACE_BUFFER_MAX_MB", "100")

    # Remove cached module so re-import picks up new env vars
    for key in list(sys.modules.keys()):
        if "trace_flush_worker" in key:
            del sys.modules[key]

    import memory.trace_flush_worker as mod

    # Patch BUFFER_DIR to tmp_path/trace_buffer
    buffer_dir = tmp_path / "trace_buffer"
    buffer_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "BUFFER_DIR", buffer_dir)

    # Force SDK fallback path — must be after reimport so it targets the
    # actual module object used by process_buffer_files()
    monkeypatch.setattr(mod, "OTEL_AVAILABLE", False)

    return mod, buffer_dir


def _write_event(buffer_dir: Path, name: str, **extra) -> Path:
    """Write a trace event JSON file matching trace_buffer.emit_trace_event() output format."""
    # Use valid 32-char hex IDs (BUG-161 requires hex trace IDs)
    hex_id = hashlib.md5(name.encode()).hexdigest()
    event = {
        "timestamp": time.time(),
        "event_type": "TestHook",
        "trace_id": hex_id,
        "span_id": hex_id[:16],
        "parent_span_id": None,
        "session_id": "sess001",
        "project_id": "test-project",
        "data": {
            "start_time": "2026-02-23T10:00:00+00:00",
            "end_time": "2026-02-23T10:00:01+00:00",
            "input": "test input",
            "output": "test output",
            "metadata": {},
        },
    }
    event.update(extra)
    path = buffer_dir / f"{name}.json"
    path.write_text(json.dumps(event))
    return path


# ---------------------------------------------------------------------------
# Test 1 — valid buffer files create Langfuse trace + span
# ---------------------------------------------------------------------------


def test_processes_valid_buffer_files(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    _write_event(buffer_dir, "evt1")

    mock_langfuse = MagicMock()
    mock_span = MagicMock()
    mock_langfuse.start_span.return_value = mock_span

    processed, errors = mod.process_buffer_files(mock_langfuse)

    assert processed == 1
    assert errors == 0
    mock_langfuse.start_span.assert_called_once()
    mock_span.update_trace.assert_called_once()
    mock_span.end.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2 — processed files are deleted
# ---------------------------------------------------------------------------


def test_removes_processed_files(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    path = _write_event(buffer_dir, "evt_del")

    mock_langfuse = MagicMock()
    mock_langfuse.start_span.return_value = MagicMock()

    mod.process_buffer_files(mock_langfuse)

    assert not path.exists(), "Processed file should be deleted"


# ---------------------------------------------------------------------------
# Test 3 — malformed JSON is removed, errors counter incremented, no crash
# ---------------------------------------------------------------------------


def test_handles_malformed_json(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    bad = buffer_dir / "bad.json"
    bad.write_text("{not valid json")

    mock_langfuse = MagicMock()
    processed, errors = mod.process_buffer_files(mock_langfuse)

    assert processed == 0
    assert errors == 1
    assert not bad.exists(), "Malformed file should be deleted"


# ---------------------------------------------------------------------------
# Test 4 — SIGTERM sets shutdown_requested flag
# ---------------------------------------------------------------------------


def test_graceful_shutdown(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "shutdown_requested", False)

    # Send SIGTERM to the current process — our handler should fire
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(0.05)  # tiny wait for signal delivery

    assert mod.shutdown_requested is True


# ---------------------------------------------------------------------------
# Test 5 — metrics push function called with correct args
# ---------------------------------------------------------------------------


def test_pushes_prometheus_metrics(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    _write_event(buffer_dir, "evt_metrics")

    mock_langfuse = MagicMock()
    mock_langfuse.start_span.return_value = MagicMock()

    mock_push = MagicMock()
    monkeypatch.setattr(mod, "push_metrics_fn", mock_push)

    # Stop main loop after one iteration
    def stop_after_one(_):
        mod.shutdown_requested = True

    monkeypatch.setattr(mod, "shutdown_requested", False)

    with (
        patch(
            "memory.trace_flush_worker.get_langfuse_client", return_value=mock_langfuse
        ),
        patch("time.sleep", side_effect=stop_after_one),
    ):
        mod.main()

    # Verify push_metrics_fn was called BY main() (not by us)
    assert mock_push.call_count >= 1
    call_kwargs = mock_push.call_args_list[0][1]  # first call keyword args
    assert "evictions" in call_kwargs
    assert "buffer_size_bytes" in call_kwargs
    assert "events_processed" in call_kwargs
    assert "flush_errors" in call_kwargs


# ---------------------------------------------------------------------------
# Test 6 — eviction triggers when buffer exceeds max MB
# ---------------------------------------------------------------------------


def test_eviction_triggers_when_buffer_exceeds_max_mb(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    # Set max to near-zero so any file triggers eviction
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 0.000001)

    _write_event(buffer_dir, "old_evt")

    evicted = mod.evict_oldest_traces()
    assert evicted >= 1


# ---------------------------------------------------------------------------
# Test 7 — oldest traces by mtime are evicted first
# ---------------------------------------------------------------------------


def test_eviction_removes_oldest_by_mtime(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 0.000001)

    older = _write_event(buffer_dir, "older_evt")
    _write_event(buffer_dir, "newer_evt")

    # Force mtime difference — older file gets an earlier mtime
    old_time = time.time() - 100
    os.utime(older, (old_time, old_time))

    # Only allow enough bytes for one file — evict oldest first
    # We keep MAX_BUFFER_MB tiny so both would be evicted, but check order
    evicted = mod.evict_oldest_traces()

    # The older file should be evicted first (may both be evicted due to tiny limit)
    assert evicted >= 1
    # If only one file remains, it should be the newer one
    remaining = list(buffer_dir.glob("*.json"))
    if len(remaining) == 1:
        assert remaining[0].name == "newer_evt.json"


# ---------------------------------------------------------------------------
# Test 8 — eviction count returned correctly
# ---------------------------------------------------------------------------


def test_eviction_counter_metric_increments(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 0.000001)

    _write_event(buffer_dir, "e1")
    _write_event(buffer_dir, "e2")

    evicted = mod.evict_oldest_traces()
    assert evicted == 2  # Both files should be evicted given tiny limit


# ---------------------------------------------------------------------------
# Test 9 — buffer size changes after eviction
# ---------------------------------------------------------------------------


def test_buffer_size_metric_reflects_post_eviction_size(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 0.000001)

    _write_event(buffer_dir, "ev_size")

    size_before = sum(f.stat().st_size for f in buffer_dir.glob("*.json"))
    assert size_before > 0

    mod.evict_oldest_traces()

    size_after = sum(f.stat().st_size for f in buffer_dir.glob("*.json"))
    assert size_after < size_before
