#!/usr/bin/env python3
"""Retry-queue drain scheduler daemon.

Runs ``process_retry_queue.process_queue()`` on a fixed interval from inside the
Docker Compose stack, replacing the WSL2 host cron that recovered ≈0 entries
(BUG-522). A container-side loop is the only dependable + portable scheduler on
WSL2: the Docker utility VM stays up when the user's distro idles out, which is
the exact case an in-distro cron/systemd-timer fails (BP-181).

Architecture (mirrors the evaluator-scheduler daemon, DEC-110):
- Synchronous daemon with a fixed-interval loop (BP-181 — no cron cadence needed)
- Health-file heartbeat at /tmp/retry-queue-drain.health for the Docker healthcheck
- Graceful shutdown via SIGTERM handler + interruptible sleep
- Never crashes on a drain failure — logs and continues to the next cycle

Usage:
    python scripts/memory/retry_drain_scheduler.py

Environment:
    RETRY_DRAIN_INTERVAL_SECONDS   Seconds between drains (default: 900 = 15 min)
    RETRY_DRAIN_LIMIT              Max entries per drain cycle (default: 100)
    AI_MEMORY_LOG_LEVEL           Log level (default: INFO)

Reference:
- BP-181 (WSL2 periodic execution), BP-180 (durable retry queue), BUG-522
- DEC-110 (standalone scheduler container pattern)
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path

# Setup Python path for imports (mirrors evaluator_scheduler.py)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# process_retry_queue.py lives alongside this module; import its drain entry point.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from process_retry_queue import drain_lock, process_queue  # noqa: E402

HEALTH_FILE = Path("/tmp/retry-queue-drain.health")

# Defaults chosen per BP-181: a ~15-minute cadence is a good balance between
# recovery latency and load for a durable queue.
DEFAULT_INTERVAL_SECONDS = 900
DEFAULT_LIMIT = 100

logging.basicConfig(
    level=os.environ.get("AI_MEMORY_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ai_memory.retry_drain.scheduler")

# Graceful shutdown flag (set by SIGTERM handler)
_shutdown_requested = False


def _handle_sigterm(signum, frame) -> None:
    """SIGTERM handler — request graceful shutdown."""
    global _shutdown_requested
    logger.info("sigterm_received — requesting graceful shutdown")
    _shutdown_requested = True


def _touch_health_file() -> None:
    """Write the health-check marker for the Docker healthcheck (best-effort)."""
    try:
        HEALTH_FILE.touch()
        logger.debug("health_file_updated: %s", HEALTH_FILE)
    except Exception as exc:
        logger.warning("health_file_update_failed: %s", exc)


def _interruptible_sleep(seconds: float, chunk: float = 5.0) -> None:
    """Sleep for *seconds*, waking every *chunk* seconds to check the shutdown flag."""
    remaining = seconds
    while remaining > 0 and not _shutdown_requested:
        sleep_for = min(remaining, chunk)
        time.sleep(sleep_for)
        remaining -= sleep_for


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back to *default*."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid_%s=%r — using default %d", name.lower(), raw, default)
        return default
    if value <= 0:
        logger.warning(
            "non_positive_%s=%d — using default %d", name.lower(), value, default
        )
        return default
    return value


def run_scheduler() -> None:
    """Main drain loop: drain, heartbeat, sleep — until shutdown is requested."""
    interval = _positive_int_env(
        "RETRY_DRAIN_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS
    )
    limit = _positive_int_env("RETRY_DRAIN_LIMIT", DEFAULT_LIMIT)

    logger.info(
        "retry_drain_scheduler_starting interval_seconds=%d limit=%d", interval, limit
    )

    # Touch health file on startup so the Docker healthcheck passes immediately
    # (do not wait until the first drain completes — BUG-045 pattern).
    _touch_health_file()

    while not _shutdown_requested:
        try:
            # Global drain across all groups (each entry stores under its own
            # persisted group_id — BP-180). Never crash the daemon on failure.
            # Hold the shared drain lock so this cycle and an on-session-start
            # opportunistic drain never run concurrently.
            with drain_lock() as acquired:
                if not acquired:
                    logger.info("drain_skipped — another drain holds the lock")
                    _touch_health_file()
                    _interruptible_sleep(interval)
                    continue
                stats = process_queue(limit=limit)
            logger.info(
                "drain_cycle_complete processed=%d success=%d failed=%d moved_to_dlq=%d",
                stats.get("processed", 0),
                stats.get("success", 0),
                stats.get("failed", 0),
                stats.get("moved_to_dlq", 0),
            )
            _touch_health_file()
        except Exception as exc:
            logger.error(
                "drain_cycle_failed: %s — continuing to next cycle", exc, exc_info=True
            )
            # Do NOT update the health file on failure.

        _interruptible_sleep(interval)


def main() -> None:
    """Entry point."""
    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        run_scheduler()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        logger.info("retry_drain_scheduler_stopped")


if __name__ == "__main__":
    main()
