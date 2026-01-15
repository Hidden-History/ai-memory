"""Integration tests for graceful degradation with real services.

These tests verify graceful degradation patterns with actual Qdrant
and embedding service instances (or their absence).

Test Scenarios:
    - Hook execution with all services up
    - Hook execution with Qdrant down → queue_to_file
    - Hook execution with embedding down → pending_embedding
    - Hook execution with both down → passthrough
    - Queue file creation and replay

Requirements:
    - Docker services may or may not be running
    - Tests adapt to current service state (conditional)
    - Tests verify exit codes and behavior
    - Tests check queue file creation

Note:
    These are basic integration tests for MVP. Full integration testing
    with Docker Compose up/down orchestration can be added in Story 1.8.
"""

import pytest
import subprocess
import sys
import json
from pathlib import Path
from unittest.mock import patch


class TestGracefulDegradationIntegration:
    """Test graceful degradation with real service scenarios."""

    def test_example_hook_executes_successfully(self):
        """Example hook should execute and exit 0 or 1."""
        # Run example hook
        result = subprocess.run(
            [sys.executable, ".claude/hooks/scripts/example_hook.py"],
            capture_output=True,
            timeout=15  # 15s timeout (includes service health checks)
        )

        # Should exit 0 (success) or 1 (non-blocking error)
        # Depending on whether services are running
        assert result.returncode in [0, 1], \
            f"Unexpected exit code: {result.returncode}"

    def test_example_hook_never_exits_2(self):
        """Example hook should never exit 2 (blocking)."""
        # Run example hook multiple times
        for _ in range(3):
            result = subprocess.run(
                [sys.executable, ".claude/hooks/scripts/example_hook.py"],
                capture_output=True,
                timeout=15  # 15s timeout (includes service health checks)
            )

            # Never blocking error
            assert result.returncode != 2, \
                "Hook should never exit with blocking code 2"

    def test_hook_with_services_running(self):
        """Test hook behavior when services are available."""
        from src.memory.health import check_services

        health = check_services()

        if not health["all_healthy"]:
            pytest.skip("Services not running - cannot test normal mode")

        # Run hook with services up
        result = subprocess.run(
            [sys.executable, ".claude/hooks/scripts/example_hook.py"],
            capture_output=True,
            timeout=15  # 15s timeout (includes service health checks)
        )

        # Should exit 0 (success)
        assert result.returncode == 0
        # Should log normal mode
        assert b"normal" in result.stderr or b"normal" in result.stdout

    def test_queue_file_creation_when_qdrant_down(self, tmp_path, monkeypatch):
        """Test queue file creation when Qdrant unavailable."""
        # Monkeypatch queue location
        test_queue_dir = tmp_path / "queue"
        test_queue_file = test_queue_dir / "pending.jsonl"

        # We'll test queue_operation directly since we can't easily
        # control Docker services in CI/CD
        from src.memory.queue import queue_operation

        # Override queue paths
        import src.memory.queue
        original_queue_dir = src.memory.queue.QUEUE_DIR
        original_queue_file = src.memory.queue.QUEUE_FILE

        try:
            src.memory.queue.QUEUE_DIR = test_queue_dir
            src.memory.queue.QUEUE_FILE = test_queue_file

            # Queue test operation
            operation = {
                "content": "Integration test memory",
                "group_id": "integration-test",
                "type": "implementation",
                "timestamp": "2026-01-11T00:00:00Z"
            }

            result = queue_operation(operation)

            assert result is True
            assert test_queue_file.exists()

            # Verify queue file has correct permissions
            mode = test_queue_dir.stat().st_mode & 0o777
            assert mode == 0o700

            # Verify JSONL format
            with open(test_queue_file, "r") as f:
                lines = f.readlines()

            assert len(lines) == 1
            queued = json.loads(lines[0])
            assert queued["content"] == "Integration test memory"
            assert queued["group_id"] == "integration-test"

        finally:
            # Restore original paths
            src.memory.queue.QUEUE_DIR = original_queue_dir
            src.memory.queue.QUEUE_FILE = original_queue_file

    def test_graceful_degradation_decision_tree(self):
        """Test complete degradation decision tree."""
        from src.memory.health import get_fallback_mode

        # Test all possible health states
        test_cases = [
            ({"qdrant": True, "embedding": True, "all_healthy": True}, "normal"),
            ({"qdrant": False, "embedding": True, "all_healthy": False}, "queue_to_file"),
            ({"qdrant": True, "embedding": False, "all_healthy": False}, "pending_embedding"),
            ({"qdrant": False, "embedding": False, "all_healthy": False}, "passthrough"),
        ]

        for health, expected_mode in test_cases:
            mode = get_fallback_mode(health)
            assert mode == expected_mode, \
                f"Health {health} should yield mode {expected_mode}, got {mode}"

    def test_hook_output_contains_structured_logging(self):
        """Hook should use structured logging throughout."""
        result = subprocess.run(
            [sys.executable, ".claude/hooks/scripts/example_hook.py"],
            capture_output=True,
            timeout=15  # 15s timeout (includes service health checks)
        )

        output = result.stderr.decode() + result.stdout.decode()

        # Should contain structured log messages
        assert "example_hook_started" in output
        assert "service_health_checked" in output
        assert "fallback_mode_selected" in output

    def test_hook_completes_within_timeout(self):
        """Hook should complete quickly (not hang)."""
        import time

        start_time = time.time()

        result = subprocess.run(
            [sys.executable, ".claude/hooks/scripts/example_hook.py"],
            capture_output=True,
            timeout=15  # 15s timeout (includes service health checks)
        )

        elapsed_time = time.time() - start_time

        # Should complete well under 15 seconds (allows for health checks)
        assert elapsed_time < 15.0
        assert result.returncode in [0, 1]


