"""Unit tests for the type-aware payload-index diff (PLAN-036 P3, BUG-530).

The diff is pure, so these tests assert on real ``PayloadIndexInfo`` values —
the exact shape a live ``payload_schema`` returns, per the round-trip measured
in ``memory.payload_index_doctor``'s module docstring. Nothing here fakes the
comparison surface itself; the end-to-end teeth run against a real Qdrant in
``tests/integration/test_payload_index_doctor.py``.

The client double used for the audit-level tests **can raise** — a double that
cannot fail would make the unreachable → SKIP policy untestable, which is the
defect being repaired in the P5 harness work.
"""

from __future__ import annotations

import pytest
from qdrant_client.models import (
    KeywordIndexParams,
    PayloadIndexInfo,
    PayloadSchemaType,
    TextIndexParams,
    TokenizerType,
)

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    COLLECTION_JIRA_DATA,
)
from memory.payload_index_doctor import (
    AUDITED_COLLECTIONS,
    MISMATCHED,
    MISSING,
    audit_payload_indexes,
    diff_payload_schema,
    expected_shape,
)
from memory.qdrant_client import canonical_payload_indexes

# ─── Live-schema builders ─────────────────────────────────────────────────────
# These mirror the measured round-trip exactly: a bare PayloadSchemaType comes
# back as params=None; an *IndexParams object comes back echoed verbatim.


def _live_enum(data_type: PayloadSchemaType) -> PayloadIndexInfo:
    return PayloadIndexInfo(data_type=data_type, params=None, points=0)


def _live_params(params) -> PayloadIndexInfo:
    raw = getattr(params.type, "value", params.type)
    return PayloadIndexInfo(data_type=PayloadSchemaType(raw), params=params, points=0)


def _healthy_schema(collection: str) -> dict[str, PayloadIndexInfo]:
    """The live schema a correctly-indexed collection returns."""
    schema = {}
    for field, spec in canonical_payload_indexes(collection).items():
        if isinstance(spec, PayloadSchemaType):
            schema[field] = _live_enum(spec)
        else:
            schema[field] = _live_params(spec)
    return schema


class FailingClient:
    """Client double that CAN fail — required to test the unreachable policy."""

    def __init__(self, schemas=None, list_error=None, get_errors=None):
        self._schemas = schemas or {}
        self._list_error = list_error
        self._get_errors = get_errors or {}

    def get_collections(self):
        if self._list_error:
            raise self._list_error

        class _C:
            def __init__(self, name):
                self.name = name

        class _R:
            pass

        r = _R()
        r.collections = [_C(n) for n in self._schemas]
        return r

    def get_collection(self, name):
        if name in self._get_errors:
            raise self._get_errors[name]

        class _Info:
            def __init__(self, schema):
                self.payload_schema = schema

        return _Info(self._schemas[name])


# ─── expected_shape: encodes the measured normalization ───────────────────────


class TestExpectedShape:
    @pytest.mark.parametrize(
        "enum_spec",
        [
            PayloadSchemaType.KEYWORD,
            PayloadSchemaType.DATETIME,
            PayloadSchemaType.FLOAT,
            PayloadSchemaType.BOOL,
            PayloadSchemaType.INTEGER,
        ],
    )
    def test_bare_enum_implies_no_params(self, enum_spec):
        """Measured: a bare enum round-trips to params=None, so it declares none."""
        assert expected_shape(enum_spec) == (enum_spec, {})

    def test_tenant_keyword_params(self):
        data_type, params = expected_shape(
            KeywordIndexParams(type="keyword", is_tenant=True)
        )
        assert data_type == PayloadSchemaType.KEYWORD
        assert params == {"is_tenant": True}

    def test_plain_keyword_params_reduce_to_empty(self):
        """KeywordIndexParams() and a bare KEYWORD enum describe the same index."""
        data_type, params = expected_shape(KeywordIndexParams(type="keyword"))
        assert data_type == PayloadSchemaType.KEYWORD
        assert params == {}

    def test_text_params(self):
        data_type, params = expected_shape(
            TextIndexParams(
                type="text",
                tokenizer=TokenizerType.WORD,
                min_token_len=2,
                max_token_len=20,
            )
        )
        assert data_type == PayloadSchemaType.TEXT
        assert params == {
            "tokenizer": "word",
            "min_token_len": 2,
            "max_token_len": 20,
        }


# ─── The diff ─────────────────────────────────────────────────────────────────


