"""File-based retry queue for pending memory operations.

This module provides a persistent queue for memory operations that fail due to
service unavailability (Qdrant down, embedding timeout). Operations are queued
to $AI_MEMORY_INSTALL_DIR/queue/pending_queue.jsonl and retried with exponential backoff.

Key Features:
- JSONL format (one JSON object per line)
- File locking (fcntl.flock) for concurrent access
- Atomic writes with temp file + rename
- Exponential backoff: 1min, 5min, 15min (capped)
- Queue statistics for monitoring

Architecture Compliance:
- Python naming: snake_case functions, PascalCase classes
- Structured logging with extras dict
- File permissions: 0700 directory, 0600 file
- Graceful degradation: never crash hooks

Best Practices (2026):
- fcntl.flock (not fcntl.lockf or fcntl.fcntl)
- dataclass (not Pydantic) for performance
- Queue-based retry (not decorator) for NFR-P1 compliance
- Atomic operations with os.replace()

References:
- Story 5.1: File-Based Retry Queue
- [File Locks And Concurrency In Python](https://heycoach.in/blog/file-locks-and-concurrency-in-python/)
- [Stack and Queues in Python: Modern Practice for 2026](https://thelinuxcode.com/stack-and-queues-in-python-modern-practice-for-2026/)
"""

import fcntl
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai_memory.queue")

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from .metrics import queue_size
except ImportError:
    queue_size = None

# Default lock timeout per AC 5.1.4
LOCK_TIMEOUT_SECONDS = 5.0

# Default queue file path - uses AI_MEMORY_INSTALL_DIR for multi-project support
# Use MemoryQueue(queue_path=...) or MEMORY_QUEUE_PATH env var for custom paths
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
QUEUE_FILE = Path(INSTALL_DIR) / "queue" / "pending_queue.jsonl"


def _acquire_lock_with_timeout(fd: int, timeout_seconds: float = LOCK_TIMEOUT_SECONDS) -> bool:
    """Acquire exclusive lock with timeout.

    Uses non-blocking lock with retry loop per AC 5.1.4.
    Retries every 100ms until timeout reached.

    Args:
        fd: File descriptor to lock
        timeout_seconds: Maximum wait time (default 5s per AC 5.1.4)

    Returns:
        bool: True if lock acquired, False on timeout
    """
    start = time.monotonic()
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            elapsed = time.monotonic() - start
            if elapsed >= timeout_seconds:
                logger.warning(
                    "lock_acquisition_timeout",
                    extra={
                        "timeout_seconds": timeout_seconds,
                        "elapsed": round(elapsed, 2),
                    },
                )
                return False
            time.sleep(0.1)  # 100ms retry interval


class LockTimeoutError(Exception):
    """Raised when lock acquisition times out."""

    pass


@dataclass
class QueueEntry:
    """Queue entry for pending memory operation.

    Represents a memory operation that failed and needs retry with backoff.

    Attributes:
        id: UUID v4 string identifying this queue entry
        memory_data: Complete memory data dict for store_memory()
        failure_reason: Error code (QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT)
        retry_count: Number of retry attempts so far (0-based)
        max_retries: Maximum retry attempts before giving up
        queued_at: ISO 8601 timestamp when first queued
        next_retry_at: ISO 8601 timestamp when eligible for retry
    """

    id: str
    memory_data: dict
    failure_reason: str
    retry_count: int = 0
    max_retries: int = 3
    queued_at: str = ""
    next_retry_at: str = ""

    def __post_init__(self):
        """Initialize timestamps if not provided."""
        if not self.queued_at:
            self.queued_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.next_retry_at:
            self.next_retry_at = self._calculate_next_retry()

    def _calculate_next_retry(self) -> str:
        """Calculate next retry timestamp with exponential backoff.

        Backoff schedule:
        - Retry 1: 1 minute
        - Retry 2: 5 minutes
        - Retry 3+: 15 minutes (capped)

        Returns:
            str: ISO 8601 timestamp with Z suffix
        """
        delays = [1, 5, 15]  # Minutes
        delay_minutes = delays[min(self.retry_count, len(delays) - 1)]
        next_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        return next_time.isoformat().replace("+00:00", "Z")


