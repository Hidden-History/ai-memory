"""Tests for the canonical payload-index helper (BUG-530 / PLAN-036 P1).

The full canonical payload-index set used to be authored only in
``scripts/setup-collections.py``. Every other path that creates or recreates a
collection either created zero indexes or copy-forwarded a captured schema that
could be empty — so a recreated collection silently lost its ``timestamp``
range index and ``get_recent()`` started raising ``QdrantUnavailable``.

These tests lock in that the set is authored once in
``memory.qdrant_client.ensure_payload_indexes`` and that all four
collection-recreate paths land the full set:

1. ``scripts/setup-collections.py``           — create_collections()
2. ``scripts/memory/migrate_v2_collections.py`` — create_collection_if_not_exists()
3. ``scripts/migrate_v221_hybrid_vectors.py``  — ensure_sparse_config()
4. ``scripts/restore_qdrant.py``               — ensure_canonical_payload_indexes()

No live Qdrant is touched: every path runs against an in-memory fake client
(or, for the REST-based restore script, a patched ``httpx.put``).
"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import KeywordIndexParams, PayloadSchemaType

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
)
from memory.qdrant_client import (
    BASE_PAYLOAD_INDEXES,
    canonical_payload_indexes,
    ensure_payload_indexes,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SETUP_SCRIPT = _REPO_ROOT / "scripts" / "setup-collections.py"
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


# ─── Fake Qdrant client ───────────────────────────────────────────────────────


class FakeQdrantClient:
    """Minimal in-memory stand-in that records payload indexes per collection.

    ``get_collection().payload_schema`` reflects the indexes created so far,
    mirroring how a real Qdrant reports them — so tests can assert on the
    resulting schema rather than on call bookkeeping.
    """

    def __init__(self, existing: list[str] | None = None):
        self.payload_schemas: dict[str, dict] = {}
        self.collections: list[str] = list(existing or [])
        self.points: dict[str, int] = {}

    # -- schema surface ----------------------------------------------------
    def create_payload_index(self, collection_name, field_name, field_schema, **_):
        self.payload_schemas.setdefault(collection_name, {})[field_name] = field_schema

    def get_collection(self, collection_name):
        return SimpleNamespace(
            payload_schema=dict(self.payload_schemas.get(collection_name, {})),
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=None, shard_number=1, on_disk_payload=True
                ),
                hnsw_config=SimpleNamespace(
                    m=16, ef_construct=100, full_scan_threshold=10000, on_disk=True
                ),
                quantization_config=None,
            ),
            points_count=self.points.get(collection_name, 0),
        )

    def schema_keys(self, collection_name) -> set[str]:
        return set(self.get_collection(collection_name).payload_schema)

    # -- collection lifecycle ---------------------------------------------
    def create_collection(self, collection_name, **_):
        self.collections.append(collection_name)
        self.payload_schemas.setdefault(collection_name, {})

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def delete_collection(self, collection_name):
        if collection_name in self.collections:
            self.collections.remove(collection_name)
        self.payload_schemas.pop(collection_name, None)

    def get_collections(self):
        return SimpleNamespace(
            collections=[SimpleNamespace(name=n) for n in self.collections]
        )

    def count(self, collection_name, **_):
        return SimpleNamespace(count=self.points.get(collection_name, 0))


def _load_script(path: Path, name: str):
    """Load a script module by file path, without leaking its env changes.

    ``restore_qdrant.py`` and ``migrate_v221_hybrid_vectors.py`` call
    ``load_install_env()`` at import time, which would otherwise push the
    operator's real installed ``.env`` into ``os.environ`` for the remainder
    of the pytest session and break unrelated config-default tests.
    """
    saved_env = dict(os.environ)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
    return module


# ─── The helper itself ────────────────────────────────────────────────────────


class TestEnsurePayloadIndexes:
    """The canonical set is authored once and applied in full."""

    @pytest.mark.parametrize("collection", ALL_COLLECTIONS)
    def test_schema_matches_canonical_set(self, collection):
        """post-ensure payload_schema (names AND field_schema values) == canonical."""
        client = FakeQdrantClient()

        ensure_payload_indexes(client, collection)

        assert client.payload_schemas[collection] == canonical_payload_indexes(
            collection
        )

    @pytest.mark.parametrize("collection", ALL_COLLECTIONS)
    def test_bug530_critical_fields_present(self, collection):
        """timestamp (order_by), content (full-text) and group_id are never lost."""
        client = FakeQdrantClient()

        ensure_payload_indexes(client, collection)

        assert {"timestamp", "content", "group_id"} <= client.schema_keys(collection)

    def test_collection_specific_extras(self):
        """Per-collection extras are additive on top of the base set."""
        base = set(BASE_PAYLOAD_INDEXES)

        assert set(canonical_payload_indexes(COLLECTION_CODE_PATTERNS)) - base == {
            "file_path"
        }
        assert set(canonical_payload_indexes(COLLECTION_DISCUSSIONS)) - base == {
            "agent_id"
        }
        assert set(canonical_payload_indexes(COLLECTION_CONVENTIONS)) == base
        assert "github_id" in canonical_payload_indexes(COLLECTION_GITHUB)
        assert "jira_issue_key" in canonical_payload_indexes(COLLECTION_JIRA_DATA)

    def test_unknown_collection_gets_base_set(self):
        """A collection with no registered extras still gets the base set."""
        assert set(canonical_payload_indexes("some-other-collection")) == set(
            BASE_PAYLOAD_INDEXES
        )

    def test_is_idempotent(self):
        """Calling twice is safe and leaves the same schema."""
        client = FakeQdrantClient()

        ensure_payload_indexes(client, COLLECTION_GITHUB)
        first = client.schema_keys(COLLECTION_GITHUB)
        ensure_payload_indexes(client, COLLECTION_GITHUB)

        assert client.schema_keys(COLLECTION_GITHUB) == first

    def test_returns_ensured_fields(self):
        """The return value names every field that was ensured."""
        client = FakeQdrantClient()

        ensured = ensure_payload_indexes(client, COLLECTION_DISCUSSIONS)

        assert set(ensured) == set(canonical_payload_indexes(COLLECTION_DISCUSSIONS))


class TestGithubFieldSchemaTypes:
    """Literal-value checks restoring the type/param assertions deleted from
    tests/unit/connectors/github/test_schema.py when the dead GITHUB_INDEXES
    list was retired for the single authoring site (TD-874).

    These compare against hardcoded expected values, NOT against
    ``canonical_payload_indexes()`` — a check derived from that same function
    can never fail when the regression is in its own source data
    (``BASE_PAYLOAD_INDEXES`` / ``COLLECTION_PAYLOAD_INDEXES``), since both
    sides of the comparison would drift together.
    """

    @pytest.fixture
    def github_schema(self):
        client = FakeQdrantClient()
        ensure_payload_indexes(client, COLLECTION_GITHUB)
        return client.payload_schemas[COLLECTION_GITHUB]

    def test_source_is_tenant_keyword(self, github_schema):
        """source uses KeywordIndexParams(type='keyword', is_tenant=True) (BUG-116)."""
        schema = github_schema["source"]
        assert isinstance(schema, KeywordIndexParams)
        assert schema.type == "keyword"
        assert schema.is_tenant is True

    def test_github_id_is_integer(self, github_schema):
        assert github_schema["github_id"] == PayloadSchemaType.INTEGER

    def test_last_synced_is_datetime(self, github_schema):
        assert github_schema["last_synced"] == PayloadSchemaType.DATETIME

    def test_is_current_is_bool(self, github_schema):
        assert github_schema["is_current"] == PayloadSchemaType.BOOL

    def test_source_authority_is_float(self, github_schema):
        assert github_schema["source_authority"] == PayloadSchemaType.FLOAT


# ─── Path 1: setup-collections.py ─────────────────────────────────────────────


class TestSetupCollectionsPath:
    def test_full_schema_on_every_created_collection(self):
        client = FakeQdrantClient()

        with (
            patch("memory.qdrant_client.get_qdrant_client", return_value=client),
            patch("memory.config.get_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock(
                qdrant_host="localhost",
                qdrant_port=6333,
                qdrant_api_key=None,
                qdrant_use_https=False,
                jira_sync_enabled=True,
            )
            module = _load_script(SETUP_SCRIPT, "setup_collections_p1")
            module.create_collections(dry_run=False, force=False)

        for collection in ALL_COLLECTIONS:
            assert client.schema_keys(collection) == set(
                canonical_payload_indexes(collection)
            ), f"{collection} did not get the canonical index set"


# ─── Path 2: migrate_v2_collections.py ────────────────────────────────────────


class TestMigrateV2Path:
    def test_created_collection_gets_full_schema(self):
        """Previously created vectors-only — zero payload indexes."""
        client = FakeQdrantClient()
        module = _load_script(MIGRATE_V2_SCRIPT, "migrate_v2_collections_p1")

        created = module.create_collection_if_not_exists(
            client, COLLECTION_CODE_PATTERNS
        )

        assert created is True
        assert client.schema_keys(COLLECTION_CODE_PATTERNS) == set(
            canonical_payload_indexes(COLLECTION_CODE_PATTERNS)
        )


# ─── Path 3: migrate_v221_hybrid_vectors.py ───────────────────────────────────


class TestMigrateV221Path:
    def test_recreated_collection_gets_full_schema_from_empty_source(self):
        """An empty captured payload_schema no longer means zero indexes."""
        module = _load_script(MIGRATE_V221_SCRIPT, "migrate_v221_p1")
        client = FakeQdrantClient(existing=[COLLECTION_DISCUSSIONS])

        with (
            patch.object(module, "collection_has_sparse", return_value=False),
            patch.object(
                module,
                "create_collection_with_sparse",
                side_effect=lambda c, name, *_: c.create_collection(name),
            ),
            patch.object(module, "scroll_copy", return_value=0),
        ):
            ok = module.ensure_sparse_config(
                client, COLLECTION_DISCUSSIONS, batch_size=100, dry_run=False
            )

        assert ok is True
        assert client.schema_keys(COLLECTION_DISCUSSIONS) == set(
            canonical_payload_indexes(COLLECTION_DISCUSSIONS)
        )

    def test_copy_forward_extras_are_preserved(self):
        """The backstop adds to the copy-forward — it does not replace it."""
        module = _load_script(MIGRATE_V221_SCRIPT, "migrate_v221_p1_extras")
        client = FakeQdrantClient()
        client.create_collection(COLLECTION_CONVENTIONS)

        module.recreate_payload_indices(
            client,
            COLLECTION_CONVENTIONS,
            {"user_added_field": SimpleNamespace(params=None, data_type="keyword")},
        )
        module.ensure_canonical_payload_indices(client, COLLECTION_CONVENTIONS)

        assert client.schema_keys(COLLECTION_CONVENTIONS) == set(
            canonical_payload_indexes(COLLECTION_CONVENTIONS)
        ) | {"user_added_field"}


# ─── Path 4: restore_qdrant.py ────────────────────────────────────────────────


def _mock_get_response(fields) -> MagicMock:
    """Fake GET /collections/{name} reporting `fields` as indexed (BP-194 Q1 read-back)."""
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "result": {
            "payload_schema": {name: {} for name in fields},
            "config": {"params": {}},
        }
    }
    return response


class TestRestorePath:
    def test_canonical_indexes_applied_over_rest(self):
        """The restore backstop PUTs the full canonical set for the collection."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1")

        put_response = MagicMock(status_code=200)
        get_response = _mock_get_response(canonical_payload_indexes(COLLECTION_GITHUB))
        with (
            patch.object(module.httpx, "put", return_value=put_response) as mock_put,
            patch.object(module.httpx, "get", return_value=get_response),
        ):
            module.ensure_canonical_payload_indexes(COLLECTION_GITHUB)

        fields = {c.kwargs["json"]["field_name"] for c in mock_put.call_args_list}
        assert fields == set(canonical_payload_indexes(COLLECTION_GITHUB))
        # BP-194 Q1: async by default — every index PUT must pass wait=true.
        assert all(
            c.kwargs.get("params") == {"wait": True} for c in mock_put.call_args_list
        )

    def test_field_schemas_are_json_serializable(self):
        """Structured schemas (keyword is_tenant, text tokenizer) survive REST."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_json")

        put_response = MagicMock(status_code=200)
        get_response = _mock_get_response(
            canonical_payload_indexes(COLLECTION_CODE_PATTERNS)
        )
        with (
            patch.object(module.httpx, "put", return_value=put_response) as mock_put,
            patch.object(module.httpx, "get", return_value=get_response),
        ):
            module.ensure_canonical_payload_indexes(COLLECTION_CODE_PATTERNS)

        sent = {
            c.kwargs["json"]["field_name"]: c.kwargs["json"]["field_schema"]
            for c in mock_put.call_args_list
        }
        assert sent["timestamp"] == "datetime"
        assert sent["group_id"]["type"] == "keyword"
        assert sent["group_id"]["is_tenant"] is True
        assert sent["content"]["type"] == "text"
        assert sent["content"]["tokenizer"] == "word"

    def test_manifest_recreate_with_empty_schema_still_indexes(self):
        """A manifest whose captured payload_schema is empty is backstopped."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_manifest")

        put_response = MagicMock(status_code=200)
        get_response = _mock_get_response(
            canonical_payload_indexes(COLLECTION_CONVENTIONS)
        )
        with (
            patch.object(module.httpx, "put", return_value=put_response) as mock_put,
            patch.object(module.httpx, "get", return_value=get_response),
        ):
            ok, err = module.create_collection_from_manifest_schema(
                COLLECTION_CONVENTIONS,
                {"params": {"vectors": {"size": 768, "distance": "Cosine"}}},
            )
            assert ok is True, err
            # The manifest carried no payload_schema — nothing was recreated.
            index_calls = [c for c in mock_put.call_args_list if "/index" in c.args[0]]
            assert index_calls == []

            module.ensure_canonical_payload_indexes(COLLECTION_CONVENTIONS)

        fields = {
            c.kwargs["json"]["field_name"]
            for c in mock_put.call_args_list
            if "/index" in c.args[0]
        }
        assert fields == set(canonical_payload_indexes(COLLECTION_CONVENTIONS))

    def test_missing_canonical_field_after_ensure_raises(self):
        """BLOCKER fix: a canonical field absent from the read-back fails loud.

        BP-194 Q1: wait=true is bounded by an internal queue timeout, so the
        PUT responses alone are not proof the index landed. If the read-back
        shows a canonical field still missing, this must raise rather than
        silently report success (issue #337's failure mode).
        """
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_missing")

        canonical = canonical_payload_indexes(COLLECTION_CONVENTIONS)
        incomplete = {k: v for k, v in canonical.items() if k != "timestamp"}
        put_response = MagicMock(status_code=200)
        get_response = _mock_get_response(incomplete)
        with (
            patch.object(module.httpx, "put", return_value=put_response),
            patch.object(module.httpx, "get", return_value=get_response),
            patch.object(module.time, "sleep"),
            pytest.raises(RuntimeError, match="timestamp"),
        ):
            module.ensure_canonical_payload_indexes(COLLECTION_CONVENTIONS)

    def test_slow_landing_index_recovers_within_poll_budget(self):
        """A field missing on the first read-back but present on a later one
        does not raise — the bounded poll gives a slow index time to land."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_slow_land")

        canonical = canonical_payload_indexes(COLLECTION_CONVENTIONS)
        incomplete = _mock_get_response(
            {k: v for k, v in canonical.items() if k != "timestamp"}
        )
        complete = _mock_get_response(canonical)
        put_response = MagicMock(status_code=200)
        with (
            patch.object(module.httpx, "put", return_value=put_response),
            patch.object(
                module.httpx, "get", side_effect=[incomplete, incomplete, complete]
            ),
            patch.object(module.time, "sleep"),
        ):
            module.ensure_canonical_payload_indexes(COLLECTION_CONVENTIONS)

    def test_transient_verify_get_failure_does_not_raise(self):
        """A read-back GET that keeps raising (timeout/connection error) is
        inconclusive, not "all fields missing" — it must not raise (and so
        must not trigger the caller's rollback of an otherwise-good restore).
        """
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_get_fail")

        put_response = MagicMock(status_code=200)
        with (
            patch.object(module.httpx, "put", return_value=put_response),
            patch.object(
                module.httpx, "get", side_effect=module.httpx.ConnectError("boom")
            ),
            patch.object(module.time, "sleep"),
        ):
            module.ensure_canonical_payload_indexes(COLLECTION_CONVENTIONS)

    def test_collection_confirmed_absent_after_ensure_still_raises(self):
        """A read-back that cleanly reports 404 (collection absent) the whole
        poll budget is a definitive answer, not a transient blip — it must
        still fail loud."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_absent")

        put_response = MagicMock(status_code=200)
        absent_get = MagicMock(status_code=404)
        with (
            patch.object(module.httpx, "put", return_value=put_response),
            patch.object(module.httpx, "get", return_value=absent_get),
            patch.object(module.time, "sleep"),
            pytest.raises(RuntimeError, match=COLLECTION_CONVENTIONS),
        ):
            module.ensure_canonical_payload_indexes(COLLECTION_CONVENTIONS)

    def test_persistent_5xx_verify_failure_does_not_raise(self):
        """A transient server-side non-200 (503) is NOT the same as a 404.

        Unlike a 404 (collection genuinely absent), a persistent 5xx during
        the read-back poll is a server-side hiccup, not evidence the
        collection is missing. Misreading it as "all fields missing" would
        raise after the poll budget and roll back an otherwise-successful
        restore. It must land in the same inconclusive bucket as a raised
        connection/timeout error.
        """
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_5xx")

        put_response = MagicMock(status_code=200)
        unavailable_get = module.httpx.Response(
            503, request=module.httpx.Request("GET", "http://qdrant/collections/x")
        )
        with (
            patch.object(module.httpx, "put", return_value=put_response),
            patch.object(module.httpx, "get", return_value=unavailable_get),
            patch.object(module.time, "sleep"),
        ):
            # Must not raise — a persistent 5xx is inconclusive, not
            # definitive-missing.
            module.ensure_canonical_payload_indexes(COLLECTION_CONVENTIONS)


