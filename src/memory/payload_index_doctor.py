"""Type-aware payload-index divergence detection (BUG-530 / issue #337, PLAN-036 P3).

Diffs each live collection's ``payload_schema`` against the canonical index set
in :mod:`memory.qdrant_client`, reporting fields that are **missing** and fields
that are present-but-**mismatched** (the declared type or its params diverge).

Read-only by construction: this module never calls ``ensure_payload_indexes``
and never creates, deletes, or repairs an index. It is framework-neutral — no
printing, no ``sys.exit`` — so both ``scripts/aim_doctor.py`` and (per PLAN-037
§2) ``aim-verify`` can register it without either owning the logic. The
dependency direction is adapter → this module, never the reverse.

Why type-aware and not a name diff (TD-888)
-------------------------------------------
``group_id`` (project separation) and ``discussions.agent_id`` / ``github.source``
(agent separation within a project) are expressed physically as
``KeywordIndexParams(type="keyword", is_tenant=True)``. Qdrant's tenant-optimized
layout drives physical point ordering, so a lost ``is_tenant`` is an unguarded
**isolation boundary**, not a performance nit — and it degrades filtering with no
failing signal, which is the BUG-530 signature exactly.

A field whose canonical spec is ``KeywordIndexParams(is_tenant=True)`` but which
was created as a bare ``PayloadSchemaType.KEYWORD`` is invisible to a name-only
diff **and** to a ``data_type``-only diff: measurement below shows the degraded
field still reports ``data_type == PayloadSchemaType.KEYWORD``. Only the
``params`` carry the difference. Hence the comparison here is over
(``data_type``, meaningful ``params``), not over field names.

Measured live round-trip
------------------------
Canonical values are a **mix** of bare ``PayloadSchemaType`` enums and
``*IndexParams`` objects, while a live ``payload_schema`` is a plain ``dict`` of
``PayloadIndexInfo(data_type, params, points)`` — so a naive ``==`` between a
canonical value and a live value never matches. The normalization below was
derived **empirically**, not by reasoning: each canonical spec form was created
on a throwaway collection and the resulting live ``payload_schema`` recorded.

Measured against Qdrant ``v1.16.3`` (the pin in ``docker/docker-compose.yml``)
via ``qdrant-client`` ``1.18.0``, on the ``ephemeral_qdrant`` fixture:

===================================================  ======================  =============================================
canonical spec                                       live ``data_type``      live ``params``
===================================================  ======================  =============================================
``PayloadSchemaType.KEYWORD``                        ``…KEYWORD``            ``None``
``PayloadSchemaType.DATETIME``                       ``…DATETIME``           ``None``
``PayloadSchemaType.FLOAT``                          ``…FLOAT``              ``None``
``PayloadSchemaType.BOOL``                           ``…BOOL``               ``None``
``PayloadSchemaType.INTEGER``                        ``…INTEGER``            ``None``
``KeywordIndexParams(type="keyword")``               ``…KEYWORD``            echoed verbatim, ``is_tenant=None``
``KeywordIndexParams(type="keyword",                 ``…KEYWORD``            echoed verbatim, ``is_tenant=True``
is_tenant=True)``
``TextIndexParams(type="text", tokenizer=WORD,       ``…TEXT``               echoed verbatim, unset optionals ``None``
min_token_len=2, max_token_len=20)``
===================================================  ======================  =============================================

Four facts follow from that measurement, and the comparison rests on them:

1. A **bare enum round-trips to** ``params=None``. So ``params is None`` is the
   *correct* live shape for an enum-specified field, never a degradation.
2. An ``*IndexParams`` object is **echoed back verbatim**, and the echoed object
   compares equal to the canonical one (``live.params == canonical`` measured
   ``True`` for the plain-keyword, tenant-keyword, and text forms). Pydantic
   value equality is therefore a sound comparison — once both sides are reduced
   to the same shape.
3. ``data_type`` is derivable from the canonical spec: a bare enum *is* the
   ``data_type``; ``KeywordIndexParams`` → ``KEYWORD``; ``TextIndexParams`` →
   ``TEXT``.
4. ``data_type`` alone is **not** sufficient. Measured directly: a field
   canonically ``KeywordIndexParams(is_tenant=True)`` but created as a bare
   ``PayloadSchemaType.KEYWORD`` still reports ``data_type == KEYWORD`` (``True``)
   while ``params`` is ``None`` — the isolation boundary is silently gone. The
   same holds for text drift: a different ``tokenizer``/``min_token_len`` still
   reports ``data_type == TEXT``.

``KeywordIndexParams(type="keyword")`` (all optionals unset) and a bare
``PayloadSchemaType.KEYWORD`` describe the *same* index, so params are compared
after dropping ``type`` and any unset (``None``) option — otherwise
``content_hash``, whose canonical spec is the former, would be reported as
diverging from a live index that is in fact identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client.models import PayloadSchemaType

from .config import COLLECTION_NAMES
from .qdrant_client import COLLECTION_PAYLOAD_INDEXES, canonical_payload_indexes

__all__ = [
    "AUDITED_COLLECTIONS",
    "MISMATCHED",
    "MISSING",
    "CollectionAudit",
    "FieldDivergence",
    "SchemaAudit",
    "audit_payload_indexes",
    "diff_payload_schema",
    "expected_shape",
]

MISSING = "missing"
MISMATCHED = "mismatched"

# Collections this module will audit. Union of the iteration list and every
# collection carrying registered payload indexes: COLLECTION_NAMES omits
# jira-data, which does have canonical indexes, and auditing by that list alone
# would leave a jira-data divergence undetected. Deriving the set from the index
# registry also keeps a *foreign* collection sharing the same Qdrant out of
# scope — canonical_payload_indexes() returns the base set for any unknown name,
# so auditing an unrelated collection would manufacture divergences.
AUDITED_COLLECTIONS: tuple[str, ...] = tuple(
    dict.fromkeys([*COLLECTION_NAMES, *COLLECTION_PAYLOAD_INDEXES])
)


@dataclass(frozen=True)
class FieldDivergence:
    """One canonical field that is missing from, or mismatched on, a collection.

    ``expected`` and ``actual`` are rendered from index specs only — never from
    a connection URL or an API key — so a divergence report is secret-free by
    construction.
    """

    collection: str
    field: str
    kind: str  # MISSING | MISMATCHED
    expected: str
    actual: str

    def describe(self) -> str:
        if self.kind == MISSING:
            return f"{self.collection}.{self.field}: missing (expected {self.expected})"
        return (
            f"{self.collection}.{self.field}: expected {self.expected}, "
            f"found {self.actual}"
        )


@dataclass(frozen=True)
class CollectionAudit:
    """Per-collection result. ``unreachable`` set ⇒ divergences are unknown."""

    collection: str
    divergences: tuple[FieldDivergence, ...] = ()
    unreachable: str | None = None


@dataclass(frozen=True)
class SchemaAudit:
    """Whole-instance result.

    ``unreachable`` set ⇒ Qdrant itself could not be reached and *nothing* was
    audited. Per PLAN-036 §2a, a read-only checker must not assert a divergence
    it cannot see: unreachable is reported as such, never as "all missing".
    """

    collections: tuple[CollectionAudit, ...] = ()
    unreachable: str | None = None

    @property
    def divergences(self) -> tuple[FieldDivergence, ...]:
        return tuple(d for c in self.collections for d in c.divergences)

    @property
    def unverifiable(self) -> tuple[str, ...]:
        return tuple(c.collection for c in self.collections if c.unreachable)


def expected_shape(spec: Any) -> tuple[PayloadSchemaType, dict[str, Any]]:
    """Normalize a canonical spec to the (data_type, meaningful params) it implies.

    See the module docstring for the measurement this encodes. A bare
    ``PayloadSchemaType`` implies no params; an ``*IndexParams`` object implies
    itself, reduced to its set, non-``type`` options.
    """
    if isinstance(spec, PayloadSchemaType):
        return spec, {}
    # *IndexParams: `type` is a per-params enum (KeywordIndexType/TextIndexType)
    # whose value matches the PayloadSchemaType the live schema reports.
    raw_type = getattr(spec.type, "value", spec.type)
    return PayloadSchemaType(raw_type), _meaningful_params(spec)


def _meaningful_params(params: Any) -> dict[str, Any]:
    """Options a params object actually declares, comparable across both shapes.

    Drops ``type`` (already carried by ``data_type``) and every unset option, so
    ``KeywordIndexParams(type="keyword")`` and a bare ``PayloadSchemaType.KEYWORD``
    — which describe the same index — reduce to the same ``{}``.
    """
    if params is None:
        return {}
    dumped = params.model_dump(exclude_none=True)
    dumped.pop("type", None)
    return {k: getattr(v, "value", v) for k, v in dumped.items()}


def _describe(data_type: Any, params: dict[str, Any]) -> str:
    label = getattr(data_type, "value", str(data_type))
    if not params:
        return str(label)
    rendered = ", ".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{label}({rendered})"


def _is_tenant(params: dict[str, Any]) -> bool:
    return params.get("is_tenant") is True


def diff_payload_schema(
    collection: str, live_schema: dict[str, Any] | None
) -> tuple[FieldDivergence, ...]:
    """Diff one collection's live ``payload_schema`` against its canonical set.

    Pure: takes the already-fetched schema, performs no I/O. ``live_schema`` is
    the ``payload_schema`` mapping from ``get_collection()``; ``None`` is treated
    as an empty schema (every canonical field missing) and is only ever passed by
    a caller that actually read it.
    """
    live = live_schema or {}
    divergences: list[FieldDivergence] = []

    for field, spec in canonical_payload_indexes(collection).items():
        exp_type, exp_params = expected_shape(spec)
        info = live.get(field)
        if info is None:
            divergences.append(
                FieldDivergence(
                    collection=collection,
                    field=field,
                    kind=MISSING,
                    expected=_describe(exp_type, exp_params),
                    actual="absent",
                )
            )
            continue

        live_type = getattr(info, "data_type", None)
        live_params = _meaningful_params(getattr(info, "params", None))
        expected = _describe(exp_type, exp_params)
        actual = _describe(live_type, live_params)

        if live_type != exp_type:
            reason = actual
        elif _is_tenant(exp_params) != _is_tenant(live_params):
            # Called out separately from generic param drift: is_tenant is an
            # isolation boundary, and it is bounded in BOTH directions — lost
            # (degraded separation) and silently added (a high-cardinality
            # field given tenant layout) are each a divergence.
            lost = _is_tenant(exp_params)
            reason = (
                f"{actual} — tenant-optimized layout "
                f"{'lost' if lost else 'added'} (isolation boundary)"
            )
        elif exp_params != live_params:
            reason = actual
        else:
            continue

        divergences.append(
            FieldDivergence(
                collection=collection,
                field=field,
                kind=MISMATCHED,
                expected=expected,
                actual=reason,
            )
        )

    return tuple(divergences)


def audit_payload_indexes(
    client: Any, collections: tuple[str, ...] = AUDITED_COLLECTIONS
) -> SchemaAudit:
    """Audit each existing canonical collection's payload indexes. Read-only.

    Only collections that exist live are audited — an absent collection means
    "not installed" (or a disabled integration), not a divergence.

    Any failure to read is reported as unreachable rather than as a divergence:
    if listing collections fails, the whole audit is unreachable; if a single
    ``get_collection`` fails, only that collection is. Failure reasons carry the
    exception **type name only**, never its message, so a URL or credential
    embedded in a client error can never reach a report.
    """
    try:
        existing = {c.name for c in client.get_collections().collections}
    except Exception as e:
        return SchemaAudit(unreachable=type(e).__name__)

    audits: list[CollectionAudit] = []
    for name in collections:
        if name not in existing:
            continue
        try:
            live_schema = client.get_collection(name).payload_schema
        except Exception as e:
            audits.append(
                CollectionAudit(collection=name, unreachable=type(e).__name__)
            )
            continue
        audits.append(
            CollectionAudit(
                collection=name, divergences=diff_payload_schema(name, live_schema)
            )
        )

    return SchemaAudit(collections=tuple(audits))
