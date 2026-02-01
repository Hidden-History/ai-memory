"""Unit tests for memory queue module.

Tests cover QueueEntry dataclass and MemoryQueue class operations including:
- Queue entry creation and backoff calculation
- Enqueue/dequeue operations
- File locking and concurrent access
- Atomic write operations
- Queue statistics and filtering

Follows Story 5.1 acceptance criteria and 2026 best practices.
"""

import fcntl
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.memory.queue import (
    LockedFileAppend,
    LockedReadModifyWrite,
    LockTimeoutError,
    MemoryQueue,
    QueueEntry,
    _acquire_lock_with_timeout,
)


class TestQueueEntry:
    """Tests for QueueEntry dataclass."""

    def test_queue_entry_initialization_with_defaults(self):
        """Test QueueEntry initializes with automatic timestamps."""
        entry = QueueEntry(
            id=str(uuid.uuid4()), memory_data={"content": "test"}, failure_reason="TEST"
        )

        assert entry.id is not None
        assert entry.memory_data == {"content": "test"}
        assert entry.failure_reason == "TEST"
        assert entry.retry_count == 0
        assert entry.max_retries == 3
        assert entry.queued_at.endswith("Z")
        assert entry.next_retry_at.endswith("Z")

    def test_queue_entry_backoff_first_retry(self):
        """Test first retry uses 1 minute delay."""
        entry = QueueEntry(
            id="test-id",
            memory_data={"content": "test"},
            failure_reason="TEST",
            retry_count=0,
        )

        # Parse timestamps
        queued = datetime.fromisoformat(entry.queued_at.replace("Z", ""))
        next_retry = datetime.fromisoformat(entry.next_retry_at.replace("Z", ""))

        # Should be ~1 minute apart
        delta = (next_retry - queued).total_seconds()
        assert 58 <= delta <= 62, f"Expected ~60s, got {delta}s"

    def test_queue_entry_backoff_second_retry(self):
        """Test second retry uses 5 minute delay."""
        entry = QueueEntry(
            id="test-id",
            memory_data={"content": "test"},
            failure_reason="TEST",
            retry_count=1,
        )

        # Calculate next retry manually
        next_retry_calculated = entry._calculate_next_retry()

        # Parse timestamps
        queued = datetime.fromisoformat(entry.queued_at.replace("Z", ""))
        next_retry = datetime.fromisoformat(next_retry_calculated.replace("Z", ""))

        # Should be ~5 minutes apart
        delta = (next_retry - queued).total_seconds()
        assert 298 <= delta <= 302, f"Expected ~300s (5min), got {delta}s"

    def test_queue_entry_backoff_third_retry(self):
        """Test third retry uses 15 minute delay (capped)."""
        entry = QueueEntry(
            id="test-id",
            memory_data={"content": "test"},
            failure_reason="TEST",
            retry_count=2,
        )

        # Calculate next retry manually
        next_retry_calculated = entry._calculate_next_retry()

        # Parse timestamps
        queued = datetime.fromisoformat(entry.queued_at.replace("Z", ""))
        next_retry = datetime.fromisoformat(next_retry_calculated.replace("Z", ""))

        # Should be ~15 minutes apart
        delta = (next_retry - queued).total_seconds()
        assert 898 <= delta <= 902, f"Expected ~900s (15min), got {delta}s"

    def test_queue_entry_backoff_max_capped(self):
        """Test backoff stays at 15 minutes after max retries."""
        entry = QueueEntry(
            id="test-id",
            memory_data={"content": "test"},
            failure_reason="TEST",
            retry_count=5,  # Beyond max_retries
        )

        # Calculate next retry manually
        next_retry_calculated = entry._calculate_next_retry()

        # Parse timestamps
        queued = datetime.fromisoformat(entry.queued_at.replace("Z", ""))
        next_retry = datetime.fromisoformat(next_retry_calculated.replace("Z", ""))

        # Should still be 15 minutes (capped)
        delta = (next_retry - queued).total_seconds()
        assert 898 <= delta <= 902, f"Expected ~900s (15min), got {delta}s"