class TestRestoreSchemaCompatGate:
    """BP-194 Q4: the existing-target restore gate excludes payload_schema."""

    def test_index_only_difference_does_not_block(self):
        """An index-set-only difference between manifest and live target is ignored."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_gate_relax")

        manifest_schema = {
            "params": {"vectors": {"size": 768, "distance": "Cosine"}},
            "hnsw_config": {"m": 16},
            "quantization_config": None,
            "payload_schema": {"group_id": {"data_type": "keyword"}},
        }
        live_schema = {
            "params": {"vectors": {"size": 768, "distance": "Cosine"}},
            "hnsw_config": {"m": 16},
            "quantization_config": None,
            "payload_schema": {},  # fewer indexes than the manifest — benign
        }
        assert module._data_compat_signature(
            manifest_schema
        ) == module._data_compat_signature(live_schema)

    def test_vector_dimension_difference_still_hard_fails(self):
        """A real data-incompatible difference (vector dim) still blocks restore."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_gate_strict")

        manifest_schema = {
            "params": {"vectors": {"size": 768, "distance": "Cosine"}},
            "hnsw_config": {"m": 16},
            "quantization_config": None,
            "payload_schema": {},
        }
        live_schema = {
            "params": {"vectors": {"size": 1536, "distance": "Cosine"}},
            "hnsw_config": {"m": 16},
            "quantization_config": None,
            "payload_schema": {},
        }
        assert module._data_compat_signature(
            manifest_schema
        ) != module._data_compat_signature(live_schema)

    def test_quantization_difference_still_hard_fails(self):
        """A quantization-config difference still blocks restore."""
        module = _load_script(RESTORE_SCRIPT, "restore_qdrant_p1_gate_quant")

        manifest_schema = {
            "params": {"vectors": {"size": 768, "distance": "Cosine"}},
            "hnsw_config": {"m": 16},
            "quantization_config": None,
            "payload_schema": {"group_id": {"data_type": "keyword"}},
        }
        live_schema = {
            "params": {"vectors": {"size": 768, "distance": "Cosine"}},
            "hnsw_config": {"m": 16},
            "quantization_config": {"scalar": {"type": "int8"}},
            "payload_schema": {},
        }
        assert module._data_compat_signature(
            manifest_schema
        ) != module._data_compat_signature(live_schema)


