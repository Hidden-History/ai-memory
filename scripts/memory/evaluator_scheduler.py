#!/usr/bin/env python3
"""Evaluator scheduler daemon.

Runs LLM-as-Judge evaluation pipeline on a cron schedule defined in
evaluator_config.yaml.

Architecture:
- Synchronous daemon with croniter for schedule parsing (DEC-110)
- Health check via /tmp/evaluator-scheduler.health timestamp file
- Graceful shutdown via atexit + SIGTERM handler
- Placed in docker-compose.langfuse.yml under langfuse profile

Usage:
    python scripts/memory/evaluator_scheduler.py

Reference:
- DEC-110: Standalone evaluator-scheduler container design
- PLAN-012 Phase 2: LLM-as-Judge evaluation pipeline
"""

# LANGFUSE: V3 SDK ONLY. See LANGFUSE-INTEGRATION-SPEC.md

import atexit
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Setup Python path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Configuration
CONFIG_PATH = os.environ.get("EVALUATOR_CONFIG_PATH", "/app/evaluator_config.yaml")
HEALTH_FILE = Path("/tmp/evaluator-scheduler.health")

# Setup logging
logging.basicConfig(
    level=os.environ.get("AI_MEMORY_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ai_memory.evaluator.scheduler")

# Graceful shutdown flag (set by SIGTERM handler)
_shutdown_requested = False


# =============================================================================
# HEALTH CHECK
# =============================================================================


def _touch_health_file() -> None:
    """Write health check marker for Docker healthcheck (graceful degradation)."""
    try:
        HEALTH_FILE.touch()
        logger.debug("health_file_updated: %s", HEALTH_FILE)
    except Exception as exc:
        logger.warning("health_file_update_failed: %s", exc)


# =============================================================================
# SIGNAL HANDLING + LANGFUSE SHUTDOWN
# =============================================================================


def _handle_sigterm(signum, frame) -> None:
    """SIGTERM handler — request graceful shutdown."""
    global _shutdown_requested
    logger.info("sigterm_received — requesting graceful shutdown")
    _shutdown_requested = True


def _register_langfuse_shutdown() -> None:
    """Register atexit handler to flush and shutdown Langfuse V3 client on exit."""

    def _langfuse_shutdown() -> None:
        try:
            from langfuse import get_client

            client = get_client()
            if client:
                client.flush()
                client.shutdown()  # V3 spec: NO arguments — shutdown(timeout=x) raises TypeError
        except Exception:
            pass  # Never fail on process exit

    atexit.register(_langfuse_shutdown)


# =============================================================================
# CONFIG LOADING
# =============================================================================


def load_schedule_config(config_path: str) -> dict:
    """Load and return the schedule section from evaluator_config.yaml.

    Args:
        config_path: Path to evaluator_config.yaml

    Returns:
        Schedule config dict with keys: enabled, cron, lookback_hours
    """
    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("schedule", {})


# =============================================================================
# SLEEP HELPER
# =============================================================================


def _interruptible_sleep(seconds: float, chunk: float = 5.0) -> None:
    """Sleep for `seconds`, waking every `chunk` seconds to check shutdown flag.

    Args:
        seconds: Total sleep duration in seconds
        chunk: Maximum sleep chunk size in seconds (default: 5.0)
    """
    remaining = seconds
    while remaining > 0 and not _shutdown_requested:
        sleep_for = min(remaining, chunk)
        time.sleep(sleep_for)
        remaining -= sleep_for


# =============================================================================
# SCHEDULER LOOP
# =============================================================================


def run_scheduler(config_path: str = CONFIG_PATH) -> None:
    """Main scheduler loop.

    Reads schedule config, sleeps until next cron tick, then invokes
    EvaluatorRunner.run(). Errors in evaluation are logged and the
    scheduler continues to the next cycle — it never crashes on eval failure.

    Args:
        config_path: Path to evaluator_config.yaml
    """
    global _shutdown_requested

    logger.info("evaluator_scheduler_starting, config=%s", config_path)

    # Write health file on startup (Docker healthcheck passes immediately — like
    # classifier worker BUG-045 fix: don't wait until first run completes)
    _touch_health_file()

    while not _shutdown_requested:
        # Reload schedule config each cycle to support live config changes
        try:
            schedule = load_schedule_config(config_path)
        except Exception as exc:
            logger.error("config_load_failed: %s — retrying in 60s", exc)
            _interruptible_sleep(60)
            continue

        if not schedule.get("enabled", False):
            logger.info("schedule_disabled — sleeping 300s before recheck")
            _interruptible_sleep(300)
            continue

        cron_expr = schedule.get("cron", "0 5 * * *")
        lookback_hours = int(schedule.get("lookback_hours", 24))

        # Calculate next run time using croniter
        from croniter import croniter

        now = datetime.now(tz=timezone.utc)
        try:
            cron = croniter(cron_expr, now)
            next_run: datetime = cron.get_next(datetime)
        except (ValueError, KeyError) as exc:
            logger.error("invalid_cron_expression: %s — retrying in 60s", exc)
            _interruptible_sleep(60)
            continue

        sleep_seconds = (next_run - now).total_seconds()
        logger.info(
            "next_evaluation_scheduled: cron=%s next_run_utc=%s sleep_seconds=%.0f",
            cron_expr,
            next_run.isoformat(),
            sleep_seconds,
        )

        # Sleep until next cron tick, waking periodically to check shutdown
        _interruptible_sleep(sleep_seconds)

        if _shutdown_requested:
            break

        # Re-check enabled — config may have changed while sleeping
        try:
            schedule = load_schedule_config(config_path)
        except Exception as exc:
            logger.error("config_reload_failed before run: %s — skipping cycle", exc)
            continue

        if not schedule.get("enabled", False):
            logger.info("schedule_disabled at run time — skipping cycle")
            continue

        # Re-read lookback_hours from reloaded config (avoid stale value from first load)
        lookback_hours = int(schedule.get("lookback_hours", 24))

        # Run evaluation with lookback window
        since = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
        logger.info(
            "evaluation_starting: since=%s lookback_hours=%d",
            since.isoformat(),
            lookback_hours,
        )

        try:
            from memory.evaluator import EvaluatorRunner

            runner = EvaluatorRunner(config_path)
            summary = runner.run(since=since)
            logger.info("evaluation_complete: %s", summary)
            # Touch health file only after successful run (not on failure)
            _touch_health_file()
        except Exception as exc:
            logger.error(
                "evaluation_failed: %s — continuing to next cycle",
                exc,
                exc_info=True,
            )
            # Do NOT update health file on failure
            # Continue scheduling — do not crash daemon on evaluation errors


# =============================================================================
# ENTRY POINT
# =============================================================================


def main() -> None:
    """Entry point."""
    signal.signal(signal.SIGTERM, _handle_sigterm)
    _register_langfuse_shutdown()

    try:
        run_scheduler()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        logger.info("evaluator_scheduler_stopped")


if __name__ == "__main__":
    main()
