"""Tests for the at-exit Langfuse drain in the Jira sync connector (TD-625).

Covers:
- The drain cannot block past its external watchdog bound even when the
  Langfuse SDK ``flush()`` hangs (reachable-but-slow backend).
- The drain is skipped entirely when Langfuse is disabled at the app level.
- ``atexit`` registration honors the app-level enabled flag.
"""

import atexit as _atexit
import importlib
import threading
import time
from unittest.mock import Mock

from src.memory.connectors.jira import sync


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
    """The watchdog bound must abandon a hanging flush instead of wedging."""
    release = threading.Event()
    client = _HangingClient(release)
    monkeypatch.setattr(sync, "_langfuse_get_client", lambda: client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: True)
    monkeypatch.setattr(sync, "_LANGFUSE_SHUTDOWN_TIMEOUT_SECONDS", 0.3)

    try:
        start = time.monotonic()
        sync._langfuse_shutdown()
        elapsed = time.monotonic() - start

        # The drain actually ran (flush was entered) ...
        assert client.flush_started.wait(1.0)
        # ... but returned bounded by the watchdog (~2x the patched 0.3s bound),
        # not on the infinite flush.
        assert elapsed < 0.6
        # ... and it honored the external bound rather than returning instantly.
        assert elapsed >= 0.25
    finally:
        # Release the abandoned daemon thread so it can finish cleanly.
        release.set()


def test_shutdown_flushes_and_shuts_down_on_normal_path(monkeypatch):
    """On the normal path (enabled + healthy client) the drain must call BOTH
    flush() and shutdown() exactly once — a no-op'd flush would otherwise pass
    every other test in this module."""
    client = Mock()
    monkeypatch.setattr(sync, "_langfuse_get_client", lambda: client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: True)

    sync._langfuse_shutdown()

    client.flush.assert_called_once()
    client.shutdown.assert_called_once()


def test_shutdown_skips_drain_when_disabled(monkeypatch):
    """With the app-level flag off, the client is never even retrieved."""
    get_client = Mock()
    monkeypatch.setattr(sync, "_langfuse_get_client", get_client)
    monkeypatch.setattr(sync, "_langfuse_enabled", lambda: False)

    sync._langfuse_shutdown()

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
        # langfuse is a hard project dependency, so _langfuse_get_client is always
        # importable and the registration must occur unconditionally.
        assert "_langfuse_shutdown" in registered
    finally:
        # Restore a consistently initialized module for any later importers.
        importlib.reload(sync)
