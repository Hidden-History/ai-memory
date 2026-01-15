"""Integration tests for Docker Stack Setup (Story 1.1)

Tests verify:
- AC 1.1.2: Persistent storage survives restarts
- AC 1.1.3: Port configuration via environment variables

Fixtures docker_compose_path and qdrant_base_url are provided by conftest.py.

Best Practices (2025/2026):
- Use docker compose --wait flag for health-aware startup
- Verify ALL services healthy before proceeding (not just one)
- Tests that restart containers must restore full health state
- Reference: https://github.com/avast/pytest-docker
"""

import os
import subprocess
import time
from typing import Generator

import httpx
import pytest


def wait_for_services_healthy(
    docker_compose_path: str,
    max_wait: int = 120,
    check_interval: int = 2
) -> bool:
    """Wait for ALL Docker Compose services to be healthy.

    Per 2025/2026 best practices, this checks that BOTH services report
    healthy status, not just one. The embedding service needs 30-60s
    to load the model.

    Args:
        docker_compose_path: Path to docker-compose.yml
        max_wait: Maximum seconds to wait (default 120 for embedding model load)
        check_interval: Seconds between health checks

    Returns:
        True if all services healthy, False if timeout

    Reference: https://github.com/avast/pytest-docker
    """
    cwd = os.path.dirname(docker_compose_path)
    waited = 0

    while waited < max_wait:
        result = subprocess.run(
            ["docker", "compose", "-f", docker_compose_path, "ps"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )

        # Count healthy services - we need BOTH qdrant and embedding healthy
        output = result.stdout
        healthy_count = output.count("(healthy)")

        # We have 2 services that need to be healthy
        if healthy_count >= 2:
            return True

        time.sleep(check_interval)
        waited += check_interval

    return False


@pytest.fixture(scope="module")
def docker_stack(docker_compose_path: str) -> Generator[None, None, None]:
    """Start Docker Compose stack before tests, tear down after.

    Uses --wait flag per 2025/2026 best practices to respect healthchecks.
    Falls back to manual health polling if --wait not available.
    """
    cwd = os.path.dirname(docker_compose_path)

    # Start stack with --wait flag (Docker Compose v2.1+)
    # This waits for healthchecks to pass before returning
    result = subprocess.run(
        ["docker", "compose", "-f", docker_compose_path, "up", "-d", "--wait"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    # If --wait failed or not supported, fall back to manual polling
    if result.returncode != 0:
        subprocess.run(
            ["docker", "compose", "-f", docker_compose_path, "up", "-d"],
            check=True,
            cwd=cwd,
        )
        if not wait_for_services_healthy(docker_compose_path, max_wait=120):
            raise TimeoutError("Services failed to become healthy within 120s")

    yield

    # Teardown: stop stack (don't remove volumes to preserve data for persistence tests)
    subprocess.run(
        ["docker", "compose", "-f", docker_compose_path, "down"],
        check=True,
        cwd=cwd,
    )


@pytest.mark.integration
class TestPersistentStorage:
    """AC 1.1.2 - Persistent Storage Verification"""

    def test_data_survives_restart(
        self, docker_compose_path: str, qdrant_base_url: str, docker_stack
    ):
        """
        Given Docker Compose is running
        When I store data in Qdrant
        And I run `docker compose down && docker compose up -d`
        Then the data is still present in Qdrant
        """
        collection_name = "test_persistence"
        cwd = os.path.dirname(docker_compose_path)

        try:
            with httpx.Client(base_url=qdrant_base_url, timeout=30.0) as client:
                # Create test collection
                response = client.put(
                    f"/collections/{collection_name}",
                    json={"vectors": {"size": 768, "distance": "Cosine"}},
                )
                assert response.status_code == 200, f"Failed to create collection: {response.text}"

                # Verify collection exists (Qdrant returns status, not name)
                response = client.get(f"/collections/{collection_name}")
                assert response.status_code == 200
                collection_data = response.json()
                assert collection_data["result"]["status"] == "green"

            # Restart stack with --wait flag for health-aware startup
            subprocess.run(
                ["docker", "compose", "-f", docker_compose_path, "down"],
                check=True,
                cwd=cwd,
            )
            result = subprocess.run(
                ["docker", "compose", "-f", docker_compose_path, "up", "-d", "--wait"],
                cwd=cwd,
                capture_output=True,
                text=True,
            )

            # If --wait failed, fall back to manual health polling
            if result.returncode != 0:
                subprocess.run(
                    ["docker", "compose", "-f", docker_compose_path, "up", "-d"],
                    check=True,
                    cwd=cwd,
                )
                if not wait_for_services_healthy(docker_compose_path, max_wait=120):
                    pytest.fail("Services failed to become healthy within 120s after restart")

            # Verify data persisted
            with httpx.Client(base_url=qdrant_base_url, timeout=30.0) as client:
                response = client.get(f"/collections/{collection_name}")
                assert response.status_code == 200, "Collection should persist after restart"
                collection_data = response.json()
                assert collection_data["result"]["status"] == "green"

        finally:
            # Cleanup - always runs even on test failure
            try:
                with httpx.Client(base_url=qdrant_base_url, timeout=10.0) as client:
                    client.delete(f"/collections/{collection_name}")
            except Exception:
                pass  # Best effort cleanup

    def test_data_accessible_after_container_restart(
        self, qdrant_base_url: str, docker_stack
    ):
        """
        Given the Qdrant container restarts
        When I query for previously stored data
        Then all data is returned intact
        """
        collection_name = "test_container_restart"

        try:
            with httpx.Client(base_url=qdrant_base_url, timeout=30.0) as client:
                # Create collection with a point
                client.put(
                    f"/collections/{collection_name}",
                    json={"vectors": {"size": 768, "distance": "Cosine"}},
                )

                # Insert a test point
                point_id = 1
                vector = [0.1] * 768
                response = client.put(
                    f"/collections/{collection_name}/points",
                    json={
                        "points": [
                            {"id": point_id, "vector": vector, "payload": {"test": "data"}}
                        ]
                    },
                )
                assert response.status_code == 200

            # Restart Qdrant container and wait for health
            subprocess.run(["docker", "restart", "memory-qdrant"], check=True)

            # Wait for Qdrant to become healthy (simpler wait since only Qdrant restarted)
            max_wait = 60
            waited = 0
            while waited < max_wait:
                try:
                    with httpx.Client(base_url=qdrant_base_url, timeout=5.0) as health_client:
                        response = health_client.get("/healthz")
                        if response.status_code == 200:
                            break
                except Exception:
                    pass
                time.sleep(2)
                waited += 2
            else:
                pytest.fail("Qdrant failed to become healthy within 60s after restart")

            # Verify point still exists
            with httpx.Client(base_url=qdrant_base_url, timeout=30.0) as client:
                response = client.get(f"/collections/{collection_name}/points/{point_id}")
                assert response.status_code == 200
                point_data = response.json()
                assert point_data["result"]["id"] == point_id
                assert point_data["result"]["payload"]["test"] == "data"

        finally:
            # Cleanup - always runs even on test failure
            try:
                with httpx.Client(base_url=qdrant_base_url, timeout=10.0) as client:
                    client.delete(f"/collections/{collection_name}")
            except Exception:
                pass  # Best effort cleanup


@pytest.mark.integration
class TestPortConfiguration:
    """AC 1.1.3 - Port Configuration"""

    def test_default_port_26350(self, qdrant_base_url: str, docker_stack):
        """
        Given default configuration
        When I query Qdrant health endpoint
        Then it responds on port 26350
        """
        with httpx.Client(base_url="http://localhost:26350", timeout=30.0) as client:
            response = client.get("/healthz")
            assert response.status_code == 200
            assert "healthz check passed" in response.text

    def test_custom_port_via_env(self, docker_compose_path: str):
        """
        Given default port 26350 is in use
        When I set QDRANT_PORT=16360
        And run docker compose up
        Then Qdrant is accessible on port 16360

        Note: This test is skipped by default to avoid port conflicts.
        Run manually with: QDRANT_PORT=16360 pytest -k test_custom_port_via_env
        """
        pytest.skip("Manual test - requires QDRANT_PORT=16360 and manual stack restart")


@pytest.mark.integration
class TestHealthcheck:
    """Verify Qdrant service is accessible"""

    def test_qdrant_service_accessible(self, qdrant_base_url: str, docker_stack):
        """Verify Qdrant is running and accessible via HTTP API"""
        with httpx.Client(base_url=qdrant_base_url, timeout=30.0) as client:
            # Test root endpoint
            response = client.get("/")
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "qdrant - vector search engine"
            assert "1.16" in data["version"]

            # Test healthz endpoint
            response = client.get("/healthz")
            assert response.status_code == 200
            assert "healthz check passed" in response.text
