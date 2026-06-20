"""Tests for the bounded at-exit Langfuse drain in the evaluator scheduler (TD-698).

Covers:
- The drain cannot block past its external watchdog bound even when the Langfuse
  SDK ``flush()`` hangs (reachable-but-slow backend).
- ``atexit`` registration honors the app-level enabled flag (skipped when off).
"""

import atexit as _atexit
import importlib.util
import sys
import threading
import time
import types
from pathlib import Path

_SCHEDULER_PATH = (
    Path(__file__).parent.parent.parent / "scripts/memory/evaluator_scheduler.py"
)


def _load_scheduler():
    """Load evaluator_scheduler module via importlib (not on sys.path as a package)."""
    spec = importlib.util.spec_from_file_location(
        "evaluator_scheduler", _SCHEDULER_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _HangingClient:
    """Fake Langfuse client whose flush() blocks until explicitly released."""

    def __init__(self, release: threading.Event):
        self._release = release
        self.flush_started = threading.Event()

    def flush(self):
        self.flush_started.set()
        self._release.wait()

    def shutdown(self):
        pass


def _install_fake_langfuse(monkeypatch, client):
    fake = types.ModuleType("langfuse")
    fake.get_client = lambda: client
    monkeypatch.setitem(sys.modules, "langfuse", fake)


def test_shutdown_does_not_block_when_flush_hangs(monkeypatch):
    """The watchdog bound must abandon a hanging flush instead of wedging."""
    sched = _load_scheduler()
    release = threading.Event()
    client = _HangingClient(release)
    _install_fake_langfuse(monkeypatch, client)
    monkeypatch.setattr(sched, "_LANGFUSE_SHUTDOWN_TIMEOUT_SECONDS", 0.3)

    try:
        start = time.monotonic()
        sched._langfuse_shutdown()
        elapsed = time.monotonic() - start

        assert client.flush_started.wait(1.0)
        assert elapsed < 5.0
        assert elapsed >= 0.15
    finally:
        release.set()


def test_registration_skipped_when_disabled(monkeypatch):
    """With the app-level flag off, the at-exit handler is never registered."""
    sched = _load_scheduler()
    registered: list[str] = []
    monkeypatch.setattr(
        _atexit,
        "register",
        lambda fn, *a, **k: registered.append(getattr(fn, "__name__", "")),
    )
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")

    sched._register_langfuse_shutdown()

    assert "_langfuse_shutdown" not in registered


def test_registration_performed_when_enabled(monkeypatch):
    """With the app-level flag on, the bounded handler is registered."""
    sched = _load_scheduler()
    registered: list[str] = []
    monkeypatch.setattr(
        _atexit,
        "register",
        lambda fn, *a, **k: registered.append(getattr(fn, "__name__", "")),
    )
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")

    sched._register_langfuse_shutdown()

    assert "_langfuse_shutdown" in registered
