"""Tests for classification queue.

RESOURCE LIMITS FOR TESTS:
- pytest timeout: 30 seconds per test
- Max 4 threads in thread safety test
- Cleanup after each test
"""

import pytest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


from memory.classifier.queue import (
    enqueue_for_classification,
    dequeue_batch,
    get_queue_size,
    clear_queue,
    ClassificationTask,
    MAX_BATCH_SIZE,
)


# Override queue location for tests
@pytest.fixture(autouse=True)
def temp_queue_dir(tmp_path, monkeypatch):
    """Use temporary directory for queue during tests."""
    import memory.classifier.queue as queue_module

    monkeypatch.setattr(queue_module, "QUEUE_DIR", tmp_path)
    monkeypatch.setattr(queue_module, "QUEUE_FILE", tmp_path / "test_queue.jsonl")
    yield tmp_path


def make_task(point_id: str = "test-123") -> ClassificationTask:
    """Create test task."""
    return ClassificationTask(
        point_id=point_id,
        collection="discussions",
        content="Test content",
        current_type="user_message",
        group_id="test-project",
        source_hook="PostToolUse",
        created_at="2026-01-24T00:00:00Z",
    )


@pytest.mark.timeout(30)
def test_enqueue_dequeue():
    """Test basic enqueue/dequeue cycle."""
    task = make_task()
    assert enqueue_for_classification(task) is True
    assert get_queue_size() == 1

    tasks = dequeue_batch(1)
    assert len(tasks) == 1
    assert tasks[0].point_id == "test-123"
    assert get_queue_size() == 0


@pytest.mark.timeout(30)
def test_batch_size_enforced():
    """Test dequeue respects MAX_BATCH_SIZE."""
    # Enqueue more than MAX_BATCH_SIZE
    for i in range(MAX_BATCH_SIZE + 5):
        enqueue_for_classification(make_task(f"task-{i}"))

    # Request more than max
    tasks = dequeue_batch(100)
    assert len(tasks) == MAX_BATCH_SIZE


@pytest.mark.timeout(30)
def test_thread_safety():
    """Test concurrent enqueue from limited threads."""
    results = []

    def enqueue_task(task_id: int) -> bool:
        task = make_task(f"thread-task-{task_id}")
        return enqueue_for_classification(task)

    # Use limited thread pool (4 threads, not unlimited)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(enqueue_task, i) for i in range(20)]
        for future in as_completed(futures):
            results.append(future.result())

    assert all(results)
    assert get_queue_size() == 20


@pytest.mark.timeout(30)
def test_clear_queue():
    """Test clear_queue removes all items."""
    for i in range(5):
        enqueue_for_classification(make_task(f"clear-{i}"))

    assert get_queue_size() == 5
    cleared = clear_queue()
    assert cleared == 5
    assert get_queue_size() == 0


@pytest.mark.timeout(30)
def test_empty_queue_dequeue():
    """Test dequeue from empty queue returns empty list."""
    tasks = dequeue_batch(10)
    assert tasks == []


@pytest.mark.timeout(10)
def test_lock_timeout_enqueue(temp_queue_dir, monkeypatch):
    """Verify enqueue returns False when lock cannot be acquired (HIGH-2)."""
    import fcntl
    import memory.classifier.queue as queue_module

    task = make_task("lock-test")

    # Create queue file and hold lock
    queue_file = temp_queue_dir / "test_queue.jsonl"
    queue_file.touch()

    with open(queue_file, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)

        # Temporarily reduce timeout for faster test
        original_timeout = queue_module.LOCK_TIMEOUT_SECONDS
        monkeypatch.setattr(queue_module, "LOCK_TIMEOUT_SECONDS", 0.5)

        try:
            result = enqueue_for_classification(task)
            assert result is False, "Should return False when lock unavailable"
        finally:
            monkeypatch.setattr(queue_module, "LOCK_TIMEOUT_SECONDS", original_timeout)
            fcntl.flock(f, fcntl.LOCK_UN)


@pytest.mark.timeout(10)
def test_lock_timeout_dequeue(temp_queue_dir, monkeypatch):
    """Verify dequeue returns empty list when lock unavailable (HIGH-2)."""
    import fcntl
    import memory.classifier.queue as queue_module

    queue_file = temp_queue_dir / "test_queue.jsonl"

    # Write valid entry
    queue_file.write_text('{"point_id":"1","collection":"discussions","content":"test","current_type":"user_message","group_id":"test","source_hook":"Test","created_at":"2026-01-24T00:00:00Z"}\n')

    with open(queue_file, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)

        # Temporarily reduce timeout for faster test
        original_timeout = queue_module.LOCK_TIMEOUT_SECONDS
        monkeypatch.setattr(queue_module, "LOCK_TIMEOUT_SECONDS", 0.5)

        try:
            result = dequeue_batch(10)
            assert result == [], "Should return empty list when lock unavailable"
        finally:
            monkeypatch.setattr(queue_module, "LOCK_TIMEOUT_SECONDS", original_timeout)
            fcntl.flock(f, fcntl.LOCK_UN)
