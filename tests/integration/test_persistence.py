"""Integration tests for data persistence across restarts.

Tests verify that memories persist correctly through:
- Docker container restarts (FR31, FR32)
- Python process restarts (FR31)
- Multiple restart cycles (stress testing)
- Volume mount configuration validation

Per Story 5.3: Persistence Verification Tests

Requirements:
- Docker Compose file at ~/.bmad-memory/docker/docker-compose.yml
- Qdrant service running on port 16350
- Named volume (not bind mount) for /qdrant/storage

Test Execution:
    # Run all persistence tests
    pytest tests/integration/test_persistence.py -v

    # Run specific test
    pytest tests/integration/test_persistence.py::test_data_persists_across_docker_restart -v

    # Skip slow tests (multi-restart)
    pytest tests/integration/test_persistence.py -m "not slow" -v

    # Run with coverage
    pytest tests/integration/test_persistence.py --cov=src/memory --cov-report=html

Troubleshooting:
    - "Docker Compose file not found": Install module or configure ~/.bmad-memory/
    - "Qdrant health check timeout": Check docker ps, restart manually if needed
    - "Data loss detected": Verify named volume exists (docker volume ls)
    - "Permission error on queue file": Check file mode is 0600

2026 Best Practices Applied:
    - subprocess.run() with timeout (not os.system)
    - Exponential backoff for health checks
    - Named volumes validation (not bind mounts)
    - pytest markers (integration, slow)
    - Explicit failure messages

Sources:
    - https://github.com/avast/pytest-docker
    - https://moldstud.com/articles/p-advanced-integration-testing-techniques-for-python-developers-expert-guide-2025
    - https://docs.docker.com/reference/cli/docker/compose/restart/
"""

import os
import subprocess
import time
import pytest
import httpx
import httpcore
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
from qdrant_client.models import Filter, FieldCondition, MatchValue
from src.memory.models import MemoryType

# Import shared helper from conftest (Story 5.4 code review - Issue 7)
from conftest import wait_for_qdrant_healthy

# Use environment variables for port configuration (Issue 2 fix)
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:26350")

# Test group IDs for cleanup tracking
TEST_GROUP_IDS = ["persistence-test", "multi-restart-test"]


@pytest.fixture
def cleanup_test_memories():
    """Fixture to cleanup test memories after test completion (Issue 4 fix).

    Removes all test memories created during persistence tests to prevent
    data pollution across test runs.

    Per pytest-docker-tools best practices:
    "At the end of the test the environment will be thrown away."

    Note: Creates fresh client connection for cleanup since test may have
    restarted Qdrant, invalidating the original qdrant_client fixture connection.
    """
    yield  # Test runs here

    # Wait for Qdrant to be healthy before cleanup (handles post-restart state)
    try:
        wait_for_qdrant_healthy(timeout=30)
    except TimeoutError:
        return  # Skip cleanup if Qdrant not available

    # Create fresh client for cleanup (original may have stale connection)
    try:
        cleanup_client = QdrantClient(url=QDRANT_URL, timeout=10.0)

        # Cleanup: Delete test memories by group_id
        for group_id in TEST_GROUP_IDS:
            try:
                cleanup_client.delete(
                    collection_name="code-patterns",
                    points_selector=Filter(
                        must=[FieldCondition(key="group_id", match=MatchValue(value=group_id))]
                    )
                )
            except Exception:
                # Best effort cleanup - don't fail test if cleanup fails
                pass
    except Exception:
        # Silently fail cleanup if Qdrant unreachable
        pass


