"""Integration test fixtures for AI Memory Module.

Sets up environment for integration tests that require real Docker services.

Per DEC-005: CPU mode takes 20-30s per embedding for 7B model.
GPU mode achieves <2s (NFR-P2 compliant).
Integration tests use longer timeouts for CPU compatibility.
"""

import contextlib
import os
import shutil
import socket
import subprocess
import time
import uuid

import httpx
import pytest


def pytest_configure(config):
    """Configure environment for integration tests.

    Sets EMBEDDING_READ_TIMEOUT to 60s for CPU-bound embedding operations.
    The 7B Nomic Embed Code model on CPU requires 20-30s per embedding.
    Sets QDRANT_URL to correct host port (26350 not container port 6333).
    """
    # Only set if not already configured (allows override)
    if "EMBEDDING_READ_TIMEOUT" not in os.environ:
        os.environ["EMBEDDING_READ_TIMEOUT"] = "60.0"

    # Set correct Qdrant URL for integration tests (host port, not container port)
    if "QDRANT_URL" not in os.environ:
        os.environ["QDRANT_URL"] = "http://localhost:26350"


def pytest_collection_modifyitems(items):
    """Auto-apply @pytest.mark.integration to all tests in this directory.

    Ensures `pytest -m 'not integration'` excludes ALL integration tests,
    even if individual test classes lack explicit markers (TD-158).
    """
    for item in items:
        if "/tests/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session", autouse=True)
def integration_environment():
    """Ensure integration test environment is properly configured.

    This fixture runs automatically for all integration tests.
    """
    # Verify embedding timeout is set appropriately for CPU mode
    timeout = float(os.environ.get("EMBEDDING_READ_TIMEOUT", "15.0"))
    if timeout < 30.0:
        import warnings

        warnings.warn(
            f"EMBEDDING_READ_TIMEOUT={timeout}s may be too short for CPU mode. "
            "7B model typically needs 20-30s. Set EMBEDDING_READ_TIMEOUT=60 for safety.",
            stacklevel=2,
        )
    yield


# ─── Ephemeral Qdrant (BP-194 Q5 / PLAN-036 P1) ────────────────────────────────
# Payload-index integrity tests need a REAL Qdrant — a permissive fake reports
# an index as present the instant it is "created" and cannot catch the
# async-write race (issue #337: wait=false PUTs return `acknowledged`, and a
# get_collection() immediately after sees only a few of them). This fixture
# never targets the operator's live installation on :26350.

_QDRANT_IMAGE = "qdrant/qdrant:v1.16.3"  # pinned to match docker/docker-compose.yml


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def ephemeral_qdrant():
    """A real, throwaway Qdrant instance for payload-index teeth tests.

    In CI, the ``integration-tests`` job already provisions its own ephemeral
    Qdrant service container and exports ``QDRANT_HOST``/``QDRANT_PORT`` — that
    instance is reused directly. Locally, spins up a throwaway
    ``qdrant/qdrant:v1.16.3`` container on a random free port and tears it
    down at session end.

    Yields:
        dict with ``host``, ``port``, ``api_key`` (``api_key`` is ``None``
        when no auth is configured).
    """
    ci_host = os.environ.get("QDRANT_HOST")
    ci_port = os.environ.get("QDRANT_PORT")
    if ci_host and ci_port and int(ci_port) != 26350:
        yield {
            "host": ci_host,
            "port": int(ci_port),
            "api_key": os.environ.get("QDRANT_API_KEY") or None,
        }
        return

    if not shutil.which("docker"):
        pytest.skip("docker not available to start an ephemeral Qdrant")

    port = _free_port()
    container = f"aim-test-qdrant-{uuid.uuid4().hex[:8]}"
    proc = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "-p",
            f"127.0.0.1:{port}:6333",
            _QDRANT_IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        pytest.skip(f"could not start ephemeral Qdrant: {proc.stderr.strip()}")

    try:
        deadline = time.monotonic() + 30
        url = f"http://127.0.0.1:{port}/healthz"
        healthy = False
        while time.monotonic() < deadline:
            with contextlib.suppress(Exception):
                if httpx.get(url, timeout=2.0).status_code == 200:
                    healthy = True
                    break
            time.sleep(0.5)
        if not healthy:
            pytest.skip("ephemeral Qdrant did not become healthy in time")

        yield {"host": "127.0.0.1", "port": port, "api_key": None}
    finally:
        subprocess.run(["docker", "stop", container], capture_output=True, timeout=30)
