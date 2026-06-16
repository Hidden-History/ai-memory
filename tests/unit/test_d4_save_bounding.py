"""D4 save-bounding + write-time supersession tests (v2.7.0, DEC-PM338-D4).

Covers:
    F-1 write-side cap + overflow (bounded lead + pointer) — proven against the
        REAL chunker/store path: an over-cap handoff stores as ONE point, not
        20+ (the producer side of the L7 injection-staleness bug).
    F-2 write-time supersession helpers (flag-in-place, never delete).
    group_id-unset → friendly ValueError contract.

Approach mirrors tests/test_session_close_decision_emit.py: in-memory Qdrant +
mocked embedding client, AI_MEMORY_PROJECT_ID unset (DEC-109 CI conventions).
Realistic-size fixture per [[feedback_realistic_size_production_artifact_tests]].
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# Add lib/ to sys.path so parzival_save_common is importable without install.
_LIB = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "memory", "lib")
)
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from parzival_save_common import (  # noqa: E402
    HANDOFF_MAX_BYTES,
    HANDOFF_MAX_LINES,
    HANDOFF_SINGLE_VECTOR_MAX_TOKENS,
    INSIGHT_MAX_CHARS,
    _count_tokens,
    bound_handoff_content,
    bound_insight_content,
)

FIXED_VECTOR = [0.5] * 768


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Clear ambient AI_MEMORY_PROJECT_ID per DEC-109 CI conventions."""
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)


@pytest.fixture(autouse=True)
def _disable_detect_secrets(monkeypatch):
    from memory import security_scanner

    monkeypatch.setattr(security_scanner, "_detect_secrets_available", False)


@pytest.fixture
def qdrant_inmemory():
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="discussions",
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )
    return client


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.embed.return_value = [FIXED_VECTOR]
    with (
        patch("memory.storage.EmbeddingClient", return_value=mock),
        patch("memory.search.EmbeddingClient", return_value=mock),
    ):
        yield mock


@pytest.fixture
def storage_with_inmemory(qdrant_inmemory, mock_embedding, monkeypatch):
    from memory.config import get_config, reset_config
    from memory.storage import MemoryStorage

    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()
    config = get_config()
    storage = MemoryStorage(config)
    storage.qdrant_client = qdrant_inmemory
    return storage, config


def _overcap_handoff_body() -> str:
    """A realistic over-cap handoff (~400 lines / ~36 KB / >3000 tokens).

    Sized to exceed the chunker's 3000-token AGENT_RESPONSE whole-store
    threshold so the UNBOUNDED control fan-chunks into many points — the
    producer-side defect D4 F-1 fixes. Front-loaded sections lead the body so
    the bounded lead preserves them.
    """
    header = (
        "# Session Handoff\n\n"
        "## Executive Summary\nFront-loaded summary that must survive bounding.\n\n"
        "## Status\nAll lanes green.\n\n"
        "## Next Steps\nShip v2.7.0.\n\n"
        "## Detail\n"
    )
    filler = "\n".join(
        f"- detail line {i}: lorem ipsum dolor sit amet consectetur adipiscing "
        f"elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua"
        for i in range(400)
    )
    body = header + filler
    assert len(body.encode("utf-8")) > HANDOFF_MAX_BYTES
    assert body.count("\n") + 1 > HANDOFF_MAX_LINES
    return body


def _token_dense_handoff_body() -> str:
    """A token-dense handoff (~36 KB of JSON-like lines, ~2.2 ch/tok).

    Token-dense content packs more real tokens per byte than the chunker's
    char-estimate (len/4) assumes, so even a byte-bounded lead can breach the
    3000-token whole-store threshold. This fixture proves bound_handoff_content
    verifies the ACTUAL token count and tightens the byte budget so the result
    is guaranteed single-vector.
    """
    header = (
        "# Session Handoff\n\n"
        "## Executive Summary\nDense JSON state dump follows.\n\n"
        "## Next Steps\nShip v2.7.0.\n\n"
        "## State\n"
    )
    dense = "\n".join(
        f'{{"k":{i},"v":{i * 7},"s":"a1b2c3d4","t":67890,"u":12345}},'
        for i in range(800)
    )
    body = header + dense
    assert len(body.encode("utf-8")) > HANDOFF_MAX_BYTES
    return body