class TestQueueReplay:
    """Test queue replay functionality."""

    def test_queue_can_be_loaded_and_replayed(self, tmp_path, monkeypatch):
        """Test loading and processing queued operations."""
        from src.memory.queue import queue_operation, load_queue, remove_from_queue

        # Monkeypatch queue location
        test_queue_dir = tmp_path / "queue"
        test_queue_file = test_queue_dir / "pending.jsonl"

        import src.memory.queue
        original_queue_dir = src.memory.queue.QUEUE_DIR
        original_queue_file = src.memory.queue.QUEUE_FILE

        try:
            src.memory.queue.QUEUE_DIR = test_queue_dir
            src.memory.queue.QUEUE_FILE = test_queue_file

            # Queue multiple operations
            ops = [
                {"content_hash": "hash1", "content": "Op1", "type": "impl"},
                {"content_hash": "hash2", "content": "Op2", "type": "pattern"},
                {"content_hash": "hash3", "content": "Op3", "type": "error"},
            ]

            for op in ops:
                queue_operation(op)

            # Load queue
            loaded = load_queue()
            assert len(loaded) == 3

            # Simulate processing operation 1 (success)
            # Remove from queue
            remove_from_queue("hash1")

            # Verify operation removed
            remaining = load_queue()
            assert len(remaining) == 2
            assert remaining[0]["content_hash"] == "hash2"
            assert remaining[1]["content_hash"] == "hash3"

            # Simulate processing operation 2 (success)
            remove_from_queue("hash2")

            # Verify only operation 3 remains
            remaining = load_queue()
            assert len(remaining) == 1
            assert remaining[0]["content_hash"] == "hash3"

        finally:
            src.memory.queue.QUEUE_DIR = original_queue_dir
            src.memory.queue.QUEUE_FILE = original_queue_file


class TestExitCodeBehavior:
    """Test exit code compliance."""

    def test_hook_never_crashes_with_traceback(self):
        """Hook should use graceful_hook decorator to catch exceptions."""
        # Run hook - should never crash with traceback
        result = subprocess.run(
            [sys.executable, ".claude/hooks/scripts/example_hook.py"],
            capture_output=True,
            timeout=15  # 15s timeout (includes service health checks)
        )

        output = result.stderr.decode() + result.stdout.decode()

        # Should not contain Python traceback
        assert "Traceback (most recent call last):" not in output

    def test_hook_respects_exit_code_policy(self):
        """Hook should follow exit code policy (0, 1, never 2)."""
        # Run hook multiple times
        for _ in range(5):
            result = subprocess.run(
                [sys.executable, ".claude/hooks/scripts/example_hook.py"],
                capture_output=True,
                timeout=15  # 15s timeout (includes service health checks)
            )

            # Should be 0 or 1, never 2
            assert result.returncode in [0, 1]
            assert result.returncode != 2


# Skip integration tests if running in minimal environment
pytest_plugins = []
