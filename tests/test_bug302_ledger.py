"""PLAN-028 P2-3 — BUG-302 marker fix + per-source budget ledger tests.

Covers:
- BUG-302: tier-2 fallback marker renders remaining= so the reject is
  self-evidently correct (budget - tokens_used, not budget total).
- Per-source ledger: select_results_greedy accumulates per-collection
  requested/loaded/dropped tokens in meta["per_source"].
- Reconciliation: per collection, loaded_tokens + dropped["budget_exceeded"]["tokens"]
  == requested_tokens.
- Behavior-unchanged: selected + tokens_used are byte-identical pre/post for the
  same multi-source input (observe-only proof).
- Realistic multi-source fixture: ≥3 collections, ≥1 over-budget drop.

All tests exercise the real select_results_greedy path (no mocks of the
selection function itself).
"""

import json

import pytest

from memory.injection import log_injection_event, select_results_greedy

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _silence_observability(monkeypatch):
    """Silence Langfuse + Prometheus side-effects for hermetic tests."""
    monkeypatch.setattr("memory.injection.emit_trace_event", None, raising=False)
    import memory.metrics_push as _mpush

    monkeypatch.setattr(_mpush, "push_retrieval_reject_metric_async", lambda **k: None)


def _r(point_id, content, score, type_="decision", collection="discussions"):
    return {
        "id": point_id,
        "content": content,
        "score": score,
        "type": type_,
        "collection": collection,
    }


# ---------------------------------------------------------------------------
# BUG-302: meta carries budget and tokens_used; remaining = budget - tokens_used
# ---------------------------------------------------------------------------


class TestBug302MarkerRemaining:
    """BUG-302 reproducer: meta must carry budget and tokens_used so the
    caller can compute remaining = budget - tokens_used and render it in
    the tier-2 fallback marker.
    """

    def test_remaining_is_self_evident_for_correct_reject(self):
        """Reproduce PM #290 scenario: tokens=160, budget=1171, tokens_used=1050.

        After selecting ~1050 tokens of fillers, a 160-token handoff arrives.
        remaining = 1171 - 1050 = 121. tokens=160 > remaining=121 → reject is correct.
        The new marker formula: remaining = meta["budget"] - meta["tokens_used"].
        """
        # ~210 tokens per filler; 5 fillers ≈ 1050 tokens
        filler_content = "word " * 210
        fillers = [
            _r(f"f{i}", filler_content, 0.9, "session", "discussions") for i in range(5)
        ]
        # Handoff sized to exceed the remaining budget after fillers load
        big_handoff = _r(
            "h-reject",
            "word " * 200,
            0.95,
            "agent_handoff",
            "discussions",
        )
        budget = 1200
        results = [*fillers, big_handoff]

        _selected, tokens_used, meta = select_results_greedy(
            results, budget=budget, return_meta=True, tier=2
        )

        # meta must carry budget and tokens_used for marker computation
        assert meta["budget"] == budget
        assert meta["tokens_used"] == tokens_used

        remaining = meta["budget"] - meta["tokens_used"]
        assert remaining >= 0, "remaining must be non-negative"

        # If the handoff was budget-rejected, its tokens must exceed remaining
        budget_rejects = [
            r for r in meta["rejects"] if r.get("reason") == "budget_exceeded"
        ]
        for rej in budget_rejects:
            if rej.get("type") == "agent_handoff":
                assert rej["tokens"] > remaining, (
                    f"BUG-302: tokens={rej['tokens']} must exceed remaining={remaining} "
                    f"for the reject to be self-evidently correct. "
                    f"budget={budget}, tokens_used={tokens_used}"
                )

    def test_remaining_formula_with_tight_budget(self):
        """Direct test: meta budget/tokens_used allow correct remaining computation."""
        # Two fillers that fit; one large result that doesn't
        small = "word " * 40  # ~40 tokens
        large = "word " * 500  # ~500 tokens, won't fit after 2 smalls

        results = [
            _r("a", small, 0.90, "decision", "discussions"),
            _r("b", small, 0.85, "decision", "discussions"),
            _r("c", large, 0.80, "agent_handoff", "discussions"),
        ]
        budget = 150  # enough for a+b (~80 tokens), not c

        _selected, _tokens_used, meta = select_results_greedy(
            results, budget=budget, return_meta=True, tier=2
        )

        remaining = meta["budget"] - meta["tokens_used"]
        assert remaining >= 0

        # c must be budget-rejected and its tokens must exceed remaining
        budget_rejects = [
            r for r in meta["rejects"] if r.get("reason") == "budget_exceeded"
        ]
        assert budget_rejects, "large result must be budget-rejected"
        rej = budget_rejects[0]
        assert (
            rej["tokens"] > remaining
        ), f"tokens={rej['tokens']} must exceed remaining={remaining}"

    def test_result_larger_than_whole_budget_remaining_non_negative(self):
        """Edge case: single result larger than the whole budget.

        remaining = budget - 0 = budget (≥ 0). tokens > budget. Marker is sensible.
        """
        huge = _r("big", "x " * 5000, 0.95, "agent_handoff", "discussions")
        budget = 100

        _selected, tokens_used, meta = select_results_greedy(
            [huge], budget=budget, return_meta=True, tier=2
        )

        assert tokens_used == 0
        remaining = meta["budget"] - meta["tokens_used"]
        assert remaining == budget  # nothing loaded, remaining = whole budget
        assert remaining >= 0

        budget_rejects = [
            r for r in meta["rejects"] if r.get("reason") == "budget_exceeded"
        ]
        assert budget_rejects
        # tokens of the huge result must exceed the whole budget
        assert budget_rejects[0]["tokens"] > budget


