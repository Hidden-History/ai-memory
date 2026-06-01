"""Unit tests for memory.trace_flush_worker — SPEC-020 §9.1 + BUG-315 / BP-169 (P4 L1)."""

import contextlib
import hashlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch


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
    mock_langfuse.start_observation.return_value = mock_span
    mock_propagate = MagicMock()
    monkeypatch.setattr(mod, "_langfuse_propagate_attributes", mock_propagate)

    processed, errors = mod.process_buffer_files(mock_langfuse)

    assert processed == 1
    assert errors == 0
    mock_langfuse.start_observation.assert_called_once()
    # V4: trace attrs set via propagate_attributes, not update_trace
    mock_propagate.assert_called_once()
    mock_span.update_trace.assert_not_called()
    mock_span.end.assert_called_once()
    # V2 methods must NOT be called (regression guard)
    mock_langfuse.start_span.assert_not_called()
    mock_langfuse.start_generation.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — processed files are deleted
# ---------------------------------------------------------------------------


def test_removes_processed_files(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    path = _write_event(buffer_dir, "evt_del")

    mock_langfuse = MagicMock()
    mock_langfuse.start_observation.return_value = MagicMock()

    mod.process_buffer_files(mock_langfuse)

    assert not path.exists(), "Processed file should be deleted"
    # V2 methods must NOT be called (regression guard)
    mock_langfuse.start_span.assert_not_called()
    mock_langfuse.start_generation.assert_not_called()


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
    mock_langfuse.start_observation.return_value = MagicMock()

    mock_push = MagicMock()
    monkeypatch.setattr(mod, "push_metrics_fn", mock_push)
    # Backend reachable so the drain path runs (preflight gate, BUG-315).
    monkeypatch.setattr(mod, "_backend_reachable", lambda: True)

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
    # V2 methods must NOT be called (regression guard)
    mock_langfuse.start_span.assert_not_called()
    mock_langfuse.start_generation.assert_not_called()


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


# ===========================================================================
# BUG-315 (PLAN-028 P4 L1) — wedge fix: bounded batch, heartbeat decoupling,
# backend preflight, stall watchdog, loss-safe drain.
# ===========================================================================


def _write_agent_event(buffer_dir: Path, name: str, **data_extra) -> Path:
    """Write a buffer event whose data.metadata carries agent identity/role."""
    hex_id = hashlib.md5(name.encode()).hexdigest()
    data = {
        "start_time": "2026-02-23T10:00:00+00:00",
        "end_time": "2026-02-23T10:00:01+00:00",
        "input": "i",
        "output": "o",
        "metadata": {"agent_name": "dev-w1", "agent_role": "worker"},
    }
    data.update(data_extra)
    event = {
        "event_type": "1_capture",
        "trace_id": hex_id,
        "span_id": hex_id[:16],
        "parent_span_id": None,
        "session_id": "sess001",
        "project_id": "test-project",
        "data": data,
    }
    path = buffer_dir / f"{name}.json"
    path.write_text(json.dumps(event))
    return path


# --- R1(b): heartbeat decoupled from a blocking flush (the BUG-315 regression) --


def test_bug315_heartbeat_refreshed_despite_blocking_flush(tmp_path, monkeypatch):
    """Realistic-size repro: heartbeat must refresh even while flush() blocks.

    Pre-fix the heartbeat was touched AFTER the flush, so a flush that blocked on
    an unreachable backend left the heartbeat stale and wedged the loop. The fix
    touches the heartbeat at the top of the loop (decoupled from flush).
    """
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 1000)
    # Realistic backlog (not a 3-file synthetic).
    for i in range(600):
        _write_agent_event(buffer_dir, f"evt{i}")

    blocked = threading.Event()
    fake = MagicMock()
    fake.start_observation.return_value = MagicMock()
    # Models flush() blocking on an unreachable backend (never throws).
    fake.flush.side_effect = lambda: blocked.wait(timeout=30)

    monkeypatch.setattr(mod, "shutdown_requested", False)
    monkeypatch.setattr(mod, "_langfuse_propagate_attributes", MagicMock())
    monkeypatch.setattr(mod, "_backend_reachable", lambda: True)

    hb = mod.HEARTBEAT_FILE
    with patch.object(mod, "get_langfuse_client", return_value=fake):
        t = threading.Thread(target=mod.main, daemon=True)
        t.start()
        try:
            # Heartbeat must appear quickly even though flush is blocking.
            deadline = time.time() + 5
            while not hb.exists() and time.time() < deadline:
                time.sleep(0.05)
            assert hb.exists(), "Heartbeat must refresh while flush blocks (decoupled)"
        finally:
            mod.shutdown_requested = True
            blocked.set()
            t.join(timeout=5)


