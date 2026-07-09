"""Unit tests for TD-777: bounded gRPC-readiness preflight in the retry-drain daemon.

Tests:
- Preflight retries the gRPC probe on failure, then proceeds once it succeeds.
- Preflight bounds out past its attempt budget WITHOUT raising/crashing.
- Preflight never poisons get_qdrant_client's module-level client cache.
- run_scheduler() invokes the preflight before the first process_queue() call.
"""

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Module loader helper (mirrors test_evaluator_scheduler.py)
# ---------------------------------------------------------------------------

_SCHEDULER_PATH = (
    Path(__file__).parent.parent.parent / "scripts/memory/retry_drain_scheduler.py"
)


def _load_scheduler():
    """Load retry_drain_scheduler module via importlib (not on sys.path as a package)."""
    spec = importlib.util.spec_from_file_location(
        "retry_drain_scheduler", _SCHEDULER_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_config():
    """Build a MagicMock MemoryConfig with just the fields _wait_for_grpc_ready reads."""
    cfg = MagicMock()
    cfg.qdrant_host = "qdrant"
    cfg.qdrant_port = 26350
    cfg.qdrant_use_https = False
    cfg.qdrant_timeout = 5
    cfg.qdrant_api_key = None
    return cfg


# ---------------------------------------------------------------------------
# Test: _wait_for_grpc_ready retry + bounded-out behavior
# ---------------------------------------------------------------------------


class TestGrpcPreflightRetry:
    def test_retries_then_succeeds(self, monkeypatch):
        """Probe fails twice then succeeds — preflight retries and proceeds."""
        mod = _load_scheduler()
        mod._shutdown_requested = False
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_MAX_ATTEMPTS", "5")
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_SLEEP_SECONDS", "1")

        call_count = [0]
        succeed_client = MagicMock()

        def fake_qdrant_client(**kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("grpc not ready")
            return succeed_client

        with (
            patch.object(mod, "QdrantClient", side_effect=fake_qdrant_client),
            patch.object(mod, "get_config", return_value=_make_config()),
            patch.object(mod, "time") as mock_time,
        ):
            mod._wait_for_grpc_ready()

        assert call_count[0] == 3
        succeed_client.get_collections.assert_called_once()
        # Slept after attempt 1 and attempt 2 (both failures); no sleep after success.
        assert mock_time.sleep.call_count == 2

    def test_budget_exhausted_falls_through_without_raising(self, monkeypatch):
        """Probe fails on every attempt — preflight bounds out and does NOT raise."""
        mod = _load_scheduler()
        mod._shutdown_requested = False
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_MAX_ATTEMPTS", "3")
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_SLEEP_SECONDS", "1")

        def always_fail(**kwargs):
            raise ConnectionError("grpc never ready")

        with (
            patch.object(mod, "QdrantClient", side_effect=always_fail),
            patch.object(mod, "get_config", return_value=_make_config()),
            patch.object(mod, "time") as mock_time,
        ):
            # Must not raise — daemon falls through to normal operation.
            mod._wait_for_grpc_ready()

        # 3 attempts total; sleeps between attempt 1->2 and 2->3, none after the last.
        assert mock_time.sleep.call_count == 2

    def test_preflight_never_poisons_client_cache(self, monkeypatch):
        """The preflight probes with a THROWAWAY client — get_qdrant_client's
        module-level cache must remain untouched regardless of outcome."""
        from memory import qdrant_client as qc_module

        mod = _load_scheduler()
        mod._shutdown_requested = False
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_MAX_ATTEMPTS", "2")
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_SLEEP_SECONDS", "1")

        qc_module._client_cache.clear()

        def always_fail(**kwargs):
            raise ConnectionError("grpc never ready")

        with (
            patch.object(mod, "QdrantClient", side_effect=always_fail),
            patch.object(mod, "get_config", return_value=_make_config()),
            patch.object(mod, "time"),
        ):
            mod._wait_for_grpc_ready()

        assert qc_module._client_cache == {}

    def test_shutdown_during_preflight_aborts_promptly(self, monkeypatch):
        """Shutdown requested while the probe loop is failing — the preflight
        must return promptly instead of draining the full attempt budget."""
        mod = _load_scheduler()
        mod._shutdown_requested = True
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_MAX_ATTEMPTS", "30")
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_SLEEP_SECONDS", "1")

        call_count = [0]

        def always_fail(**kwargs):
            call_count[0] += 1
            raise ConnectionError("grpc not ready")

        with (
            patch.object(mod, "QdrantClient", side_effect=always_fail),
            patch.object(mod, "get_config", return_value=_make_config()),
            patch.object(mod, "time") as mock_time,
        ):
            mod._wait_for_grpc_ready()

        # Bounded to a single probe attempt, not the full 30-attempt budget.
        assert call_count[0] == 1
        mock_time.sleep.assert_not_called()

    def test_config_error_falls_through_without_raising(self, monkeypatch):
        """get_config() raising must not crash the daemon — the preflight
        logs a warning and returns."""
        mod = _load_scheduler()
        mod._shutdown_requested = False
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_MAX_ATTEMPTS", "5")
        monkeypatch.setenv("RETRY_DRAIN_GRPC_PREFLIGHT_SLEEP_SECONDS", "1")

        def broken_config():
            raise ValueError("bad qdrant config")

        with (
            patch.object(mod, "QdrantClient") as mock_client,
            patch.object(mod, "get_config", side_effect=broken_config),
        ):
            # Must not raise — daemon falls through to normal operation.
            mod._wait_for_grpc_ready()

        mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# Test: run_scheduler() calls the preflight before the first process_queue()
# ---------------------------------------------------------------------------


class TestRunSchedulerPreflightOrdering:
    def test_preflight_runs_before_first_process_queue(self):
        mod = _load_scheduler()
        mod._shutdown_requested = False

        call_order = []

        def fake_preflight():
            call_order.append("preflight")

        def fake_process_queue(limit):
            call_order.append("process_queue")
            return {"processed": 0, "success": 0, "failed": 0, "moved_to_dlq": 0}

        def fake_sleep(seconds, chunk=5.0):
            # Shut down after the first cycle so the loop exits.
            mod._shutdown_requested = True

        @contextmanager
        def fake_drain_lock():
            yield True

        with (
            patch.object(mod, "_wait_for_grpc_ready", side_effect=fake_preflight),
            patch.object(mod, "process_queue", side_effect=fake_process_queue),
            patch.object(mod, "drain_lock", fake_drain_lock),
            patch.object(mod, "_interruptible_sleep", side_effect=fake_sleep),
            patch.object(mod, "_touch_health_file"),
        ):
            mod.run_scheduler()

        assert call_order == ["preflight", "process_queue"]
