"""BUG-297 realistic-size handoff integration tests.

PM #287 escape lesson per [[feedback_realistic_size_production_artifact_tests]]:
synthetic <200-byte fixtures cannot expose budget/scale-emergent defects.
This file exercises the L1 handoff retrieval + budget pipeline against a
production-scale fixture (40 chunks, ~32K bytes, ~5,320 tokens) preserving
Session 47's load-bearing token count — the actual escape case for BUG-297.

Coverage:
    1. Within-ceiling: aggregated handoff included; meta.fallback_signaled False.
    2. Sub-ceiling override: ceiling rejection triggers FALLBACK marker.
    3. Above-max-ceiling: even at handoff_ceiling_tokens=10000 (Field max),
       an ~12,000-token body is rejected.
    4. Observability: log line emitted, push_retrieval_reject_metric_async
       called, on cases 2 and 3.

References:
    - oversight/bugs/BUG-297-td518-aggregation-silently-dropped-by-budget.md
    - oversight/knowledge/best-practices/BP-158-rag-budget-reject-silent-drop-fallback-sentinel-observability-2026.md
    - tests/test_l1_handoff_aggregation.py (precedent infrastructure)
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from memory.chunking.truncation import count_tokens

FIXED_VECTOR = [0.5] * 768

# Per MEMORY.md "Optimal Parameters 2026": prose chunks 512-token soft target,
# 15% overlap. Session 47 (the BUG-297 escape case) emitted 40 chunks with an
# aggregated body of ~5,386 tokens (real prose, ~2.76 bytes/token). The
# synthetic _BASE_SENTENCE below is repetitive structure-rich English which
# cl100k_base tokenizes more efficiently (~6 bytes/token empirical); bytes-
# per-chunk is therefore tuned to preserve the *token-count* load-bearing
# property (which is what the L1 ceiling pre-filter actually gates on) rather
# than Session 47's byte ratio. Per Q6 dispatch ruling the load-bearing
# properties are: chunk count = 40, aggregated token count ~5,400, per-chunk
# token count within chunker spec bounds (>=25, <=512).
_BASE_SENTENCE = (
    "This synthetic prose chunk mirrors a real session handoff segment "
    "with sentence-level rhythm, punctuation, and lexical variety so "
    "tokenization matches production paragraphs rather than padding. "
)
# Empirical measurement at module-load (informational; the load-bearing
# regression guards are the per-chunk and aggregated assertions in case (a)).
_BASE_SENTENCE_TOKENS = count_tokens(_BASE_SENTENCE)
SESSION47_CHUNK_COUNT = 40
SESSION47_BYTES_PER_CHUNK = 800  # 40 chunks x 800 bytes -> ~32K bytes / ~5,320 tokens
SESSION47_TOKENS_PER_CHUNK = (
    140  # ~133 tokens/chunk empirical, within chunker spec bounds
)


@pytest.fixture(autouse=True)
def _disable_detect_secrets(monkeypatch):
    """Match precedent — keep entropy scanner out of unit-test path."""
    from memory import security_scanner

    monkeypatch.setattr(security_scanner, "_detect_secrets_available", False)


@pytest.fixture
def qdrant_inmemory():
    """In-memory Qdrant client with the discussions collection."""
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="discussions",
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    return client


@pytest.fixture
def mock_embedding():
    """Deterministic 768-dim embedding for the SEMANTIC bootstrap layers."""
    mock = MagicMock()
    mock.embed.return_value = [FIXED_VECTOR]
    with (
        patch("memory.storage.EmbeddingClient", return_value=mock),
        patch("memory.search.EmbeddingClient", return_value=mock),
    ):
        yield mock


def _build_realistic_chunks(
    *,
    chunk_count: int,
    bytes_per_chunk: int,
) -> list[str]:
    """Build N synthetic prose chunks of the requested byte size.

    Content is real English prose (not 'a' x N) so count_tokens() returns a
    realistic token count per chunk rather than a single-character outlier.
    """
    chunks: list[str] = []
    for idx in range(chunk_count):
        # Per-chunk preamble keeps content distinct so dedup does not collapse
        # the fixture; pad up to the requested byte size with the base sentence.
        prefix = f"Chunk {idx:03d} of {chunk_count:03d}. "
        body = prefix
        while len(body.encode("utf-8")) < bytes_per_chunk:
            body += _BASE_SENTENCE
        # Trim to target size to keep aggregate stable.
        chunks.append(body[:bytes_per_chunk])
    return chunks


def _insert_handoff_chunks(
    client: QdrantClient,
    *,
    group_id: str,
    created_at: str,
    chunks: list[str],
    total_chunks: int | None = None,
) -> list[str]:
    """Insert synthetic agent_handoff chunks at a shared created_at."""
    total = total_chunks if total_chunks is not None else len(chunks)
    point_ids: list[str] = []
    points = []
    for idx, content in enumerate(chunks):
        pid = str(uuid.uuid4())
        point_ids.append(pid)
        points.append(
            PointStruct(
                id=pid,
                vector=FIXED_VECTOR,
                payload={
                    "content": content,
                    "type": "agent_handoff",
                    "agent_id": "parzival",
                    "group_id": group_id,
                    "created_at": created_at,
                    "timestamp": created_at,
                    "chunking_metadata": {
                        "chunk_type": "prose",
                        "chunk_index": idx,
                        "total_chunks": total,
                    },
                },
            )
        )
    client.upsert(collection_name="discussions", points=points)
    return point_ids


def _make_search_client(qdrant_inmemory, monkeypatch):
    """Return a MemorySearch wired to the in-memory Qdrant client."""
    from memory.config import get_config, reset_config
    from memory.search import MemorySearch

    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()
    config = get_config()
    search = MemorySearch(config)
    search.client = qdrant_inmemory
    return search, config


# ─── Case (a) — Within-ceiling: aggregated handoff included ─────────────────


def test_realistic_handoff_within_ceiling__included_in_results(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """Session 47-class fixture (40 chunks, ~5,320 tokens, ~32K bytes) fits
    within the default handoff_ceiling_tokens=8000 and is included in the
    bootstrap result list. meta.fallback_signaled must remain False.
    """
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-bug297-within-ceiling"
    created_at = "2026-05-13T09:00:00Z"
    chunks = _build_realistic_chunks(
        chunk_count=SESSION47_CHUNK_COUNT,
        bytes_per_chunk=SESSION47_BYTES_PER_CHUNK,
    )
    # Per-chunk token sanity: regression-guards future tokenizer-model
    # migration (e.g. Jina v3) by flagging if cl100k_base behavior shifts the
    # synthetic per-chunk token count outside the chunker spec band.
    chunk0_tokens = count_tokens(chunks[0])
    assert 100 <= chunk0_tokens <= 200, (
        f"Per-chunk synthetic token count ({chunk0_tokens}) drifted outside "
        f"[100, 200]. Audit count_tokens() tokenizer model or _BASE_SENTENCE."
    )
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunks,
        total_chunks=SESSION47_CHUNK_COUNT,
    )

    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    # default handoff_ceiling_tokens=8000; fixture aggregates to ~5,320 tokens
    assert config.handoff_ceiling_tokens == 8000

    results, meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert len(handoff_results) == 1, (
        "Within-ceiling handoff must be present in results — "
        "BUG-297 verification: silent-drop no longer occurs."
    )
    handoff_content = handoff_results[0]["content"]
    # Aggregation byte-equivalence (precedent: T2 in test_l1_handoff_aggregation)
    assert handoff_content == "".join(chunks)
    # Load-bearing regression guard: aggregated token count must remain within
    # Session 47's empirical band so a future ratio drift (chunker params,
    # _BASE_SENTENCE rewrite, count_tokens() model migration) can't silently
    # flip case (a) into a ceiling-rejection scenario and hide a regression.
    agg_tokens = count_tokens(handoff_content)
    assert 4_500 <= agg_tokens <= 6_500, (
        f"Realistic-size fixture aggregated token count ({agg_tokens}) drifted "
        f"outside Session 47's empirical band [4500, 6500]. "
        f"Tighten _build_realistic_chunks params or audit count_tokens() tokenizer model."
    )
    # Byte-size sanity: synthetic content tokenizes at ~6 bytes/token, so the
    # ~5,400-token target lands ~32K bytes (not Session 47's 14.8K, because
    # real prose tokenizes at ~2.76 b/t — see module-level comment).
    assert 28_000 <= len(handoff_content.encode("utf-8")) <= 35_000
    assert meta["fallback_signaled"] is False
    assert meta["rejects"] == []


# ─── Case (b) — Sub-ceiling override: aggregation rejected, fallback fires ──


def test_realistic_handoff_exceeds_synthetic_2500_ceiling__triggers_fallback(
    qdrant_inmemory, mock_embedding, monkeypatch, caplog
):
    """When handoff_ceiling_tokens is overridden to a synthetic 2500 (mimicking
    the original BUG-297 silent-drop condition where bootstrap_token_budget
    was the only gate), the Session 47-class fixture is rejected at the
    Layer 1 ceiling pre-filter. meta.fallback_signaled fires with
    reason=ceiling_exceeded so the bootstrap skill emits the FALLBACK marker.
    """
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-bug297-ceiling-override"
    created_at = "2026-05-13T09:05:00Z"
    chunks = _build_realistic_chunks(
        chunk_count=SESSION47_CHUNK_COUNT,
        bytes_per_chunk=SESSION47_BYTES_PER_CHUNK,
    )
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunks,
        total_chunks=SESSION47_CHUNK_COUNT,
    )

    monkeypatch.setenv("HANDOFF_CEILING_TOKENS", "2500")
    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    assert config.handoff_ceiling_tokens == 2500

    with caplog.at_level(logging.WARNING, logger="ai_memory.injection"):
        results, meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert handoff_results == [], (
        "Handoff exceeding the per-tier ceiling must be excluded from results "
        "so downstream greedy fill does not silently re-encounter the bug."
    )
    assert meta["fallback_signaled"] is True
    ceiling_rejects = [
        r for r in meta["rejects"] if r.get("reason") == "ceiling_exceeded"
    ]
    assert len(ceiling_rejects) == 1
    reject = ceiling_rejects[0]
    assert reject["type"] == "agent_handoff"
    assert reject["tier"] == "1_bootstrap"
    assert reject["tokens"] > 2500
    # Observability: structured log fires per BP-158 P1
    log_messages = [r.message for r in caplog.records]
    assert any(
        "retrieval_budget_reject" in m for m in log_messages
    ), f"Expected retrieval_budget_reject WARN; got {log_messages!r}"


# ─── Case (c) — Above-max-ceiling: even at the Field upper bound, reject ────


def test_synthetic_12k_token_handoff_exceeds_max_ceiling__triggers_fallback(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """Even at handoff_ceiling_tokens=10000 (the Field upper bound),
    a sufficiently large handoff (~12,000 tokens) still rejects. This
    confirms the ceiling is a real boundary, not a config knob with
    infinite slack — synthetic >10K artifacts trigger fallback exactly
    as Session 47-class artifacts trigger budget rejection at default.
    """
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-bug297-above-max-ceiling"
    created_at = "2026-05-13T09:10:00Z"
    # 90 chunks x 800 bytes = ~72,000 bytes / ~11,970 tokens aggregated. The
    # synthetic content tokenizes at ~6 bytes/token (see module-level comment),
    # so 90 chunks at SESSION47_BYTES_PER_CHUNK comfortably exceeds the
    # handoff_ceiling_tokens=10000 Field upper bound.
    chunks = _build_realistic_chunks(
        chunk_count=90,
        bytes_per_chunk=SESSION47_BYTES_PER_CHUNK,
    )
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunks,
        total_chunks=90,
    )

    monkeypatch.setenv("HANDOFF_CEILING_TOKENS", "10000")
    search, config = _make_search_client(qdrant_inmemory, monkeypatch)
    assert config.handoff_ceiling_tokens == 10000

    results, meta = retrieve_bootstrap_context(search, group_id, config)

    handoff_results = [r for r in results if r.get("type") == "agent_handoff"]
    assert handoff_results == []
    assert meta["fallback_signaled"] is True
    ceiling_rejects = [
        r for r in meta["rejects"] if r.get("reason") == "ceiling_exceeded"
    ]
    assert len(ceiling_rejects) == 1
    assert ceiling_rejects[0]["tokens"] > 10000


# ─── Case (d) — Observability: Prometheus counter increments on rejection ───


def test_ceiling_rejection_emits_prometheus_counter(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """The push_retrieval_reject_metric_async helper is invoked at least once
    per ceiling rejection, with the expected label set
    {reason=ceiling_exceeded, tier=1_bootstrap, collection=discussions}.
    Verifies the BP-158 P3 cardinality discipline at the call site.
    """
    import memory.metrics_push as _metrics_push_module
    from memory.injection import retrieve_bootstrap_context

    group_id = "test-bug297-counter-observability"
    created_at = "2026-05-13T09:15:00Z"
    chunks = _build_realistic_chunks(
        chunk_count=SESSION47_CHUNK_COUNT,
        bytes_per_chunk=SESSION47_BYTES_PER_CHUNK,
    )
    _insert_handoff_chunks(
        qdrant_inmemory,
        group_id=group_id,
        created_at=created_at,
        chunks=chunks,
        total_chunks=SESSION47_CHUNK_COUNT,
    )

    monkeypatch.setenv("HANDOFF_CEILING_TOKENS", "2500")
    search, config = _make_search_client(qdrant_inmemory, monkeypatch)

    # Patch the metrics helper at the module attribute that injection.py's
    # inline `from memory.metrics_push import push_retrieval_reject_metric_async`
    # resolves to. monkeypatch.setattr is more deterministic across Python
    # versions than unittest.mock.patch combined with parenthesized-with
    # context managers (one of which deferred to a wraps that was unused).
    push_mock = MagicMock()
    monkeypatch.setattr(
        _metrics_push_module,
        "push_retrieval_reject_metric_async",
        push_mock,
    )

    _results, meta = retrieve_bootstrap_context(search, group_id, config)

    assert meta["fallback_signaled"] is True
    matching_calls = [
        call
        for call in push_mock.call_args_list
        if call.kwargs.get("reason") == "ceiling_exceeded"
        and call.kwargs.get("tier") == "1_bootstrap"
        and call.kwargs.get("collection") == "discussions"
    ]
    assert len(matching_calls) >= 1, (
        f"Expected at least one push_retrieval_reject_metric_async call with "
        f"ceiling_exceeded labels; got call_args_list={push_mock.call_args_list!r}"
    )
