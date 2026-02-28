"""Classification queue for async processing.

Uses file-based queue (not Redis) for simplicity.
Queue file: ~/.ai-memory/queue/classification_queue.jsonl

RESOURCE LIMITS:
- File locking timeout: 5 seconds
- Max batch size: 10 items
- No unbounded loops
"""

import fcntl
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("ai_memory.classifier.queue")

# Queue location (configurable via env for Docker deployment)
_default_queue_dir = os.path.expanduser("~/.ai-memory/queue")
QUEUE_DIR = Path(os.environ.get("AI_MEMORY_QUEUE_DIR", _default_queue_dir))
QUEUE_FILE = QUEUE_DIR / "classification_queue.jsonl"

# Resource limits
MAX_BATCH_SIZE = 10
LOCK_TIMEOUT_SECONDS = 5.0

__all__ = [
    "MAX_BATCH_SIZE",
    "QUEUE_DIR",
    "QUEUE_FILE",
    "ClassificationTask",
    "clear_queue",
    "dequeue_batch",
    "enqueue_for_classification",
    "get_queue_size",
]


@dataclass
class ClassificationTask:
    """Task in the classification queue."""

    point_id: str
    collection: str
    content: str
    current_type: str
    group_id: str
    source_hook: str
    created_at: str
    retry_count: int = 0
    last_error: str | None = None
    trace_id: str | None = None
    session_id: str | None = None  # Wave 1H: Propagate session_id to 9_classify trace


def _acquire_lock(file_handle, timeout: float = LOCK_TIMEOUT_SECONDS) -> bool:
    """Acquire file lock with timeout. Returns True if acquired."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            fcntl.flock(file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            time.sleep(0.1)
    return False


def _release_lock(file_handle) -> None:
    """Release file lock."""
    try:
        fcntl.flock(file_handle, fcntl.LOCK_UN)
    except Exception as e:
        logger.warning("lock_release_failed", extra={"error": str(e)})


def enqueue_for_classification(task: ClassificationTask) -> bool:
    """Add task to classification queue (thread-safe with file locking).

    Returns:
        True if enqueued successfully, False otherwise
    """
    try:
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        with open(QUEUE_FILE, "a") as f:
            if not _acquire_lock(f):
                logger.warning("queue_lock_timeout", extra={"point_id": task.point_id})
                return False
            try:
                f.write(json.dumps(asdict(task)) + "\n")
                return True
            finally:
                _release_lock(f)
    except Exception as e:
        logger.error(
            "enqueue_failed", extra={"error": str(e), "point_id": task.point_id}
        )
        return False


def dequeue_batch(batch_size: int = MAX_BATCH_SIZE) -> list[ClassificationTask]:
    """Get batch of tasks from queue (FIFO, thread-safe, atomic).

    Uses atomic temp file + rename to prevent queue corruption on crash.
    Invalid JSON entries are preserved for manual inspection.

    Args:
        batch_size: Max items to return (capped at MAX_BATCH_SIZE)

    Returns:
        List of ClassificationTask objects
    """
    batch_size = min(batch_size, MAX_BATCH_SIZE)  # Enforce cap

    if not QUEUE_FILE.exists():
        return []

    tasks: list[ClassificationTask] = []
    remaining_lines: list[str] = []

    try:
        with open(QUEUE_FILE, "r+") as f:
            if not _acquire_lock(f):
                logger.warning("dequeue_lock_timeout")
                return []

            try:
                lines = f.readlines()

                # Parse all lines first (transaction-like semantics)
                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        continue

                    if len(tasks) < batch_size:
                        try:
                            data = json.loads(line)
                            task = ClassificationTask(**data)
                            tasks.append(task)
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.warning(
                                "invalid_queue_entry",
                                extra={"line": i, "error": str(e)},
                            )
                            # Keep invalid entries for manual inspection
                            remaining_lines.append(line + "\n")
                    else:
                        remaining_lines.append(line + "\n")

                # Atomic update: write to temp file, then rename
                # Only modify queue if we successfully dequeued something
                if tasks:
                    temp_file = QUEUE_FILE.with_suffix(".tmp")
                    temp_file.write_text("".join(remaining_lines))
                    temp_file.rename(QUEUE_FILE)

            finally:
                _release_lock(f)

    except Exception as e:
        logger.error("dequeue_batch_failed", extra={"error": str(e)})
        return []

    logger.info(
        "batch_dequeued", extra={"count": len(tasks), "remaining": len(remaining_lines)}
    )
    return tasks


def get_queue_size() -> int:
    """Get current queue size for metrics."""
    if not QUEUE_FILE.exists():
        return 0
    try:
        with open(QUEUE_FILE) as f:
            return sum(1 for _ in f)
    except Exception as e:
        logger.warning("queue_size_check_failed", extra={"error": str(e)})
        return 0


def clear_queue() -> int:
    """Clear all items from queue. Returns count of cleared items."""
    if not QUEUE_FILE.exists():
        return 0
    try:
        count = get_queue_size()
        QUEUE_FILE.unlink()
        return count
    except Exception as e:
        logger.warning("queue_clear_failed", extra={"error": str(e)})
        return 0
