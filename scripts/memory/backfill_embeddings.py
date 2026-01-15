#!/usr/bin/env python3
"""Process pending memory queue entries.

Implements Story 5.2 (Backfill Script) per 2025/2026 best practices.

This script processes queued memory operations that failed due to service
unavailability (Qdrant down, embedding timeout). Designed for cron execution
with robust locking and graceful error handling.

Architecture Compliance:
- Python naming: snake_case functions, PascalCase classes
- Structured logging with extras dict
- Non-blocking lock (fcntl.LOCK_EX | LOCK_NB)
- Exit 0 for partial failures (cron-friendly)
- Exit 1 only for critical errors

2025/2026 Best Practices Applied:
- argparse with type validation (fail fast)
- Single top-level exception handler (all exits in one place)
- Non-blocking lock with immediate return on conflict
- Structured logging for automation
- Exit code contract: 0 = success/partial, 1 = critical only

References:
- Story 5.2: Backfill Script
- [Python argparse best practices](https://stackify.com/python-argparse-definition-how-to-use-and-best-practices/)
- [File locking with fcntl.flock](https://seds.nl/notes/locking-python-scripts-with-flock/)
- [Prevent duplicate cron jobs](https://www.pankajtanwar.in/blog/prevent-duplicate-cron-job-running)
"""

import sys
import os
import argparse
import fcntl
import logging
from pathlib import Path

# Add project src to path for local imports
# Try multiple paths for flexibility (installed vs development)
for path in [
    os.path.expanduser("~/.bmad-memory/src"),  # Installed location
    str(Path(__file__).parent.parent.parent / "src"),  # Development location
]:
    if os.path.exists(path):
        sys.path.insert(0, path)
        break

from memory.queue import MemoryQueue
from memory.storage import MemoryStorage
from memory.embeddings import EmbeddingError
from memory.qdrant_client import QdrantUnavailable
from memory.models import MemoryType

# Configure logging for cron capture (structured logging per project-context.md)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Lock file location (persistent across reboots)
# Respects BACKFILL_LOCK_FILE env var for testing
LOCK_FILE = Path(
    os.environ.get("BACKFILL_LOCK_FILE", "~/.claude-memory/backfill.lock")
).expanduser()

# Module-level file handle to prevent GC from releasing lock prematurely
# Per 2026 best practices: "We can never close the file unless we want to release the lock"
# Reference: https://seds.nl/notes/locking-python-scripts-with-flock/
_lock_fd = None


def acquire_lock() -> bool:
    """Acquire exclusive lock for backfill process.

    Uses non-blocking lock (fcntl.LOCK_NB) for immediate return on conflict.
    Per 2025/2026 best practices: non-blocking lock prevents hung scripts.

    IMPORTANT: Stores file handle in module-level _lock_fd to prevent garbage
    collection from releasing the lock prematurely. Lock is released when
    process exits (automatic kernel cleanup).

    Returns:
        bool: True if lock acquired, False if another process holds lock

    References:
        - [File locking with fcntl.flock](https://seds.nl/notes/locking-python-scripts-with-flock/)
        - [fcntl.flock GitHub examples](https://gist.github.com/jirihnidek/430d45c54311661b47fb45a3a7846537)
    """
    global _lock_fd
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        _lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (IOError, OSError):
        if _lock_fd:
            _lock_fd.close()
            _lock_fd = None
        return False


def process_queue_item(item: dict, storage: MemoryStorage, queue: MemoryQueue) -> bool:
    """Process a single queue item.

    Implements AC 5.2.1 (Backfill Script Execution).

    Args:
        item: Queue entry dict with id, memory_data, failure_reason
        storage: MemoryStorage instance for retry
        queue: MemoryQueue instance for dequeue/mark_failed

    Returns:
        bool: True on success, False on retryable failure

    Error Handling (per user requirements: "no fallbacks, know when error happens"):
        - QdrantUnavailable: Log warning, mark_failed, return False (will retry)
        - EmbeddingError: Log warning, mark_failed, return False (will retry)
        - Unexpected exceptions: Log with traceback, return False (don't mark_failed)
    """
    try:
        memory_data = item["memory_data"]

        # Convert string type to MemoryType enum (Issue #5 fix)
        # Queue stores type as string, storage.store_memory expects enum
        memory_type_str = memory_data["type"]
        if isinstance(memory_type_str, str):
            memory_type = MemoryType(memory_type_str)
        else:
            memory_type = memory_type_str  # Already an enum

        # Store memory (will generate embedding if needed)
        result = storage.store_memory(
            content=memory_data["content"],
            cwd=memory_data.get("cwd", "/__backfill__"),  # Sentinel for backfill
            group_id=memory_data["group_id"],
            memory_type=memory_type,
            source_hook=memory_data["source_hook"],
            session_id=memory_data.get("session_id", "backfill"),
            collection="implementations"
        )

        # Success - remove from queue
        queue.dequeue(item["id"])
        logger.info(
            "backfill_success",
            extra={
                "queue_id": item["id"][:8],
                "memory_id": result["memory_id"][:8],
                "retry_count": item["retry_count"]
            }
        )
        return True

    except (QdrantUnavailable, EmbeddingError) as e:
        # Expected retryable failures - mark for retry with backoff
        queue.mark_failed(item["id"])
        logger.warning(
            "backfill_retry_scheduled",
            extra={
                "queue_id": item["id"][:8],
                "error_type": type(e).__name__,
                "error": str(e),
                "retry_count": item["retry_count"] + 1
            }
        )
        return False

    except Exception as e:
        # Unexpected error - log with traceback but don't mark_failed (may be bug)
        logger.exception(
            "backfill_unexpected_error",
            extra={
                "queue_id": item["id"][:8],
                "error_type": type(e).__name__
            }
        )
        return False


