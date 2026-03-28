# Location: ai-memory/tests/unit/test_trace_flush_degraded.py
"""Unit tests for TD-206: trace_flush_worker degraded mode when Langfuse is unavailable."""

import contextlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_shutdown_flag():
    """Reset the module-level shutdown_requested flag after each test."""
    import memory.trace_flush_worker as tfw

    tfw.shutdown_requested = False
    yield
    tfw.shutdown_requested = False


class TestDegradedMode:
    """When get_langfuse_client() returns None, worker runs without sys.exit."""

    def _run_one_cycle(self, extra_patches=None):
        """Run main() for exactly one loop iteration then stop."""
        import memory.trace_flush_worker as tfw

        def set_shutdown(*_):
            tfw.shutdown_requested = True

        patches = {
            "memory.trace_flush_worker.get_langfuse_client": MagicMock(
                return_value=None
            ),
            "memory.trace_flush_worker.evict_oldest_traces": MagicMock(return_value=0),
            "memory.trace_flush_worker.process_buffer_files": MagicMock(
                return_value=(0, 0)
            ),
            "time.sleep": MagicMock(side_effect=set_shutdown),
        }
        if extra_patches:
            patches.update(extra_patches)

        with contextlib.ExitStack() as stack:
            mocks = {k: stack.enter_context(patch(k, v)) for k, v in patches.items()}
            tfw.main()

        return mocks

    def test_no_sys_exit_when_client_none(self):
        """main() must not call sys.exit when Langfuse client is unavailable."""
        with patch("sys.exit") as mock_exit:
            self._run_one_cycle()
        mock_exit.assert_not_called()

    def test_degraded_mode_calls_evict(self):
        """Eviction runs in degraded mode to prevent buffer disk overflow."""
        mocks = self._run_one_cycle()
        mocks["memory.trace_flush_worker.evict_oldest_traces"].assert_called()

    def test_degraded_mode_touches_heartbeat(self, tmp_path):
        """Heartbeat file is touched in degraded mode (Docker liveness probe must pass)."""
        import memory.trace_flush_worker as tfw

        heartbeat = tmp_path / ".heartbeat"
        original = tfw.HEARTBEAT_FILE
        tfw.HEARTBEAT_FILE = heartbeat
        try:
            self._run_one_cycle()
        finally:
            tfw.HEARTBEAT_FILE = original

        assert heartbeat.exists(), "Heartbeat must be touched even in degraded mode"

    def test_degraded_mode_skips_process_buffer(self):
        """process_buffer_files must NOT be called in degraded mode."""
        mocks = self._run_one_cycle()
        mocks["memory.trace_flush_worker.process_buffer_files"].assert_not_called()

    def test_degraded_mode_skips_langfuse_flush(self):
        """langfuse.flush() is never called in degraded mode (client is None)."""
        # If it were called, it would AttributeError on None — this verifies it isn't.
        mocks = self._run_one_cycle()
        # process_buffer_files not called → no flush path reached
        mocks["memory.trace_flush_worker.process_buffer_files"].assert_not_called()

    def test_degraded_mode_still_pushes_metrics(self):
        """M-1: Pushgateway metrics are pushed even in degraded mode.

        Evictions still occur and the buffer still grows when Langfuse is down;
        operator visibility must not go dark at exactly the wrong moment.
        """
        mock_push_fn = MagicMock()
        self._run_one_cycle(
            extra_patches={"memory.trace_flush_worker.push_metrics_fn": mock_push_fn}
        )
        mock_push_fn.assert_called_once()
        call_kwargs = mock_push_fn.call_args.kwargs
        # events_processed and flush_errors are 0 in degraded mode
        assert call_kwargs.get("events_processed", 0) == 0
        assert call_kwargs.get("flush_errors", 0) == 0

    def test_normal_mode_processes_buffer(self):
        """When client is available, process_buffer_files IS called."""
        import memory.trace_flush_worker as tfw

        mock_client = MagicMock()

        def set_shutdown(*_):
            tfw.shutdown_requested = True

        with (
            patch(
                "memory.trace_flush_worker.get_langfuse_client",
                return_value=mock_client,
            ),
            patch("memory.trace_flush_worker.evict_oldest_traces", return_value=0),
            patch(
                "memory.trace_flush_worker.process_buffer_files", return_value=(0, 0)
            ) as mock_process,
            patch("time.sleep", side_effect=set_shutdown),
        ):
            tfw.main()

        # Called in loop iteration AND shutdown path — at minimum once
        mock_process.assert_called_with(mock_client)