# ---------------------------------------------------------------------------
# Per-source ledger
# ---------------------------------------------------------------------------


class TestPerSourceLedger:
    """Per-source ledger accumulation in meta['per_source']."""

    def test_per_source_present_in_meta(self):
        """meta['per_source'] is present when return_meta=True."""
        results = [_r("a", "content here", 0.9)]
        _, _, meta = select_results_greedy(results, budget=10_000, return_meta=True)
        assert "per_source" in meta
        assert isinstance(meta["per_source"], dict)

    def test_per_source_absent_when_return_meta_false(self):
        """return_meta=False preserves legacy 2-tuple (no per_source leak)."""
        results = [_r("a", "content here", 0.9)]
        out = select_results_greedy(results, budget=10_000)
        assert len(out) == 2

    def test_per_source_tracks_loaded_tokens(self):
        """loaded_tokens in per_source matches what was actually selected."""
        content = "selected content word " * 20
        results = [_r("a", content, 0.9, "decision", "discussions")]
        _selected, tokens_used, meta = select_results_greedy(
            results, budget=10_000, return_meta=True
        )
        ps = meta["per_source"]
        assert "discussions" in ps
        assert ps["discussions"]["loaded_tokens"] == tokens_used

    def test_per_source_reconciles_budget_drops(self):
        """loaded_tokens + dropped["budget_exceeded"]["tokens"] == requested_tokens."""
        content_a = "first content word " * 20  # moderate size, fits
        content_b = "second content word " * 500  # large, budget_exceeded

        results = [
            _r("a", content_a, 0.9, "decision", "discussions"),
            _r("b", content_b, 0.85, "session", "discussions"),
        ]
        budget = 200  # enough for a, not b

        _selected, _tokens_used, meta = select_results_greedy(
            results, budget=budget, return_meta=True
        )
        ps = meta["per_source"]
        assert "discussions" in ps
        src = ps["discussions"]

        loaded = src["loaded_tokens"]
        budget_dropped_tokens = (
            src["dropped"].get("budget_exceeded", {}).get("tokens", 0)
        )
        requested = src["requested_tokens"]

        assert loaded + budget_dropped_tokens == requested, (
            f"Reconciliation failed: loaded={loaded} + budget_dropped={budget_dropped_tokens} "
            f"!= requested={requested}"
        )

    def test_per_source_dropped_counts_by_reason(self):
        """dropped dict contains per-reason counts for early-drop reasons."""
        results = [
            _r("x", "excluded content here", 0.9, "decision", "discussions"),
            _r("a", "real content alpha", 0.85, "decision", "discussions"),
        ]
        _selected, _tokens, meta = select_results_greedy(
            results, budget=10_000, excluded_ids=["x"], return_meta=True
        )
        ps = meta["per_source"]
        assert "discussions" in ps
        src = ps["discussions"]
        assert "already_injected" in src["dropped"]
        assert src["dropped"]["already_injected"]["count"] == 1

    def test_per_source_no_entry_when_no_results(self):
        """Empty results list produces empty per_source."""
        _selected, _tokens, meta = select_results_greedy(
            [], budget=10_000, return_meta=True
        )
        assert meta["per_source"] == {}


# ---------------------------------------------------------------------------
# Realistic multi-source fixture (≥3 collections, ≥1 over-budget drop)
# ---------------------------------------------------------------------------


def _make_multi_source_fixture():
    """Build a realistic multi-source fixture across 3 collections.

    discussions: 2 moderate results + 1 large result (over budget)
    code-patterns: 2 small results
    conventions: 1 small result
    """
    small = "word " * 50  # ~50 tokens
    medium = "word " * 100  # ~100 tokens
    large = "word " * 600  # ~600 tokens (forces budget_exceeded at tight budgets)

    return [
        _r("d1", medium, 0.92, "decision", "discussions"),
        _r("d2", medium, 0.88, "session", "discussions"),
        _r("d3", large, 0.86, "agent_handoff", "discussions"),
        _r("c1", small, 0.84, "code_pattern", "code-patterns"),
        _r("c2", small, 0.82, "code_pattern", "code-patterns"),
        _r("v1", small, 0.80, "guideline", "conventions"),
    ]


