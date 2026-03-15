# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md
"""Unit tests for S-16.5: Evaluator scheduler daemon.

Tests:
- Cron schedule parsing via croniter
- lookback_hours calculation
- schedule.enabled=False skips evaluation
- Evaluation failure doesn't crash scheduler
- Health file written after successful run
"""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# croniter availability guard
# ---------------------------------------------------------------------------
try:
    import croniter as _croniter_pkg  # noqa: F401

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False

pytestmark_croniter = pytest.mark.skipif(
    not CRONITER_AVAILABLE,
    reason="croniter not installed — add croniter>=2.0.0 to requirements.txt",
)


def _make_croniter_mock(next_run_dt: datetime):
    """Build a minimal croniter sys.modules mock returning a fixed next_run datetime."""
    mock_instance = MagicMock()
    mock_instance.get_next.return_value = next_run_dt
    mock_cls = MagicMock(return_value=mock_instance)
    mock_module = MagicMock()
    mock_module.croniter = mock_cls
    return mock_module, mock_cls, mock_instance


# ---------------------------------------------------------------------------
# Module loader helper
# ---------------------------------------------------------------------------

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


# Load once for all tests
_mod = _load_scheduler()


# ---------------------------------------------------------------------------
# Test: load_schedule_config
# ---------------------------------------------------------------------------


class TestLoadScheduleConfig:
    def test_parses_schedule_section(self, tmp_path):
        """load_schedule_config returns the schedule dict from YAML."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text(
            "schedule:\n"
            "  enabled: true\n"
            "  cron: '0 5 * * *'\n"
            "  lookback_hours: 24\n"
        )
        result = _mod.load_schedule_config(str(config))
        assert result["enabled"] is True
        assert result["cron"] == "0 5 * * *"
        assert result["lookback_hours"] == 24

    def test_returns_empty_dict_when_schedule_missing(self, tmp_path):
        """Returns {} when schedule key is absent."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text("evaluator_model:\n  provider: ollama\n")
        result = _mod.load_schedule_config(str(config))
        assert result == {}

    def test_parses_disabled_schedule(self, tmp_path):
        """enabled: false is returned correctly."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text(
            "schedule:\n"
            "  enabled: false\n"
            "  cron: '0 3 * * *'\n"
            "  lookback_hours: 48\n"
        )
        result = _mod.load_schedule_config(str(config))
        assert result["enabled"] is False
        assert result["lookback_hours"] == 48


# ---------------------------------------------------------------------------
# Test: cron schedule parsing + next run
# ---------------------------------------------------------------------------


class TestCronScheduleParsing:
    @pytestmark_croniter
    def test_croniter_returns_future_datetime(self):
        """croniter.get_next() returns a datetime after 'now'."""
        from croniter import croniter

        now = datetime(2026, 3, 14, 4, 0, 0, tzinfo=timezone.utc)
        cron = croniter("0 5 * * *", now)
        next_run = cron.get_next(datetime)

        # Should be 05:00 UTC on the same day
        assert next_run > now
        assert next_run.hour == 5
        assert next_run.minute == 0

    @pytestmark_croniter
    def test_croniter_sleep_seconds_positive(self):
        """sleep_seconds should always be positive (next run is in the future)."""
        from croniter import croniter

        now = datetime(2026, 3, 14, 4, 59, 59, tzinfo=timezone.utc)
        cron = croniter("0 5 * * *", now)
        next_run = cron.get_next(datetime)
        sleep_seconds = (next_run - now).total_seconds()

        assert sleep_seconds > 0
        assert sleep_seconds <= 60  # Less than 1 minute until 05:00

    def test_lookback_hours_calculation(self):
        """since = now - timedelta(hours=lookback_hours)."""
        lookback_hours = 24
        now = datetime(2026, 3, 14, 5, 0, 0, tzinfo=timezone.utc)
        since = now - timedelta(hours=lookback_hours)

        expected = datetime(2026, 3, 13, 5, 0, 0, tzinfo=timezone.utc)
        assert since == expected

    def test_lookback_hours_48(self):
        """lookback_hours=48 looks back 2 days."""
        lookback_hours = 48
        now = datetime(2026, 3, 14, 5, 0, 0, tzinfo=timezone.utc)
        since = now - timedelta(hours=lookback_hours)

        expected = datetime(2026, 3, 12, 5, 0, 0, tzinfo=timezone.utc)
        assert since == expected


# ---------------------------------------------------------------------------
# Test: schedule.enabled=False skips evaluation
# ---------------------------------------------------------------------------


class TestScheduleDisabled:
    def test_enabled_false_does_not_call_runner(self, tmp_path):
        """When schedule.enabled=False, EvaluatorRunner.run() is never called."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text(
            "schedule:\n"
            "  enabled: false\n"
            "  cron: '0 5 * * *'\n"
            "  lookback_hours: 24\n"
        )

        # Reload module with fresh globals to avoid state bleed
        mod = _load_scheduler()
        mod._shutdown_requested = False

        _call_count = 0

        def fake_interruptible_sleep(seconds, chunk=5.0):
            # After one sleep (schedule disabled), set shutdown to stop the loop
            mod._shutdown_requested = True

        with (
            patch.object(
                mod, "_interruptible_sleep", side_effect=fake_interruptible_sleep
            ),
            patch.object(mod, "load_schedule_config", return_value={"enabled": False}),
            patch("memory.evaluator.EvaluatorRunner") as mock_runner_cls,
        ):
            mod.run_scheduler(str(config))
            mock_runner_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test: evaluation failure doesn't crash scheduler
