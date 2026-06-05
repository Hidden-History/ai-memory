"""TD-612 adversarial isolation tests — a leaked flush-watchdog daemon's real
os._exit must never kill the test runner.

These exercise the session-wide guard in tests/conftest.py
(_neutralize_and_join_flush_watchdog): even a watchdog bound to a superseded,
re-imported module object — the TD-612 root cause — resolves os._exit to the
shared recorder and so cannot terminate the process. Under -p no:randomly the
module keeps its definition order, so the second test demonstrates that a
subsequent test survives a prior leak.
"""

import sys
import threading
import time


def _import_worker(monkeypatch, tmp_path):
    """Import a fresh memory.trace_flush_worker bound to an isolated buffer dir."""
    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    monkeypatch.setenv("LANGFUSE_FLUSH_INTERVAL", "0")
    for key in list(sys.modules):
        if "trace_flush_worker" in key:
            del sys.modules[key]

    import memory.trace_flush_worker as mod

    return mod


def _arm_stalled_watchdog(mod):
    """Configure a worker module so its watchdog trips its stall deadline at once."""
    mod.STALL_DEADLINE_SECONDS = 0.1
    mod.shutdown_requested = False
    mod._last_loop_progress = time.monotonic() - 5  # already past the deadline


def _stop_watchdog(mod, thread):
    """Signal shutdown on the daemon's own module object and join it."""
    mod.shutdown_requested = True
    mod._watchdog_wakeup.set()
    thread.join(timeout=5)


def _wait_for_exit_capture(exit_calls, timeout=3.0):
    """Wait until the neutralized os._exit(1) is recorded (or time out)."""
    deadline = time.time() + timeout
    while 1 not in exit_calls and time.time() < deadline:
        time.sleep(0.02)


def test_stale_bound_watchdog_real_exit_is_neutralized(
    tmp_path, monkeypatch, _neutralize_and_join_flush_watchdog
):
    """Root-cause reproduction: a watchdog bound to a re-imported (stale) module
    object fires the real os._exit on its stall deadline; the guard must capture it
    instead of letting it hard-kill the runner."""
    exit_calls = _neutralize_and_join_flush_watchdog

    mod1 = _import_worker(monkeypatch, tmp_path)
    _arm_stalled_watchdog(mod1)
    # Do NOT patch os._exit here — the watchdog must reach the conftest recorder.
    watchdog = threading.Thread(
        target=mod1._watchdog_loop, name="flush-watchdog", daemon=True
    )
    watchdog.start()

    # Re-import the module (as _load_module does between tests) so the live daemon is
    # now bound to a superseded module object — the exact TD-612 escape that a
    # module-scoped guard could not signal.
    _import_worker(monkeypatch, tmp_path)

    # The stale-bound daemon trips its 0.1s deadline and calls the real os._exit; the
    # process must survive (we keep executing) and the recorder must have caught it.
    _wait_for_exit_capture(exit_calls)
    assert (
        1 in exit_calls
    ), "neutralized os._exit(1) from a stale-bound watchdog was not captured"

    _stop_watchdog(mod1, watchdog)
    assert not watchdog.is_alive()


def test_following_test_survives_prior_leak(
    tmp_path, monkeypatch, _neutralize_and_join_flush_watchdog
):
    """The next test (definition order under -p no:randomly) runs to completion: its
    own armed watchdog fires past the deadline into the recorder, and the parent
    process survives."""
    exit_calls = _neutralize_and_join_flush_watchdog

    mod = _import_worker(monkeypatch, tmp_path)
    _arm_stalled_watchdog(mod)
    watchdog = threading.Thread(
        target=mod._watchdog_loop, name="flush-watchdog", daemon=True
    )
    watchdog.start()

    time.sleep(0.4)  # sleep past the 0.1s deadline; the watchdog fires meanwhile
    assert 1 in exit_calls, "watchdog exit not neutralized in the following test"

    _stop_watchdog(mod, watchdog)
    assert not watchdog.is_alive()
