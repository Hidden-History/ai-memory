"""Integration tests for monitoring API.

Tests verify 2026 FastAPI monitoring best practices:
- Kubernetes liveness/readiness probes
- Health checks with dependency validation
- Async endpoints
- Pydantic response models
- Structured logging
"""

import pytest
import httpx


@pytest.fixture(scope="module")
def monitoring_api_url():
    """Monitoring API base URL."""
    return "http://localhost:28000"


@pytest.mark.integration
def test_health_endpoint(monitoring_api_url):
    """Test health endpoint returns correct status with Qdrant check."""
    response = httpx.get(f"{monitoring_api_url}/health", timeout=10)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["qdrant_available"] is True
    assert data["collections_count"] >= 0


@pytest.mark.integration
def test_health_endpoint_structure(monitoring_api_url):
    """Test health endpoint returns Pydantic-validated structure (2026)."""
    response = httpx.get(f"{monitoring_api_url}/health", timeout=10)

    data = response.json()
    # Verify all required fields present (Pydantic validation)
    assert "status" in data
    assert "qdrant_available" in data
    assert "collections_count" in data
    # Verify types
    assert isinstance(data["status"], str)
    assert isinstance(data["qdrant_available"], bool)
    assert isinstance(data["collections_count"], int)


@pytest.mark.integration
def test_liveness_probe(monitoring_api_url):
    """Test Kubernetes liveness probe (2026 best practice)."""
    response = httpx.get(f"{monitoring_api_url}/live", timeout=10)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.integration
def test_readiness_probe(monitoring_api_url):
    """Test Kubernetes readiness probe (2026 best practice)."""
    response = httpx.get(f"{monitoring_api_url}/ready", timeout=10)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["qdrant_available"] is True


@pytest.mark.integration
def test_collection_stats(monitoring_api_url):
    """Test collection statistics endpoint."""
    response = httpx.get(f"{monitoring_api_url}/stats/implementations", timeout=10)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["collection"] == "code-patterns"
    assert "points_count" in data
    assert "vectors_count" in data
    assert "indexed_vectors_count" in data


@pytest.mark.integration
def test_collection_stats_not_found(monitoring_api_url):
    """Test collection stats with non-existent collection."""
    response = httpx.get(f"{monitoring_api_url}/stats/nonexistent", timeout=10)

    assert response.status_code == 404


@pytest.mark.integration
def test_memory_endpoint_not_found(monitoring_api_url):
    """Test GET /memory/{memory_id} returns not_found for non-existent memory."""
    # Use valid UUID format - Qdrant requires UUID or integer IDs
    response = httpx.get(
        f"{monitoring_api_url}/memory/550e8400-e29b-41d4-a716-446655440000",
        params={"collection": "code-patterns"},
        timeout=10
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_found"
    assert data["data"] is None
    assert "error" in data
    assert "not found" in data["error"].lower()


@pytest.mark.integration
def test_memory_endpoint_structure(monitoring_api_url):
    """Test /memory endpoint returns Pydantic-validated response structure."""
    # Use valid UUID format - Qdrant requires UUID or integer IDs
    response = httpx.get(
        f"{monitoring_api_url}/memory/00000000-0000-0000-0000-000000000001",
        params={"collection": "code-patterns"},
        timeout=10
    )

    data = response.json()
    # Verify all MemoryResponse fields present (Pydantic validation)
    assert "status" in data
    assert "data" in data
    assert "error" in data
    # Verify types
    assert isinstance(data["status"], str)
    assert data["data"] is None or isinstance(data["data"], dict)
    assert data["error"] is None or isinstance(data["error"], str)


@pytest.mark.integration
def test_memory_endpoint_invalid_collection(monitoring_api_url):
    """Test /memory with non-existent collection returns 503."""
    # Use valid UUID format for ID, but non-existent collection
    response = httpx.get(
        f"{monitoring_api_url}/memory/00000000-0000-0000-0000-000000000002",
        params={"collection": "nonexistent_collection"},
        timeout=10
    )

    # Qdrant returns UnexpectedResponse for non-existent collection → 503
    assert response.status_code == 503


@pytest.mark.integration
def test_openapi_docs_available(monitoring_api_url):
    """Test OpenAPI documentation endpoints (2026 standard)."""
    # Swagger UI
    response = httpx.get(f"{monitoring_api_url}/docs", timeout=10)
    assert response.status_code == 200

    # ReDoc
    response = httpx.get(f"{monitoring_api_url}/redoc", timeout=10)
    assert response.status_code == 200


@pytest.mark.integration
def test_async_endpoint_performance(monitoring_api_url):
    """Test that async endpoints perform well (2026 best practice)."""
    import time

    start = time.time()
    response = httpx.get(f"{monitoring_api_url}/health", timeout=10)
    elapsed = time.time() - start

    assert response.status_code == 200
    # Health check should complete in <2s per NFR-P3
    assert elapsed < 2.0
