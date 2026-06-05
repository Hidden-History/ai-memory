"""Integration test for aim-github-search default collection routing (BUG-318).

Non-mocked: seeds one point with source=github into the live `github` Qdrant
collection, runs query.py with NO --collection flag, asserts >0 rows returned.

Auto-marked @pytest.mark.integration by tests/integration/conftest.py.
Skipped automatically when Qdrant is not reachable.

Seed/teardown pattern follows test_collection_statistics.py (qdrant_client fixture)
and test_monitoring.py (upsert + cleanup in yield fixture).
"""

from __future__ import annotations

import contextlib
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WORKTREE_ROOT = Path(__file__).parent.parent.parent
_QUERY_PY = (
    _WORKTREE_ROOT
    / "_ai-memory"
    / "skills"
    / "aim-github-search"
    / "scripts"
    / "query.py"
)

_TEST_GROUP_ID = "bug318-integration-test/ai-memory"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qdrant_client():
    """Provide QdrantClient connected to the live Qdrant stack.

    Uses get_qdrant_client() — the same call path as query.py — so the
    fixture exercises the identical config/auth resolution.
    Skips the entire module if Qdrant is not reachable.
    """
    from memory.config import get_config
    from memory.qdrant_client import get_qdrant_client

    try:
        config = get_config()
        client = get_qdrant_client(config)
        client.get_collections()  # connectivity check
        return client
    except Exception as exc:
        pytest.skip(f"Qdrant not reachable: {exc}")


@pytest.fixture
def seeded_github_point(qdrant_client):
    """Seed one source=github point into the github collection; remove it in teardown.

    Yields the point ID (UUID string) so the test can reference it if needed.
    Cleanup is attempted unconditionally via contextlib.suppress so a test
    failure never orphans the point.
    """
    from qdrant_client.models import PointStruct

    from memory.config import COLLECTION_GITHUB

    point_id = str(uuid.uuid4())
    qdrant_client.upsert(
        collection_name=COLLECTION_GITHUB,
        points=[
            PointStruct(
                id=point_id,
                vector=[0.1] * 768,
                payload={
                    "source": "github",
                    "type": "github_issue",
                    "group_id": _TEST_GROUP_ID,
                    "content": "BUG-318 integration test: default collection routing",
                    "state": "open",
                },
            )
        ],
        wait=True,
    )
    yield point_id

    # Teardown: delete only the seeded test point
    with contextlib.suppress(Exception):
        from qdrant_client.models import PointIdsList

        qdrant_client.delete(
            collection_name=COLLECTION_GITHUB,
            points_selector=PointIdsList(points=[point_id]),
            wait=True,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_query_module():
    """Load query.py via importlib so tests exercise the real module without mocks.

    Sets AI_MEMORY_INSTALL_DIR to the worktree root so query.py's sys.path
    insertion resolves to the worktree src/ (same directory pytest adds via
    pythonpath config).  Purges any cached 'query' module between loads.
    """
    import os

    os.environ.setdefault("AI_MEMORY_INSTALL_DIR", str(_WORKTREE_ROOT))
    sys.modules.pop("query", None)

    spec = importlib.util.spec_from_file_location("query", _QUERY_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGithubSearchDefaultCollection:
    """Verify that query.py routes to the github collection when --collection is absent."""

    def test_default_collection_returns_seeded_point(
        self, seeded_github_point, monkeypatch, capsys
    ):
        """No --collection flag → scroll targets github collection → >0 rows returned.

        This is the canonical BUG-318 regression guard: the as-documented
        invocation must return results.
        """
        mod = _load_query_module()
        monkeypatch.setattr(
            sys,
            "argv",
            ["query.py", "--group-id", _TEST_GROUP_ID],
        )

        rc = mod.main()
        assert rc == 0

        out = capsys.readouterr().out
        # Table format prints "Found N points"; seeded exactly 1 point
        assert "Found 1 points" in out, (
            f"Expected 'Found 1 points' in output but got:\n{out}\n"
            "Possible cause: query.py is still routing to 'discussions' instead of "
            f"the 'github' collection (BUG-318). Seeded point id={seeded_github_point}"
        )