class MemoryQueue:
    """File-based queue for pending memory operations.

    Provides persistent queue with:
    - File locking for concurrent access
    - Atomic operations via temp file + rename
    - Exponential backoff retry scheduling
    - Queue statistics for monitoring

    Thread-safe: Uses fcntl.flock for exclusive locking during writes.
    Process-safe: File-based locking works across processes.

    Example:
        queue = MemoryQueue()

        # Enqueue failed operation
        memory_data = {"content": "...", "group_id": "project", ...}
        queue_id = queue.enqueue(memory_data, "QDRANT_UNAVAILABLE")

        # Later: Get items ready for retry
        pending = queue.get_pending(limit=10)
        for entry in pending:
            try:
                # Attempt retry
                storage.store_memory(entry["memory_data"])
                # Success - remove from queue
                queue.dequeue(entry["id"])
            except Exception:
                # Failed again - increment retry count
                queue.mark_failed(entry["id"])
    """

    def __init__(self, queue_path: Optional[str] = None):
        """Initialize queue with optional custom path.

        Args:
            queue_path: Custom queue file path. Falls back to MEMORY_QUEUE_PATH
                        env var, then $AI_MEMORY_INSTALL_DIR/queue/pending_queue.jsonl
        """
        # Priority: explicit arg > env var > default (uses AI_MEMORY_INSTALL_DIR)
        resolved_path = (
            queue_path
            or os.environ.get("MEMORY_QUEUE_PATH")
            or str(QUEUE_FILE)  # Uses AI_MEMORY_INSTALL_DIR-based default
        )
        self.queue_path = Path(resolved_path)
        self._ensure_directory()

    def _ensure_directory(self):
        """Ensure queue directory exists with proper permissions.

        Creates directory with 0700 (owner-only) if not exists.
        """
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.queue_path.parent, 0o700)

    def _update_queue_metrics(self):
        """Update queue_size gauge with current stats and push to Pushgateway.

        Metrics: Update queue_size gauge (Story 6.1, AC 6.1.3)
        Labels: status in ["pending", "exhausted", "ready"]
        - pending: Items with retry_count < max_retries (awaiting backoff)
        - exhausted: Items with retry_count >= max_retries
        - ready: Items ready for immediate retry (next_retry_at <= now)
        """
        stats = self.get_stats()
        # Pending = awaiting_backoff (not yet ready)
        pending_count = stats["awaiting_backoff"]
        exhausted_count = stats["exhausted"]
        ready_count = stats["ready_for_retry"]

        # Update in-memory gauge if available
        if queue_size is not None:
            queue_size.labels(status="pending").set(pending_count)
            queue_size.labels(status="exhausted").set(exhausted_count)

        # Push to Pushgateway for dashboard visibility
        try:
            from .metrics_push import push_queue_metrics_async
            push_queue_metrics_async(pending_count, exhausted_count, ready_count)
        except ImportError:
            pass  # Graceful degradation if push module not available

    def enqueue(self, memory_data: dict, failure_reason: str, immediate: bool = False) -> str:
        """Add memory operation to queue.

        Args:
            memory_data: Complete memory data dict for store_memory()
            failure_reason: Error code (QDRANT_UNAVAILABLE, EMBEDDING_TIMEOUT)
            immediate: If True, item is immediately ready for retry (no backoff).
                       Default False uses exponential backoff.

        Returns:
            str: Queue entry ID (UUID v4)
        """
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # For immediate retry, set next_retry_at to now (past is also valid)
        next_retry = now if immediate else ""

        entry = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data=memory_data,
            failure_reason=failure_reason,
            next_retry_at=next_retry  # Override default backoff if immediate
        )

        with self._locked_append() as f:
            f.write(json.dumps(asdict(entry)) + "\n")

        # Set file permissions to 0600 (owner-only)
        os.chmod(self.queue_path, 0o600)

        logger.info(
            "memory_queued",
            extra={"queue_id": entry.id, "failure_reason": failure_reason},
        )

        # Metrics: Update queue_size gauge after enqueue (Story 6.1, AC 6.1.3)
        self._update_queue_metrics()

        return entry.id

    def dequeue(self, queue_id: str) -> None:
        """Remove entry from queue after successful processing.

        Args:
            queue_id: Queue entry ID to remove
        """
        with self._locked_read_modify_write() as (entries, write_fn):
            entries = [e for e in entries if e["id"] != queue_id]
            write_fn(entries)

        logger.info("memory_dequeued", extra={"queue_id": queue_id})

        # Metrics: Update queue_size gauge after dequeue (Story 6.1, AC 6.1.3)
        self._update_queue_metrics()

    def get_pending(self, limit: int = 10, include_exhausted: bool = False) -> list[dict]:
        """Get entries ready for retry (next_retry_at <= now).

        Filters for:
        - next_retry_at <= current time
        - retry_count < max_retries (unless include_exhausted=True)

        Args:
            limit: Maximum number of entries to return
            include_exhausted: If True, include items that exceeded max_retries
                               (for --force mode in backfill script). Default: False

        Returns:
            list: Queue entries ready for retry
        """
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entries = self._read_all()

        if include_exhausted:
            # Force mode: Include all items where next_retry_at has passed
            ready = [e for e in entries if e["next_retry_at"] <= now]
        else:
            # Normal mode: Only items within max_retries
            ready = [
                e
                for e in entries
                if e["next_retry_at"] <= now and e["retry_count"] < e["max_retries"]
            ]

        return ready[:limit]

    def mark_failed(self, queue_id: str) -> None:
        """Increment retry_count and update next_retry_at with backoff.

        Args:
            queue_id: Queue entry ID that failed retry
        """
        with self._locked_read_modify_write() as (entries, write_fn):
            for entry in entries:
                if entry["id"] == queue_id:
                    entry["retry_count"] += 1
                    # Calculate next retry with exponential backoff
                    delays = [1, 5, 15]
                    delay = delays[min(entry["retry_count"], len(delays) - 1)]
                    next_time = datetime.now(timezone.utc) + timedelta(minutes=delay)
                    entry["next_retry_at"] = next_time.isoformat().replace("+00:00", "Z")
                    break
            write_fn(entries)

        # Metrics: Update queue_size gauge after mark_failed (Story 6.1, AC 6.1.3)
        # Incrementing retry_count may move item from pending to exhausted
        self._update_queue_metrics()

    def get_stats(self) -> dict:
        """Return queue statistics for monitoring.

        Returns:
            dict: Statistics including:
                - total_items: Total entries in queue
                - ready_for_retry: Entries ready now
                - awaiting_backoff: Entries waiting for backoff
                - exhausted: Entries at max retries
                - by_failure_reason: Count by error type
        """
        entries = self._read_all()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        return {
            "total_items": len(entries),
            "ready_for_retry": sum(
                1
                for e in entries
                if e["next_retry_at"] <= now and e["retry_count"] < e["max_retries"]
            ),
            "awaiting_backoff": sum(
                1
                for e in entries
                if e["next_retry_at"] > now and e["retry_count"] < e["max_retries"]
            ),
            "exhausted": sum(1 for e in entries if e["retry_count"] >= e["max_retries"]),
            "by_failure_reason": self._count_by_reason(entries),
        }

    def _count_by_reason(self, entries: list[dict]) -> dict:
        """Count entries by failure reason.

        Args:
            entries: List of queue entries

        Returns:
            dict: {reason: count}
        """
        counts = {}
        for e in entries:
            reason = e.get("failure_reason", "unknown")
            counts[reason] = counts.get(reason, 0) + 1
        return counts

    def _locked_read_modify_write(self):
        """Context manager for locked read-modify-write operations.

        Acquires exclusive lock, reads entries, yields entries + write function,
        and ensures write completes before releasing lock.

        Returns:
            LockedReadModifyWrite: Context manager for atomic RMW operations
        """
        return LockedReadModifyWrite(self.queue_path)

    def _locked_append(self):
        """Context manager for locked file append.

        Returns:
            LockedFileAppend: Context manager for append with exclusive lock
        """
        return LockedFileAppend(self.queue_path)

    def _read_all(self) -> list[dict]:
        """Read all entries from queue file.

        Handles:
        - Missing file (returns empty list)
        - Corrupt JSON lines (skips with warning)

        Returns:
            list: All queue entries as dicts
        """
        if not self.queue_path.exists():
            return []

        entries = []
        with open(self.queue_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(
                            "corrupt_queue_entry", extra={"line": line[:50]}
                        )
        return entries

    def _write_all(self, entries: list[dict]) -> None:
        """Write all entries to queue file (atomic).

        Uses temp file + atomic rename for crash safety.
        Thread-safe: Uses unique temp file per write operation.

        Args:
            entries: List of queue entry dicts
        """
        # Use unique temp file name for concurrent safety
        fd, tmp_path_str = tempfile.mkstemp(
            dir=self.queue_path.parent, prefix=".queue_", suffix=".tmp"
        )
        tmp_path = Path(tmp_path_str)

        try:
            with os.fdopen(fd, "w") as f:
                for entry in entries:
                    f.write(json.dumps(entry) + "\n")
            tmp_path.replace(self.queue_path)  # Atomic rename
            os.chmod(self.queue_path, 0o600)
        except Exception:
            # Clean up temp file on error
            if tmp_path.exists():
                tmp_path.unlink()
            raise


class LockedFileAppend:
    """Context manager for locked file append operations.

    Uses fcntl.flock for exclusive locking.

    Example:
        with LockedFileAppend(path) as f:
            f.write("data\\n")
    """

    def __init__(self, path: Path):
        """Initialize with file path.

        Args:
            path: Path to file to append
        """
        self.path = path
        self.file = None

    def __enter__(self):
        """Open file and acquire exclusive lock with timeout.

        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout (AC 5.1.4)
        """
        self.file = open(self.path, "a")
        if not _acquire_lock_with_timeout(self.file.fileno()):
            self.file.close()
            self.file = None
            raise LockTimeoutError(
                f"Failed to acquire lock on {self.path} within {LOCK_TIMEOUT_SECONDS}s"
            )
        return self.file

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release lock and close file."""
        if self.file:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()


class LockedReadModifyWrite:
    """Context manager for locked read-modify-write operations.

    Acquires exclusive lock, reads all entries, yields entries + write function,
    and ensures atomic write before releasing lock.

    Example:
        with LockedReadModifyWrite(path) as (entries, write_fn):
            # Modify entries
            entries = [e for e in entries if e["id"] != "remove-me"]
            # Write atomically
            write_fn(entries)
    """

    def __init__(self, path: Path):
        """Initialize with file path.

        Args:
            path: Path to queue file
        """
        self.path = path
        self.lock_file = None
        self.entries = []

    def __enter__(self):
        """Acquire lock, read entries, and yield (entries, write_fn).

        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout (AC 5.1.4)
        """
        # Open file for reading and acquire exclusive lock
        # Use 'r+' mode to allow both read and lock on same file descriptor
        if not self.path.exists():
            # Create empty file if doesn't exist
            self.path.touch()
            os.chmod(self.path, 0o600)

        self.lock_file = open(self.path, "r+")
        if not _acquire_lock_with_timeout(self.lock_file.fileno()):
            self.lock_file.close()
            self.lock_file = None
            raise LockTimeoutError(
                f"Failed to acquire lock on {self.path} within {LOCK_TIMEOUT_SECONDS}s"
            )

        # Read all entries
        self.entries = []
        for line in self.lock_file:
            line = line.strip()
            if line:
                try:
                    self.entries.append(json.loads(line))
                except json.JSONDecodeError:
                    # Skip corrupt lines (logged elsewhere)
                    pass

        # Return entries and write function
        return (self.entries, self._write_entries)

    def _write_entries(self, entries: list[dict]) -> None:
        """Write entries directly to file while holding lock.

        Args:
            entries: List of queue entry dicts to write
        """
        # Truncate file and write from beginning
        # We're already holding the lock, so this is safe
        self.lock_file.seek(0)
        self.lock_file.truncate()
        for entry in entries:
            self.lock_file.write(json.dumps(entry) + "\n")
        self.lock_file.flush()
        os.fsync(self.lock_file.fileno())

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release lock and close file."""
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()


def queue_operation(data: dict, reason: str = "HOOK_STORAGE_FAILED", immediate: bool = False) -> bool:
    """Queue a memory operation for later retry.

    Simple wrapper for hooks that need to queue failed operations.
    Provides graceful degradation by never raising exceptions.

    Enhanced in CR-1.3 to consolidate queue_to_file() from hook scripts.

    Args:
        data: Dictionary with memory operation data (content, group_id, etc.)
        reason: Failure reason code (default: "HOOK_STORAGE_FAILED")
                Examples: "qdrant_unavailable", "timeout", "embedding_failed"
        immediate: If True, queued item is immediately ready for retry (no backoff)

    Returns:
        True if queued successfully, False on any error
    """
    try:
        queue = MemoryQueue()
        queue.enqueue(data, reason, immediate=immediate)
        return True
    except Exception as e:
        # Graceful degradation: log error but never crash
        logger.error(
            "queue_operation_failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return False


# Export public API
__all__ = [
    "MemoryQueue",
    "QueueEntry",
    "LockedFileAppend",
    "LockedReadModifyWrite",
    "LockTimeoutError",
    "LOCK_TIMEOUT_SECONDS",
    "queue_operation",
]
