"""Integration tests for queue concurrent access and file locking.

Tests verify:
- Concurrent enqueue operations don't corrupt queue file
- File locking prevents race conditions
- Atomic operations work correctly under concurrent load
- Queue integrity maintained with multiple processes

Uses threading (not multiprocessing) for faster test execution while still
validating file locking behavior.
"""

import concurrent.futures
import json
import time
from pathlib import Path

import pytest

from src.memory.queue import MemoryQueue


class TestConcurrentAccess:
    """Tests for concurrent queue access."""

    @pytest.fixture
    def queue_path(self, tmp_path):
        """Provide temporary queue file path."""
        return tmp_path / "concurrent_queue.jsonl"

    @pytest.fixture
    def queue(self, queue_path):
        """Provide MemoryQueue instance."""
        return MemoryQueue(queue_path=str(queue_path))

    def test_concurrent_enqueue_no_corruption(self, queue, queue_path):
        """Test concurrent enqueue operations maintain data integrity."""
        num_threads = 10
        items_per_thread = 5

        def enqueue_items(thread_id: int) -> list[str]:
            """Enqueue multiple items from a single thread."""
            queue_ids = []
            for i in range(items_per_thread):
                memory_data = {
                    "content": f"Thread {thread_id} - Item {i}",
                    "group_id": "test-project",
                    "type": "implementation",
                }
                queue_id = queue.enqueue(memory_data, "TEST")
                queue_ids.append(queue_id)
            return queue_ids

        # Enqueue concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(enqueue_items, i) for i in range(num_threads)]
            all_ids = []
            for future in concurrent.futures.as_completed(futures):
                all_ids.extend(future.result())

        # Verify all items present
        entries = queue._read_all()
        assert len(entries) == num_threads * items_per_thread

        # Verify all IDs unique
        entry_ids = [e["id"] for e in entries]
        assert len(entry_ids) == len(set(entry_ids))

        # Verify all IDs returned match entries
        assert set(all_ids) == set(entry_ids)

        # Verify file is valid JSONL (no corrupt lines)
        with open(queue_path, "r") as f:
            line_count = 0
            for line in f:
                line_count += 1
                # Should parse without error
                entry = json.loads(line)
                assert "id" in entry
                assert "memory_data" in entry
        assert line_count == num_threads * items_per_thread

    def test_concurrent_enqueue_and_dequeue(self, queue):
        """Test concurrent enqueue and dequeue operations."""
        num_enqueue_threads = 5
        num_dequeue_threads = 3
        items_per_enqueue_thread = 10

        enqueued_ids = []

        def enqueue_items(thread_id: int) -> list[str]:
            """Enqueue items."""
            ids = []
            for i in range(items_per_enqueue_thread):
                memory_data = {"content": f"T{thread_id}-I{i}"}
                queue_id = queue.enqueue(memory_data, "TEST")
                ids.append(queue_id)
                time.sleep(0.001)  # Small delay to interleave
            return ids

        def dequeue_items(dequeue_list: list[str]) -> int:
            """Dequeue items from list."""
            dequeued = 0
            for queue_id in dequeue_list:
                if queue_id:
                    queue.dequeue(queue_id)
                    dequeued += 1
                    time.sleep(0.001)
            return dequeued

        # First enqueue all items
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_enqueue_threads
        ) as executor:
            futures = [
                executor.submit(enqueue_items, i) for i in range(num_enqueue_threads)
            ]
            for future in concurrent.futures.as_completed(futures):
                enqueued_ids.extend(future.result())

        # Verify all enqueued
        assert len(enqueued_ids) == num_enqueue_threads * items_per_enqueue_thread

        # Split IDs for concurrent dequeue
        ids_per_dequeue = len(enqueued_ids) // num_dequeue_threads
        id_chunks = [
            enqueued_ids[i : i + ids_per_dequeue]
            for i in range(0, len(enqueued_ids), ids_per_dequeue)
        ]

        # Dequeue concurrently
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_dequeue_threads
        ) as executor:
            futures = [executor.submit(dequeue_items, chunk) for chunk in id_chunks]
            total_dequeued = sum(f.result() for f in concurrent.futures.as_completed(futures))

        # Should have dequeued all items
        assert total_dequeued == len(enqueued_ids)

        # Queue should be empty
        entries = queue._read_all()
        assert len(entries) == 0

    def test_concurrent_mark_failed(self, queue):
        """Test concurrent mark_failed operations don't corrupt retry counts."""
        # Enqueue some items
        queue_ids = []
        for i in range(10):
            memory_data = {"content": f"Item {i}"}
            queue_id = queue.enqueue(memory_data, "TEST")
            queue_ids.append(queue_id)

        # Concurrently mark all as failed
        def mark_failed_wrapper(queue_id: str) -> None:
            queue.mark_failed(queue_id)
            time.sleep(0.001)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(mark_failed_wrapper, qid) for qid in queue_ids]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        # Verify all have retry_count = 1
        entries = queue._read_all()
        assert len(entries) == 10
        for entry in entries:
            assert entry["retry_count"] == 1

    def test_concurrent_get_pending(self, queue):
        """Test concurrent get_pending operations are safe."""
        # Enqueue items
        for i in range(20):
            memory_data = {"content": f"Item {i}"}
            queue.enqueue(memory_data, "TEST")

        # Concurrently call get_pending
        def get_pending_wrapper() -> list:
            return queue.get_pending(limit=5)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(get_pending_wrapper) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed and return data
        for result in results:
            assert isinstance(result, list)
            assert len(result) <= 5

    def test_file_locking_prevents_corruption(self, queue, queue_path):
        """Test fcntl.flock prevents file corruption during concurrent writes."""
        num_threads = 20
        items_per_thread = 10

        def stress_enqueue(thread_id: int) -> int:
            """Rapidly enqueue items."""
            for i in range(items_per_thread):
                memory_data = {"content": f"Stress-T{thread_id}-I{i}"}
                queue.enqueue(memory_data, "STRESS_TEST")
            return items_per_thread

        # Heavy concurrent load
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(stress_enqueue, i) for i in range(num_threads)]
            total_enqueued = sum(f.result() for f in concurrent.futures.as_completed(futures))

        assert total_enqueued == num_threads * items_per_thread

        # Verify file integrity - no corrupt lines
        with open(queue_path, "r") as f:
            valid_lines = 0
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    assert "id" in entry
                    valid_lines += 1
                except json.JSONDecodeError:
                    pytest.fail(f"Corrupt line found: {line[:50]}")

        assert valid_lines == total_enqueued

    def test_atomic_write_under_concurrent_dequeue(self, queue):
        """Test atomic _write_all during concurrent dequeue operations."""
        # Enqueue many items
        queue_ids = []
        for i in range(50):
            memory_data = {"content": f"Item {i}"}
            queue_id = queue.enqueue(memory_data, "TEST")
            queue_ids.append(queue_id)

        # Concurrently dequeue (each triggers atomic write)
        def dequeue_wrapper(queue_id: str) -> None:
            queue.dequeue(queue_id)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(dequeue_wrapper, qid) for qid in queue_ids]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        # Queue should be empty
        entries = queue._read_all()
        assert len(entries) == 0
