"""Integration test fixtures for AI Memory Module.

Sets up environment for integration tests that require real Docker services.

Per DEC-005: CPU mode takes 20-30s per embedding for 7B model.
GPU mode achieves <2s (NFR-P2 compliant).
Integration tests use longer timeouts for CPU compatibility.
"""

import os

import pytest

from tests.datastore_guard import assert_not_production, install_safe_defaults


def pytest_configure(config):
    """Configure environment for integration tests.

    Sets EMBEDDING_READ_TIMEOUT to 60s for CPU-bound embedding operations.
    The 7B Nomic Embed Code model on CPU requires 20-30s per embedding.

    TD-876: this used to default QDRANT_URL to the operator's live install for
    the whole directory, while the only refusal lived inside a single fixture
    and so protected nothing but that fixture's own consumers. The refusal is
    now directory-wide and shared with the root conftest, so the two levels
    cannot drift into two different answers.
    """
    # Only set if not already configured (allows override)
    if "EMBEDDING_READ_TIMEOUT" not in os.environ:
        os.environ["EMBEDDING_READ_TIMEOUT"] = "60.0"

    install_safe_defaults()
    assert_not_production()


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
