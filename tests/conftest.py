"""Shared pytest fixtures for BMAD Memory Module tests.

This module provides common fixtures for test setup and teardown,
following project-context.md testing conventions and 2026 pytest best practices.

Fixture Organization (2026 Best Practices):
    - Mock fixtures: Isolated mocks for external dependencies (Qdrant, embedding service)
    - Sample data fixtures: Pre-configured test data instances
    - Temporary resource fixtures: Temp directories with proper cleanup
    - Integration fixtures: Docker/service fixtures for integration tests

References:
    - pytest fixtures docs: https://docs.pytest.org/en/stable/how-to/fixtures.html
    - pytest-mock patterns: https://www.datacamp.com/tutorial/pytest-mock
"""

import os
import sys
import time
from pathlib import Path
from typing import Generator
from unittest.mock import Mock

import httpx
import httpcore
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
from qdrant_client.models import Filter, FieldCondition, MatchValue

from src.memory.models import MemoryPayload, MemoryType, EmbeddingStatus

# Add tests directory to sys.path so test_session_start.py can import
# session_start_test_helpers from tests directory
tests_dir = Path(__file__).parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))


# =============================================================================
# Metrics Registry Reset (Autouse - Prevents Duplicate Registration)
# =============================================================================


def pytest_sessionstart(session):
    """Hook called at the start of the test session to clear metrics registry.

    Story 6.1: Clear the Prometheus REGISTRY before pytest starts collecting tests.
    This prevents duplicate registration errors when test modules import memory modules
    at the module level during collection.
    """
    try:
        from prometheus_client import REGISTRY
        collectors = list(REGISTRY._collector_to_names.keys())
        for collector in collectors:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    except ImportError:
        pass  # prometheus_client not installed


def pytest_collection_modifyitems(session, config, items):
    """Hook called after test collection to fix module pollution.

    Story 6.5: test_session_retrieval_logging.py mocks memory.session_logger at
    import time (during collection), which pollutes sys.modules for other tests.
    This hook runs after collection but before tests, allowing us to restore
    the real module.
    """
    # Check if memory.session_logger was mocked during collection
    from unittest.mock import Mock
    if 'memory.session_logger' in sys.modules:
        mod = sys.modules['memory.session_logger']
        if isinstance(mod, Mock):
            # Remove the mock to allow reimport of real module
            del sys.modules['memory.session_logger']
            # Also clear any submodules
            keys_to_delete = [k for k in sys.modules if k.startswith('memory.session_logger.')]
            for k in keys_to_delete:
                del sys.modules[k]


