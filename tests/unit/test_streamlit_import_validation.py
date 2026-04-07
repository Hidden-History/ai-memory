"""Tests for Streamlit import validation (TD-384).

Unit test file - NOT in tests/integration/ to avoid path-based skip markers.
This test MUST run in CI to alert when Streamlit dependencies are missing.
"""

import os
import sys


def test_streamlit_import_succeeds_in_ci():
    """Validate that Streamlit app can be imported.

    TD-384: This test MUST NOT be skipped. It should FAIL when
    Streamlit dependencies are missing, alerting CI to the problem.

    If this test fails, ensure Streamlit and its dependencies are
    installed in the test environment.

    Install: pip install streamlit qdrant-client httpx
    """
    import_error = None
    streamlit_imported = False

    try:
        sys.path.insert(
            0,
            os.path.join(os.path.dirname(__file__), "..", "..", "docker", "streamlit"),
        )
        from app import COLLECTION_NAMES, COLLECTION_TYPES  # noqa: F401

        streamlit_imported = True
    except ImportError as e:
        import_error = str(e)
        streamlit_imported = False

    assert streamlit_imported, (
        f"Streamlit app import failed: {import_error}. "
        f"Streamlit dependencies are required for CI to validate "
        f"COLLECTION_TYPES against MemoryType enum. "
        f"Install with: pip install streamlit qdrant-client httpx"
    )
