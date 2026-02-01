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

import contextlib
import os
import socket
import sys
import time
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import httpcore
import httpx
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from src.memory.models import EmbeddingStatus, MemoryType

# Add tests directory to sys.path so test_session_start.py can import
# session_start_test_helpers from tests directory
tests_dir = Path(__file__).parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))


# =============================================================================
# Pytest CLI Options (BP-031: GitHub Actions CI for Docker-Dependent Tests)
# =============================================================================


def pytest_addoption(parser):
    """Add custom command line options for test selection."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests requiring external services (Qdrant)",
    )
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests requiring Playwright browsers",
    )


# =============================================================================
# Service Availability Check (TECH-DEBT-019)
# =============================================================================


def _is_port_open(port: int, host: str = "localhost") -> bool:
    """Check if a port is accepting connections.

    Args:
        port: Port number to check
        host: Hostname to check (default: localhost)

    Returns:
        bool: True if port is open and accepting connections, False otherwise
    """
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


@pytest.fixture(autouse=True)
def skip_without_services(request):
    """Auto-skip tests when required services are unavailable.

    TECH-DEBT-019: Skip tests that require Docker services when services are down.

    Checks pytest markers:
    - requires_qdrant: Skips if Qdrant (port 26350) is unavailable
    - requires_embedding: Skips if Embedding service (port 28080) is unavailable
    - requires_docker_stack: Skips if either service is unavailable

    Example:
        @pytest.mark.requires_qdrant
        def test_storage():
            # Will skip if Qdrant not available on port 26350
            pass
    """
    if request.node.get_closest_marker("requires_qdrant") and not _is_port_open(26350):
        pytest.skip("Qdrant not available on port 26350")
    if request.node.get_closest_marker("requires_embedding") and not _is_port_open(28080):
        pytest.skip("Embedding service not available on port 28080")
    if request.node.get_closest_marker("requires_docker_stack") and not (
        _is_port_open(26350) and _is_port_open(28080)
    ):
        pytest.skip("Docker stack not fully available")


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

        collectors = list(REGISTRY._names_to_collectors.values())
        for collector in collectors:
            with contextlib.suppress(Exception):
                REGISTRY.unregister(collector)
    except ImportError:
        pass  # prometheus_client not installed


def pytest_collection_modifyitems(session, config, items):
    """Hook called after test collection to manage test selection.

    BP-031: GitHub Actions CI for Docker-Dependent Tests
    - Skip integration tests unless --run-integration is provided
    - Skip E2E tests unless --run-e2e is provided
    - Clean up mocked modules from collection phase

    Story 6.5: Fix module pollution from mocking during collection.
    """
    run_integration = config.getoption("--run-integration", default=False)
    run_e2e = config.getoption("--run-e2e", default=False)

    skip_integration = pytest.mark.skip(
        reason="Need --run-integration option to run integration tests"
    )
    skip_e2e = pytest.mark.skip(reason="Need --run-e2e option to run E2E tests")

    for item in items:
        # Skip integration tests unless explicitly requested
        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)

        # Skip E2E tests unless explicitly requested
        if "e2e" in item.keywords and not run_e2e:
            item.add_marker(skip_e2e)

        # Also check for path-based detection (tests in e2e/ or integration/ folders)
        item_path = str(item.fspath)
        if "/e2e/" in item_path and not run_e2e:
            item.add_marker(skip_e2e)
        if "/integration/" in item_path and not run_integration:
            item.add_marker(skip_integration)

    # Story 6.5: Clean up mocked modules from collection phase
    # test_session_retrieval_logging.py mocks these modules at import time
    # which pollutes sys.modules for other test files during collection.
    # Clean up ALL modules that may have been mocked.
    modules_to_check = [
        "memory.search",
        "memory.config",
        "memory.qdrant_client",
        "memory.health",
        "memory.project",
        "memory.logging_config",
        "memory.metrics",
        "memory.session_logger",
        # Also check src.memory.* paths for compatibility
        "src.memory.search",
        "src.memory.config",
        "src.memory.qdrant_client",
        "src.memory.health",
        "src.memory.project",
        "src.memory.logging_config",
        "src.memory.metrics",
        "src.memory.session_logger",
    ]
    for module_path in modules_to_check:
        if module_path in sys.modules:
            mod = sys.modules[module_path]
            # Check if it's a Mock (mocks have _mock_name or spec attributes)
            if isinstance(mod, Mock) or hasattr(mod, "_mock_name"):
                del sys.modules[module_path]
                # Also delete any sub-modules
                keys_to_delete = [
                    k for k in sys.modules if k.startswith(f"{module_path}.")
                ]
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
    collectors = list(REGISTRY._names_to_collectors.values())
    for collector in collectors:
        with contextlib.suppress(Exception):
            REGISTRY.unregister(collector)

    # Remove metrics modules from sys.modules (both src.memory and memory paths)
    modules_to_remove = [
        k
        for k in sys.modules
        if k.startswith("src.memory.classifier.metrics")
        or k.startswith("memory.classifier.metrics")
        or k.startswith("src.memory.metrics")
        or k.startswith("memory.metrics")
        or k.startswith("ai_memory.")
    ]
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)

    yield

    # Clean up after test - clear registry again
    collectors = list(REGISTRY._names_to_collectors.values())
    for collector in collectors:
        with contextlib.suppress(Exception):
            REGISTRY.unregister(collector)

    modules_to_remove = [
        k
        for k in sys.modules
        if k.startswith("src.memory.classifier.metrics")
        or k.startswith("memory.classifier.metrics")
        or k.startswith("src.memory.metrics")
        or k.startswith("memory.metrics")
        or k.startswith("ai_memory.")
    ]
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

    # Get the ai_memory logger
    logger = logging.getLogger("ai_memory")

    # Remove all handlers from ai_memory and its children
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith("ai_memory"):
            child_logger = logging.getLogger(name)
            child_logger.handlers.clear()
            child_logger.propagate = True  # Re-enable propagation for testing

    # Clear root logger handlers as well
    logger.handlers.clear()
    logger.propagate = True

    yield

    # Clean up after test
    for name in list(logging.Logger.manager.loggerDict.keys()):
        if name.startswith("ai_memory"):
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
        vectors_count=0, points_count=0, status="green"
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
    mock = mocker.patch("src.memory.embeddings.EmbeddingClient", autospec=True)

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
        "embedding_model": "jina-embeddings-v2-base-en",
        "timestamp": "2026-01-11T00:00:00Z",
        "metadata": {
            "tags": ["python", "backend", "testing"],
            "domain": "backend",
            "importance": "high",
        },
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
        "type": MemoryType.GUIDELINE.value,
        "source_hook": "manual",
        "session_id": "seed-session",
        "embedding_status": EmbeddingStatus.COMPLETE.value,
        "embedding_model": "jina-embeddings-v2-base-en",
        "timestamp": "2026-01-11T00:00:00Z",
        "metadata": {
            "tags": ["logging", "python", "best-practice"],
            "domain": "observability",
            "importance": "high",
        },
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
                "tags": ["python", "testing"],
            },
        },
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
    return os.path.join(os.path.dirname(__file__), "../docker/docker-compose.yml")


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
        Index is created once per test and reused for "code-patterns" collection.
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

    # Ensure all v2.0 collections exist (code-patterns + conventions + discussions)
    try:
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        from qdrant_client.models import Distance, VectorParams

        if "code-patterns" not in collection_names:
            # Create code-patterns collection (DEC-010: 768d)
            client.create_collection(
                collection_name="code-patterns",
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )

        # Create conventions collection for cross-project sharing (Story 4.3, AC 4.4.4)
        if "conventions" not in collection_names:
            client.create_collection(
                collection_name="conventions",
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )

        # Create group_id index with is_tenant=True for both collections (AC 4.2.3)
        from src.memory.qdrant_client import create_group_id_index

        for collection in ["code-patterns", "conventions"]:
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
    with contextlib.suppress(Exception):
        qdrant_client.delete(f"/collections/{collection_name}")


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
            check=False,
        )
        services_running = len(result.stdout.strip()) > 0
        yield services_running
    except Exception:
        yield False


def _check_service_available(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a service is available on host:port.

    Args:
        host: Service hostname
        port: Service port
        timeout: Connection timeout in seconds

    Returns:
        bool: True if service is reachable, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.fixture(autouse=True)
def skip_if_service_unavailable(request):
    """Auto-skip tests marked with service requirements if services not available.

    Checks for pytest markers and skips tests if required services aren't running:
    - @pytest.mark.requires_qdrant: Skips if Qdrant (port 26350) unavailable
    - @pytest.mark.requires_embedding: Skips if Embedding service (port 28080) unavailable
    - @pytest.mark.requires_docker_stack: Skips if either service unavailable

    This fixture runs automatically (autouse=True) before each test.

    Example:
        @pytest.mark.requires_qdrant
        def test_qdrant_integration():
            # Test automatically skipped if Qdrant not running
            pass

    Best Practice (2026): Declarative marker-based skipping prevents test pollution
    and provides clear test requirements in test signatures.
    Source: https://docs.pytest.org/en/stable/how-to/skipping.html
    """
    # Get marker from test
    requires_qdrant = request.node.get_closest_marker("requires_qdrant")
    requires_embedding = request.node.get_closest_marker("requires_embedding")
    requires_docker_stack = request.node.get_closest_marker("requires_docker_stack")

    # Check if any service marker is present
    if not (requires_qdrant or requires_embedding or requires_docker_stack):
        return  # No service requirements, continue test

    # Get configured ports from environment
    qdrant_port = int(os.environ.get("QDRANT_PORT", "26350"))
    embedding_port = int(os.environ.get("EMBEDDING_SERVICE_PORT", "28080"))

    # Check service availability based on markers
    if (requires_qdrant or requires_docker_stack) and not _check_service_available(
        "localhost", qdrant_port
    ):
        pytest.skip(f"Qdrant service not available on port {qdrant_port}")

    if (requires_embedding or requires_docker_stack) and not _check_service_available(
        "localhost", embedding_port
    ):
        pytest.skip(f"Embedding service not available on port {embedding_port}")


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
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.ReadError,
            httpcore.ReadError,
            httpcore.ConnectError,
            ConnectionRefusedError,
            UnexpectedResponse,
            ResponseHandlingException,
            OSError,
        ):
            # Specific connection-related exceptions only
            # ResponseHandlingException wraps underlying connection errors in qdrant-client
            pass

        # Exponential backoff with cap
        wait_time = wait_intervals[min(interval_index, len(wait_intervals) - 1)]
        time.sleep(wait_time)
        interval_index += 1

    raise TimeoutError(f"Qdrant did not become healthy within {timeout}s after restart")


# Edge case test content patterns for cleanup (TECH-DEBT-024 fix)
# Tests create dynamic group_ids (e.g., "concurrent-test-edge-{timestamp}")
# but we need to match by CONTENT patterns since group_ids are unpredictable.
# Qdrant 2026 best practice: scroll + content filter + delete by IDs
EDGE_CASE_TEST_CONTENT_PATTERNS = [
    "Concurrent test memory",
    "test implementation",
    "Malformed test",
    "Timeout test",
    "edge-case-test",
    "test-memory-content",
]


@pytest.fixture
def cleanup_edge_case_memories():
    """Fixture to cleanup edge case test memories after test completion.

    Story 5.4 Code Review - Issue 6 fix: Add cleanup fixture like test_persistence.py.
    TECH-DEBT-024 Fix: Changed from static group_id matching to content-based
    pattern matching since tests create dynamic group_ids.

    Qdrant 2026 Best Practice: Scroll + filter in Python + delete by IDs.
    This handles dynamic group_ids like "concurrent-test-edge-{timestamp}".

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

        # Qdrant 2026 Best Practice: Scroll all points, filter by content, delete by IDs
        # This handles dynamic group_ids that can't be predicted at fixture definition time
        try:
            results, _ = cleanup_client.scroll(
                collection_name="code-patterns",
                limit=500,  # Reasonable limit for test data
                with_payload=True,
                with_vectors=False,  # Optimization: don't fetch vectors
            )

            # Filter points by content patterns (test data has recognizable patterns)
            test_point_ids = []
            for point in results:
                content = point.payload.get("content", "")
                group_id = point.payload.get("group_id", "")

                # Match by content patterns
                content_match = any(
                    pattern.lower() in content.lower()
                    for pattern in EDGE_CASE_TEST_CONTENT_PATTERNS
                )

                # Also match by group_id prefix (handles dynamic timestamps)
                group_id_match = any(
                    group_id.startswith(prefix)
                    for prefix in [
                        "concurrent-test-",
                        "malformed-test-",
                        "metadata-test-",
                        "outage-test-",
                        "timeout-test-",
                        "edge-case-",
                    ]
                )

                if content_match or group_id_match:
                    test_point_ids.append(point.id)

            # Delete identified test points
            if test_point_ids:
                cleanup_client.delete(
                    collection_name="code-patterns", points_selector=test_point_ids
                )
        except Exception:
            # Best effort cleanup - don't fail test if cleanup fails
            pass
    except Exception:
        # Silently fail cleanup if Qdrant unreachable
        pass
