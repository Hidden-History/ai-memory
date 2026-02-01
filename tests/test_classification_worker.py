"""Tests for classification worker startup and health check behavior.

F1: Unit tests for BUG-045 fix - health file creation at startup.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def mock_health_file(tmp_path):
    """Mock health file location for testing."""
    health_file = tmp_path / "worker.health"
    return health_file


@pytest.fixture
def mock_dependencies():
    """Mock external dependencies for worker tests."""
    with patch("scripts.memory.process_classification_queue.dequeue_batch") as mock_dequeue, \
         patch("scripts.memory.process_classification_queue.get_queue_size") as mock_queue_size, \
         patch("scripts.memory.process_classification_queue.push_metrics") as mock_metrics, \
         patch("scripts.memory.process_classification_queue.setup_hook_logging") as mock_logging:

        # Configure mocks
        mock_dequeue.return_value = []  # Empty queue
        mock_queue_size.return_value = 0
        mock_logging.return_value = MagicMock()

        yield {
            "dequeue": mock_dequeue,
            "queue_size": mock_queue_size,
            "metrics": mock_metrics,
            "logging": mock_logging
        }


class TestHealthFileCreation:
    """Tests for health file creation at worker startup (BUG-045)."""

    def test_touch_health_file_creates_file(self, tmp_path):
        """Test that _touch_health_file creates the health file."""
        from scripts.memory.process_classification_queue import _touch_health_file

        # Mock the health file path
        health_file = tmp_path / "worker.health"

        with patch("scripts.memory.process_classification_queue.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            _touch_health_file()

            # Verify touch() was called
            mock_path_instance.touch.assert_called_once()

    def test_touch_health_file_handles_errors_gracefully(self, tmp_path):
        """Test that _touch_health_file handles errors without crashing (graceful degradation)."""
        from scripts.memory.process_classification_queue import _touch_health_file

        with patch("scripts.memory.process_classification_queue.Path") as mock_path:
            # Simulate permission error
            mock_path_instance = MagicMock()
            mock_path_instance.touch.side_effect = PermissionError("Read-only filesystem")
            mock_path.return_value = mock_path_instance

            # Should not raise - graceful degradation
            try:
                _touch_health_file()
            except Exception as e:
                pytest.fail(f"_touch_health_file should not raise exceptions, got: {e}")

    def test_touch_health_file_logs_success(self, tmp_path, caplog):
        """Test that _touch_health_file logs success (F4 fix verification)."""
        import logging
        from scripts.memory.process_classification_queue import _touch_health_file

        health_file = tmp_path / "worker.health"

        # Set up logging to capture structured logs
        caplog.set_level(logging.DEBUG, logger="ai_memory.classifier.processor")

        with patch("scripts.memory.process_classification_queue.Path") as mock_path:
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance

            _touch_health_file()

            # F4: Verify success is logged (check both message and record name)
            log_messages = [record.getMessage() for record in caplog.records]
            assert any("health_file_updated" in msg for msg in log_messages)

    def test_touch_health_file_logs_failure(self, tmp_path, caplog):
        """Test that _touch_health_file logs failures (F3 fix verification)."""
        import logging
        from scripts.memory.process_classification_queue import _touch_health_file

        # Set up logging to capture structured logs
        caplog.set_level(logging.WARNING, logger="ai_memory.classifier.processor")

        with patch("scripts.memory.process_classification_queue.Path") as mock_path:
            # Simulate permission error
            mock_path_instance = MagicMock()
            mock_path_instance.touch.side_effect = PermissionError("Read-only filesystem")
            mock_path.return_value = mock_path_instance

            _touch_health_file()

            # F3: Verify failure is logged with warning
            log_messages = [record.getMessage() for record in caplog.records]
            assert any("health_file_update_failed" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_worker_creates_health_file_at_startup(self, tmp_path):
        """Test that ClassificationWorker.run() creates health file at startup (BUG-045 fix verification).

        This is the PRIMARY test for BUG-045 fix.
        """
        from scripts.memory.process_classification_queue import ClassificationWorker

        health_file = tmp_path / "worker.health"

        with patch("scripts.memory.process_classification_queue.Path") as mock_path, \
             patch("scripts.memory.process_classification_queue.setup_hook_logging") as mock_logging, \
             patch("scripts.memory.process_classification_queue.get_queue_size") as mock_queue_size, \
             patch.object(ClassificationWorker, "process_queue") as mock_process_queue:

            # Setup mocks
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_logging.return_value = MagicMock()
            mock_queue_size.return_value = 0

            # Make process_queue return immediately for test (use AsyncMock to avoid coroutine warning)
            mock_process_queue.side_effect = AsyncMock(return_value=None)

            worker = ClassificationWorker(batch_size=10, poll_interval=5.0)

            # Mock signal handler setup
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop_instance = MagicMock()
                mock_loop.return_value = mock_loop_instance

                # Run worker (will exit immediately due to mocked process_queue)
                await worker.run()

                # BUG-045 FIX VERIFICATION: Health file should be created (touch() called)
                mock_path_instance.touch.assert_called()

    @pytest.mark.asyncio
    async def test_worker_updates_health_file_after_batch(self, tmp_path):
        """Test that health file is updated after processing batches (existing behavior maintained)."""
        from scripts.memory.process_classification_queue import ClassificationWorker

        health_file = tmp_path / "worker.health"

        with patch("scripts.memory.process_classification_queue.Path") as mock_path, \
             patch("scripts.memory.process_classification_queue.setup_hook_logging") as mock_logging, \
             patch("scripts.memory.process_classification_queue.dequeue_batch") as mock_dequeue, \
             patch("scripts.memory.process_classification_queue.get_queue_size") as mock_queue_size, \
             patch("scripts.memory.process_classification_queue.push_metrics") as mock_metrics:

            # Setup mocks
            mock_path_instance = MagicMock()
            mock_path.return_value = mock_path_instance
            mock_logging.return_value = MagicMock()
            mock_queue_size.return_value = 0
            mock_dequeue.return_value = []  # Empty queue

            worker = ClassificationWorker(batch_size=10, poll_interval=0.1)

            # Start worker and let it run one iteration
            async def run_one_iteration():
                await worker.process_batch([])  # Empty batch

            await run_one_iteration()

            # Health file should be updated after batch processing
            assert mock_path_instance.touch.call_count >= 1


class TestWorkerConfiguration:
    """Tests for worker configuration and initialization."""

    def test_worker_initialization(self):
        """Test ClassificationWorker initializes with correct defaults."""
        from scripts.memory.process_classification_queue import ClassificationWorker

        worker = ClassificationWorker()

        assert worker.batch_size == 10
        assert worker.poll_interval == 5.0
        assert worker.consecutive_failures == 0
        assert worker.current_batch_task is None

    def test_worker_respects_batch_size_limit(self):
        """Test worker caps batch size at MAX_BATCH_SIZE."""
        from scripts.memory.process_classification_queue import ClassificationWorker, MAX_BATCH_SIZE

        # Try to create worker with oversized batch
        worker = ClassificationWorker(batch_size=9999)

        # Should be capped at MAX_BATCH_SIZE
        assert worker.batch_size <= MAX_BATCH_SIZE