class TestHealthyCollections:
    @pytest.mark.parametrize("collection", AUDITED_COLLECTIONS)
    def test_healthy_collection_has_no_divergences(self, collection):
        assert diff_payload_schema(collection, _healthy_schema(collection)) == ()

    def test_plain_keyword_created_as_bare_enum_is_not_a_divergence(self):
        """content_hash: KeywordIndexParams() vs a bare KEYWORD index are the same.

        Guards against the obvious over-strict implementation — comparing the
        canonical object to live params directly — which would flag every
        content_hash index in the fleet as broken.
        """
        schema = _healthy_schema(COLLECTION_CODE_PATTERNS)
        schema["content_hash"] = _live_enum(PayloadSchemaType.KEYWORD)

        assert diff_payload_schema(COLLECTION_CODE_PATTERNS, schema) == ()


class TestMissingFields:
    def test_missing_timestamp_is_reported(self):
        """The BUG-530 symptom: no timestamp index makes get_recent() raise."""
        schema = _healthy_schema(COLLECTION_CODE_PATTERNS)
        del schema["timestamp"]

        found = diff_payload_schema(COLLECTION_CODE_PATTERNS, schema)

        assert [(d.field, d.kind) for d in found] == [("timestamp", MISSING)]
        assert "datetime" in found[0].expected

    def test_empty_schema_reports_every_canonical_field_missing(self):
        found = diff_payload_schema(COLLECTION_DISCUSSIONS, {})

        assert {d.field for d in found} == set(
            canonical_payload_indexes(COLLECTION_DISCUSSIONS)
        )
        assert all(d.kind == MISSING for d in found)

    def test_none_schema_is_treated_as_empty(self):
        assert diff_payload_schema(COLLECTION_DISCUSSIONS, None)


class TestTypeMismatch:
    def test_wrong_data_type_is_mismatched_not_missing(self):
        schema = _healthy_schema(COLLECTION_CODE_PATTERNS)
        schema["timestamp"] = _live_enum(PayloadSchemaType.KEYWORD)

        (found,) = diff_payload_schema(COLLECTION_CODE_PATTERNS, schema)

        assert (found.field, found.kind) == ("timestamp", MISMATCHED)
        assert found.expected == "datetime"
        assert found.actual == "keyword"

    def test_text_index_param_drift_is_mismatched(self):
        """content stays data_type=TEXT under drift — only params reveal it."""
        schema = _healthy_schema(COLLECTION_CODE_PATTERNS)
        schema["content"] = _live_params(
            TextIndexParams(
                type="text",
                tokenizer=TokenizerType.PREFIX,
                min_token_len=3,
                max_token_len=20,
            )
        )

        (found,) = diff_payload_schema(COLLECTION_CODE_PATTERNS, schema)

        assert (found.field, found.kind) == ("content", MISMATCHED)
        assert "tokenizer=word" in found.expected
        assert "tokenizer=prefix" in found.actual


class TestTenantIsolationBoundary:
    """is_tenant is an isolation boundary — bounded in BOTH directions.

    ``group_id`` is project separation, ``discussions.agent_id`` and
    ``github.source`` are agent separation within a project. Losing is_tenant
    degrades filtering with no failing signal (the BUG-530 signature); silently
    adding it to a high-cardinality field is a footgun nothing else detects.
    """

    @pytest.mark.parametrize(
        ("collection", "field"),
        [
            (COLLECTION_CODE_PATTERNS, "group_id"),
            (COLLECTION_DISCUSSIONS, "group_id"),
            (COLLECTION_DISCUSSIONS, "agent_id"),
            (COLLECTION_GITHUB, "source"),
            (COLLECTION_JIRA_DATA, "group_id"),
        ],
    )
    def test_lost_is_tenant_is_detected(self, collection, field):
        """THE name-only blind spot: still data_type=KEYWORD, still present.

        A name-only diff reports this collection clean. A data_type-only diff
        also reports it clean — measured: the degraded field returns
        data_type == KEYWORD. Only params carry the loss.
        """
        schema = _healthy_schema(collection)
        schema[field] = _live_enum(PayloadSchemaType.KEYWORD)

        (found,) = diff_payload_schema(collection, schema)

        assert (found.field, found.kind) == (field, MISMATCHED)
        assert "is_tenant=True" in found.expected
        assert "lost" in found.actual
        assert "isolation boundary" in found.actual

    def test_silently_added_is_tenant_is_detected(self):
        """content_hash is high-cardinality — tenant layout must not appear."""
        schema = _healthy_schema(COLLECTION_CODE_PATTERNS)
        schema["content_hash"] = _live_params(
            KeywordIndexParams(type="keyword", is_tenant=True)
        )

        (found,) = diff_payload_schema(COLLECTION_CODE_PATTERNS, schema)

        assert (found.field, found.kind) == ("content_hash", MISMATCHED)
        assert "added" in found.actual
        assert "isolation boundary" in found.actual

    def test_added_is_tenant_on_enum_field_is_detected(self):
        schema = _healthy_schema(COLLECTION_CODE_PATTERNS)
        schema["type"] = _live_params(
            KeywordIndexParams(type="keyword", is_tenant=True)
        )

        (found,) = diff_payload_schema(COLLECTION_CODE_PATTERNS, schema)

        assert (found.field, found.kind) == ("type", MISMATCHED)
        assert "added" in found.actual