# ---------------------------------------------------------------------------


class TestEvaluationFailure:
    def test_evaluation_error_continues_to_next_cycle(self, tmp_path):
        """If EvaluatorRunner.run() raises, the scheduler logs and continues."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text(
            "schedule:\n"
            "  enabled: true\n"
            "  cron: '0 5 * * *'\n"
            "  lookback_hours: 24\n"
        )

        mod = _load_scheduler()
        mod._shutdown_requested = False

        sleep_call_count = [0]

        def fake_interruptible_sleep(seconds, chunk=5.0):
            sleep_call_count[0] += 1
            # Shut down after the second sleep (after one failed eval cycle)
            if sleep_call_count[0] >= 2:
                mod._shutdown_requested = True

        mock_runner = MagicMock()
        mock_runner.run.side_effect = RuntimeError("LLM provider unavailable")

        _next_run = datetime(2026, 3, 14, 5, 0, 0, tzinfo=timezone.utc)
        mock_croniter_mod, _, _ = _make_croniter_mock(_next_run)

        with (
            patch.dict(sys.modules, {"croniter": mock_croniter_mod}),
            patch.object(
                mod, "_interruptible_sleep", side_effect=fake_interruptible_sleep
            ),
            patch.object(
                mod,
                "load_schedule_config",
                return_value={
                    "enabled": True,
                    "cron": "* * * * *",
                    "lookback_hours": 1,
                },
            ),
            patch.object(mod, "_touch_health_file") as mock_touch,
            patch("memory.evaluator.EvaluatorRunner", return_value=mock_runner),
        ):
            # Should NOT raise — errors are caught and logged
            mod.run_scheduler(str(config))

        # Runner was called at least once
        mock_runner.run.assert_called()
        # Health file should have been touched on startup only (not on failure)
        assert mock_touch.call_count == 1

    def test_evaluation_failure_does_not_update_health_file(self, tmp_path):
        """Health file is NOT touched after a failed evaluation."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text(
            "schedule:\n"
            "  enabled: true\n"
            "  cron: '* * * * *'\n"
            "  lookback_hours: 1\n"
        )

        mod = _load_scheduler()
        mod._shutdown_requested = False

        sleep_calls = [0]
        startup_touch_done = [False]
        touch_after_startup = [0]

        def fake_sleep(seconds, chunk=5.0):
            sleep_calls[0] += 1
            if sleep_calls[0] >= 2:
                mod._shutdown_requested = True

        def fake_touch():
            if startup_touch_done[0]:
                touch_after_startup[0] += 1
            startup_touch_done[0] = True

        mock_runner = MagicMock()
        mock_runner.run.side_effect = Exception("eval error")

        _next_run = datetime(2026, 3, 14, 5, 0, 0, tzinfo=timezone.utc)
        mock_croniter_mod, _, _ = _make_croniter_mock(_next_run)

        with (
            patch.dict(sys.modules, {"croniter": mock_croniter_mod}),
            patch.object(mod, "_interruptible_sleep", side_effect=fake_sleep),
            patch.object(
                mod,
                "load_schedule_config",
                return_value={
                    "enabled": True,
                    "cron": "* * * * *",
                    "lookback_hours": 1,
                },
            ),
            patch.object(mod, "_touch_health_file", side_effect=fake_touch),
            patch("memory.evaluator.EvaluatorRunner", return_value=mock_runner),
        ):
            mod.run_scheduler(str(config))

        # Health file should NOT be touched after the failed evaluation
        assert touch_after_startup[0] == 0