class TestMemoryQueue:
    """Tests for MemoryQueue class."""

    @pytest.fixture
    def queue_path(self, tmp_path):
        """Provide temporary queue file path."""
        return tmp_path / "test_queue.jsonl"

    @pytest.fixture
    def queue(self, queue_path):
        """Provide MemoryQueue instance with temporary path."""
        return MemoryQueue(queue_path=str(queue_path))

    def test_queue_initialization(self, queue, queue_path):
        """Test MemoryQueue initializes correctly."""
        assert queue.queue_path == queue_path
        assert queue_path.parent.exists()
        # Check directory permissions are 0700
        dir_stat = os.stat(queue_path.parent)
        assert oct(dir_stat.st_mode)[-3:] == "700"

    def test_enqueue_creates_file_with_permissions(self, queue, queue_path):
        """Test enqueue creates queue file with 0600 permissions."""
        memory_data = {
            "content": "test implementation",
            "group_id": "test-project",
            "type": "implementation",
        }

        queue_id = queue.enqueue(memory_data, "QDRANT_UNAVAILABLE")

        assert isinstance(queue_id, str)
        assert queue_path.exists()

        # Check file permissions are 0600
        file_stat = os.stat(queue_path)
        assert oct(file_stat.st_mode)[-3:] == "600"

    def test_enqueue_returns_uuid(self, queue):
        """Test enqueue returns valid UUID string."""
        memory_data = {"content": "test"}
        queue_id = queue.enqueue(memory_data, "TEST")

        # Should be valid UUID
        uuid.UUID(queue_id)  # Raises ValueError if invalid

    def test_enqueue_writes_valid_jsonl(self, queue, queue_path):
        """Test enqueue writes valid JSONL format."""
        memory_data = {"content": "test"}
        queue_id = queue.enqueue(memory_data, "TEST")

        # Read raw file
        with open(queue_path) as f:
            line = f.readline()

        # Should be valid JSON
        entry = json.loads(line)
        assert entry["id"] == queue_id
        assert entry["memory_data"] == memory_data
        assert entry["failure_reason"] == "TEST"

    def test_dequeue_removes_entry(self, queue):
        """Test dequeue removes entry from queue."""
        memory_data = {"content": "test"}
        queue_id = queue.enqueue(memory_data, "TEST")

        # Verify entry exists
        entries = queue._read_all()
        assert len(entries) == 1

        # Dequeue
        queue.dequeue(queue_id)

        # Verify entry removed
        entries = queue._read_all()
        assert len(entries) == 0

    def test_dequeue_nonexistent_id_no_error(self, queue):
        """Test dequeue with non-existent ID doesn't error."""
        # Should not raise
        queue.dequeue("non-existent-id")

    def test_get_pending_filters_by_time(self, queue):
        """Test get_pending returns only items ready for retry."""
        # Create entry with past retry time
        past_entry = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data={"content": "past"},
            failure_reason="TEST",
            retry_count=0,
        )
        # Manually set next_retry_at to past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        past_entry.next_retry_at = past_time.isoformat() + "Z"

        # Create entry with future retry time
        future_entry = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data={"content": "future"},
            failure_reason="TEST",
            retry_count=0,
        )
        # Manually set next_retry_at to future
        future_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        future_entry.next_retry_at = future_time.isoformat() + "Z"

        # Write both to queue
        from dataclasses import asdict

        queue._write_all([asdict(past_entry), asdict(future_entry)])

        # Get pending
        pending = queue.get_pending()

        # Should only return past entry
        assert len(pending) == 1
        assert pending[0]["id"] == past_entry.id

    def test_get_pending_respects_limit(self, queue):
        """Test get_pending respects limit parameter."""
        # Create 5 entries all ready for retry
        entries = []
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        for i in range(5):
            entry = QueueEntry(
                id=str(uuid.uuid4()),
                memory_data={"content": f"test {i}"},
                failure_reason="TEST",
                retry_count=0,
            )
            entry.next_retry_at = past_time.isoformat() + "Z"
            entries.append(entry)

        from dataclasses import asdict

        queue._write_all([asdict(e) for e in entries])

        # Get pending with limit
        pending = queue.get_pending(limit=3)

        assert len(pending) == 3

    def test_get_pending_excludes_exhausted(self, queue):
        """Test get_pending excludes entries at max retries."""
        # Create entry at max retries
        exhausted_entry = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data={"content": "exhausted"},
            failure_reason="TEST",
            retry_count=3,  # At max
            max_retries=3,
        )
        # Set to past time
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        exhausted_entry.next_retry_at = past_time.isoformat() + "Z"

        from dataclasses import asdict

        queue._write_all([asdict(exhausted_entry)])

        # Get pending
        pending = queue.get_pending()

        # Should be empty (exhausted)
        assert len(pending) == 0

    def test_mark_failed_increments_retry_count(self, queue):
        """Test mark_failed increments retry_count."""
        memory_data = {"content": "test"}
        queue_id = queue.enqueue(memory_data, "TEST")

        # Mark failed
        queue.mark_failed(queue_id)

        # Read entry
        entries = queue._read_all()
        entry = entries[0]

        assert entry["retry_count"] == 1

    def test_mark_failed_updates_next_retry_with_backoff(self, queue):
        """Test mark_failed updates next_retry_at with exponential backoff."""
        memory_data = {"content": "test"}
        queue_id = queue.enqueue(memory_data, "TEST")

        # Get initial next_retry_at
        entries = queue._read_all()
        initial_next_retry = entries[0]["next_retry_at"]

        # Mark failed (should move to 5 minute backoff)
        queue.mark_failed(queue_id)

        # Get updated next_retry_at
        entries = queue._read_all()
        updated_next_retry = entries[0]["next_retry_at"]

        # Parse timestamps
        initial = datetime.fromisoformat(initial_next_retry.replace("Z", ""))
        updated = datetime.fromisoformat(updated_next_retry.replace("Z", ""))

        # Updated should be later (5 minutes vs 1 minute from now)
        assert updated > initial

    def test_get_stats_returns_correct_counts(self, queue):
        """Test get_stats returns accurate queue statistics."""
        # Create mixed entries
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=5)

        entries = []

        # Ready for retry
        ready = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data={"content": "ready"},
            failure_reason="QDRANT_UNAVAILABLE",
            retry_count=0,
        )
        ready.next_retry_at = past_time.isoformat() + "Z"
        entries.append(ready)

        # Awaiting backoff
        awaiting = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data={"content": "awaiting"},
            failure_reason="EMBEDDING_TIMEOUT",
            retry_count=1,
        )
        awaiting.next_retry_at = future_time.isoformat() + "Z"
        entries.append(awaiting)

        # Exhausted
        exhausted = QueueEntry(
            id=str(uuid.uuid4()),
            memory_data={"content": "exhausted"},
            failure_reason="QDRANT_UNAVAILABLE",
            retry_count=3,
            max_retries=3,
        )
        exhausted.next_retry_at = past_time.isoformat() + "Z"
        entries.append(exhausted)

        from dataclasses import asdict

        queue._write_all([asdict(e) for e in entries])

        # Get stats
        stats = queue.get_stats()

        assert stats["total_items"] == 3
        assert stats["ready_for_retry"] == 1
        assert stats["awaiting_backoff"] == 1
        assert stats["exhausted"] == 1
        assert stats["by_failure_reason"]["QDRANT_UNAVAILABLE"] == 2
        assert stats["by_failure_reason"]["EMBEDDING_TIMEOUT"] == 1

    def test_read_all_handles_corrupt_entry(self, queue, queue_path):
        """Test _read_all skips corrupt JSON lines."""
        # Write mixed valid and corrupt entries
        with open(queue_path, "w") as f:
            f.write('{"id": "valid-1", "memory_data": {}, "failure_reason": "TEST"}\n')
            f.write("CORRUPT JSON LINE\n")
            f.write('{"id": "valid-2", "memory_data": {}, "failure_reason": "TEST"}\n')

        # Read all
        entries = queue._read_all()

        # Should skip corrupt line
        assert len(entries) == 2
        assert entries[0]["id"] == "valid-1"
        assert entries[1]["id"] == "valid-2"

    def test_read_all_handles_empty_file(self, queue, queue_path):
        """Test _read_all handles empty queue file."""
        # Create empty file
        queue_path.touch()

        entries = queue._read_all()

        assert entries == []

    def test_write_all_uses_atomic_rename(self, queue, queue_path):
        """Test _write_all uses atomic rename pattern."""
        entries = [
            {"id": "test-1", "memory_data": {}, "failure_reason": "TEST"},
            {"id": "test-2", "memory_data": {}, "failure_reason": "TEST"},
        ]

        queue._write_all(entries)

        # Verify file exists and has correct content
        assert queue_path.exists()
        with open(queue_path) as f:
            lines = f.readlines()
        assert len(lines) == 2

        # Verify temp file is cleaned up
        tmp_path = queue_path.with_suffix(".tmp")
        assert not tmp_path.exists()

    def test_write_all_sets_file_permissions(self, queue, queue_path):
        """Test _write_all sets 0600 permissions."""
        entries = [{"id": "test", "memory_data": {}, "failure_reason": "TEST"}]

        queue._write_all(entries)

        file_stat = os.stat(queue_path)
        assert oct(file_stat.st_mode)[-3:] == "600"


