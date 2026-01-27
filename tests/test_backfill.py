"""Unit tests for backfill script functions.

Tests Task 6.1-6.3 from Story 5.2:
- acquire_lock() behavior (success, conflict)
- process_queue_item() success path
- process_queue_item() failure paths (retryable, unexpected)

Per project-context.md:
- Test location: tests/ (root level)
- Naming: test_*.py prefix
- Coverage target: >90%
"""

import fcntl
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Import backfill module functions
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "memory"))
import backfill_embeddings as backfill

from memory.queue import MemoryQueue
from memory.storage import MemoryStorage
from memory.qdrant_client import QdrantUnavailable
from memory.embeddings import EmbeddingError


class TestAcquireLock:
    """Test file locking functionality (Task 6.1)."""

    def test_acquire_lock_success(self, tmp_path):
        """Test successful lock acquisition.

        AC 5.2.4: Non-blocking lock acquisition succeeds when no conflict.
        """
        lock_file = tmp_path / "test.lock"

        with patch.object(backfill, "LOCK_FILE", lock_file):
            result = backfill.acquire_lock()

        assert result is True
        assert lock_file.exists()

    def test_acquire_lock_conflict(self, tmp_path):
        """Test lock acquisition failure when file already locked.

        AC 5.2.4: Non-blocking lock returns False immediately on conflict.

        Per 2025/2026 best practices: LOCK_NB flag ensures immediate return
        without blocking, critical for cron scripts.
        """
        lock_file = tmp_path / "test.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Acquire lock in outer context (simulates another process)
        with open(lock_file, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

            # Try to acquire in inner context (should fail immediately)
            with patch.object(backfill, "LOCK_FILE", lock_file):
                result = backfill.acquire_lock()

            assert result is False

    def test_acquire_lock_creates_parent_directory(self, tmp_path):
        """Test lock acquisition creates parent directory if missing.

        AC 5.2.4: Lock file path uses ~/.claude-memory/ which may not exist
        on first run.
        """
        lock_file = tmp_path / "nonexistent" / "dir" / "test.lock"

        with patch.object(backfill, "LOCK_FILE", lock_file):
            result = backfill.acquire_lock()

        assert result is True
        assert lock_file.parent.exists()
        assert lock_file.exists()


class TestProcessQueueItem:
    """Test queue item processing (Task 6.2, 6.3)."""

    def test_process_queue_item_success(self, mocker):
        """Test successful queue item processing.

        AC 5.2.1: Success path dequeues item and logs.
        AC 5.2.2: Calls storage.store_memory() with all required fields.
        """
        # Mock storage
        mock_storage = mocker.MagicMock(spec=MemoryStorage)
        mock_storage.store_memory.return_value = {
            "memory_id": "test-memory-id",
            "status": "stored",
            "embedding_status": "complete"
        }

        # Mock queue
        mock_queue = mocker.MagicMock(spec=MemoryQueue)

        # Sample queue entry
        item = {
            "id": "queue-id-123",
            "retry_count": 0,
            "memory_data": {
                "content": "test implementation code",
                "group_id": "test-project",
                "type": "implementation",
                "source_hook": "PostToolUse",
                "session_id": "sess-456"
            }
        }

        # Process item
        result = backfill.process_queue_item(item, mock_storage, mock_queue)

        # Verify success
        assert result is True

        # Verify storage called correctly
        mock_storage.store_memory.assert_called_once()
        call_kwargs = mock_storage.store_memory.call_args[1]
        assert call_kwargs["content"] == "test implementation code"
        assert call_kwargs["group_id"] == "test-project"
        assert call_kwargs["memory_type"] == "implementation"
        assert call_kwargs["source_hook"] == "PostToolUse"
        assert call_kwargs["collection"] == "code-patterns"

        # Verify dequeue called
        mock_queue.dequeue.assert_called_once_with("queue-id-123")

    def test_process_queue_item_qdrant_unavailable(self, mocker):
        """Test handling of Qdrant unavailable error.

        AC 5.2.1: Failed items have retry_count incremented.
        Per user requirements: "no fallbacks, know when error happens"
        - Must log warning (not silent)
        - Must mark_failed (increments retry)
        - Must return False (signals failure)
        """
        # Mock storage that raises QdrantUnavailable
        mock_storage = mocker.MagicMock(spec=MemoryStorage)
        mock_storage.store_memory.side_effect = QdrantUnavailable("Qdrant unreachable")

        # Mock queue
        mock_queue = mocker.MagicMock(spec=MemoryQueue)

        # Sample queue entry
        item = {
            "id": "queue-id-456",
            "retry_count": 1,
            "memory_data": {
                "content": "test",
                "group_id": "proj",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "sess"
            }
        }

        # Mock logger to verify warning
        mock_logger = mocker.patch.object(backfill, "logger")
        result = backfill.process_queue_item(item, mock_storage, mock_queue)

        # Verify failure handling
        assert result is False
        mock_queue.mark_failed.assert_called_once_with("queue-id-456")
        mock_queue.dequeue.assert_not_called()

        # Verify warning logged (not silent)
        assert mock_logger.warning.called
        warning_call = mock_logger.warning.call_args
        assert warning_call[0][0] == "backfill_retry_scheduled"

    def test_process_queue_item_embedding_error(self, mocker):
        """Test handling of embedding timeout error.

        AC 5.2.1: Embedding failures also trigger retry.
        """
        # Mock storage that raises EmbeddingError
        mock_storage = mocker.MagicMock(spec=MemoryStorage)
        mock_storage.store_memory.side_effect = EmbeddingError("Timeout generating embedding")

        # Mock queue
        mock_queue = mocker.MagicMock(spec=MemoryQueue)

        item = {
            "id": "queue-id-789",
            "retry_count": 0,
            "memory_data": {
                "content": "test",
                "group_id": "proj",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "sess"
            }
        }

        result = backfill.process_queue_item(item, mock_storage, mock_queue)

        # Verify retry scheduled
        assert result is False
        mock_queue.mark_failed.assert_called_once_with("queue-id-789")

    def test_process_queue_item_unexpected_error(self, mocker):
        """Test handling of unexpected errors.

        Per user requirements: "no fallbacks, know when error happens"
        Unexpected errors (bugs, corrupt data) should:
        - Log with traceback (logger.exception)
        - NOT mark_failed (might repeat bug)
        - Return False
        """
        # Mock storage that raises unexpected error
        mock_storage = mocker.MagicMock(spec=MemoryStorage)
        mock_storage.store_memory.side_effect = ValueError("Unexpected validation error")

        # Mock queue
        mock_queue = mocker.MagicMock(spec=MemoryQueue)

        item = {
            "id": "queue-id-999",
            "retry_count": 2,
            "memory_data": {
                "content": "test",
                "group_id": "proj",
                "type": "implementation",
                "source_hook": "test",
                "session_id": "sess"
            }
        }

        # Mock logger to verify exception logging
        mock_logger = mocker.patch.object(backfill, "logger")
        result = backfill.process_queue_item(item, mock_storage, mock_queue)

        # Verify error handling
        assert result is False
        mock_queue.mark_failed.assert_not_called()  # Don't mark_failed for bugs
        mock_queue.dequeue.assert_not_called()

        # Verify exception logged (not just warning)
        assert mock_logger.exception.called
        exception_call = mock_logger.exception.call_args
        assert exception_call[0][0] == "backfill_unexpected_error"


class TestValidateLimit:
    """Test CLI argument validation (Task 6.4)."""

    def test_validate_limit_valid_values(self):
        """Test validation accepts valid limit values."""
        assert backfill.validate_limit("1") == 1
        assert backfill.validate_limit("50") == 50
        assert backfill.validate_limit("1000") == 1000

    def test_validate_limit_rejects_zero(self):
        """Test validation rejects zero."""
        with pytest.raises(Exception) as exc_info:
            backfill.validate_limit("0")
        assert "must be positive" in str(exc_info.value)

    def test_validate_limit_rejects_negative(self):
        """Test validation rejects negative values."""
        with pytest.raises(Exception) as exc_info:
            backfill.validate_limit("-5")
        assert "must be positive" in str(exc_info.value)

    def test_validate_limit_rejects_too_high(self):
        """Test validation rejects values over 1000.

        AC 5.2.3: Max limit 1000 to prevent overwhelming services.
        """
        with pytest.raises(Exception) as exc_info:
            backfill.validate_limit("1001")
        assert "too high" in str(exc_info.value)
        assert "1000" in str(exc_info.value)

    def test_validate_limit_rejects_non_integer(self):
        """Test validation rejects non-integer values."""
        with pytest.raises(Exception) as exc_info:
            backfill.validate_limit("fifty")
        assert "must be integer" in str(exc_info.value)

    def test_validate_limit_rejects_float(self):
        """Test validation rejects float values."""
        with pytest.raises(Exception) as exc_info:
            backfill.validate_limit("50.5")
        # argparse will reject this at parse time, not in validator
        # because int("50.5") raises ValueError
        assert "must be integer" in str(exc_info.value)
