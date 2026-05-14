"""TD-519 (F-002): Decision-type emit at session closeout — round-trip + idempotency.

Verifies the additive emit path implemented per locked design D-1..D-7 in
TECH-DEBT-519:
  - D-2-A: ``"decision"`` accepted by ``store_agent_memory`` validation.
  - D-2: payload contains ``dec_id``, ``pm_number``, ``decision_summary``,
    ``rationale_text`` metadata fields.
  - D-3: re-emit of same DEC content is idempotent via SHA-256 content_hash dedup.
  - D-4: stored WHOLE — ``chunking_metadata.chunk_type='whole'`` and
    ``total_chunks=1`` (load-bearing per Q-D3 course-correction:
    ``content_type_map`` does NOT map ``MemoryType.DECISION``, so the chunker
    is skipped entirely).
  - D-5: L2 retrieval ``get_recent(memory_type=["decision"])`` returns DEC
    content (previously always empty).

Test approach: in-memory Qdrant + mocked embedding client (mirrors
``tests/integration/test_e2e_cross_phase.py`` pattern). Direct
``MemoryStorage.store_agent_memory`` invocation from in-process — the script's
argparse + skill metric paths are covered by ``test_T6_*``/``test_T7_*``
mocked unit tests below.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

FIXED_VECTOR = [0.5] * 768


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
    """Deterministic 768-dim embedding for store + search paths."""
    mock = MagicMock()
    mock.embed.return_value = [FIXED_VECTOR]
    with (
        patch("memory.storage.EmbeddingClient", return_value=mock),
        patch("memory.search.EmbeddingClient", return_value=mock),
    ):
        yield mock


@pytest.fixture
def storage_with_inmemory(qdrant_inmemory, mock_embedding, monkeypatch):
    """Wire MemoryStorage to the in-memory Qdrant client."""
    from memory.config import get_config, reset_config
    from memory.storage import MemoryStorage

    monkeypatch.setenv("DECAY_ENABLED", "false")
    reset_config()
    config = get_config()
    storage = MemoryStorage(config)
    storage.qdrant_client = qdrant_inmemory
    return storage, config


# ─── T1: Allowlist accepts memory_type="decision" (D-2-A) ───────────────────


def test_T1_decision_type_accepted_by_allowlist(storage_with_inmemory):
    """D-2-A: ``store_agent_memory(memory_type="decision", ...)`` does NOT
    raise ValueError. Was previously rejected — load-bearing for the entire
    decision-emit path.
    """
    storage, _config = storage_with_inmemory

    result = storage.store_agent_memory(
        content=(
            "DEC-PM285-D2: Add 'decision' to VALID_AGENT_TYPES allowlist.\n"
            "Rationale: Closes TD-519 / F-002 retrieval gap."
        ),
        memory_type="decision",
        agent_id="parzival",
        cwd="/tmp/test-decision",
        metadata={
            "dec_id": "DEC-PM285-D2",
            "pm_number": 285,
            "decision_summary": "Add 'decision' to VALID_AGENT_TYPES allowlist.",
            "rationale_text": "Closes TD-519 / F-002 retrieval gap.",
        },
    )
    assert result["status"] == "stored"
    assert "memory_id" in result


# ─── T2: Round-trip — store 2 DECs, retrieve via L2 (get_recent) ─────────────


def test_T2_round_trip_two_decs_retrievable_via_get_recent(storage_with_inmemory):
    """D-5: After emit, ``get_recent(collection=discussions,
    memory_type=["decision"], group_id=...)`` returns both DECs with
    metadata intact.
    """
    from memory.config import COLLECTION_DISCUSSIONS
    from memory.search import MemorySearch

    storage, config = storage_with_inmemory
    group_id = "test-td519-t2"

    decs = [
        ("DEC-TEST-1", "Decision 1: First test decision.\nRationale: T2 round-trip."),
        ("DEC-TEST-2", "Decision 2: Second test decision.\nRationale: T2 idempotency."),
    ]
    for dec_id, content in decs:
        storage.store_agent_memory(
            content=content,
            memory_type="decision",
            agent_id="parzival",
            group_id=group_id,
            metadata={
                "dec_id": dec_id,
                "pm_number": 285,
                "decision_summary": content.split("\n")[0][:200],
                "rationale_text": None,
            },
        )

    search = MemorySearch(config)
    search.client = storage.qdrant_client
    results = search.get_recent(
        collection=COLLECTION_DISCUSSIONS,
        group_id=group_id,
        memory_type=["decision"],
        limit=5,
    )

    assert len(results) == 2
    returned_ids = sorted(r.get("dec_id") for r in results)
    assert returned_ids == ["DEC-TEST-1", "DEC-TEST-2"]
    for r in results:
        assert r.get("type") == "decision"
        assert r.get("agent_id") == "parzival"
        assert r.get("pm_number") == 285


# ─── T3: Idempotency — re-emit same DEC produces single point (dedup) ───────


def test_T3_reemit_same_dec_dedup_via_content_hash(storage_with_inmemory):
    """D-3: Re-invoking emit for the same DEC body MUST return
    ``status="duplicate"`` on the second call and the collection MUST contain
    exactly 1 point — not 2 — via SHA-256 content_hash dedup.
    """
    from memory.config import COLLECTION_DISCUSSIONS
    from memory.search import MemorySearch

    storage, config = storage_with_inmemory
    group_id = "test-td519-t3"
    content = "DEC-TEST-IDEM: Idempotency check.\nRationale: Re-emit must dedup."

    first = storage.store_agent_memory(
        content=content,
        memory_type="decision",
        agent_id="parzival",
        group_id=group_id,
        metadata={"dec_id": "DEC-TEST-IDEM", "pm_number": 285},
    )
    second = storage.store_agent_memory(
        content=content,
        memory_type="decision",
        agent_id="parzival",
        group_id=group_id,
        metadata={"dec_id": "DEC-TEST-IDEM", "pm_number": 285},
    )

    assert first["status"] == "stored"
    assert second["status"] == "duplicate"

    search = MemorySearch(config)
    search.client = storage.qdrant_client
    results = search.get_recent(
        collection=COLLECTION_DISCUSSIONS,
        group_id=group_id,
        memory_type=["decision"],
        limit=5,
    )
    assert len(results) == 1, "Re-emit must NOT create a second point"


# ─── T4: D-4 storage shape — whole, 1 vector, no chunking ───────────────────


def test_T4_decision_stored_whole_no_chunking(storage_with_inmemory):
    """D-4 (Chunking-Strategy-V2 §3.3 + §7): decisions store WHOLE
    (1 vector, no chunking).

    Per Q-D3 course-correction in recommendation-first-r1.md: the
    ``content_type_map`` in storage.py intentionally does NOT map
    ``MemoryType.DECISION`` — unmapped types skip the chunker entirely.
    This test load-bears that assumption empirically. If it fails,
    a chunker map entry has been added (regression vs. D-4) — STOP and
    surface, do NOT auto-add.
    """
    from memory.config import COLLECTION_DISCUSSIONS
    from memory.search import MemorySearch

    storage, config = storage_with_inmemory
    group_id = "test-td519-t4"
    # Reasonably long content — well under 8192 token Jina v2 limit but long
    # enough that a wrong content_type_map=PROSE entry would chunk into >1
    # vector with default 512-token thresholds.
    content = "DEC-TEST-WHOLE: Long-decision storage shape verification.\n" + (
        "Rationale paragraph. " * 200
    )

    storage.store_agent_memory(
        content=content,
        memory_type="decision",
        agent_id="parzival",
        group_id=group_id,
        metadata={"dec_id": "DEC-TEST-WHOLE", "pm_number": 285},
    )

    search = MemorySearch(config)
    search.client = storage.qdrant_client
    results = search.get_recent(
        collection=COLLECTION_DISCUSSIONS,
        group_id=group_id,
        memory_type=["decision"],
        limit=5,
    )
    assert len(results) == 1, (
        f"Decision must store as exactly 1 vector (D-4); got {len(results)}. "
        "If >1, the chunker is processing 'decision' — verify content_type_map."
    )
    cm = results[0].get("chunking_metadata") or {}
    assert cm.get("chunk_type") == "whole", (
        f"Expected chunk_type='whole'; got {cm!r}. "
        "D-4 contract violation — chunker is processing decision type."
    )
    assert cm.get("total_chunks") == 1, (
        f"Expected total_chunks=1; got {cm!r}. "
        "D-4 contract violation — decision was chunked."
    )


# ─── T5: Closeout step-04 references the new skill ──────────────────────────


_STEP_04_PATH = (
    Path(__file__).resolve().parent.parent
    / "_ai-memory"
    / "pov"
    / "workflows"
    / "session"
    / "close"
    / "steps-c"
    / "step-04-save-and-confirm.md"
)


def test_T5_closeout_step_04_invokes_save_decision_skill():
    """Static-analysis: closeout step-04 must reference
    ``/parzival-save-decision`` so per-DEC emit fires at session close.
    """
    assert _STEP_04_PATH.exists(), f"Missing step-04 file: {_STEP_04_PATH}"
    text = _STEP_04_PATH.read_text(encoding="utf-8")
    assert (
        "/parzival-save-decision" in text
    ), "step-04-save-and-confirm.md must invoke /parzival-save-decision per TD-519"
    assert "TD-519" in text, "step-04 must cite TD-519 for traceability"
    # Ensure the closeout-continues semantics survive in prose
    assert (
        "decision-log.md" in text
    ), "step-04 must name decision-log.md as primary record"
    assert (
        "WHOLE" in text or "whole" in text
    ), "step-04 must cite the whole-store contract"


# ─── T6/T7: Mocked unit tests for the script — argparse + graceful failure ──


_DECISION_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "memory"
    / "parzival_save_decision.py"
)


def _load_decision_script():
    spec = importlib.util.spec_from_file_location(
        "parzival_save_decision_under_test", _DECISION_SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_T6_script_argparse_required_flags():
    """parzival_save_decision.py argparse: --dec-id and --content are required;
    --rationale, --session-id, --pm-number are optional.
    """
    if not _DECISION_SCRIPT.exists():
        pytest.skip(f"Script not found: {_DECISION_SCRIPT}")
    mod = _load_decision_script()

    with patch.object(
        mod.sys,
        "argv",
        ["parzival_save_decision.py", "--dec-id", "DEC-T6", "--content", "body"],
    ):
        ns = mod.parse_args()
    assert ns.dec_id == "DEC-T6"
    assert ns.content == "body"
    assert ns.rationale is None
    assert ns.session_id is None
    assert ns.pm_number is None

    # Missing --content must SystemExit (argparse default behavior)
    with (
        patch.object(mod.sys, "argv", ["script", "--dec-id", "DEC-T6"]),
        pytest.raises(SystemExit),
    ):
        mod.parse_args()


def test_T7_script_graceful_qdrant_failure_returns_zero():
    """T7: If storage raises, the script prints a warning, pushes an error
    metric, and returns 0 (closeout-continues semantics — file is primary).
    """
    if not _DECISION_SCRIPT.exists():
        pytest.skip(f"Script not found: {_DECISION_SCRIPT}")
    mod = _load_decision_script()

    failing_storage = MagicMock()
    failing_storage.store_agent_memory.side_effect = RuntimeError("qdrant down")
    mock_config = MagicMock()
    mock_config.parzival_enabled = True

    with (
        patch.object(
            mod.sys,
            "argv",
            [
                "parzival_save_decision.py",
                "--dec-id",
                "DEC-T7",
                "--content",
                "test body",
                "--pm-number",
                "285",
            ],
        ),
        patch.object(mod, "get_config", return_value=mock_config),
        patch.object(mod, "MemoryStorage", return_value=failing_storage),
        patch.object(mod, "push_skill_metrics_async") as mock_metric,
    ):
        rc = mod.main()

    assert rc == 0, "Script must return 0 on Qdrant failure (closeout-continues)"
    failing_storage.store_agent_memory.assert_called_once()
    # Error metric pushed
    mock_metric.assert_called()
    metric_args = mock_metric.call_args
    assert metric_args[0][0] == "parzival-save-decision"
    assert metric_args[0][1] == "error"


def test_T8_script_parzival_disabled_returns_zero():
    """If PARZIVAL_ENABLED=false, script returns 0 without attempting storage."""
    if not _DECISION_SCRIPT.exists():
        pytest.skip(f"Script not found: {_DECISION_SCRIPT}")
    mod = _load_decision_script()

    mock_storage = MagicMock()
    mock_config = MagicMock()
    mock_config.parzival_enabled = False

    with (
        patch.object(
            mod.sys,
            "argv",
            ["script", "--dec-id", "DEC-T8", "--content", "x"],
        ),
        patch.object(mod, "get_config", return_value=mock_config),
        patch.object(mod, "MemoryStorage", return_value=mock_storage),
    ):
        rc = mod.main()

    assert rc == 0
    mock_storage.store_agent_memory.assert_not_called()


# ─── T9: decision_summary strip — DEC-prefix matched only ──────────────────
#
# T9a: input has DEC-PMxxx-D# prefix → strip
# T9b: input is a URL with embedded colon (no DEC prefix) → unchanged
# T9c: input is prose with leading qualifier ("Important note:") → unchanged
# T9d: input has lowercase DEC prefix (case-insensitive match) → strip
#
# T9b/c/d cover the over-broad-strip regressions that an unconditional
# split-on-colon would silently corrupt. T9a is the original happy path.


@pytest.mark.parametrize(
    "first_line,expected_summary,case_id",
    [
        (
            "DEC-PM286-T9: Strip the prefix.",
            "Strip the prefix.",
            "T9a-dec-prefix-stripped",
        ),
        (
            "Use Postgres URL https://example.com:5432/db",
            "Use Postgres URL https://example.com:5432/db",
            "T9b-url-unchanged",
        ),
        (
            "Important note: Decision X applies",
            "Important note: Decision X applies",
            "T9c-prose-qualifier-unchanged",
        ),
        (
            "dec-pm286-t9: lowercase prefix should also strip",
            "lowercase prefix should also strip",
            "T9d-case-insensitive-dec-prefix-stripped",
        ),
    ],
)
def test_T9_decision_summary_regex_strip(
    storage_with_inmemory, first_line, expected_summary, case_id
):
    """The regex-based DEC-prefix strip must:
      - strip the leading DEC-XXX-D#: prefix when present (T9a, T9d)
      - leave unrelated colon-bearing content intact (T9b URL, T9c prose)

    This exercises the same regex (`_DEC_PREFIX_RE`) the script uses to
    derive `decision_summary`, so a future change that loosens the regex
    (back to over-broad split-on-colon) surfaces here.
    """
    # Import the regex from the canonical script and exercise it directly so
    # the test assertion follows the same code path the script's main()
    # follows when computing decision_summary.
    import importlib.util
    from pathlib import Path

    from memory.config import COLLECTION_DISCUSSIONS
    from memory.search import MemorySearch

    script_path = (
        Path(__file__).resolve().parent.parent
        / "scripts"
        / "memory"
        / "parzival_save_decision.py"
    )
    spec = importlib.util.spec_from_file_location(
        "parzival_save_decision_regex_under_test", script_path
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    derived_summary = mod._DEC_PREFIX_RE.sub("", first_line).strip()[:200]
    assert derived_summary == expected_summary, (
        f"[{case_id}] regex strip produced {derived_summary!r}; "
        f"expected {expected_summary!r}"
    )

    # Round-trip: store via storage layer with the derived summary and
    # confirm it survives intact (no further mutation in the storage path).
    storage, config = storage_with_inmemory
    group_id = f"test-td519-t9-{case_id}"
    full_content = first_line + "\nRationale: T9 regex coverage check."

    storage.store_agent_memory(
        content=full_content,
        memory_type="decision",
        agent_id="parzival",
        group_id=group_id,
        metadata={
            "dec_id": f"DEC-PM286-T9-{case_id}",
            "pm_number": 286,
            "decision_summary": derived_summary,
            "rationale_text": None,
        },
    )

    search = MemorySearch(config)
    search.client = storage.qdrant_client
    results = search.get_recent(
        collection=COLLECTION_DISCUSSIONS,
        group_id=group_id,
        memory_type=["decision"],
        limit=5,
    )
    assert len(results) == 1
    stored_summary = results[0].get("decision_summary")
    assert stored_summary == expected_summary, (
        f"[{case_id}] stored summary {stored_summary!r}; expected "
        f"{expected_summary!r}"
    )