def _count_points(client: QdrantClient) -> int:
    return client.count(collection_name="discussions").count


# ─── F-1 bounding helpers (pure) ────────────────────────────────────────────


def test_compliant_handoff_returned_unchanged():
    body = "# Handoff\n\nShort and within both caps.\n"
    assert bound_handoff_content(body, source_path="/x/y.md") == body


def test_overcap_handoff_bounded_with_pointer_and_under_cap():
    body = _overcap_handoff_body()
    bounded = bound_handoff_content(body, source_path="/abs/handoff.md")
    assert "[truncated — full handoff: /abs/handoff.md]" in bounded
    # Bounded vector stays within the cap (so it stores whole).
    assert len(bounded.encode("utf-8")) <= HANDOFF_MAX_BYTES
    # Front-loaded sections are preserved in the lead.
    assert "Executive Summary" in bounded
    assert "Next Steps" in bounded


def test_overcap_handoff_inline_pointer_without_path():
    bounded = bound_handoff_content(_overcap_handoff_body())
    assert "[truncated — full handoff retained on disk]" in bounded


def test_compliant_insight_returned_unchanged():
    text = "Insight: prefer get_recent over semantic search for recency."
    assert bound_insight_content(text) == text


def test_overcap_insight_bounded_within_single_chunk_boundary():
    text = "x" * (INSIGHT_MAX_CHARS * 3)
    bounded = bound_insight_content(text)
    assert bounded.endswith("[truncated]")
    assert len(bounded) <= INSIGHT_MAX_CHARS


# ─── F-1 the load-bearing proof: over-cap handoff stores ONE point ──────────


def test_overcap_handoff_stores_single_point_not_many(storage_with_inmemory):
    """DONE-WHEN: an over-cap handoff stores 1 bounded point, not 20+.

    Control + treatment against the REAL store/chunk path:
      - RAW over-cap body → chunker fan-chunks into many discussions points.
      - bound_handoff_content() body → exactly ONE point.
    """
    storage, _config = storage_with_inmemory
    raw = _overcap_handoff_body()

    # Control: unbounded raw content fan-chunks (the producer-side defect).
    storage.store_agent_memory(
        content=raw,
        memory_type="agent_handoff",
        agent_id="parzival",
        group_id="proj-control",
    )
    raw_points = _count_points(storage.qdrant_client)
    assert raw_points > 1, (
        "Control precondition: an unbounded over-cap handoff must fan-chunk "
        f"into multiple points (got {raw_points})."
    )

    # Treatment: bounded content stores as exactly one point in a fresh project.
    before = _count_points(storage.qdrant_client)
    storage.store_agent_memory(
        content=bound_handoff_content(raw, source_path="/abs/handoff.md"),
        memory_type="agent_handoff",
        agent_id="parzival",
        group_id="proj-bounded",
    )
    added = _count_points(storage.qdrant_client) - before
    assert added == 1, f"Bounded handoff must store exactly 1 point, got {added}."


def test_token_dense_handoff_bounded_under_single_vector_threshold():
    """DONE-WHEN: a token-dense handoff is bounded to <= the chunker's
    single-vector token threshold (not just the byte cap)."""
    body = _token_dense_handoff_body()
    # Precondition: the raw byte-cap-sized prefix is token-dense enough to breach
    # the 3000-token threshold — proving the byte cap alone is insufficient.
    raw_prefix = body.encode("utf-8")[:HANDOFF_MAX_BYTES].decode("utf-8", "ignore")
    assert _count_tokens(raw_prefix) > HANDOFF_SINGLE_VECTOR_MAX_TOKENS

    bounded = bound_handoff_content(body, source_path="/abs/handoff.md")
    assert "[truncated — full handoff: /abs/handoff.md]" in bounded
    assert len(bounded.encode("utf-8")) <= HANDOFF_MAX_BYTES
    # The binding guarantee: actual token count is under the whole-store cap.
    assert _count_tokens(bounded) <= HANDOFF_SINGLE_VECTOR_MAX_TOKENS