# ---------------------------------------------------------------------------
# Test: health file written after successful run
# ---------------------------------------------------------------------------


class TestHealthFile:
    def test_health_file_touched_on_startup(self, tmp_path):
        """Health file is touched on daemon startup before any evaluation."""
        mod = _load_scheduler()
        mod._shutdown_requested = False

        touch_calls = []

        def fake_touch():
            touch_calls.append("touch")

        def fake_sleep(seconds, chunk=5.0):
            # Immediately shut down after first sleep
            mod._shutdown_requested = True

        with (
            patch.object(mod, "_touch_health_file", side_effect=fake_touch),
            patch.object(
                mod,
                "load_schedule_config",
                return_value={"enabled": False},
            ),
            patch.object(mod, "_interruptible_sleep", side_effect=fake_sleep),
        ):
            mod.run_scheduler(str(tmp_path / "evaluator_config.yaml"))

        # At minimum, touched on startup
        assert len(touch_calls) >= 1

    def test_health_file_touched_after_successful_run(self, tmp_path):
        """Health file is touched after a successful evaluation run."""
        config = tmp_path / "evaluator_config.yaml"
        config.write_text(
            "schedule:\n"
            "  enabled: true\n"
            "  cron: '* * * * *'\n"
            "  lookback_hours: 1\n"
        )

        mod = _load_scheduler()
        mod._shutdown_requested = False

        touch_calls = [0]
        sleep_calls = [0]

        def fake_touch():
            touch_calls[0] += 1

        def fake_sleep(seconds, chunk=5.0):
            sleep_calls[0] += 1
            # Shut down after second sleep (after one successful eval cycle)
            if sleep_calls[0] >= 2:
                mod._shutdown_requested = True

        mock_runner = MagicMock()
        mock_runner.run.return_value = {
            "fetched": 10,
            "sampled": 5,
            "evaluated": 5,
            "scored": 5,
        }

        _next_run = datetime(2026, 3, 14, 5, 0, 0, tzinfo=timezone.utc)
        mock_croniter_mod, _, _ = _make_croniter_mock(_next_run)

        with (
            patch.dict(sys.modules, {"croniter": mock_croniter_mod}),
            patch.object(mod, "_touch_health_file", side_effect=fake_touch),
            patch.object(mod, "_interruptible_sleep", side_effect=fake_sleep),
            patch.object(
                mod,
                "load_schedule_config",
                return_value={
                    "enabled": True,
                    "cron": "* * * * *",
                    "lookback_hours": 1,
                },
            ),
            patch("memory.evaluator.EvaluatorRunner", return_value=mock_runner),
        ):
            mod.run_scheduler(str(config))

        # Touched on startup + once after successful run = at least 2 calls
        assert touch_calls[0] >= 2
        mock_runner.run.assert_called_once()

    def test_health_file_actual_touch(self, tmp_path):
        """_touch_health_file() creates the file on disk."""
        health_file = tmp_path / "evaluator-scheduler.health"

        mod = _load_scheduler()
        original_health = mod.HEALTH_FILE
        mod.HEALTH_FILE = health_file

        try:
            assert not health_file.exists()
            mod._touch_health_file()
            assert health_file.exists()
        finally:
            mod.HEALTH_FILE = original_health

    def test_health_file_touch_graceful_on_error(self, tmp_path):
        """_touch_health_file() does not raise even if file path is unwritable."""
        mod = _load_scheduler()
        original_health = mod.HEALTH_FILE
        mod.HEALTH_FILE = Path("/nonexistent_dir/evaluator-scheduler.health")

        try:
            # Should not raise
            mod._touch_health_file()
        finally:
            mod.HEALTH_FILE = original_health
