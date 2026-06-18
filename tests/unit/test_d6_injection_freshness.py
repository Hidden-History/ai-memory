"""D6 injection-freshness read-path tests (v2.7.0, DEC-PM338-D6).

The DATA-SAFETY CRUX: the discussions read filter must EXCLUDE only
explicitly-superseded points (is_current==False) while RETURNING legacy
field-absent points (a match(is_current==True) would silently drop every
such point — catastrophic loss). The github namespace keeps its own
match(is_current==True) and must NOT be unified.

Covers:
    P0  must_not(is_current==False) on discussions returns field-absent +
        is_current==True points and drops is_current==False (functional, in-memory).
    P0  github path keeps match(is_current==True); non-discussions collections
        get no is_current filter (filter-shape, deterministic).
    P0  no superseded point is injected by bootstrap (functional).
    P1  Layer-3 insights retrieved by deterministic recency (get_recent).

Approach mirrors tests/test_l1_handoff_realistic_size.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from memory.config import COLLECTION_DISCUSSIONS

FIXED_VECTOR = [0.5] * 768


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    monkeypatch.delenv("AI_MEMORY_PROJECT_ID", raising=False)
    monkeypatch.setenv("DECAY_ENABLED", "false")


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


def _make_search(qdrant_inmemory, monkeypatch):
    from memory.config import get_config, reset_config
    from memory.search import MemorySearch

    reset_config()
    config = get_config()
    search = MemorySearch(config)
    search.client = qdrant_inmemory
    return search, config


def _insert_insight(client, *, pid, group_id, ts, is_current="OMIT"):
    payload = {
        "content": f"insight {pid}",
        "type": "agent_insight",
        "agent_id": "parzival",
        "group_id": group_id,
        "timestamp": ts,
        "created_at": ts,
    }
    if is_current != "OMIT":
        payload["is_current"] = is_current
    client.upsert(
        collection_name="discussions",
        points=[PointStruct(id=pid, vector=FIXED_VECTOR, payload=payload)],
    )


# ─── P0 — the data-safety crux: must_not==False RETURNS field-absent points ──


def test_get_recent_returns_field_absent_and_current__drops_superseded(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """DONE-WHEN proof: must_not(is_current==False) on discussions returns
    legacy field-absent AND is_current==True points, and drops ONLY the
    explicitly-superseded (is_current==False) point."""
    import uuid

    group_id = "proj-crux"
    current = str(uuid.uuid4())
    superseded = str(uuid.uuid4())
    legacy_absent = str(uuid.uuid4())
    _insert_insight(
        qdrant_inmemory,
        pid=current,
        group_id=group_id,
        ts="2026-03-01T00:00:00Z",
        is_current=True,
    )
    _insert_insight(
        qdrant_inmemory,
        pid=superseded,
        group_id=group_id,
        ts="2026-03-02T00:00:00Z",
        is_current=False,
    )
    _insert_insight(
        qdrant_inmemory, pid=legacy_absent, group_id=group_id, ts="2026-03-03T00:00:00Z"
    )  # field absent

    search, _config = _make_search(qdrant_inmemory, monkeypatch)
    results = search.get_recent(
        collection=COLLECTION_DISCUSSIONS,
        group_id=group_id,
        memory_type=["agent_insight"],
        agent_id="parzival",
        limit=10,
    )
    ids = {str(r["id"]) for r in results}
    assert (
        legacy_absent in ids
    ), "field-absent legacy point MUST be returned (absent != False)"
    assert current in ids, "is_current==True point must be returned"
    assert superseded not in ids, "explicitly-superseded point must be excluded"


def test_search_discussions_excludes_superseded_keeps_field_absent(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """Tier-2 discussions search() applies the same exclude-superseded filter."""
    import uuid

    group_id = "proj-crux-search"
    current = str(uuid.uuid4())
    superseded = str(uuid.uuid4())
    legacy_absent = str(uuid.uuid4())
    _insert_insight(
        qdrant_inmemory,
        pid=current,
        group_id=group_id,
        ts="2026-03-01T00:00:00Z",
        is_current=True,
    )
    _insert_insight(
        qdrant_inmemory,
        pid=superseded,
        group_id=group_id,
        ts="2026-03-02T00:00:00Z",
        is_current=False,
    )
    _insert_insight(
        qdrant_inmemory, pid=legacy_absent, group_id=group_id, ts="2026-03-03T00:00:00Z"
    )

    search, _config = _make_search(qdrant_inmemory, monkeypatch)
    results = search.search(
        query="insight",
        collection=COLLECTION_DISCUSSIONS,
        group_id=group_id,
        limit=10,
        memory_type=["agent_insight"],
        agent_id="parzival",
        fast_mode=True,
    )
    ids = {str(r["id"]) for r in results}
    assert superseded not in ids
    assert legacy_absent in ids
    assert current in ids


# ─── P0 — github path unchanged; non-discussions get no is_current filter ────


def _capture_scroll_filter(monkeypatch, **get_recent_kwargs):
    from memory.config import get_config, reset_config
    from memory.search import MemorySearch

    reset_config()
    search = MemorySearch(get_config())
    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)
    search.client = mock_client
    search.get_recent(**get_recent_kwargs)
    return mock_client.scroll.call_args.kwargs["scroll_filter"]


def _has_is_current(conditions, value):
    if not conditions:
        return False
    for c in conditions:
        key = getattr(c, "key", None)
        match = getattr(c, "match", None)
        if key == "is_current" and getattr(match, "value", None) is value:
            return True
    return False


def test_discussions_get_recent_filter_adds_must_not_false(monkeypatch):
    f = _capture_scroll_filter(
        monkeypatch,
        collection=COLLECTION_DISCUSSIONS,
        group_id="g",
        memory_type=["agent_insight"],
    )
    assert _has_is_current(
        f.must_not, False
    ), "discussions must_not(is_current==False) missing"
    assert not _has_is_current(
        f.must, True
    ), "discussions must NOT add match(is_current==True)"


def test_github_get_recent_filter_keeps_match_true_unchanged(monkeypatch):
    from memory.config import COLLECTION_GITHUB

    f = _capture_scroll_filter(
        monkeypatch,
        collection=COLLECTION_GITHUB,
        group_id="g",
        source="github",
    )
    assert _has_is_current(f.must, True), "github must keep match(is_current==True)"
    assert not _has_is_current(
        f.must_not, False
    ), "github must NOT get the discussions must_not"


def test_code_patterns_get_recent_filter_has_no_is_current(monkeypatch):
    from memory.config import COLLECTION_CODE_PATTERNS

    f = _capture_scroll_filter(
        monkeypatch,
        collection=COLLECTION_CODE_PATTERNS,
        group_id="g",
    )
    assert not _has_is_current(f.must_not, False)
    assert not _has_is_current(f.must, True)


# ─── P0 + P1 — bootstrap injects no superseded point; Layer-3 by recency ─────


def test_bootstrap_does_not_inject_superseded_insight(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    import uuid

    from memory.injection import retrieve_bootstrap_context

    group_id = "proj-bootstrap-supersede"
    current = str(uuid.uuid4())
    superseded = str(uuid.uuid4())
    _insert_insight(
        qdrant_inmemory,
        pid=current,
        group_id=group_id,
        ts="2026-03-01T00:00:00Z",
        is_current=True,
    )
    _insert_insight(
        qdrant_inmemory,
        pid=superseded,
        group_id=group_id,
        ts="2026-03-02T00:00:00Z",
        is_current=False,
    )

    search, config = _make_search(qdrant_inmemory, monkeypatch)
    results, _meta = retrieve_bootstrap_context(search, group_id, config)
    ids = {str(r.get("id")) for r in results}
    assert (
        superseded not in ids
    ), "bootstrap must not inject an explicitly-superseded point"
    assert current in ids


def test_layer3_insights_retrieved_by_recency(
    qdrant_inmemory, mock_embedding, monkeypatch
):
    """P1: Layer-3 uses deterministic get_recent — newest insights, agent-scoped,
    NOT a generic-string semantic match."""
    import uuid

    from memory.injection import retrieve_bootstrap_context

    group_id = "proj-recency"
    ids_by_age = []
    for day in range(1, 6):  # 5 insights, ascending timestamp
        pid = str(uuid.uuid4())
        ids_by_age.append(pid)
        _insert_insight(
            qdrant_inmemory,
            pid=pid,
            group_id=group_id,
            ts=f"2026-04-0{day}T00:00:00Z",
            is_current=True,
        )

    search, config = _make_search(qdrant_inmemory, monkeypatch)
    results, _meta = retrieve_bootstrap_context(search, group_id, config)
    insight_ids = {
        str(r.get("id")) for r in results if r.get("type") == "agent_insight"
    }
    # Layer-3 limit=3 → the 3 NEWEST insights (days 5,4,3), not the oldest.
    assert ids_by_age[-1] in insight_ids  # newest present
    assert ids_by_age[0] not in insight_ids  # oldest excluded by recency cap
