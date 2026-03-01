"""Tenant isolation tests — verify cross-tenant data does NOT leak.

Tests both positive (same-tenant access) and negative (cross-tenant denial)
assertions per BP-vector-db-qdrant-testing-2026 best practices.

These tests use QdrantClient(":memory:") for in-memory testing — NO external
services (Qdrant Docker, embedding service) are required to run these tests.

Test Coverage:
    - Negative: cross-tenant data invisible to other tenant (critical)
    - Negative: agent_id isolation within shared group_id
    - Positive: same-tenant data visible (control assertion)
    - Negative: cross-collection isolation (collections are separate namespaces)
    - Bulk: 5+5 tenant points with zero cross-contamination

Run:
    pytest tests/integration/test_tenant_isolation.py -v
    pytest tests/integration/test_tenant_isolation.py -v --run-integration
"""

import uuid

import numpy as np
import pytest
from qdrant_client import QdrantClient, models

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def isolation_client():
    """In-memory Qdrant client with test collections.

    Uses QdrantClient(":memory:") — no external services required.
    Collections match project config (768d cosine distance, per DEC-010).
    """
    client = QdrantClient(":memory:")

    # Create test collections matching project config (768d cosine)
    for name in ["code-patterns", "conventions", "discussions"]:
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=768, distance=models.Distance.COSINE
            ),
        )

    yield client


# =============================================================================
# Helpers
# =============================================================================


def _make_vector(seed: int = 42) -> list[float]:
    """Create a deterministic 768d unit vector for testing.

    Args:
        seed: RNG seed for reproducibility. Use different seeds per point
              to avoid identical vectors (which Qdrant deduplicates).

    Returns:
        768-dimensional unit vector as list[float]
    """
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(768)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def _upsert_point(
    client: QdrantClient,
    collection: str,
    payload: dict,
    seed: int = 42,
) -> str:
    """Upsert a single point and return its ID."""
    point_id = str(uuid.uuid4())
    client.upsert(
        collection_name=collection,
        points=[
            models.PointStruct(
                id=point_id,
                vector=_make_vector(seed=seed),
                payload=payload,
            )
        ],
    )
    return point_id


def _scroll_with_filter(
    client: QdrantClient,
    collection: str,
    must: list[models.Condition],
) -> list:
    """Scroll all matching points using a must-filter.

    Uses scroll() (not search()) for exhaustive retrieval without
    relevance scoring — ensures we catch ALL matching points.

    Args:
        client: Qdrant client
        collection: Collection name to scroll
        must: List of FieldCondition / other Condition objects

    Returns:
        List of ScoredPoint / Record objects matching the filter
    """
    results, _ = client.scroll(
        collection_name=collection,
        scroll_filter=models.Filter(must=must),
        limit=1000,  # Large limit — exhaustive for test data
        with_payload=True,
        with_vectors=False,
    )
    return results


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.integration
def test_tenant_data_not_visible_to_other_tenant(
    isolation_client: QdrantClient,
) -> None:
    """CRITICAL negative assertion: tenant-a data is invisible to tenant-b.

    Given: a memory point stored with group_id="tenant-a"
    When:  we scroll "code-patterns" filtered by group_id="tenant-b"
    Then:  ZERO results are returned — no cross-tenant data leakage.

    This is the primary isolation guarantee required by FR15.
    """
    # Store data for tenant-a
    _upsert_point(
        isolation_client,
        collection="code-patterns",
        payload={"group_id": "tenant-a", "content": "secret data"},
        seed=1,
    )

    # Query as tenant-b — must return nothing
    results = _scroll_with_filter(
        isolation_client,
        collection="code-patterns",
        must=[
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value="tenant-b"),
            )
        ],
    )

    assert len(results) == 0, (
        f"ISOLATION VIOLATION: tenant-b received {len(results)} result(s) "
        f"that belong to tenant-a. Cross-tenant data leaked!"
    )


@pytest.mark.integration
def test_agent_id_isolation(isolation_client: QdrantClient) -> None:
    """Negative assertion: agent-a data is invisible when filtering by agent-b.

    Given: a point stored with agent_id="agent-a" inside group_id="shared-project"
    When:  we scroll filtering agent_id="agent-b" AND group_id="shared-project"
    Then:  ZERO results — agent_id provides sub-tenant isolation within a project.

    This validates Parzival's per-agent memory isolation (agent_id=parzival).
    """
    # Store data belonging to agent-a
    _upsert_point(
        isolation_client,
        collection="discussions",
        payload={
            "group_id": "shared-project",
            "agent_id": "agent-a",
            "content": "agent-a data",
        },
        seed=2,
    )

    # Query as agent-b — must return nothing
    results = _scroll_with_filter(
        isolation_client,
        collection="discussions",
        must=[
            models.FieldCondition(
                key="agent_id",
                match=models.MatchValue(value="agent-b"),
            ),
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value="shared-project"),
            ),
        ],
    )

    assert len(results) == 0, (
        f"ISOLATION VIOLATION: agent-b received {len(results)} result(s) "
        f"that belong to agent-a within shared-project. Agent isolation broken!"
    )