@pytest.mark.integration
def test_data_persists_across_docker_restart(qdrant_client, tmp_path, cleanup_test_memories):
    """Verify memories survive Qdrant container restart (FR31, FR32).

    Critical persistence validation per product brief:
    "Memories persist across Claude sessions and system restarts"

    Test Flow:
        1. Store test memory with unique identifier
        2. Verify memory retrievable before restart
        3. Restart Qdrant container via Docker Compose
        4. Wait for Qdrant to become healthy (exponential backoff)
        5. Verify memory still retrievable after restart
        6. Validate content integrity (exact match, not just existence)

    2026 Best Practice: subprocess.run() with explicit timeout prevents hanging tests.
    Source: https://docs.docker.com/reference/cli/docker/compose/restart/
    """
    from src.memory.storage import MemoryStorage
    from src.memory.search import MemorySearch

    storage = MemoryStorage()
    search = MemorySearch()

    # 1. Store test memory with unique identifier
    test_content = f"Persistence test memory - survives restart - {int(time.time())}"
    result = storage.store_memory(
        content=test_content,
        cwd="/tmp/test",  # Test context working directory
        memory_type=MemoryType.IMPLEMENTATION,
        source_hook="PostToolUse",
        session_id="persistence-session",
        collection="code-patterns",
        group_id="persistence-test"
    )

    assert result["status"] == "stored", "Memory storage failed"
    memory_id = result["memory_id"]

    # Wait for embedding generation (NFR-P2 <2s)
    time.sleep(3)

    # 2. Verify memory exists before restart
    pre_restart_results = search.search(
        query=test_content,
        collection="code-patterns",
        group_id="persistence-test",
        limit=5
    )

    assert len(pre_restart_results) > 0, \
        "Memory not found before restart"

    found_before = any(
        r["id"] == memory_id and test_content in r["content"]
        for r in pre_restart_results
    )

    assert found_before, \
        f"Memory {memory_id[:8]} not retrievable before restart"

    # 3. Restart Qdrant container
    # Try installed location first, then project root (local dev)
    compose_file = Path.home() / ".bmad-memory" / "docker" / "docker-compose.yml"
    if not compose_file.exists():
        # Fallback to project root for local development
        compose_file = Path(__file__).parent.parent.parent / "docker" / "docker-compose.yml"

    if not compose_file.exists():
        pytest.skip(f"Docker Compose file not found at {compose_file}")

    # Restart Qdrant (preserves volume mount)
    # 2026 Best Practice: subprocess.run() with timeout, not os.system()
    restart_result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "restart", "qdrant"],
        capture_output=True,
        text=True,
        timeout=60  # Prevent hanging tests
    )

    assert restart_result.returncode == 0, \
        f"Docker restart failed: {restart_result.stderr}"

    # 4. Wait for Qdrant to become healthy
    wait_for_qdrant_healthy(timeout=60)

    # Brief stabilization delay - Qdrant needs time to fully accept connections
    # after health check passes (observed in WSL2 environments)
    time.sleep(2)

    # 5. Verify memory still exists after restart
    # Create fresh search client (original has stale connections after restart)
    search_after_restart = MemorySearch()
    post_restart_results = search_after_restart.search(
        query=test_content,
        collection="code-patterns",
        group_id="persistence-test",
        limit=5
    )

    assert len(post_restart_results) > 0, \
        "Memory not found after restart - DATA LOSS DETECTED!"

    found_after = any(
        r["id"] == memory_id and test_content in r["content"]
        for r in post_restart_results
    )

    assert found_after, \
        f"Memory {memory_id[:8]} not retrievable after restart - DATA LOSS!"

    # 6. Verify content integrity (not just existence)
    for result in post_restart_results:
        if result["id"] == memory_id:
            assert result["content"] == test_content, \
                "Memory content changed after restart - CORRUPTION DETECTED!"
            assert result["group_id"] == "persistence-test", \
                "Memory group_id changed after restart"
            break