# --- R1(a): bounded batch per pass --------------------------------------------


def test_process_buffer_files_bounded_batch(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    for i in range(5):
        _write_event(buffer_dir, f"b{i}")

    mock_langfuse = MagicMock()
    mock_langfuse.start_observation.return_value = MagicMock()

    processed, errors = mod.process_buffer_files(mock_langfuse, limit=2)

    assert processed == 2
    assert errors == 0
    assert len(list(buffer_dir.glob("*.json"))) == 3  # remainder left for next pass


# --- R1(e): loss-safe drain — flush before unlink -----------------------------


def test_process_buffer_files_flushes_before_unlink(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    path = _write_event(buffer_dir, "lossafe")

    seen = {}
    mock_langfuse = MagicMock()
    mock_langfuse.start_observation.return_value = MagicMock()

    def flush_side_effect():
        seen["file_exists_at_flush"] = path.exists()

    mock_langfuse.flush.side_effect = flush_side_effect

    processed, _ = mod.process_buffer_files(mock_langfuse)

    assert processed == 1
    mock_langfuse.flush.assert_called_once()
    assert seen["file_exists_at_flush"] is True  # not yet unlinked when flush ran
    assert not path.exists()  # removed only after flush confirmed enqueue


def test_process_buffer_files_retains_files_when_flush_raises(tmp_path, monkeypatch):
    """F-5: if flush() raises (theoretical per BP-168), files are retained, not dropped."""
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    path = _write_event(buffer_dir, "flush_raises")

    mock_langfuse = MagicMock()
    mock_langfuse.start_observation.return_value = MagicMock()
    mock_langfuse.flush.side_effect = RuntimeError("flush blew up")

    processed, _ = mod.process_buffer_files(mock_langfuse)

    assert processed == 0
    assert (
        path.exists()
    ), "File must be retained for retry when flush raises (loss-safe)"


# --- R1(c): backend preflight (HTTP /api/public/health probe) -----------------


class _FakeHealthResp:
    """Minimal context-manager stand-in for urllib's urlopen response."""

    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_backend_reachable_true_on_200(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda *a, **k: _FakeHealthResp(200)
    )
    assert mod._backend_reachable() is True


def test_backend_reachable_false_on_non_200(tmp_path, monkeypatch):
    """A TCP-up-but-app-hung backend answers non-200 → treated as unreachable."""
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(
        mod.urllib.request, "urlopen", lambda *a, **k: _FakeHealthResp(503)
    )
    assert mod._backend_reachable() is False


def test_backend_reachable_false_on_urlerror(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise mod.urllib.error.URLError("connection refused")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    assert mod._backend_reachable() is False


def test_backend_reachable_false_on_empty_url(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "LANGFUSE_BASE_URL", "")
    assert mod._backend_reachable() is False


def test_preflight_skips_drain_when_unreachable(tmp_path, monkeypatch):
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    _write_event(buffer_dir, "pf1")

    monkeypatch.setattr(mod, "_backend_reachable", lambda: False)
    monkeypatch.setattr(mod, "shutdown_requested", False)

    called = []

    def fake_process(*a, **k):
        called.append(1)
        return (0, 0)

    monkeypatch.setattr(mod, "process_buffer_files", fake_process)

    def stop(_):
        mod.shutdown_requested = True

    with (
        patch.object(mod, "get_langfuse_client", return_value=MagicMock()),
        patch("time.sleep", side_effect=stop),
    ):
        mod.main()

    assert called == [], "Drain must be skipped when backend is unreachable"
    assert mod.HEARTBEAT_FILE.exists(), "Heartbeat must still refresh during outage"


# --- R1(d): stall watchdog ----------------------------------------------------


def test_is_stalled(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    now = 10_000.0
    assert mod._is_stalled(now - mod.STALL_DEADLINE_SECONDS - 1, now) is True
    assert mod._is_stalled(now - 1, now) is False


def test_watchdog_exits_when_stalled(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "shutdown_requested", False)
    mod._last_loop_progress = time.monotonic() - (mod.STALL_DEADLINE_SECONDS + 5)

    calls = []

    def fake_exit(code):
        calls.append(code)
        mod.shutdown_requested = True  # break the watchdog loop
        mod._watchdog_wakeup.set()

    monkeypatch.setattr(mod.os, "_exit", fake_exit)
    mod._watchdog_loop()

    assert calls == [1], "Watchdog must hard-exit(1) on a wedged loop"


def test_watchdog_does_not_exit_when_progressing(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "shutdown_requested", False)
    mod._last_loop_progress = time.monotonic()  # fresh progress

    calls = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: calls.append(code))

    # Run the watchdog briefly then stop it.
    t = threading.Thread(target=mod._watchdog_loop, daemon=True)
    t.start()
    time.sleep(0.2)
    mod.shutdown_requested = True
    mod._watchdog_wakeup.set()
    t.join(timeout=2)

    assert calls == [], "Watchdog must not exit while the loop is progressing"


# --- F-1(a): watchdog-deadline configuration warning -------------------------


def test_stall_deadline_warning_fires_on_large_batch_default_deadline(
    tmp_path, monkeypatch
):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.delenv("LANGFUSE_STALL_DEADLINE_SECONDS", raising=False)
    monkeypatch.setattr(mod, "FLUSH_BATCH_MAX", mod._DEFAULT_FLUSH_BATCH_MAX * 10)
    assert mod._stall_deadline_warning() is not None


def test_stall_deadline_no_warning_when_deadline_explicitly_set(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setenv("LANGFUSE_STALL_DEADLINE_SECONDS", "3600")
    monkeypatch.setattr(mod, "FLUSH_BATCH_MAX", mod._DEFAULT_FLUSH_BATCH_MAX * 10)
    assert mod._stall_deadline_warning() is None


def test_stall_deadline_no_warning_at_default_batch(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.delenv("LANGFUSE_STALL_DEADLINE_SECONDS", raising=False)
    monkeypatch.setattr(mod, "FLUSH_BATCH_MAX", mod._DEFAULT_FLUSH_BATCH_MAX)
    assert mod._stall_deadline_warning() is None


# --- F-4: watchdog x slow-but-progressing bounded drain through real main() ---


def test_bug315_watchdog_survives_slow_progressing_multibatch_drain(
    tmp_path, monkeypatch
):
    """F-1 x F-4: a slow-but-progressing drain over MANY bounded batches, run through
    the real main()/process_buffer_files path with the live watchdog, must NOT trip
    the stall watchdog. The watchdog kills only a zero-progress wedge; each bounded
    batch advances _last_loop_progress, so a deadline sized for one bounded batch is
    independent of the total backlog size (scale-independence)."""
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 1000)
    # Force a small batch so the backlog drains over MANY main() iterations (real
    # process_buffer_files logic runs; only the per-pass cap is pinned for the test).
    real_process = mod.process_buffer_files
    monkeypatch.setattr(
        mod, "process_buffer_files", lambda lf, limit=5: real_process(lf, limit)
    )
    # Deadline comfortably larger than one bounded-batch flush; the WHOLE drain takes
    # longer, proving progress (not total time) is what the watchdog measures.
    monkeypatch.setattr(mod, "STALL_DEADLINE_SECONDS", 2.0)
    for i in range(40):
        _write_agent_event(buffer_dir, f"evt{i}")

    fake = MagicMock()
    fake.start_observation.return_value = MagicMock()
    # Slow-but-progressing: each bounded batch's flush blocks briefly, then returns.
    fake.flush.side_effect = lambda: time.sleep(0.02)

    monkeypatch.setattr(mod, "shutdown_requested", False)
    monkeypatch.setattr(mod, "_langfuse_propagate_attributes", MagicMock())
    monkeypatch.setattr(mod, "_backend_reachable", lambda: True)

    exits = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))

    with patch.object(mod, "get_langfuse_client", return_value=fake):
        t = threading.Thread(target=mod.main, daemon=True)
        t.start()
        try:
            deadline = time.time() + 8
            while time.time() < deadline and list(buffer_dir.glob("*.json")):
                time.sleep(0.05)
        finally:
            mod.shutdown_requested = True
            mod._watchdog_wakeup.set()
            t.join(timeout=5)

    assert list(buffer_dir.glob("*.json")) == [], "Backlog must fully drain"
    assert exits == [], "Watchdog must not hard-exit a slow-but-progressing drain"


# --- F-7: graceful shutdown drains multiple batches until empty (bounded) -----


def test_shutdown_drains_multiple_batches_within_budget(tmp_path, monkeypatch):
    """F-7: graceful shutdown drains MORE than one batch (until empty or time budget),
    not just a single FLUSH_BATCH_MAX batch."""
    mod, buffer_dir = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "MAX_BUFFER_MB", 1000)
    real_process = mod.process_buffer_files
    monkeypatch.setattr(
        mod, "process_buffer_files", lambda lf, limit=5: real_process(lf, limit)
    )
    monkeypatch.setattr(mod, "SHUTDOWN_DRAIN_SECONDS", 5.0)
    monkeypatch.setattr(mod, "_backend_reachable", lambda: True)
    monkeypatch.setattr(mod, "_langfuse_propagate_attributes", MagicMock())
    monkeypatch.setattr(mod, "shutdown_requested", False)

    exits = []
    monkeypatch.setattr(mod.os, "_exit", lambda code: exits.append(code))

    for i in range(12):
        _write_event(buffer_dir, f"sd{i}")

    fake = MagicMock()
    fake.start_observation.return_value = MagicMock()

    # Stop the main loop on its first sleep; the shutdown drain then empties the rest.
    def stop(_):
        mod.shutdown_requested = True

    with (
        patch.object(mod, "get_langfuse_client", return_value=fake),
        patch("time.sleep", side_effect=stop),
    ):
        mod.main()

    assert (
        list(buffer_dir.glob("*.json")) == []
    ), "Shutdown must drain all batches within the time budget"
    assert exits == []


# --- G1/G2/G3: identity, role, agent-graph type (BP-169) ----------------------


def test_resolve_user_id_and_role():
    from memory.trace_flush_worker import _resolve_role_tag, _resolve_user_id

    assert _resolve_user_id({"agent_name": "parzival"}) == "agent:parzival"
    assert _resolve_user_id({}) == "system:unknown"
    assert _resolve_role_tag({"agent_role": "worker"}) == "role:worker"
    assert _resolve_role_tag({}) is None


def test_sdk_path_emits_agent_identity_role_and_type(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)  # OTEL_AVAILABLE False

    captured = {}

    def fake_propagate(**kw):
        captured.update(kw)
        return contextlib.nullcontext()

    monkeypatch.setattr(mod, "_langfuse_propagate_attributes", fake_propagate)

    mock_langfuse = MagicMock()
    mock_langfuse.start_observation.return_value = MagicMock()

    event = {
        "event_type": "orchestrate",
        "trace_id": "a" * 32,
        "parent_span_id": None,
        "session_id": "s",
        "project_id": "p",
        "as_type": "agent",
        "tags": ["pipeline"],
    }
    data = {
        "start_time": "2026-02-23T10:00:00+00:00",
        "end_time": "2026-02-23T10:00:01+00:00",
        "metadata": {"agent_name": "dev-w1", "agent_role": "worker"},
    }

    mod._process_event_sdk(event, data, mock_langfuse)

    # G1: identity
    assert captured["user_id"] == "agent:dev-w1"
    # G2: role in propagated metadata + tag
    assert captured["metadata"]["agent_role"] == "worker"
    assert "role:worker" in captured["tags"]
    assert "pipeline" in captured["tags"]
    # G3: agent type passed through (not collapsed to span)
    assert mock_langfuse.start_observation.call_args.kwargs["as_type"] == "agent"


def test_sdk_path_identityless_event_uses_system_unknown(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)

    captured = {}

    def fake_propagate(**kw):
        captured.update(kw)
        return contextlib.nullcontext()

    monkeypatch.setattr(mod, "_langfuse_propagate_attributes", fake_propagate)
    mock_langfuse = MagicMock()
    mock_langfuse.start_observation.return_value = MagicMock()

    event = {
        "event_type": "1_capture",
        "trace_id": "b" * 32,
        "parent_span_id": None,
        "session_id": "s",
        "project_id": "p",
    }
    data = {
        "start_time": "2026-02-23T10:00:00+00:00",
        "end_time": "2026-02-23T10:00:01+00:00",
        "metadata": {},
    }

    mod._process_event_sdk(event, data, mock_langfuse)
    assert captured["user_id"] == "system:unknown"


def test_otel_path_emits_agent_identity_role_and_type(tmp_path, monkeypatch):
    mod, _ = _load_module(tmp_path, monkeypatch)
    monkeypatch.setattr(mod, "OTEL_AVAILABLE", True)

    fake_span = MagicMock()
    fake_tracer = MagicMock()
    fake_tracer.start_span.return_value = fake_span
    monkeypatch.setattr(mod.otel_trace_api, "get_tracer", lambda name: fake_tracer)
    monkeypatch.setattr(mod, "_make_parent_context", lambda *a, **k: None)

    event = {
        "event_type": "1_capture",
        "trace_id": "a" * 32,
        "parent_span_id": None,
        "session_id": "s",
        "project_id": "p",
        "as_type": "agent",
        "tags": ["pipeline"],
    }
    data = {
        "start_time": "2026-02-23T10:00:00+00:00",
        "end_time": "2026-02-23T10:00:01+00:00",
        "metadata": {"agent_name": "dev-w1", "agent_role": "worker"},
    }

    mod._process_event_otel(event, data)

    attrs = {c.args[0]: c.args[1] for c in fake_span.set_attribute.call_args_list}
    # G1: identity from buffer, not hardcoded "system"
    assert attrs["user.id"] == "agent:dev-w1"
    # G3: agent observation type triggers the graph view
    assert attrs["langfuse.observation.type"] == "agent"
    # G2: role tag + trace metadata
    assert "role:worker" in attrs["langfuse.trace.tags"]
    assert json.loads(attrs["langfuse.trace.metadata"])["agent_role"] == "worker"
