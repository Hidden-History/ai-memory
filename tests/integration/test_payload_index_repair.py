"""Integration teeth for the non-destructive payload-index repair command
(BUG-530 / PLAN-036 P4 / issue #337).

Runs ``scripts/memory/repair_payload_indexes.py::repair_collection`` against
a REAL, ephemeral Qdrant (never the operator's live install on :26350 — see
``ephemeral_qdrant`` in conftest.py, TD-876). Mirrors
``tests/integration/test_payload_index_teeth.py``'s client/collection-naming
helpers but does NOT reuse its name-set-only assertion pattern (P5 owns that
repair) — this file asserts point-count invariance and exercises the actual
failing operation (``scroll(..., order_by="timestamp")``) directly.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Direction,
    Distance,
    OrderBy,
    PointStruct,
    VectorParams,
)

from memory.config import MemoryConfig
from memory.qdrant_client import canonical_payload_indexes
from memory.search import MemorySearch

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPAIR_SCRIPT = _REPO_ROOT / "scripts" / "memory" / "repair_payload_indexes.py"


def _load_repair_module():
    spec = importlib.util.spec_from_file_location(
        "repair_payload_indexes_teeth", _REPAIR_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


repair = _load_repair_module()


def _client(ephemeral_qdrant: dict) -> QdrantClient:
    return QdrantClient(
        host=ephemeral_qdrant["host"],
        port=ephemeral_qdrant["port"],
        api_key=ephemeral_qdrant["api_key"],
        https=False,
        check_compatibility=False,
    )


def _test_collection_name() -> str:
    # Never a real collection name — see the identical rationale in
    # test_payload_index_teeth.py::_test_collection_name.
    return f"aim_repair_{uuid.uuid4().hex[:8]}"


def _seed_stripped_collection(
    client: QdrantClient, name: str, group_id: str, n: int
) -> None:
    """Create a bare collection (zero payload indexes) with `n` real points.

    A bare collection is exactly the #337-broken state: data present, no
    canonical payload indexes, so `scroll(order_by="timestamp")` raises.
    """
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    client.upsert(
        collection_name=name,
        points=[
            PointStruct(
                id=i,
                vector=[0.1, 0.2, 0.3, 0.4],
                payload={
                    "group_id": group_id,
                    "type": "note",
                    "content": f"seeded content {i}",
                    "timestamp": datetime(2026, 7, 25, 0, 0, i, tzinfo=UTC).isoformat(),
                    "source_hook": "test",
                    "content_hash": f"hash{i}",
                    "decay_score": 1.0,
                    "freshness_status": "fresh",
                    "source_authority": 1.0,
                    "is_current": True,
                    "version": 1,
                },
            )
            for i in range(n)
        ],
        wait=True,
    )


class TestRepairCollectionRealQdrant:
    def test_repair_restores_canonical_schema_points_unchanged_and_scroll_works(
        self, ephemeral_qdrant
    ):
        client = _client(ephemeral_qdrant)
        name = _test_collection_name()
        group_id = f"aim-repair-test-{uuid.uuid4().hex[:8]}"
        _seed_stripped_collection(client, name, group_id, n=3)
        try:
            # Precondition: genuinely broken today — the #337 failure mode.
            with pytest.raises(Exception, match="range index"):
                client.scroll(
                    collection_name=name,
                    limit=5,
                    order_by=OrderBy(key="timestamp", direction=Direction.DESC),
                )

            before_count = client.count(name, exact=True).count
            assert before_count == 3

            result = repair.repair_collection(client, name, dry_run=False)

            assert result["outcome"] == "success", result
            assert result["point_count_before"] == 3
            assert result["point_count_after"] == 3

            live_schema = set(client.get_collection(name).payload_schema or {})
            assert live_schema == set(canonical_payload_indexes(name))

            after_count = client.count(name, exact=True).count
            assert after_count == 3

            # The precise operation that fails today must now return.
            points, _ = client.scroll(
                collection_name=name,
                limit=5,
                order_by=OrderBy(key="timestamp", direction=Direction.DESC),
            )
            assert len(points) == 3
        finally:
            client.delete_collection(name)

    def test_get_recent_returns_after_repair(self, ephemeral_qdrant):
        """Empirical check of the plan's named MemorySearch.get_recent criterion.

        MemorySearch.__init__ constructs get_qdrant_client(config) +
        EmbeddingClient(config). EmbeddingClient.__init__ only builds an
        httpx.Client (no network call at construction — verified by reading
        src/memory/embeddings.py), and get_recent() calls only
        self.client.scroll(...) — it never touches embedding_client. So
        MemorySearch(config) pointed at the ephemeral instance can exercise
        get_recent() with no live embedding service required.
        """
        client = _client(ephemeral_qdrant)
        name = _test_collection_name()
        group_id = f"aim-repair-test-{uuid.uuid4().hex[:8]}"
        _seed_stripped_collection(client, name, group_id, n=2)
        try:
            repair.repair_collection(client, name, dry_run=False)

            config = MemoryConfig(
                qdrant_host=ephemeral_qdrant["host"],
                qdrant_port=ephemeral_qdrant["port"],
                qdrant_api_key=None,
            )
            search = MemorySearch(config)
            results = search.get_recent(collection=name, group_id=group_id, limit=5)

            assert len(results) == 2
        finally:
            client.delete_collection(name)

    def test_repair_is_idempotent_on_second_run(self, ephemeral_qdrant):
        client = _client(ephemeral_qdrant)
        name = _test_collection_name()
        group_id = f"aim-repair-test-{uuid.uuid4().hex[:8]}"
        _seed_stripped_collection(client, name, group_id, n=4)
        try:
            first = repair.repair_collection(client, name, dry_run=False)
            assert first["outcome"] == "success"

            schema_after_first = dict(client.get_collection(name).payload_schema or {})
            count_after_first = client.count(name, exact=True).count

            second = repair.repair_collection(client, name, dry_run=False)

            assert second["outcome"] == "success"
            assert second["added_fields"] == []  # clean no-op: nothing was missing
            assert second["point_count_before"] == count_after_first
            assert second["point_count_after"] == count_after_first
            assert set(client.get_collection(name).payload_schema or {}) == set(
                schema_after_first
            )
        finally:
            client.delete_collection(name)

    def test_dry_run_makes_no_schema_change(self, ephemeral_qdrant):
        client = _client(ephemeral_qdrant)
        name = _test_collection_name()
        group_id = f"aim-repair-test-{uuid.uuid4().hex[:8]}"
        _seed_stripped_collection(client, name, group_id, n=1)
        try:
            schema_before = dict(client.get_collection(name).payload_schema or {})
            count_before = client.count(name, exact=True).count

            result = repair.repair_collection(client, name, dry_run=True)

            assert result["outcome"] == "dry_run"
            schema_after = dict(client.get_collection(name).payload_schema or {})
            assert schema_after == schema_before
            assert client.count(name, exact=True).count == count_before
        finally:
            client.delete_collection(name)
