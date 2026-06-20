"""Tests for the bounded at-exit Langfuse drain in the classification queue
processor (TD-698).

Covers:
- The drain cannot block past its external watchdog bound even when the Langfuse
  SDK ``flush()`` hangs (reachable-but-slow backend).
- ``atexit`` registration honors the app-level enabled flag (the registration
  lives in the ``is_langfuse_enabled()`` branch, so it is skipped when off).
"""

import atexit as _atexit
import importlib
import sys
import threading
import time
import types

import scripts.memory.process_classification_queue as pcq


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
    release = threading.Event()
    client = _HangingClient(release)
    _install_fake_langfuse(monkeypatch, client)
    monkeypatch.setattr(pcq, "_LANGFUSE_SHUTDOWN_TIMEOUT_SECONDS", 0.3)

    try:
        start = time.monotonic()
        pcq._langfuse_shutdown()
        elapsed = time.monotonic() - start

        assert client.flush_started.wait(1.0)
        assert elapsed < 5.0
        assert elapsed >= 0.25
    finally:
        release.set()


def test_registration_honors_enabled_flag(monkeypatch):
    """atexit registration is skipped when disabled, performed when enabled."""
    registered: list[str] = []
    monkeypatch.setattr(
        _atexit,
        "register",
        lambda fn, *a, **k: registered.append(getattr(fn, "__name__", "")),
    )

    try:
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        importlib.reload(pcq)
        assert "_langfuse_shutdown" not in registered

        registered.clear()
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        importlib.reload(pcq)
        assert "_langfuse_shutdown" in registered
    finally:
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        importlib.reload(pcq)