@pytest.mark.integration
def test_qdrant_volume_mount_configured(tmp_path):
    """Verify Qdrant data is mounted to persistent storage (FR31).

    Validates Docker Compose configuration for data persistence.
    Per: https://qdrant.tech/documentation/guides/installation/

    Test checks:
        1. docker-compose.yml exists and is valid YAML
        2. Qdrant service is configured
        3. Named volume (NOT bind mount) is used
        4. Volume mounted to /qdrant/storage path
        5. Volume declared in top-level volumes section

    Why named volumes (2026 best practice):
        - WSL compatibility (bind mounts have issues on Windows WSL)
        - Performance (block-level storage access required by Qdrant)
        - Data persistence (survives container deletion)
        - Docker manages cleanup automatically

    Source: https://qdrant.tech/documentation/guides/installation/
    """
    import yaml

    # Try installed location first, then project root (local dev)
    compose_file = Path.home() / ".bmad-memory" / "docker" / "docker-compose.yml"
    if not compose_file.exists():
        # Fallback to project root for local development
        compose_file = Path(__file__).parent.parent.parent / "docker" / "docker-compose.yml"

    if not compose_file.exists():
        pytest.skip(f"Docker Compose file not found at {compose_file}")

    with open(compose_file) as f:
        config = yaml.safe_load(f)

    # Verify services section exists
    assert "services" in config, \
        "docker-compose.yml missing 'services' section"

    # Verify Qdrant service exists
    assert "qdrant" in config["services"], \
        "docker-compose.yml missing 'qdrant' service"

    qdrant_config = config["services"]["qdrant"]

    # Verify volumes configuration
    assert "volumes" in qdrant_config, \
        "Qdrant service missing 'volumes' configuration"

    volumes = qdrant_config["volumes"]

    # Check for persistent volume (NOT bind mount)
    persistent_volume_found = False

    for volume in volumes:
        # Named volume format: "volume_name:/container/path"
        # Bind mount format: "./host/path:/container/path" or "/host/path:/container/path"

        if isinstance(volume, str):
            if ":" in volume:
                host_part, container_part = volume.split(":", 1)

                # Persistent volume check (Issue 6 fix):
                # - Named volume (no path separators in host_part)
                # - Container path is /qdrant/storage
                # Note: Named volume format is "volume_name:/container/path"
                #       host_part = volume_name (no / or .)
                #       container_part = /qdrant/storage
                if "/" not in host_part and "." not in host_part:
                    if "/qdrant/storage" in container_part:
                        persistent_volume_found = True
                        break

    assert persistent_volume_found, \
        f"Qdrant must use persistent named volume (not bind mount). Found: {volumes}"

    # Verify volumes section defines the volume
    if "volumes" in config:
        # Named volumes should be declared at top level
        volume_names = [v.split(":")[0] for v in qdrant_config["volumes"]
                       if isinstance(v, str) and "/" not in v.split(":")[0]]

        for vol_name in volume_names:
            assert vol_name in config["volumes"], \
                f"Named volume '{vol_name}' not declared in top-level 'volumes' section"


@pytest.mark.integration
def test_queue_file_survives_process_restart(tmp_path):
    """Verify queue file persists and is readable after process restart (FR31, Story 5.1).

    Validates file-based queue durability per resilience requirements.

    Test Flow:
        1. Queue item in first MemoryQueue instance
        2. Verify queue file exists with correct permissions (0600)
        3. Destroy first queue instance (simulates process restart)
        4. Create new queue instance (simulates new process)
        5. Verify item is retrievable in new "process"
        6. Validate content integrity

    2026 Best Practice: tmp_path fixture for test isolation (not ~/.claude-memory).
    Prevents test pollution and enables parallel test execution.
    Source: https://github.com/avast/pytest-docker
    """
    from src.memory.queue import MemoryQueue

    # Use tmp_path for test isolation (not ~/.claude-memory)
    test_queue_path = tmp_path / "test_queue.jsonl"

    # 1. Queue a test item in first "process"
    queue1 = MemoryQueue(queue_path=str(test_queue_path))

    test_memory_data = {
        "content": "Queue persistence test - survives restart",
        "group_id": "queue-test",
        "type": "implementation",
        "source_hook": "PostToolUse"
    }

    queue_id = queue1.enqueue(
        memory_data=test_memory_data,
        failure_reason="TEST_PERSISTENCE"
    )

    # Verify queue file exists
    assert test_queue_path.exists(), \
        f"Queue file not created at {test_queue_path}"

    # Verify file permissions (0600 = owner read/write only)
    import stat
    file_stat = test_queue_path.stat()
    file_mode = file_stat.st_mode & 0o777

    assert file_mode == 0o600, \
        f"Queue file permissions {oct(file_mode)} != 0o600 (security risk)"

    # 2. Destroy first queue instance (simulates process restart)
    del queue1

    # 3. Create new queue instance (simulates new process)
    queue2 = MemoryQueue(queue_path=str(test_queue_path))

    # 4. Verify item is retrievable in new "process"
    # Note: get_pending() filters by next_retry_at <= now (1min delay for new items)
    # For persistence testing, we need to verify file contents directly
    all_entries = queue2._read_all()

    assert len(all_entries) > 0, \
        "No items in queue after process restart - FILE LOST!"

    # Find our specific item
    found = False
    for item in all_entries:
        if item["id"] == queue_id:
            found = True
            assert item["memory_data"] == test_memory_data, \
                "Queue item content corrupted after restart"
            assert item["failure_reason"] == "TEST_PERSISTENCE", \
                "Queue item metadata corrupted after restart"
            # Verify structure integrity
            assert "queued_at" in item, "Missing queued_at timestamp"
            assert "next_retry_at" in item, "Missing next_retry_at timestamp"
            assert "retry_count" in item, "Missing retry_count"
            assert item["retry_count"] == 0, "Initial retry_count should be 0"
            break

    assert found, \
        f"Queue item {queue_id[:8]} not found after restart - DATA LOSS!"

    # Cleanup
    queue2.dequeue(queue_id)