@pytest.fixture(autouse=True)
def reset_metrics_registry():
    """Clear Prometheus metrics registry before each test to prevent duplicate registration errors.

    Story 6.1: Prometheus metrics are registered at module import time. When running
    multiple tests that import memory modules, metrics get registered multiple times
    in the global REGISTRY, causing ValueError for duplicated timeseries.

    This fixture clears the registry before and after each test to ensure isolation.
    """
    from prometheus_client import REGISTRY

    # Clear all collectors from the registry before test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    # Remove metrics module from sys.modules
    modules_to_remove = [k for k in sys.modules.keys() if 'memory.metrics' in k or k == 'memory']
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)

    yield

    # Clean up after test - clear registry again
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except Exception:
            pass

    modules_to_remove = [k for k in sys.modules.keys() if 'memory.metrics' in k or k == 'memory']
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration before each test to allow caplog to work.

    Story 6.2: configure_logging() adds handlers to loggers in __init__.py, which
    prevents pytest's caplog fixture from capturing logs. This fixture removes all
    handlers from bmad.memory loggers before each test to ensure test isolation.
    """
    import logging

    # Get the bmad.memory logger
    logger = logging.getLogger("bmad.memory")

    # Remove all handlers from bmad.memory and its children
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith("bmad.memory"):
            child_logger = logging.getLogger(name)
            child_logger.handlers.clear()
            child_logger.propagate = True  # Re-enable propagation for testing

    # Clear root logger handlers as well
    logger.handlers.clear()
    logger.propagate = True

    yield

    # Clean up after test
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith("bmad.memory"):
            child_logger = logging.getLogger(name)
            child_logger.handlers.clear()
            child_logger.propagate = True

    logger.handlers.clear()
    logger.propagate = True


# =============================================================================
# Mock Fixtures (Function Scope - Reset per Test)
# =============================================================================


@pytest.fixture
def mock_qdrant_client(mocker):
    """Mock Qdrant client with autospec for isolation.

    Provides a mocked QdrantClient with default behavior configured.
    Uses pytest-mock mocker fixture for autospec enforcement per 2026 best practices.

    Returns:
        Mock: Mocked QdrantClient with common methods stubbed

    Example:
        def test_store(mock_qdrant_client):
            mock_qdrant_client.upsert.return_value = Mock(status="completed")
            # Test using mock...
            mock_qdrant_client.upsert.assert_called_once()
    """
    mock = mocker.Mock(spec=QdrantClient, autospec=True)

    # Configure default behavior for common operations
    mock.get_collections.return_value.collections = []
    mock.count.return_value.count = 0
    mock.search.return_value = []
    mock.upsert.return_value = Mock(status="completed")
    mock.get_collection.return_value = Mock(
        vectors_count=0,
        points_count=0,
        status="green"
    )

    return mock


@pytest.fixture
def mock_embedding_client(mocker):
    """Mock embedding service client with autospec.

    Provides mocked EmbeddingClient for testing without real embedding service.
    Uses 768d zero vector as default embedding per Jina Embeddings v2 Base Code spec (DEC-010).

    Returns:
        Mock: Mocked EmbeddingClient with health and embed methods stubbed

    Example:
        def test_embed(mock_embedding_client):
            mock_embedding_client.generate_embedding.return_value = [0.1] * 768
            # Test using mock...
            mock_embedding_client.generate_embedding.assert_called_once()
    """
    mock = mocker.patch('src.memory.embeddings.EmbeddingClient', autospec=True)

    # Configure default embeddings (768d zero vector for testing - DEC-010)
    mock.return_value.generate_embedding.return_value = [0.0] * 768
    mock.return_value.health_check.return_value = True
    mock.return_value.embed_batch.return_value = [[0.0] * 768] * 5

    return mock


# =============================================================================
# Sample Data Fixtures (Function Scope)
# =============================================================================


@pytest.fixture
def sample_memory_payload():
    """Sample MemoryPayload dict for testing.

    Provides pre-configured memory payload with typical field values.
    Use this for most unit tests to avoid repetitive test data creation.

    Returns:
        dict: Pre-configured memory payload

    Example:
        def test_validation(sample_memory_payload):
            assert sample_memory_payload["content"] == "Sample implementation pattern"
            assert sample_memory_payload["group_id"] == "test-project"
    """
    return {
        "content": "Sample implementation pattern for testing",
        "content_hash": "sha256:abc123",
        "group_id": "test-project",
        "type": MemoryType.IMPLEMENTATION.value,
        "source_hook": "PostToolUse",
        "session_id": "test-session-123",
        "embedding_status": EmbeddingStatus.COMPLETE.value,
        "embedding_model": "nomic-embed-code",
        "timestamp": "2026-01-11T00:00:00Z",
        "metadata": {
            "tags": ["python", "backend", "testing"],
            "domain": "backend",
            "importance": "high"
        }
    }


@pytest.fixture
def sample_best_practice_payload():
    """Sample best practice memory payload for testing cross-project scenarios.

    Returns:
        dict: Best practice memory payload
    """
    return {
        "content": "Use structured logging with extras dict for consistent log format",
        "content_hash": "sha256:def456",
        "group_id": "best-practices",
        "type": MemoryType.PATTERN.value,
        "source_hook": "manual",
        "session_id": "seed-session",
        "embedding_status": EmbeddingStatus.COMPLETE.value,
        "embedding_model": "nomic-embed-code",
        "timestamp": "2026-01-11T00:00:00Z",
        "metadata": {
            "tags": ["logging", "python", "best-practice"],
            "domain": "observability",
            "importance": "high"
        }
    }


@pytest.fixture
def sample_search_result():
    """Sample search result dict for testing.

    Provides pre-configured search result with realistic score and metadata.

    Returns:
        dict: Pre-configured search result

    Example:
        def test_search_formatting(sample_search_result):
            assert sample_search_result["score"] == 0.92
            assert sample_search_result["payload"]["type"] == "implementation"
    """
    return {
        "id": "mem-test-123",
        "score": 0.92,
        "payload": {
            "content": "Sample memory content from search",
            "type": MemoryType.IMPLEMENTATION.value,
            "group_id": "test-project",
            "source_hook": "PostToolUse",
            "session_id": "test-session-123",
            "content_hash": "sha256:xyz789",
            "embedding_status": EmbeddingStatus.COMPLETE.value,
            "metadata": {
                "domain": "backend",
                "importance": "high",
                "tags": ["python", "testing"]
            }
        }
    }


# =============================================================================
# Temporary Resource Fixtures (Function Scope with Cleanup)
# =============================================================================


@pytest.fixture
def temp_queue_dir(tmp_path):
    """Temporary queue directory with proper cleanup.

    Creates isolated queue directory for testing queue operations.
    Automatically cleaned up after test via tmp_path fixture.
    Sets proper permissions per project security requirements (0700).

    Yields:
        Path: Temporary queue directory path

    Example:
        def test_queue_write(temp_queue_dir):
            queue_file = temp_queue_dir / "pending.jsonl"
            # Test queue operations...
    """
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir(mode=0o700)
    yield queue_dir
    # Cleanup handled automatically by tmp_path


# =============================================================================
# Integration Test Fixtures (Session/Module Scope)
# =============================================================================


@pytest.fixture(scope="session")
def docker_compose_path() -> str:
    """Return path to docker-compose.yml."""
    return os.path.join(
        os.path.dirname(__file__), "../docker/docker-compose.yml"
    )


@pytest.fixture(scope="session")
def qdrant_base_url() -> str:
    """Return Qdrant base URL using configured or default port."""
    port = os.environ.get("QDRANT_PORT", "26350")
    return f"http://localhost:{port}"


@pytest.fixture
def qdrant_client(qdrant_base_url: str) -> Generator:
    """Provide Qdrant Python SDK client with group_id index (Story 4.2).

    Creates QdrantClient instance and ensures group_id payload index exists
    with is_tenant=True for optimal multitenancy performance (AC 4.2.3).

    Yields:
        QdrantClient: Configured Qdrant client with index ready

    Note:
        Index is created once per test and reused for "implementations" collection.
    """
    # Parse host and port from URL
    import re
    match = re.match(r"http://([^:]+):(\d+)", qdrant_base_url)
    if not match:
        pytest.fail(f"Invalid Qdrant base URL: {qdrant_base_url}")

    host, port = match.groups()

    # Create Qdrant Python SDK client (not httpx client)
    from qdrant_client import QdrantClient as QdrantSDKClient

    client = QdrantSDKClient(host=host, port=int(port), timeout=30.0)

    # Ensure both collections exist (implementations + best_practices)
    try:
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        from qdrant_client.models import Distance, VectorParams

        if "implementations" not in collection_names:
            # Create implementations collection (DEC-010: 768d)
            client.create_collection(
                collection_name="implementations",
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )

        # Create best_practices collection for cross-project sharing (Story 4.3, AC 4.4.4)
        if "best_practices" not in collection_names:
            client.create_collection(
                collection_name="best_practices",
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )

        # Create group_id index with is_tenant=True for both collections (AC 4.2.3)
        from src.memory.qdrant_client import create_group_id_index

        for collection in ["implementations", "best_practices"]:
            try:
                create_group_id_index(client, collection)
            except Exception as e:
                # Index may already exist - acceptable
                if "already exists" not in str(e).lower():
                    # Re-raise if not "already exists" error
                    raise

    except Exception as e:
        pytest.skip(f"Qdrant not available for testing: {e}")

    yield client

    # Cleanup handled by individual test fixtures (test_collection)


@pytest.fixture
def test_collection(
    qdrant_client: httpx.Client,
    request: pytest.FixtureRequest,
) -> Generator[str, None, None]:
    """Create a test collection and ensure cleanup after test.

    Yields the collection name. Collection is automatically deleted
    after the test completes, even if the test fails.
    """
    # Generate unique collection name based on test name
    collection_name = f"test_{request.node.name}"

    # Create collection with DEC-010 dimensions (Jina Embeddings v2 Base Code = 768)
    response = qdrant_client.put(
        f"/collections/{collection_name}",
        json={"vectors": {"size": 768, "distance": "Cosine"}},
    )
    if response.status_code not in (200, 409):  # 409 = already exists
        pytest.fail(f"Failed to create test collection: {response.text}")

    yield collection_name

    # Cleanup - always runs, even on test failure
    try:
        qdrant_client.delete(f"/collections/{collection_name}")
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture(scope="session")
def docker_services_available():
    """Check if Docker services are running for integration tests.

    Checks for running Docker containers. Integration tests should skip
    if services are not available using pytest.skip().

    Yields:
        bool: True if Docker services available, False otherwise

    Example:
        def test_integration(docker_services_available):
            if not docker_services_available:
                pytest.skip("Docker services not running")
            # Test with real services...
    """
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "ps", "-q"],
            cwd=os.path.join(os.path.dirname(__file__), "../docker"),
            capture_output=True,
            timeout=5,
            check=False
        )
        services_running = len(result.stdout.strip()) > 0
        yield services_running
    except Exception:
        yield False


@pytest.fixture(scope="session", autouse=True)
def integration_test_env():
    """Configure environment for integration tests.

    Sets environment variables required for integration tests that use
    real Docker services (Qdrant + Embedding Service).

    This fixture runs automatically (autouse=True) for all tests in the session,
    ensuring consistent configuration across integration and unit tests.

    Environment variables configured:
    - EMBEDDING_READ_TIMEOUT=60.0: CPU embedding service timeout (20-50s typical)
    - QDRANT_URL: Qdrant service URL with correct port for integration tests
    - QDRANT_PORT: Explicit port for integration tests (26350)
    - SIMILARITY_THRESHOLD=0.4: Lower threshold for generic test queries vs specific code
    - EMBEDDING_DIMENSION=768: DEC-010 Jina v2 Base Code dimensions (fixes store_async.py mismatch)
    """
    # Save original env vars to restore after session
    original_env = {
        "EMBEDDING_READ_TIMEOUT": os.environ.get("EMBEDDING_READ_TIMEOUT"),
        "QDRANT_URL": os.environ.get("QDRANT_URL"),
        "QDRANT_PORT": os.environ.get("QDRANT_PORT"),
        "SIMILARITY_THRESHOLD": os.environ.get("SIMILARITY_THRESHOLD"),
        "EMBEDDING_DIMENSION": os.environ.get("EMBEDDING_DIMENSION"),
    }

    # Set integration test environment
    os.environ["EMBEDDING_READ_TIMEOUT"] = "60.0"  # CPU mode: 40-50s observed
    os.environ["QDRANT_URL"] = "http://localhost:26350"
    os.environ["QDRANT_PORT"] = "26350"
    # Production threshold for Jina model (supports mixed NL + code queries)
    # 0.4 balances quality with coverage for SessionStart query patterns
    # See TECH-DEBT-002: Semantic query matching considerations
    os.environ["SIMILARITY_THRESHOLD"] = "0.4"
    # DEC-010: Jina Embeddings v2 Base Code uses 768 dimensions
    # Fix per code review: store_async.py defaults to 3584 which causes dimension mismatch
    os.environ["EMBEDDING_DIMENSION"] = "768"

    yield

    # Restore original environment after session
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# =============================================================================
# Shared Integration Test Helpers (Story 5.4 Code Review - Issue 7 fix)
# =============================================================================


def wait_for_qdrant_healthy(timeout: int = 60) -> None:
    """Wait for Qdrant to become healthy after restart.

    Uses health check endpoint with exponential backoff (2026 best practice).
    Per: https://qdrant.tech/documentation/guides/common-errors/

    Args:
        timeout: Maximum seconds to wait (default: 60)

    Raises:
        TimeoutError: If Qdrant not healthy within timeout

    Best Practice: Exponential backoff reduces API call frequency during startup.
    Total wait: 1+2+3+5+5+... seconds (efficient, prevents thundering herd).
    Source: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

    Note: Moved to conftest.py from test_persistence.py per Story 5.4 code review
    Issue 7 - sys.path anti-pattern fix.
    """
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:26350")
    start = time.time()
    wait_intervals = [1, 2, 3, 5, 5, 5]  # Total ~21s before 1s intervals
    interval_index = 0

    while time.time() - start < timeout:
        try:
            # Qdrant doesn't have /health endpoint - use collections check directly
            client = QdrantClient(url=qdrant_url, timeout=5.0)
            client.get_collections()
            return  # Success - Qdrant is healthy
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError,
                httpcore.ReadError, httpcore.ConnectError,
                ConnectionRefusedError, UnexpectedResponse, ResponseHandlingException, OSError):
            # Specific connection-related exceptions only
            # ResponseHandlingException wraps underlying connection errors in qdrant-client
            pass

        # Exponential backoff with cap
        wait_time = wait_intervals[min(interval_index, len(wait_intervals) - 1)]
        time.sleep(wait_time)
        interval_index += 1

    raise TimeoutError(
        f"Qdrant did not become healthy within {timeout}s after restart"
    )


# Edge case test group IDs for cleanup (Story 5.4 - Issue 5/6 fix)
EDGE_CASE_TEST_GROUP_IDS = [
    "concurrent-test",
    "malformed-test",
    "metadata-test",
    "outage-test",
    "timeout-test",
]


@pytest.fixture
def cleanup_edge_case_memories():
    """Fixture to cleanup edge case test memories after test completion.

    Story 5.4 Code Review - Issue 6 fix: Add cleanup fixture like test_persistence.py.

    Removes all test memories created during edge case tests to prevent
    data pollution across test runs.

    Per pytest-docker-tools best practices:
    "At the end of the test the environment will be thrown away."
    """
    yield  # Test runs here

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:26350")

    # Wait for Qdrant to be healthy before cleanup (handles post-restart state)
    try:
        wait_for_qdrant_healthy(timeout=30)
    except TimeoutError:
        return  # Skip cleanup if Qdrant not available

    # Create fresh client for cleanup
    try:
        cleanup_client = QdrantClient(url=qdrant_url, timeout=10.0)

        # Cleanup: Delete test memories by group_id
        for group_id in EDGE_CASE_TEST_GROUP_IDS:
            try:
                cleanup_client.delete(
                    collection_name="implementations",
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
