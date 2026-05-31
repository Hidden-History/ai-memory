"""PLAN-028 P2-2 Phase A — injection-noise shadow observability tests.

Covers the observe-only instrumentation added to make every current
retrieval/injection candidate-drop attributable in the noise histogram:

- R1: ``select_results_greedy`` records ``already_injected`` and
  ``empty_content`` rejects for the two formerly-silent skip branches.
- R2: a freshness-penalty-blocked candidate (score driven to 0.0 by the
  tier-2 hook) is relabeled ``freshness_block`` instead of ``score_gap``.
- R3: ``log_injection_event`` persists ``rejects[]`` + ``fallback_signaled``
  and remains backward-compatible when those are omitted.

Prime directive: these changes are observe-only. The SELECTED SET must be
byte-identical before and after — verified directly here.
"""

import json

import pytest

from memory.injection import log_injection_event, select_results_greedy


@pytest.fixture(autouse=True)
def _isolate_observability(monkeypatch):
    """Mock observability at the call boundary so tests stay hermetic.

    - ``emit_trace_event`` -> None (no Langfuse trace buffer writes).
    - ``push_retrieval_reject_metric_async`` -> no-op (no subprocess fork).

    The authoritative per-drop observability signal asserted by these tests is
    the in-memory ``meta["rejects"]`` accumulator returned by
    ``select_results_greedy``; the Prometheus counter is a fire-and-forget side
    effect (already covered by BP-158 tests) and is only silenced here.
    """
    monkeypatch.setattr("memory.injection.emit_trace_event", None, raising=False)
    # Body-local import + object setattr: the autouse conftest
    # reset_metrics_registry fixture pops memory.metrics* from sys.modules each
    # test, so a module instance captured at file-import time is stale. Importing
    # here (post-pop) re-caches the instance that the code's call-time
    # `from memory.metrics_push import ...` resolves to, so the patch sticks.
    import memory.metrics_push as _mpush

    monkeypatch.setattr(
        _mpush,
        "push_retrieval_reject_metric_async",
        lambda *a, **k: None,
    )


def _result(point_id, content, score, type_="decision", collection="discussions"):
    return {
        "id": point_id,
        "content": content,
        "score": score,
        "type": type_,
        "collection": collection,
    }


# --------------------------------------------------------------------------- #
# R1 — formerly-silent drops are now recorded                                  #
# --------------------------------------------------------------------------- #


def test_already_injected_skip_is_recorded_and_selection_unchanged():
    results = [
        _result("a", "alpha content here", 0.9),
        _result("b", "beta content here", 0.85),
    ]
    selected, _tokens, meta = select_results_greedy(
        results,
        budget=10_000,
        excluded_ids=["a"],
        return_meta=True,
    )

    # Observe-only: 'a' excluded as before, 'b' selected — selection unchanged.
    assert [r["id"] for r in selected] == ["b"]
    # New signal: the cross-turn dedup skip is now attributable in meta.rejects.
    assert "already_injected" in [r["reason"] for r in meta["rejects"]]


def test_empty_content_skip_is_recorded_and_selection_unchanged():
    results = [
        _result("a", "real content", 0.9),
        _result("b", "   ", 0.85),  # whitespace-only -> empty_content
    ]
    selected, _tokens, meta = select_results_greedy(
        results,
        budget=10_000,
        return_meta=True,
    )

    assert [r["id"] for r in selected] == ["a"]
    assert "empty_content" in [r["reason"] for r in meta["rejects"]]


# --------------------------------------------------------------------------- #
# R2 — freshness_block relabel (observe-only)                                  #
# --------------------------------------------------------------------------- #


def test_freshness_block_relabels_score_gap_drop():
    results = [
        _result("hi", "high score content", 0.9, "code_pattern", "code-patterns"),
        _result("fb", "blocked content", 0.0, "code_pattern", "code-patterns"),
        _result("sg", "low score content", 0.1, "code_pattern", "code-patterns"),
    ]
    selected, _tokens, meta = select_results_greedy(
        results,
        budget=10_000,
        return_meta=True,
        freshness_blocked_ids={"fb"},
    )

    # Only the high-score result is selected (best=0.9, cutoff=0.63).
    assert [r["id"] for r in selected] == ["hi"]

    reasons = [r["reason"] for r in meta["rejects"]]
    # 'fb' was freshness-blocked -> attributed to freshness_block.
    assert "freshness_block" in reasons
    # 'sg' is a genuine low-relevance gap -> still score_gap.
    assert "score_gap" in reasons
    # Exactly one of each (no double-count).
    assert reasons.count("freshness_block") == 1
    assert reasons.count("score_gap") == 1


def test_freshness_block_is_observe_only_selection_identical():
    """Passing freshness_blocked_ids changes only labels, never selection."""
    results = [
        _result("hi", "high score content", 0.9, "code_pattern", "code-patterns"),
        _result("fb", "blocked content", 0.0, "code_pattern", "code-patterns"),
        _result("sg", "low score content", 0.1, "code_pattern", "code-patterns"),
    ]

    sel_without, tok_without, _ = select_results_greedy(
        list(results), budget=10_000, return_meta=True
    )
    sel_with, tok_with, _ = select_results_greedy(
        list(results), budget=10_000, return_meta=True, freshness_blocked_ids={"fb"}
    )

    assert [r["id"] for r in sel_without] == [r["id"] for r in sel_with]
    assert tok_without == tok_with


# --------------------------------------------------------------------------- #
# Reject-counter push is aggregated, not forked per-drop                        #
# --------------------------------------------------------------------------- #


