"""Unit tests for trace_buffer.py (SPEC-020 §9.1).

Tests:
1. test_emit_writes_valid_json — file contains parseable JSON with all required fields
2. test_emit_atomic_write — no .tmp_* files left after write
3. test_emit_disabled — LANGFUSE_ENABLED=false → no file created, returns False
4. test_emit_includes_project_id — project_id from AI_MEMORY_PROJECT_ID env in event
5. test_buffer_overflow_guard — stops writing when buffer exceeds LANGFUSE_TRACE_BUFFER_MAX_MB
6. test_emit_performance — single write completes in <20ms
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


import memory.trace_buffer as tb
from memory.trace_buffer import emit_trace_event


def _enable_tracing(monkeypatch, tmp_path):
    """Helper: set env vars and buffer dir for a test."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_TRACE_HOOKS", "true")
    monkeypatch.setattr(tb, "TRACE_BUFFER_DIR", tmp_path / "trace_buffer")
    monkeypatch.setattr(tb, "_buffer_size_bytes", -1)


def test_emit_writes_valid_json(monkeypatch, tmp_path):
    """Emitted file contains parseable JSON with all required fields."""
    _enable_tracing(monkeypatch, tmp_path)

    result = emit_trace_event(
        event_type="1_capture",
        data={"input": "hello"},
        trace_id="trace-abc",
        span_id="span-xyz",
    )

    assert result is True
    buf_dir = tmp_path / "trace_buffer"
    files = list(buf_dir.glob("*.json"))
    assert len(files) == 1

    event = json.loads(files[0].read_text())
    assert event["event_type"] == "1_capture"
    assert event["trace_id"] == "trace-abc"
    assert event["span_id"] == "span-xyz"
    assert "start_time" in event["data"]
    assert "end_time" in event["data"]
    assert "timestamp" in event


def test_emit_atomic_write(monkeypatch, tmp_path):
    """No .tmp_* files remain after a successful write."""
    _enable_tracing(monkeypatch, tmp_path)

    emit_trace_event(event_type="5_chunk", data={"chunk": "text"})

    buf_dir = tmp_path / "trace_buffer"
    tmp_files = list(buf_dir.glob(".tmp_*"))
    assert tmp_files == []


def test_emit_disabled(monkeypatch, tmp_path):
    """When LANGFUSE_ENABLED=false, emit returns False and writes no files."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setattr(tb, "TRACE_BUFFER_DIR", tmp_path / "trace_buffer")
    monkeypatch.setattr(tb, "_buffer_size_bytes", -1)

    result = emit_trace_event(event_type="7_store", data={"key": "val"})

    assert result is False
    buf_dir = tmp_path / "trace_buffer"
    assert not buf_dir.exists() or list(buf_dir.glob("*.json")) == []


def test_emit_includes_project_id(monkeypatch, tmp_path):
    """project_id from AI_MEMORY_PROJECT_ID env var appears in emitted event."""
    _enable_tracing(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_MEMORY_PROJECT_ID", "proj-test-123")

    emit_trace_event(event_type="1_capture", data={})

    buf_dir = tmp_path / "trace_buffer"
    files = list(buf_dir.glob("*.json"))
    assert len(files) == 1

    event = json.loads(files[0].read_text())
    assert event["project_id"] == "proj-test-123"


def test_buffer_overflow_guard(monkeypatch, tmp_path):
    """emit_trace_event returns False when buffer exceeds LANGFUSE_TRACE_BUFFER_MAX_MB."""
    _enable_tracing(monkeypatch, tmp_path)
    monkeypatch.setenv("LANGFUSE_TRACE_BUFFER_MAX_MB", "1")
    monkeypatch.setattr(tb, "BUFFER_MAX_MB", 1)

    # Simulate buffer already at limit (1 MB in bytes)
    monkeypatch.setattr(tb, "_buffer_size_bytes", 1 * 1024 * 1024)

    result = emit_trace_event(event_type="overflow_test", data={"x": "y"})

    assert result is False
    buf_dir = tmp_path / "trace_buffer"
    assert not buf_dir.exists() or list(buf_dir.glob("*.json")) == []


def test_emit_performance(monkeypatch, tmp_path):
    """Single emit_trace_event call completes in under 20ms."""
    _enable_tracing(monkeypatch, tmp_path)

    start = time.perf_counter()
    emit_trace_event(event_type="perf_test", data={"load": "minimal"})
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 10, f"emit took {elapsed_ms:.1f}ms, expected <10ms"