def test_token_dense_handoff_stores_single_point(storage_with_inmemory):
    """A token-dense bounded handoff stores as exactly ONE point."""
    storage, _config = storage_with_inmemory
    before = _count_points(storage.qdrant_client)
    storage.store_agent_memory(
        content=bound_handoff_content(
            _token_dense_handoff_body(), source_path="/abs/handoff.md"
        ),
        memory_type="agent_handoff",
        agent_id="parzival",
        group_id="proj-dense",
    )
    added = _count_points(storage.qdrant_client) - before
    assert added == 1, f"Token-dense bounded handoff must store 1 point, got {added}."


def test_overcap_insight_stores_single_point(storage_with_inmemory):
    storage, _config = storage_with_inmemory
    before = _count_points(storage.qdrant_client)
    storage.store_agent_memory(
        content=bound_insight_content("y" * (INSIGHT_MAX_CHARS * 4)),
        memory_type="agent_insight",
        agent_id="parzival",
        group_id="proj-insight",
    )
    assert _count_points(storage.qdrant_client) - before == 1


# ─── group_id-unset → friendly ValueError ───────────────────────────────────


def test_group_id_empty_raises_value_error(storage_with_inmemory):
    storage, _config = storage_with_inmemory
    with pytest.raises(ValueError, match="explicit project scope"):
        storage.store_agent_memory(
            content="x",
            memory_type="agent_handoff",
            agent_id="parzival",
            group_id="",
        )


# ─── F-2 write-time supersession ─────────────────────────────────────────────


def _insert_handoff(client, *, group_id, pid, ts, is_current=None):
    payload = {
        "content": f"handoff {pid}",
        "type": "agent_handoff",
        "agent_id": "parzival",
        "group_id": group_id,
        "timestamp": ts,
        "created_at": ts,
    }
    if is_current is not None:
        payload["is_current"] = is_current
    from qdrant_client.models import PointStruct

    client.upsert(
        collection_name="discussions",
        points=[PointStruct(id=pid, vector=FIXED_VECTOR, payload=payload)],
    )


def test_supersede_prior_demotes_prior_keeps_new(storage_with_inmemory):
    """Handoff auto-supersession demotes the prior point to is_current=False
    and leaves the just-stored (excluded) point untouched."""
    import uuid

    storage, _config = storage_with_inmemory
    group_id = "proj-supersede"
    prior = str(uuid.uuid4())
    new = str(uuid.uuid4())
    _insert_handoff(
        storage.qdrant_client, group_id=group_id, pid=prior, ts="2026-01-01T00:00:00Z"
    )
    _insert_handoff(
        storage.qdrant_client, group_id=group_id, pid=new, ts="2026-02-01T00:00:00Z"
    )

    demoted = storage.supersede_prior_agent_memories(
        group_id=group_id,
        agent_id="parzival",
        memory_type="agent_handoff",
        exclude_memory_id=new,
    )
    assert demoted == 1

    recs = storage.qdrant_client.retrieve(
        collection_name="discussions", ids=[prior, new]
    )
    by_id = {str(r.id): r.payload for r in recs}
    assert by_id[prior]["is_current"] is False
    assert by_id[new].get("is_current", True) is True


def test_supersede_prior_is_idempotent(storage_with_inmemory):
    import uuid

    storage, _config = storage_with_inmemory
    group_id = "proj-idempotent"
    prior = str(uuid.uuid4())
    _insert_handoff(
        storage.qdrant_client, group_id=group_id, pid=prior, ts="2026-01-01T00:00:00Z"
    )

    first = storage.supersede_prior_agent_memories(
        group_id=group_id, agent_id="parzival", memory_type="agent_handoff"
    )
    second = storage.supersede_prior_agent_memories(
        group_id=group_id, agent_id="parzival", memory_type="agent_handoff"
    )
    assert first == 1
    assert second == 0  # already superseded → excluded by must_not(is_current==False)


