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
    monkeypatch.setattr(
        "memory.metrics_push.push_retrieval_reject_metric_async",
        lambda *a, **k: None,
        raising=True,
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