class TestRealisticMultiSourceFixture:
    """Realistic-size, multi-source tests (≥3 collections, ≥1 over-budget drop)."""

    def test_per_source_has_three_collections(self):
        """per_source covers all 3 collections in the fixture."""
        results = _make_multi_source_fixture()
        budget = 600  # tight: d3 (large) will be budget_exceeded
        _selected, _tokens, meta = select_results_greedy(
            results, budget=budget, return_meta=True, tier=2
        )
        ps = meta["per_source"]
        assert "discussions" in ps
        assert "code-patterns" in ps
        assert "conventions" in ps

    def test_at_least_one_budget_drop_in_fixture(self):
        """≥1 budget_exceeded drop occurs in the realistic fixture."""
        results = _make_multi_source_fixture()
        budget = 400  # small enough to force at least one budget_exceeded
        _selected, _tokens, meta = select_results_greedy(
            results, budget=budget, return_meta=True, tier=2
        )
        all_reasons = [r["reason"] for r in meta["rejects"]]
        assert "budget_exceeded" in all_reasons

    def test_reconciliation_all_collections(self):
        """Reconciliation holds for every collection in the realistic fixture."""
        results = _make_multi_source_fixture()
        budget = 500
        _selected, _tokens, meta = select_results_greedy(
            results, budget=budget, return_meta=True, tier=2
        )
        ps = meta["per_source"]
        for coll, src in ps.items():
            loaded = src["loaded_tokens"]
            budget_dropped = src["dropped"].get("budget_exceeded", {}).get("tokens", 0)
            requested = src["requested_tokens"]
            assert loaded + budget_dropped == requested, (
                f"Collection '{coll}': "
                f"loaded={loaded} + budget_dropped={budget_dropped} != requested={requested}"
            )

    def test_behavior_unchanged(self):
        """BEHAVIOR-UNCHANGED proof: selected IDs and tokens_used identical pre/post.

        Proves the per-source ledger is observe-only.
        """
        results = _make_multi_source_fixture()
        budget = 500

        # Legacy path (return_meta=False)
        selected_legacy, tokens_legacy = select_results_greedy(
            list(results), budget=budget, tier=2
        )

        # New ledger path (return_meta=True)
        selected_new, tokens_new, _meta = select_results_greedy(
            list(results), budget=budget, tier=2, return_meta=True
        )

        assert [r["id"] for r in selected_legacy] == [
            r["id"] for r in selected_new
        ], "selected IDs differ between legacy path and ledger path"
        assert (
            tokens_legacy == tokens_new
        ), f"tokens_used differs: legacy={tokens_legacy} new={tokens_new}"

    def test_per_source_written_to_log_jsonl(self, tmp_path):
        """per_source is written to injection-log.jsonl by log_injection_event."""
        results = _make_multi_source_fixture()
        budget = 500
        _selected, tokens_used, meta = select_results_greedy(
            results, budget=budget, tier=2, return_meta=True
        )
        log_injection_event(
            tier=2,
            trigger="UserPromptSubmit",
            project="test-proj",
            session_id="test-sess",
            results_considered=len(results),
            results_selected=len(_selected),
            tokens_used=tokens_used,
            budget=budget,
            audit_dir=tmp_path,
            per_source=meta.get("per_source"),
        )
        log_path = tmp_path / "logs" / "injection-log.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert "per_source" in entry
        # All 3 collections present in the log entry
        assert "discussions" in entry["per_source"]
        assert "code-patterns" in entry["per_source"]
        assert "conventions" in entry["per_source"]


# ---------------------------------------------------------------------------
# log_injection_event backward compatibility
# ---------------------------------------------------------------------------


class TestLogInjectionEventPerSource:
    """per_source param is backward-compatible when omitted."""

    def test_per_source_defaults_to_empty_dict(self, tmp_path):
        """Omitting per_source writes empty dict — no crash for existing callers."""
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
        log_path = tmp_path / "logs" / "injection-log.jsonl"
        entry = json.loads(log_path.read_text().strip())
        assert entry.get("per_source") == {}

    def test_per_source_written_when_provided(self, tmp_path):
        """Explicit per_source value is written to the log entry."""
        ps = {
            "discussions": {
                "requested_tokens": 200,
                "loaded_tokens": 150,
                "dropped": {"budget_exceeded": {"count": 1, "tokens": 50}},
            }
        }
        log_injection_event(
            tier=2,
            trigger="UserPromptSubmit",
            project="proj",
            session_id="sess",
            results_considered=2,
            results_selected=1,
            tokens_used=150,
            budget=200,
            audit_dir=tmp_path,
            per_source=ps,
        )
        log_path = tmp_path / "logs" / "injection-log.jsonl"
        entry = json.loads(log_path.read_text().strip())
        assert entry["per_source"] == ps