class TestLockTimeout:
    """Tests for lock timeout behavior per AC 5.1.4."""

    def test_acquire_lock_with_timeout_success(self, tmp_path):
        """Test lock acquisition succeeds when no contention."""
        queue_file = tmp_path / "test_queue.jsonl"
        queue_file.touch()

        with open(queue_file, "r+") as f:
            result = _acquire_lock_with_timeout(f.fileno(), timeout_seconds=0.5)
            assert result is True
            # Release lock
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def test_acquire_lock_with_timeout_failure(self, tmp_path):
        """Test lock acquisition fails after timeout when contention exists."""
        queue_file = tmp_path / "test_queue.jsonl"
        queue_file.touch()

        # Hold lock in blocking handle
        with open(queue_file, "r+") as blocking_handle:
            fcntl.flock(blocking_handle.fileno(), fcntl.LOCK_EX)

            # Attempt to acquire lock with short timeout - should fail
            with open(queue_file, "r+") as contending_handle:
                start = time.time()
                result = _acquire_lock_with_timeout(
                    contending_handle.fileno(), timeout_seconds=0.3
                )
                elapsed = time.time() - start

                assert result is False
                # Should have waited approximately the timeout duration
                assert 0.25 <= elapsed <= 0.5

    def test_locked_file_append_raises_timeout_error(self, tmp_path):
        """AC 5.1.4: LockedFileAppend raises LockTimeoutError on timeout."""
        queue_file = tmp_path / "test_queue.jsonl"
        queue_file.touch()

        # Hold lock in blocking handle
        with open(queue_file, "r+") as blocking_handle:
            fcntl.flock(blocking_handle.fileno(), fcntl.LOCK_EX)

            # Patch timeout to be short for test speed
            with (
                patch("src.memory.queue.LOCK_TIMEOUT_SECONDS", 0.3),
                pytest.raises(LockTimeoutError) as exc_info,
                LockedFileAppend(queue_file),
            ):
                pass  # Should not reach here

            assert "Failed to acquire lock" in str(exc_info.value)

    def test_locked_read_modify_write_raises_timeout_error(self, tmp_path):
        """AC 5.1.4: LockedReadModifyWrite raises LockTimeoutError on timeout."""
        queue_file = tmp_path / "test_queue.jsonl"
        queue_file.touch()

        # Hold lock in blocking handle
        with open(queue_file, "r+") as blocking_handle:
            fcntl.flock(blocking_handle.fileno(), fcntl.LOCK_EX)

            # Patch timeout to be short for test speed
            with (
                patch("src.memory.queue.LOCK_TIMEOUT_SECONDS", 0.3),
                pytest.raises(LockTimeoutError) as exc_info,
                LockedReadModifyWrite(queue_file) as (_entries, _write_fn),
            ):
                pass  # Should not reach here

            assert "Failed to acquire lock" in str(exc_info.value)

    def test_enqueue_raises_timeout_on_lock_contention(self, tmp_path):
        """AC 5.1.4: enqueue raises LockTimeoutError when lock held."""
        queue_file = tmp_path / "test_queue.jsonl"
        queue_file.touch()  # Create file before opening
        queue = MemoryQueue(queue_path=str(queue_file))

        # Hold lock in blocking handle
        with open(queue_file, "r+") as blocking_handle:
            fcntl.flock(blocking_handle.fileno(), fcntl.LOCK_EX)

            # Patch timeout to be short for test speed
            with (
                patch("src.memory.queue.LOCK_TIMEOUT_SECONDS", 0.3),
                pytest.raises(LockTimeoutError),
            ):
                queue.enqueue({"content": "test"}, "TEST")

    def test_dequeue_raises_timeout_on_lock_contention(self, tmp_path):
        """AC 5.1.4: dequeue raises LockTimeoutError when lock held."""
        queue_file = tmp_path / "test_queue.jsonl"
        queue = MemoryQueue(queue_path=str(queue_file))

        # Enqueue an item first (no contention)
        queue_id = queue.enqueue({"content": "test"}, "TEST")

        # Hold lock in blocking handle
        with open(queue_file, "r+") as blocking_handle:
            fcntl.flock(blocking_handle.fileno(), fcntl.LOCK_EX)

            # Patch timeout to be short for test speed
            with (
                patch("src.memory.queue.LOCK_TIMEOUT_SECONDS", 0.3),
                pytest.raises(LockTimeoutError),
            ):
                queue.dequeue(queue_id)
