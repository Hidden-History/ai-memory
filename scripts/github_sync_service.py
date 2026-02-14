#!/usr/bin/env python3
"""GitHub sync service — container entrypoint.

Runs periodic GitHub sync (issues, PRs, commits, CI, code blobs) in a loop.
Designed for Docker container with health file for liveness checks.

Usage (Docker):
    CMD ["python3", "scripts/github_sync_service.py"]

Usage (manual):
    python3 scripts/github_sync_service.py

Environment:
    GITHUB_SYNC_ON_START=true   — Run sync immediately on start (default: true)
    GITHUB_SYNC_INTERVAL=1800   — Seconds between sync cycles (default: 30 min)
    See config.py for all GITHUB_* variables.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memory.config import get_config
from memory.connectors.github.client import GitHubClient
from memory.connectors.github.sync import GitHubSyncEngine
from memory.connectors.github.code_sync import CodeBlobSync

logger = logging.getLogger("ai_memory.github.service")

HEALTH_FILE = Path("/tmp/sync.health")
SHUTDOWN_REQUESTED = False


def handle_signal(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global SHUTDOWN_REQUESTED
    logger.info("Shutdown signal received (signal=%d), finishing current cycle...", signum)
    SHUTDOWN_REQUESTED = True


async def run_sync_cycle(config) -> bool:
    """Run a single sync cycle (issues + PRs + commits + CI + code blobs).

    Returns:
        True if sync completed without fatal errors, False otherwise.
    """
    sync_ok = True

    # Phase 1: Issues, PRs, commits, CI results
    # GitHubSyncEngine creates its own GitHubClient internally
    try:
        engine = GitHubSyncEngine(config)
        result = await engine.sync()
        logger.info(
            "Sync cycle complete: issues=%d, prs=%d, commits=%d, ci=%d, errors=%d",
            result.issues_synced, result.prs_synced, result.commits_synced,
            result.ci_results_synced, result.errors,
        )
    except Exception as e:
        logger.error("Sync engine failed: %s", e)
        sync_ok = False

    # Phase 2: Code blobs (if enabled)
    # CodeBlobSync requires an external GitHubClient (caller manages lifecycle)
    if config.github_code_blob_enabled:
        try:
            client = GitHubClient(
                token=config.github_token.get_secret_value(),
                repo=config.github_repo,
            )
            async with client:
                code_sync = CodeBlobSync(client, config)
                batch_id = GitHubClient.generate_batch_id()
                code_result = await code_sync.sync_code_blobs(batch_id)
            logger.info(
                "Code sync complete: synced=%d, skipped=%d, deleted=%d, errors=%d",
                code_result.files_synced, code_result.files_skipped,
                code_result.files_deleted, code_result.errors,
            )
        except Exception as e:
            logger.error("Code blob sync failed: %s", e)
            sync_ok = False

    return sync_ok


def write_health_file():
    """Write health file for Docker healthcheck."""
    try:
        HEALTH_FILE.write_text(str(int(time.time())))
    except OSError as e:
        logger.warning("Failed to write health file: %s", e)


def main():
    """Main service loop."""
    # Setup signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Load and validate config
    try:
        config = get_config()
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        sys.exit(1)

    if not config.github_sync_enabled:
        logger.error("GITHUB_SYNC_ENABLED is not true — exiting")
        sys.exit(1)

    interval = config.github_sync_interval
    sync_on_start = os.getenv("GITHUB_SYNC_ON_START", "true").lower() == "true"

    logger.info(
        "GitHub sync service starting (interval=%ds, sync_on_start=%s, repo=%s)",
        interval, sync_on_start, config.github_repo,
    )

    # Main loop
    first_run = True
    while not SHUTDOWN_REQUESTED:
        if first_run and not sync_on_start:
            logger.info("Skipping initial sync (GITHUB_SYNC_ON_START=false)")
            first_run = False
        else:
            logger.info("Starting sync cycle...")
            success = asyncio.run(run_sync_cycle(config))
            if success:
                write_health_file()
            first_run = False

        # Sleep in small increments to allow graceful shutdown
        for _ in range(interval):
            if SHUTDOWN_REQUESTED:
                break
            time.sleep(1)

    logger.info("GitHub sync service shutting down gracefully")


if __name__ == "__main__":
    main()