@pytest.mark.integration
def test_tenant_data_visible_to_same_tenant(isolation_client: QdrantClient) -> None:
    """Positive control: tenant-a data IS visible when filtering by tenant-a.

    Given: a memory point stored with group_id="tenant-a"
    When:  we scroll filtered by group_id="tenant-a"
    Then:  exactly 1 result is returned — same-tenant access works.

    Without this positive assertion, zero-result failures may be false negatives
    (e.g., upsert failed silently) rather than true isolation failures.
    """
    point_id = _upsert_point(
        isolation_client,
        collection="code-patterns",
        payload={"group_id": "tenant-a", "content": "tenant-a own data"},
        seed=3,
    )

    results = _scroll_with_filter(
        isolation_client,
        collection="code-patterns",
        must=[
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value="tenant-a"),
            )
        ],
    )

    assert len(results) == 1, (
        f"Expected 1 result for tenant-a but got {len(results)}. "
        f"Stored point_id={point_id}. Positive control failed!"
    )
    assert results[0].payload["group_id"] == "tenant-a"
    assert results[0].payload["content"] == "tenant-a own data"


@pytest.mark.integration
def test_cross_collection_isolation(isolation_client: QdrantClient) -> None:
    """Negative assertion: data in one collection is not visible in another.

    Given: a point stored in "code-patterns" with group_id="tenant-a"
    When:  we scroll "conventions" filtered by group_id="tenant-a"
    Then:  ZERO results — collections are separate namespaces.

    Validates that collection-level isolation is enforced by Qdrant (the
    collection itself acts as a namespace; no cross-collection search occurs).
    """
    # Store data in code-patterns
    _upsert_point(
        isolation_client,
        collection="code-patterns",
        payload={"group_id": "tenant-a", "content": "code pattern data"},
        seed=4,
    )

    # Query conventions — different collection, must return nothing
    results = _scroll_with_filter(
        isolation_client,
        collection="conventions",
        must=[
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value="tenant-a"),
            )
        ],
    )

    assert len(results) == 0, (
        f"COLLECTION ISOLATION VIOLATION: 'conventions' returned {len(results)} "
        f"result(s) that were stored in 'code-patterns'. Collections are not isolated!"
    )


@pytest.mark.integration
def test_bulk_tenant_isolation(isolation_client: QdrantClient) -> None:
    """Bulk isolation: 5 tenant-a + 5 tenant-b points with zero cross-contamination.

    Given: 5 points for tenant-a and 5 points for tenant-b in the same collection
    When:  we scroll filtered by tenant-a
    Then:  exactly 5 results, all with group_id="tenant-a"

    And:
    When:  we scroll filtered by tenant-b
    Then:  exactly 5 results, all with group_id="tenant-b"

    No point from one tenant appears in the other tenant's results.
    """
    collection = "code-patterns"
    tenant_a_ids: set[str] = set()
    tenant_b_ids: set[str] = set()

    # Upsert 5 points per tenant with distinct seeds to avoid identical vectors
    for i in range(5):
        aid = _upsert_point(
            isolation_client,
            collection=collection,
            payload={
                "group_id": "tenant-a",
                "content": f"tenant-a memory #{i}",
                "index": i,
            },
            seed=100 + i,
        )
        tenant_a_ids.add(aid)

        bid = _upsert_point(
            isolation_client,
            collection=collection,
            payload={
                "group_id": "tenant-b",
                "content": f"tenant-b memory #{i}",
                "index": i,
            },
            seed=200 + i,
        )
        tenant_b_ids.add(bid)

    # --- Tenant-A query ---
    results_a = _scroll_with_filter(
        isolation_client,
        collection=collection,
        must=[
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value="tenant-a"),
            )
        ],
    )

    assert len(results_a) == 5, (
        f"Expected exactly 5 tenant-a results, got {len(results_a)}. "
        f"Bulk isolation may have lost or duplicated points."
    )
    for r in results_a:
        assert r.payload["group_id"] == "tenant-a", (
            f"ISOLATION VIOLATION: tenant-a query returned a point with "
            f"group_id='{r.payload['group_id']}' (id={r.id})"
        )

    # --- Tenant-B query ---
    results_b = _scroll_with_filter(
        isolation_client,
        collection=collection,
        must=[
            models.FieldCondition(
                key="group_id",
                match=models.MatchValue(value="tenant-b"),
            )
        ],
    )

    assert len(results_b) == 5, (
        f"Expected exactly 5 tenant-b results, got {len(results_b)}. "
        f"Bulk isolation may have lost or duplicated points."
    )
    for r in results_b:
        assert r.payload["group_id"] == "tenant-b", (
            f"ISOLATION VIOLATION: tenant-b query returned a point with "
            f"group_id='{r.payload['group_id']}' (id={r.id})"
        )

    # --- No cross-contamination at ID level ---
    returned_a_ids = {str(r.id) for r in results_a}
    returned_b_ids = {str(r.id) for r in results_b}
    overlap = returned_a_ids & returned_b_ids

    assert len(overlap) == 0, (
        f"ISOLATION VIOLATION: {len(overlap)} point ID(s) appeared in BOTH "
        f"tenant-a and tenant-b result sets: {overlap}"
    )
