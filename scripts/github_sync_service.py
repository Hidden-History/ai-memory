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
from memory.connectors.github.code_sync import CodeBlobSync
from memory.connectors.github.sync import GitHubSyncEngine

logger = logging.getLogger("ai_memory.github.service")

HEALTH_FILE = Path("/tmp/sync.health")
SHUTDOWN_REQUESTED = False


def handle_signal(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global SHUTDOWN_REQUESTED
    logger.info(
        "Shutdown signal received (signal=%d), finishing current cycle...", signum
    )
    SHUTDOWN_REQUESTED = True


def _resolve_project_token(config, project) -> str:
    """Resolve the effective GitHub token for a project.

    BUG-245: Per-project token takes precedence over global token.
    Enables fine-grained PATs scoped to specific repos.

    Args:
        config: Global MemoryConfig with shared github_token.
        project: ProjectSyncConfig with optional github_token override.

    Returns:
        The resolved token string (project-level or global).
    """
    if project.github_token:
        return project.github_token
    return config.github_token.get_secret_value()


async def validate_project_tokens(config) -> set[str]:
    """Validate GitHub token connectivity for each registered project at startup.

    BUG-245 Phase 4: Tests each project's resolved token against its repo.
    Returns set of project IDs that failed validation (sync will be skipped).

    Args:
        config: Global MemoryConfig.

    Returns:
        Set of project IDs with failed token validation.
    """
    from memory.config import discover_projects

    projects = discover_projects()
    failed_projects: set[str] = set()

    for pid, project in projects.items():
        if not project.github_enabled or not project.github_repo:
            continue

        token = _resolve_project_token(config, project)
        token_type = "project-specific" if project.github_token else "shared"

        try:
            client = GitHubClient(token=token, repo=project.github_repo)
            async with client:
                result = await client.test_repo_access()
                if result.get("success"):
                    logger.info(
                        "Token validation OK: project=%s repo=%s (using %s token)",
                        pid,
                        project.github_repo,
                        token_type,
                    )
                else:
                    error_msg = result.get("error", "unknown")
                    logger.warning(
                        "Project '%s' — GitHub token cannot access %s: %s. "
                        "Sync will be skipped until token is fixed. (using %s token)",
                        pid,
                        project.github_repo,
                        error_msg,
                        token_type,
                    )
                    failed_projects.add(pid)
        except asyncio.TimeoutError:
            logger.warning(
                "Project '%s' — token validation timed out for %s (using %s token)",
                pid,
                project.github_repo,
                token_type,
            )
            failed_projects.add(pid)
        except Exception as e:
            logger.warning(
                "Project '%s' — token validation failed for %s: %s: %s (using %s token)",
                pid,
                project.github_repo,
                type(e).__name__,
                e,
                token_type,
            )
            failed_projects.add(pid)

    return failed_projects


async def run_sync_cycle(config, skip_projects: set[str] | None = None) -> bool:
    """Run a single sync cycle across all registered projects.

    Iterates over all projects from projects.d/ that have GitHub enabled.
    Falls back to a no-op if no projects are configured.

    Args:
        config: Global MemoryConfig.
        skip_projects: Set of project IDs to skip (failed token validation).

    Returns:
        True if all syncs completed without fatal errors, False otherwise.
    """
    # Lazy import — discover_projects added by PLAN-009 Phase 1
    from memory.config import discover_projects

    projects = discover_projects()
    skip_projects = skip_projects or set()

    if not projects:
        logger.warning("No projects configured — skipping sync")
        return True

    sync_ok = True
    for pid, project in projects.items():
        if not project.github_enabled or not project.github_repo:
            logger.info("Skipping project %s (GitHub disabled or no repo)", pid)
            continue

        if pid in skip_projects:
            logger.info(
                "Skipping project %s (token validation failed at startup)", pid
            )
            continue

        # BUG-245: resolve per-project token, fall back to global
        project_token = _resolve_project_token(config, project)

        logger.info("Syncing project: %s (repo: %s)", pid, project.github_repo)

        # Phase 1: Issues, PRs, commits, CI results
        try:
            engine = GitHubSyncEngine(
                config,
                repo=project.github_repo,
                branch=project.github_branch,
                token=project_token,
            )
            result = await engine.sync()
            logger.info(
                "Sync complete: repo=%s issues=%d prs=%d commits=%d ci=%d errors=%d",
                project.github_repo,
                result.issues_synced,
                result.prs_synced,
                result.commits_synced,
                result.ci_results_synced,
                result.errors,
            )
        except Exception as e:
            logger.error("Sync failed: repo=%s error=%s", project.github_repo, e)
            sync_ok = False

        # Phase 2: Code blobs (if enabled)
        if config.github_code_blob_enabled:
            try:
                client = GitHubClient(
                    token=project_token,
                    repo=project.github_repo,
                )
                async with client:
                    code_sync = CodeBlobSync(
                        client,
                        config,
                        repo=project.github_repo,
                        branch=project.github_branch,
                    )
                    batch_id = GitHubClient.generate_batch_id()
                    code_result = await code_sync.sync_code_blobs(
                        batch_id,
                        total_timeout=config.github_sync_total_timeout,
                    )
                logger.info(
                    "Code sync: repo=%s synced=%d skipped=%d deleted=%d errors=%d",
                    project.github_repo,
                    code_result.files_synced,
                    code_result.files_skipped,
                    code_result.files_deleted,
                    code_result.errors,
                )
            except Exception as e:
                logger.error(
                    "Code sync failed: repo=%s error=%s", project.github_repo, e
                )
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
        interval,
        sync_on_start,
        config.github_repo or "multi-project",
    )

    # BUG-119: Write health file at startup so Docker healthcheck passes
    # during the (potentially long) first sync cycle
    write_health_file()
    logger.info("Startup health file written (Docker healthcheck will pass)")

    # BUG-245 Phase 4: Validate per-project tokens at startup
    logger.info("Validating GitHub tokens for registered projects...")
    failed_projects = asyncio.run(validate_project_tokens(config))
    if failed_projects:
        logger.warning(
            "Token validation failed for %d project(s): %s — these will be skipped during sync",
            len(failed_projects),
            ", ".join(sorted(failed_projects)),
        )

    # Main loop
    first_run = True
    while not SHUTDOWN_REQUESTED:
        if first_run and not sync_on_start:
            logger.info("Skipping initial sync (GITHUB_SYNC_ON_START=false)")
            first_run = False
        else:
            logger.info("Starting sync cycle...")
            sync_ok = asyncio.run(run_sync_cycle(config, skip_projects=failed_projects))
            write_health_file()
            if not sync_ok:
                logger.warning(
                    "Sync cycle completed with errors (health file still written — service is alive)"
                )
            first_run = False

        # Sleep in small increments to allow graceful shutdown
        for _ in range(interval):
            if SHUTDOWN_REQUESTED:
                break
            time.sleep(1)

    logger.info("GitHub sync service shutting down gracefully")


if __name__ == "__main__":
    main()
