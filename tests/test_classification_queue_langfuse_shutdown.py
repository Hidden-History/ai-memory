"""Tests for the bounded at-exit Langfuse drain in the classification queue
processor (TD-698).

Covers:
- The drain cannot block past its external watchdog bound even when the Langfuse
  SDK ``flush()`` hangs (reachable-but-slow backend).
- ``atexit`` registration honors the app-level enabled flag (skipped when off).

The processor module is imported lazily inside each test (mirroring
``test_classification_worker``) so collecting this file never triggers its
module-level Prometheus metric registration.
"""

import atexit as _atexit
import sys
import threading
import time
import types


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
    import scripts.memory.process_classification_queue as pcq

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


def test_registration_skipped_when_disabled(monkeypatch):
    """With the app-level flag off, the at-exit handler is never registered."""
    import scripts.memory.process_classification_queue as pcq

    registered: list[str] = []
    monkeypatch.setattr(
        _atexit,
        "register",
        lambda fn, *a, **k: registered.append(getattr(fn, "__name__", "")),
    )
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")

    pcq._register_langfuse_shutdown()

    assert "_langfuse_shutdown" not in registered


def test_registration_performed_when_enabled(monkeypatch):
    """With the app-level flag on, the bounded handler is registered."""
    import scripts.memory.process_classification_queue as pcq

    registered: list[str] = []
    monkeypatch.setattr(
        _atexit,
        "register",
        lambda fn, *a, **k: registered.append(getattr(fn, "__name__", "")),
    )
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")

    pcq._register_langfuse_shutdown()

    assert "_langfuse_shutdown" in registered