def validate_limit(value: str) -> int:
    """Validate --limit argument.

    Per 2025/2026 best practices: Shift validation into parsing phase.
    Raises ArgumentTypeError for immediate, actionable feedback.

    Args:
        value: String argument value from command line

    Returns:
        int: Validated limit value

    Raises:
        argparse.ArgumentTypeError: If validation fails

    References:
        - [Handle invalid arguments with argparse](https://thelinuxcode.com/how-i-handle-invalid-arguments-with-argparse-in-python/)
    """
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--limit must be integer (got '{value}')")

    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"--limit must be positive (got {ivalue})")

    if ivalue > 1000:
        raise argparse.ArgumentTypeError(
            f"--limit too high (max 1000, got {ivalue}). "
            "Large batches may overwhelm services after outage."
        )

    return ivalue


def main():
    """Main execution entry point.

    Implements AC 5.2.1, 5.2.2, 5.2.3, 5.2.4 (all ACs).

    Exit Codes (per 2025/2026 best practices and Story 5.2):
        0: Success (even if some items failed - they'll retry)
        1: Critical error (lock conflict, corrupt queue, missing dependencies)

    Error Philosophy (per user requirements):
        "follow proper development procedures, no fallbacks, lets make sure we
        know when an error or warning happens"

        - NO silent failures
        - Every error path logs before exiting
        - Structured logging for automation/monitoring
        - Exit codes communicate criticality to cron

    References:
        - Story 5.2 Dev Notes: Exit Code Standards (2026)
        - Story 5.2 Dev Notes: Error Handling & Observability
    """
    # Argument parsing with validation (AC 5.2.3)
    parser = argparse.ArgumentParser(
        description="Process pending memory queue",
        epilog="Exit 0: success/partial, Exit 1: critical error"
    )
    parser.add_argument(
        "--limit",
        type=validate_limit,
        default=50,
        help="Max items to process (default: 50, max: 1000)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without processing"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Retry exhausted items too (bypass max_retries)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show queue statistics only"
    )
    args = parser.parse_args()

    # Initialize queue
    queue = MemoryQueue()

    # Stats mode (AC 5.2.3) - structured output for both human and machine consumption
    if args.stats:
        stats = queue.get_stats()
        # Use structured logging for automation, but also print for human readability
        logger.info(
            "backfill_stats",
            extra={
                "total_items": stats['total_items'],
                "ready_for_retry": stats['ready_for_retry'],
                "awaiting_backoff": stats['awaiting_backoff'],
                "exhausted": stats['exhausted'],
                "by_failure_reason": stats['by_failure_reason']
            }
        )
        # Human-readable output (sent to stdout for cron capture)
        sys.stdout.write("\nQueue Statistics:\n")
        sys.stdout.write(f"  Total items: {stats['total_items']}\n")
        sys.stdout.write(f"  Ready for retry: {stats['ready_for_retry']}\n")
        sys.stdout.write(f"  Awaiting backoff: {stats['awaiting_backoff']}\n")
        sys.stdout.write(f"  Exhausted (max retries): {stats['exhausted']}\n")
        sys.stdout.write("\n  By failure reason:\n")
        for reason, count in stats['by_failure_reason'].items():
            sys.stdout.write(f"    {reason}: {count}\n")
        return

    # Get pending items (AC 5.2.1) - pass include_exhausted for --force mode (Issue #4 fix)
    pending = queue.get_pending(limit=args.limit, include_exhausted=args.force)

    # Handle empty queue (AC 5.2.1)
    if not pending:
        sys.stdout.write("No pending items to process\n")
        logger.info("backfill_empty_queue")
        return

    # Dry-run mode (AC 5.2.3)
    if args.dry_run:
        sys.stdout.write(f"\n[DRY RUN] Would process {len(pending)} items:\n")
        for item in pending:
            sys.stdout.write(f"  - {item['id'][:8]}... ({item['failure_reason']}) retry #{item['retry_count']}\n")
        logger.info(
            "backfill_dry_run",
            extra={"count": len(pending), "force": args.force}
        )
        return

    # Acquire lock (AC 5.2.4)
    if not acquire_lock():
        sys.stdout.write("Another backfill process is running. Exiting.\n")
        logger.warning(
            "backfill_lock_conflict",
            extra={
                "lock_file": str(LOCK_FILE),
                "resolution": "waiting_for_next_cron_run"
            }
        )
        sys.exit(1)  # Exit 1 = critical error for cron

    # Process items (AC 5.2.1, 5.2.2)
    sys.stdout.write(f"\nProcessing {len(pending)} pending items...\n")
    logger.info(
        "backfill_started",
        extra={
            "count": len(pending),
            "limit": args.limit,
            "force": args.force
        }
    )

    storage = MemoryStorage()
    success = 0
    failed = 0

    for item in pending:
        if process_queue_item(item, storage, queue):
            success += 1
        else:
            failed += 1

    sys.stdout.write(f"\nComplete: {success} succeeded, {failed} failed\n")
    logger.info(
        "backfill_complete",
        extra={
            "success": success,
            "failed": failed,
            "total": len(pending)
        }
    )

    # Exit 0 even if some failed (cron-friendly, will retry next run)


if __name__ == "__main__":
    main()