def test_supersede_by_id_demotes_single_point(storage_with_inmemory):
    import uuid

    storage, _config = storage_with_inmemory
    group_id = "proj-by-id"
    pid = str(uuid.uuid4())
    _insert_handoff(
        storage.qdrant_client, group_id=group_id, pid=pid, ts="2026-01-01T00:00:00Z"
    )

    assert storage.supersede_memory_by_id(pid, group_id=group_id) is True
    rec = storage.qdrant_client.retrieve(collection_name="discussions", ids=[pid])[0]
    assert rec.payload["is_current"] is False


def test_supersede_by_id_cross_project_not_demoted(storage_with_inmemory):
    """RSK-021 / W-02: a --supersedes id belonging to ANOTHER project's
    group_id is NOT demoted and returns False (shared-Qdrant tenant safety)."""
    import uuid

    storage, _config = storage_with_inmemory
    other_group = "document-pipeline"  # e.g. DocIntel on the shared Qdrant
    active_group = "proj-active"
    foreign_pid = str(uuid.uuid4())
    _insert_handoff(
        storage.qdrant_client,
        group_id=other_group,
        pid=foreign_pid,
        ts="2026-01-01T00:00:00Z",
    )

    # Active project tries to supersede a foreign point — must be a no-op.
    assert storage.supersede_memory_by_id(foreign_pid, group_id=active_group) is False
    rec = storage.qdrant_client.retrieve(
        collection_name="discussions", ids=[foreign_pid]
    )[0]
    # Foreign point is untouched (is_current never set to False).
    assert rec.payload.get("is_current", True) is True


def test_supersede_by_id_missing_point_returns_false(storage_with_inmemory):
    import uuid

    storage, _config = storage_with_inmemory
    assert (
        storage.supersede_memory_by_id(str(uuid.uuid4()), group_id="proj-active")
        is False
    )


def test_supersede_by_id_empty_group_id_raises(storage_with_inmemory):
    import uuid

    storage, _config = storage_with_inmemory
    with pytest.raises(ValueError, match="explicit project scope"):
        storage.supersede_memory_by_id(str(uuid.uuid4()), group_id="")


def test_supersede_prior_empty_group_id_raises(storage_with_inmemory):
    storage, _config = storage_with_inmemory
    with pytest.raises(ValueError, match="explicit project scope"):
        storage.supersede_prior_agent_memories(
            group_id="", agent_id="parzival", memory_type="agent_handoff"
        )


def test_supersede_prior_does_not_demote_other_project(storage_with_inmemory):
    """Cross-project isolation: a live point with a DIFFERENT group_id (same
    agent_id/type) is NOT demoted by a supersede scoped to the active project."""
    import uuid

    storage, _config = storage_with_inmemory
    active_group = "proj-active"
    other_group = "document-pipeline"
    active_pid = str(uuid.uuid4())
    foreign_pid = str(uuid.uuid4())
    _insert_handoff(
        storage.qdrant_client,
        group_id=active_group,
        pid=active_pid,
        ts="2026-01-01T00:00:00Z",
    )
    _insert_handoff(
        storage.qdrant_client,
        group_id=other_group,
        pid=foreign_pid,
        ts="2026-01-01T00:00:00Z",
    )

    demoted = storage.supersede_prior_agent_memories(
        group_id=active_group, agent_id="parzival", memory_type="agent_handoff"
    )
    assert demoted == 1  # only the active-project point

    recs = storage.qdrant_client.retrieve(
        collection_name="discussions", ids=[active_pid, foreign_pid]
    )
    by_id = {str(r.id): r.payload for r in recs}
    assert by_id[active_pid]["is_current"] is False
    # Foreign-project point is untouched.
    assert by_id[foreign_pid].get("is_current", True) is True