# ─── Audit orchestration ──────────────────────────────────────────────────────


class TestAuditPayloadIndexes:
    def test_healthy_instance_is_clean(self):
        client = FailingClient(
            schemas={c: _healthy_schema(c) for c in AUDITED_COLLECTIONS}
        )

        audit = audit_payload_indexes(client)

        assert audit.unreachable is None
        assert audit.divergences == ()
        assert audit.unverifiable == ()
        assert len(audit.collections) == len(AUDITED_COLLECTIONS)

    def test_absent_collection_is_not_a_divergence(self):
        """Not-installed / disabled integration is not a schema defect."""
        client = FailingClient(
            schemas={COLLECTION_DISCUSSIONS: _healthy_schema(COLLECTION_DISCUSSIONS)}
        )

        audit = audit_payload_indexes(client)

        assert audit.divergences == ()
        assert [c.collection for c in audit.collections] == [COLLECTION_DISCUSSIONS]

    def test_foreign_collection_is_not_audited(self):
        """A collection sharing the Qdrant that is not ours must be ignored."""
        client = FailingClient(schemas={"docintel-vectors": {}})

        audit = audit_payload_indexes(client)

        assert audit.collections == ()
        assert audit.divergences == ()

    def test_unreachable_instance_reports_unreachable_not_divergence(self):
        """Read-only checkers must not assert a divergence they cannot see."""
        client = FailingClient(list_error=ConnectionError("refused"))

        audit = audit_payload_indexes(client)

        assert audit.unreachable == "ConnectionError"
        assert audit.divergences == ()
        assert audit.collections == ()

    def test_unreadable_collection_is_unverifiable_not_divergent(self):
        client = FailingClient(
            schemas={
                COLLECTION_DISCUSSIONS: _healthy_schema(COLLECTION_DISCUSSIONS),
                COLLECTION_GITHUB: _healthy_schema(COLLECTION_GITHUB),
            },
            get_errors={COLLECTION_GITHUB: TimeoutError("slow")},
        )

        audit = audit_payload_indexes(client)

        assert audit.unverifiable == (COLLECTION_GITHUB,)
        assert audit.divergences == ()

    def test_divergence_is_attributed_to_its_collection(self):
        broken = _healthy_schema(COLLECTION_DISCUSSIONS)
        del broken["timestamp"]
        client = FailingClient(
            schemas={
                COLLECTION_DISCUSSIONS: broken,
                COLLECTION_GITHUB: _healthy_schema(COLLECTION_GITHUB),
            }
        )

        audit = audit_payload_indexes(client)

        assert [(d.collection, d.field) for d in audit.divergences] == [
            (COLLECTION_DISCUSSIONS, "timestamp")
        ]


class TestAuditedCollections:
    def test_jira_data_is_audited(self):
        """COLLECTION_NAMES omits jira-data, which does carry canonical indexes."""
        assert COLLECTION_JIRA_DATA in AUDITED_COLLECTIONS

    def test_every_indexed_collection_is_audited(self):
        from memory.qdrant_client import COLLECTION_PAYLOAD_INDEXES

        assert set(COLLECTION_PAYLOAD_INDEXES) <= set(AUDITED_COLLECTIONS)


class TestSecretFreeReporting:
    def test_failure_reason_carries_type_name_only(self):
        """A client error can embed the connection URL — never surface it."""
        secret = "s3cr3t-api-key"
        client = FailingClient(
            list_error=ConnectionError(
                f"failed: http://user:{secret}@qdrant.internal:26350"
            )
        )

        audit = audit_payload_indexes(client)

        assert audit.unreachable == "ConnectionError"
        assert secret not in audit.unreachable
        assert "qdrant.internal" not in audit.unreachable

    def test_collection_failure_reason_carries_type_name_only(self):
        secret = "s3cr3t-api-key"
        client = FailingClient(
            schemas={COLLECTION_DISCUSSIONS: {}},
            get_errors={COLLECTION_DISCUSSIONS: RuntimeError(f"key={secret}")},
        )

        audit = audit_payload_indexes(client)

        assert secret not in audit.collections[0].unreachable

    def test_divergence_text_is_built_from_specs_only(self):
        """Divergence detail derives from index specs — no URL, no credential."""
        found = diff_payload_schema(COLLECTION_DISCUSSIONS, {})

        rendered = " ".join(d.describe() for d in found)
        for leak in ("http://", "https://", "api_key", "@"):
            assert leak not in rendered
