"""Teeth tests for the canonical payload-index set against a REAL Qdrant
(BUG-530 / issue #337 / BP-194 Q5 / PLAN-036 P1).

``tests/unit/test_payload_index_helper.py`` locks in the canonical set against
an in-memory ``FakeQdrantClient`` — but a fake reports an index as present the
instant it is "created" and cannot catch the async-write race that caused
issue #337 (raw REST index PUTs without ``wait=true`` return ``acknowledged``;
a ``get_collection()`` immediately after sees only a few of them). These tests
run the same recreate paths against a real, ephemeral Qdrant (never the
operator's live install on :26350 — see ``ephemeral_qdrant`` in conftest.py)
and assert the full canonical set is present *immediately* after each path
returns, with no sleep.

Verified RED (before the ``wait=true`` + read-back fix in
``ensure_payload_indexes`` / ``ensure_canonical_payload_indexes``) / GREEN
(after) by running this file against the pre-fix and post-fix checkout.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
)
from memory.qdrant_client import canonical_payload_indexes, ensure_payload_indexes

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE_V2_SCRIPT = _REPO_ROOT / "scripts" / "memory" / "migrate_v2_collections.py"
MIGRATE_V221_SCRIPT = _REPO_ROOT / "scripts" / "migrate_v221_hybrid_vectors.py"
RESTORE_SCRIPT = _REPO_ROOT / "scripts" / "restore_qdrant.py"

ALL_COLLECTIONS = [
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
]


def _client(ephemeral_qdrant: dict) -> QdrantClient:
    return QdrantClient(
        host=ephemeral_qdrant["host"],
        port=ephemeral_qdrant["port"],
        api_key=ephemeral_qdrant["api_key"],
        https=False,
        check_compatibility=False,
    )


def _bare_collection(client: QdrantClient, name: str) -> None:
    """Create an empty 4-dim collection under ``name``; no payload indexes."""
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )


def _load_script(path: Path, name: str, ephemeral_qdrant: dict):
    """Load a restore/migration script module pointed at the ephemeral Qdrant.

    ``restore_qdrant.py`` calls ``load_install_env()`` at import time, which
    would otherwise pull the operator's REAL installed ``docker/.env``
    (QDRANT_PORT=26350) into the module's QDRANT_HOST/QDRANT_PORT globals.
    Overriding those module attributes immediately after load — before any
    function that reads them is called — redirects every REST call in the
    module to the ephemeral instance regardless of what the load picked up.
    """
    saved_env = dict(os.environ)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)

    if hasattr(module, "QDRANT_HOST"):
        module.QDRANT_HOST = ephemeral_qdrant["host"]
        module.QDRANT_PORT = ephemeral_qdrant["port"]
        module.QDRANT_API_KEY = ephemeral_qdrant["api_key"] or ""
    return module


# ─── Path: memory.qdrant_client.ensure_payload_indexes (SDK) ──────────────────
# Shared by scripts/setup-collections.py, scripts/memory/migrate_v2_collections.py
# and scripts/migrate_v221_hybrid_vectors.py::ensure_canonical_payload_indices —
# all three funnel through this single authoring site (BP-194 Q5 #1).


class TestEnsurePayloadIndexesRealQdrant:
    @pytest.mark.parametrize("collection", ALL_COLLECTIONS)
    def test_full_canonical_set_immediately_present(self, ephemeral_qdrant, collection):
        # Uses the literal collection name so COLLECTION_PAYLOAD_INDEXES extras
        # (e.g. github's github_id, jira-data's jira_issue_key) are exercised.
        client = _client(ephemeral_qdrant)
        _bare_collection(client, collection)
        try:
            ensure_payload_indexes(client, collection)
            live = set(client.get_collection(collection).payload_schema or {})
            assert live == set(canonical_payload_indexes(collection)), (
                f"{collection}: canonical set not fully present immediately "
                f"after ensure_payload_indexes (async-write race, issue #337)"
            )
        finally:
            client.delete_collection(collection)


# ─── Path: scripts/memory/migrate_v2_collections.py ────────────────────────────


def test_migrate_v2_create_collection_if_not_exists_real_qdrant(ephemeral_qdrant):
    module = _load_script(MIGRATE_V2_SCRIPT, "migrate_v2_teeth", ephemeral_qdrant)
    client = _client(ephemeral_qdrant)
    name = f"aim_teeth_{uuid.uuid4().hex[:10]}"
    try:
        created = module.create_collection_if_not_exists(client, name)
        assert created is True
        live = set(client.get_collection(name).payload_schema or {})
        # `name` is not a registered collection, so canonical_payload_indexes(name)
        # resolves to the base set only — this path does not carry per-collection
        # extras (it is used for the fixed code-patterns/conventions/discussions
        # collections in production, where the caller passes the real name).
        assert live == set(canonical_payload_indexes(name))
    finally:
        client.delete_collection(name)


# ─── Path: scripts/migrate_v221_hybrid_vectors.py ──────────────────────────────


def test_migrate_v221_ensure_canonical_payload_indices_real_qdrant(ephemeral_qdrant):
    module = _load_script(MIGRATE_V221_SCRIPT, "migrate_v221_teeth", ephemeral_qdrant)
    client = _client(ephemeral_qdrant)
    name = f"aim_teeth_{uuid.uuid4().hex[:10]}"
    _bare_collection(client, name)
    try:
        module.ensure_canonical_payload_indices(client, name)
        live = set(client.get_collection(name).payload_schema or {})
        # `name` is not a registered collection — base set only (see comment
        # in the migrate_v2 test above).
        assert live == set(canonical_payload_indexes(name))
    finally:
        client.delete_collection(name)


# ─── Path: scripts/restore_qdrant.py (raw REST) ────────────────────────────────


class TestRestoreEnsureCanonicalIndexesRealQdrant:
    @pytest.mark.parametrize("collection", ALL_COLLECTIONS)
    def test_full_canonical_set_immediately_present_over_rest(
        self, ephemeral_qdrant, collection
    ):
        module = _load_script(RESTORE_SCRIPT, "restore_teeth", ephemeral_qdrant)
        client = _client(ephemeral_qdrant)
        _bare_collection(client, collection)
        try:
            module.ensure_canonical_payload_indexes(collection)
            live = set(client.get_collection(collection).payload_schema or {})
            assert live == set(canonical_payload_indexes(collection)), (
                f"{collection}: canonical set not fully present immediately "
                f"after restore's REST ensure_canonical_payload_indexes "
                f"(async-write race, issue #337)"
            )
        finally:
            client.delete_collection(collection)

    def test_raises_loud_when_indexes_cannot_land(self, ephemeral_qdrant):
        """BLOCKER fix: a canonical field missing after ensure fails loud.

        Every PUT against a collection that does not exist returns non-200,
        so no canonical field lands — the read-back verify must raise rather
        than silently report success (the #337 bug class: a restore that
        looks green but degrades search).
        """
        module = _load_script(RESTORE_SCRIPT, "restore_teeth_missing", ephemeral_qdrant)
        missing_collection = f"aim_teeth_does_not_exist_{uuid.uuid4().hex[:8]}"

        with pytest.raises(RuntimeError, match=missing_collection):
            module.ensure_canonical_payload_indexes(missing_collection)