def test_reject_counter_push_is_aggregated_with_count(monkeypatch):
    """Many same-(reason, collection) drops emit ONE push carrying count=N.

    Guards against the per-drop subprocess-fork storm: the already_injected
    skip is high-volume on the UserPromptSubmit hot path, so the counter push
    must be aggregated. The per-drop rejects[] records stay one-per-drop.
    """
    import memory.metrics_push as _mpush

    calls = []
    monkeypatch.setattr(
        _mpush,
        "push_retrieval_reject_metric_async",
        lambda **kwargs: calls.append(kwargs),
    )

    results = [_result(str(i), f"content number {i}", 0.9) for i in range(5)]
    excluded = [str(i) for i in range(5)]
    selected, _tokens, meta = select_results_greedy(
        results,
        budget=10_000,
        excluded_ids=excluded,
        return_meta=True,
    )

    # Selection unchanged: every candidate was already injected -> none selected.
    assert selected == []
    # Per-drop audit records remain one-per-drop (these feed the histogram).
    assert [r["reason"] for r in meta["rejects"]] == ["already_injected"] * 5
    # The counter push is aggregated: ONE call for the single
    # (already_injected, discussions) pair, carrying count=5 — not five forks.
    assert len(calls) == 1
    assert calls[0]["reason"] == "already_injected"
    assert calls[0]["collection"] == "discussions"
    assert calls[0]["count"] == 5


def test_reject_counter_push_bounded_by_distinct_pairs(monkeypatch):
    """Push count is bounded by distinct (reason, collection) pairs, not drops."""
    import memory.metrics_push as _mpush

    calls = []
    monkeypatch.setattr(
        _mpush,
        "push_retrieval_reject_metric_async",
        lambda **kwargs: calls.append(kwargs),
    )

    # 3 already_injected + 2 score_gap drops = 5 drops, but only 2 distinct pairs.
    results = [
        _result("hi", "high score anchor content", 0.9),
        _result("x1", "excluded one", 0.9),
        _result("x2", "excluded two", 0.9),
        _result("x3", "excluded three", 0.9),
        _result("g1", "low gap one", 0.1),
        _result("g2", "low gap two", 0.1),
    ]
    selected, _tokens, _meta = select_results_greedy(
        results,
        budget=10_000,
        excluded_ids=["x1", "x2", "x3"],
        return_meta=True,
    )

    assert [r["id"] for r in selected] == ["hi"]
    # Bounded by DISTINCT pairs (2), not by the 5 drops.
    assert len(calls) == 2
    by_reason = {c["reason"]: c["count"] for c in calls}
    assert by_reason == {"already_injected": 3, "score_gap": 2}


# --------------------------------------------------------------------------- #
# Precedence: already_injected wins over freshness_block                        #
# --------------------------------------------------------------------------- #


def test_already_injected_takes_precedence_over_freshness_block():
    """A result that is BOTH freshness-blocked AND already-injected is recorded
    under already_injected — the earlier loop branch wins (locked precedence)."""
    results = [
        _result("hi", "high score content", 0.9, "code_pattern", "code-patterns"),
        _result("both", "blocked and injected", 0.0, "code_pattern", "code-patterns"),
    ]
    selected, _tokens, meta = select_results_greedy(
        results,
        budget=10_000,
        excluded_ids=["both"],
        return_meta=True,
        freshness_blocked_ids={"both"},
    )

    # 'hi' selected; 'both' dropped once, attributed to already_injected only.
    assert [r["id"] for r in selected] == ["hi"]
    assert [r["reason"] for r in meta["rejects"]] == ["already_injected"]


def test_return_meta_false_is_backward_compatible():
    results = [_result("a", "content one", 0.9)]
    out = select_results_greedy(results, budget=10_000)
    assert isinstance(out, tuple)
    assert len(out) == 2  # (selected, tokens_used) legacy shape


# --------------------------------------------------------------------------- #
# R3 — log_injection_event persists rejects[] + fallback_signaled             #
# --------------------------------------------------------------------------- #


def _read_last_entry(audit_dir):
    log_path = audit_dir / "logs" / "injection-log.jsonl"
    lines = log_path.read_text().strip().splitlines()
    return json.loads(lines[-1])


def test_log_injection_event_persists_rejects_and_fallback(tmp_path):
    rejects = [
        {
            "type": "agent_handoff",
            "tokens": 5000,
            "score": 0.0,
            "reason": "ceiling_exceeded",
            "tier": "1_bootstrap",
            "collection": "discussions",
        }
    ]
    log_injection_event(
        tier=1,
        trigger="skill:test",
        project="proj",
        session_id="sess",
        results_considered=3,
        results_selected=1,
        tokens_used=100,
        budget=2000,
        audit_dir=tmp_path,
        rejects=rejects,
        fallback_signaled=True,
    )
    entry = _read_last_entry(tmp_path)
    assert entry["rejects"] == rejects
    assert entry["fallback_signaled"] is True


def test_log_injection_event_backward_compatible_defaults(tmp_path):
    log_injection_event(
        tier=2,
        trigger="UserPromptSubmit",
        project="proj",
        session_id="sess",
        results_considered=0,
        results_selected=0,
        tokens_used=0,
        budget=0,
        audit_dir=tmp_path,
    )
    entry = _read_last_entry(tmp_path)
    # New fields default to empty/false — never crashes existing callers.
    assert entry["rejects"] == []
    assert entry["fallback_signaled"] is False
    # Existing fields remain intact.
    assert entry["tier"] == 2
    assert entry["gating_mode"] == "full"