@pytest.mark.integration
@pytest.mark.slow
def test_data_persists_through_multiple_restarts(qdrant_client, tmp_path, cleanup_test_memories):
    """Verify data integrity through multiple restart cycles (FR32 stress test).

    Validates long-term persistence and no cumulative corruption.

    Test Flow:
        1. Store 3 test memories before restarts
        2. Perform 3 restart cycles with verification after each
        3. Verify all memories after final restart

    2026 Best Practice: Mark slow tests with @pytest.mark.slow for selective execution.
    Enables fast feedback loop (skip slow tests locally), full coverage in CI/CD.

    Test duration: ~3-5 minutes with 3 restart cycles.

    Usage:
        # Skip slow tests locally
        pytest -m "integration and not slow"

        # Run all including slow
        pytest -m integration

    Source: https://moldstud.com/articles/p-advanced-integration-testing-techniques-for-python-developers-expert-guide-2025
    """
    from src.memory.storage import MemoryStorage
    from src.memory.search import MemorySearch

    storage = MemoryStorage()
    search = MemorySearch()

    # Try installed location first, then project root (local dev)
    compose_file = Path.home() / ".bmad-memory" / "docker" / "docker-compose.yml"
    if not compose_file.exists():
        # Fallback to project root for local development
        compose_file = Path(__file__).parent.parent.parent / "docker" / "docker-compose.yml"

    if not compose_file.exists():
        pytest.skip(f"Docker Compose file not found at {compose_file}")

    # Store 3 test memories before restarts
    memory_ids = []
    test_contents = [
        f"Multi-restart test memory {i} - {int(time.time())}"
        for i in range(1, 4)
    ]

    for content in test_contents:
        result = storage.store_memory(
            content=content,
            cwd="/tmp/test",  # Test context working directory
            memory_type=MemoryType.IMPLEMENTATION,
            source_hook="PostToolUse",
            session_id="multi-restart-session",
            collection="code-patterns",
            group_id="multi-restart-test"
        )
        memory_ids.append(result["memory_id"])

    time.sleep(3)  # Wait for embeddings

    # Perform 3 restart cycles
    restart_count = 3

    for cycle in range(1, restart_count + 1):
        # Restart Qdrant
        restart_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "restart", "qdrant"],
            capture_output=True,
            text=True,
            timeout=60
        )

        assert restart_result.returncode == 0, \
            f"Restart cycle {cycle} failed: {restart_result.stderr}"

        wait_for_qdrant_healthy(timeout=60)

        # Create fresh search client after each restart (stale connections)
        cycle_search = MemorySearch()

        # Verify all memories after this restart
        for idx, (memory_id, content) in enumerate(zip(memory_ids, test_contents)):
            results = cycle_search.search(
                query=content,
                collection="code-patterns",
                group_id="multi-restart-test",
                limit=10
            )

            found = any(
                r["id"] == memory_id and content in r["content"]
                for r in results
            )

            assert found, \
                f"Memory {idx+1} lost after restart cycle {cycle}"

    # Final verification: All memories still intact
    # Use the last cycle_search which is still fresh from final restart
    all_results = cycle_search.search(
        query="Multi-restart test memory",
        collection="code-patterns",
        group_id="multi-restart-test",
        limit=10
    )

    assert len(all_results) >= 3, \
        f"Expected 3+ memories, found {len(all_results)} after {restart_count} restarts"
