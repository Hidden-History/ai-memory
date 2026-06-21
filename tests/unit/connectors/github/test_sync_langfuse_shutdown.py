"""Tests for the bounded Langfuse drains in the GitHub sync engine (TD-698).

Covers:
- The at-exit drain cannot block past its external watchdog bound even when the
  Langfuse SDK ``flush()`` hangs (reachable-but-slow backend).
- The post-sync-cycle inline flush is bounded the same way.
- Both drains are skipped entirely when Langfuse is disabled at the app level.
- ``atexit`` registration honors the app-level enabled flag.
"""

import atexit as _atexit
import importlib
import threading
import time
from unittest.mock import Mock

from memory.connectors.github import sync


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


def test_shutdown_does_not_block_when_flush_hangs(monkeypatch):
    """The watchdog bound must abandon a hanging at-exit flush, not wedge."""
    release = threading.Event()
    client = _HangingClient(release)
    monkeypatch.setattr(sync, "_langfuse_get_client", lambda: client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: True)
    monkeypatch.setattr(sync, "_LANGFUSE_SHUTDOWN_TIMEOUT_SECONDS", 0.3)

    try:
        start = time.monotonic()
        sync._langfuse_shutdown()
        elapsed = time.monotonic() - start

        assert client.flush_started.wait(1.0)
        assert elapsed < 5.0
        assert elapsed >= 0.15
    finally:
        release.set()


def test_bounded_flush_does_not_block_when_flush_hangs(monkeypatch):
    """The post-sync-cycle inline flush must honor the same external bound."""
    release = threading.Event()
    client = _HangingClient(release)
    monkeypatch.setattr(sync, "_langfuse_get_client", lambda: client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: True)
    monkeypatch.setattr(sync, "_LANGFUSE_SHUTDOWN_TIMEOUT_SECONDS", 0.3)

    try:
        start = time.monotonic()
        sync._bounded_langfuse_flush()
        elapsed = time.monotonic() - start

        assert client.flush_started.wait(1.0)
        assert elapsed < 5.0
        assert elapsed >= 0.15
    finally:
        release.set()


def test_shutdown_skips_drain_when_disabled(monkeypatch):
    """With the app-level flag off, the client is never even retrieved."""
    get_client = Mock()
    monkeypatch.setattr(sync, "_langfuse_get_client", get_client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: False)

    sync._langfuse_shutdown()

    get_client.assert_not_called()


def test_bounded_flush_skips_when_disabled(monkeypatch):
    """The inline flush is also skipped when Langfuse is disabled."""
    get_client = Mock()
    monkeypatch.setattr(sync, "_langfuse_get_client", get_client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: False)

    sync._bounded_langfuse_flush()

    get_client.assert_not_called()


def test_registration_honors_enabled_flag(monkeypatch):
    """atexit registration is skipped when disabled, performed when enabled."""
    registered: list[str] = []
    monkeypatch.setattr(
        _atexit,
        "register",
        lambda fn, *a, **k: (registered.append(getattr(fn, "__name__", "")), fn)[1],
    )

    try:
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        importlib.reload(sync)
        assert "_langfuse_shutdown" not in registered

        registered.clear()
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        importlib.reload(sync)
        if sync._langfuse_get_client is not None:
            assert "_langfuse_shutdown" in registered
    finally:
        importlib.reload(sync)