class TestEnsurePayloadIndexesReadBack:
    """BP-194 Q1: the SDK path also reads back and fails loud (qdrant_client.py)."""

    def test_missing_field_after_ensure_raises(self):
        client = MagicMock()
        # get_collection reports every canonical field except one, every attempt.
        incomplete = {k: object() for k in list(BASE_PAYLOAD_INDEXES) if k != "version"}
        client.get_collection.return_value = SimpleNamespace(payload_schema=incomplete)

        with (
            patch("memory.qdrant_client.time.sleep"),
            pytest.raises(RuntimeError, match="version"),
        ):
            ensure_payload_indexes(client, COLLECTION_CONVENTIONS)

    def test_slow_landing_index_recovers_within_poll_budget(self):
        """A field missing on the first read-back but present on a later one
        does not raise — the bounded poll gives a slow index time to land."""
        client = MagicMock()
        canonical = canonical_payload_indexes(COLLECTION_CONVENTIONS)
        incomplete = {k: object() for k in canonical if k != "timestamp"}
        complete = {k: object() for k in canonical}
        client.get_collection.side_effect = [
            SimpleNamespace(payload_schema=incomplete),
            SimpleNamespace(payload_schema=incomplete),
            SimpleNamespace(payload_schema=complete),
        ]

        with patch("memory.qdrant_client.time.sleep"):
            ensured = ensure_payload_indexes(client, COLLECTION_CONVENTIONS)

        assert set(ensured) == set(canonical)

    def test_transient_verify_get_failure_does_not_raise(self):
        """get_collection() raising on every read-back attempt is inconclusive,
        not "all fields missing" — it must not raise (a transient verify-GET
        blip must not roll back an otherwise-good restore)."""
        client = MagicMock()
        client.get_collection.side_effect = ConnectionError("boom")

        with patch("memory.qdrant_client.time.sleep"):
            ensured = ensure_payload_indexes(client, COLLECTION_CONVENTIONS)

        assert set(ensured) == set(canonical_payload_indexes(COLLECTION_CONVENTIONS))
