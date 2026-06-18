"""PM #343 — BUG-319 (F-1/F-2/F-3) + BUG-302 (F-5) absolute-relevance gate tests.

Covers the BP-174 absolute-relevance injection gate that fixes the F-1 root cause:
the hybrid_rrf_decay path min-max-normalizes RRF scores to a [0.5, 0.95] band per
result-set, so the banded top-1 is always ~0.95 and the per-collection confidence
gate can never skip same-domain-off-topic content in a single-domain store.

- F-1 (Q1): ``MemorySearch._attach_raw_cosine`` carries an absolute raw-cosine
  signal alongside the banded score; the gate consumes raw_score, not the band.
- F-1 (Q2): ``compute_relevance_signals`` applies a store-baseline floor + the
  scale-free top-1/top-2 margin so a banded-0.95 same-domain-off-topic top-1 is
  gated out.
- F-2 (Q4): the freshness cap gates a stale top-1 out (distinct from DECAY_*).
- F-3 (Q3): ``compute_adaptive_budget`` makes topic drift a suppressor — high
  drift + no above-floor candidate no longer amplifies the budget.
- F-5 (BUG-302): the budget_exceeded reject record carries the reject-time
  ``remaining`` snapshot so the tier-2 marker renders the value that actually
  triggered the reject (not the post-loop final remaining).

The gate only changes behavior when ``injection_absolute_gate_enabled`` is True;
the signals are computed shadow-only otherwise. Tests target the pure decision
surfaces the tier-2 hook consumes, on production-size fixtures.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from memory.chunking.truncation import count_tokens
from memory.injection import (
    compute_adaptive_budget,
    compute_relevance_signals,
    select_results_greedy,
)
from memory.search import MemorySearch

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _gate_config(
    *,
    floor=0.78,
    margin_min=0.05,
    max_age_days=0,
    enabled=True,
    drift_suppressor=0.5,
):
    """Minimal config namespace carrying just the gate fields under test."""
    return SimpleNamespace(
        injection_absolute_gate_enabled=enabled,
        injection_absolute_floor=floor,
        injection_margin_min=margin_min,
        injection_freshness_max_age_days=max_age_days,
        injection_drift_suppressor_threshold=drift_suppressor,
    )


def _budget_config(**overrides):
    cfg = SimpleNamespace(
        injection_budget_floor=500,
        injection_budget_ceiling=1500,
        injection_confidence_threshold=0.6,
        injection_quality_weight=0.5,
        injection_density_weight=0.3,
        injection_drift_weight=0.2,
        injection_absolute_gate_enabled=True,
        injection_absolute_floor=0.78,
        injection_drift_suppressor_threshold=0.5,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _now():
    return datetime(2026, 6, 17, tzinfo=timezone.utc)


def _result(banded, raw, *, age_days=1, type_="decision", collection="discussions"):
    stored_at = (_now() - timedelta(days=age_days)).isoformat().replace("+00:00", "Z")
    return {
        "id": f"p-{banded}-{raw}-{age_days}",
        "content": "single-domain AI Memory internals content",
        "score": banded,
        "raw_score": raw,
        "type": type_,
        "collection": collection,
        "stored_at": stored_at,
    }


# ---------------------------------------------------------------------------
# F-1 (Q1): _attach_raw_cosine — absolute channel separate from banded score
# ---------------------------------------------------------------------------


class TestAttachRawCosine:
    def _search(self):
        # Skip __init__ (heavy deps); _attach_raw_cosine only touches self.client.
        return MemorySearch.__new__(MemorySearch)

    def test_dense_mode_copies_score_as_raw(self):
        s = self._search()
        s.client = None  # not used on the dense branch
        memories = [{"id": "a", "score": 0.81}, {"id": "b", "score": 0.42}]
        s._attach_raw_cosine(
            memories,
            search_mode="dense",
            collection="discussions",
            query_embedding=[0.1] * 768,
            query_filter=None,
            search_params=None,
        )
        assert memories[0]["raw_score"] == 0.81
        assert memories[1]["raw_score"] == 0.42

    def test_hybrid_mode_attaches_dense_cosine_not_banded(self):
        """The banded score is pinned near 0.95; raw_score must reflect the
        separate dense query — proving the gate input is decoupled from the band.
        """
        s = self._search()

        class _Pt:
            def __init__(self, id_, score):
                self.id = id_
                self.score = score

        resp = SimpleNamespace(points=[_Pt("a", 0.86), _Pt("b", 0.71)])
        s.client = SimpleNamespace(query_points=lambda **kw: resp)

        # Banded scores (post min-max) are both high; raw cosines spread.
        memories = [{"id": "a", "score": 0.95}, {"id": "b", "score": 0.50}]
        s._attach_raw_cosine(
            memories,
            search_mode="hybrid_rrf_decay",
            collection="discussions",
            query_embedding=[0.1] * 768,
            query_filter=None,
            search_params=None,
        )
        assert memories[0]["raw_score"] == 0.86
        assert memories[1]["raw_score"] == 0.71
        # Banded score untouched (ordering/display only).
        assert memories[0]["score"] == 0.95

    def test_missing_from_dense_neighborhood_gets_zero(self):
        s = self._search()
        resp = SimpleNamespace(points=[SimpleNamespace(id="a", score=0.80)])
        s.client = SimpleNamespace(query_points=lambda **kw: resp)
        memories = [{"id": "a", "score": 0.95}, {"id": "sparse-only", "score": 0.90}]
        s._attach_raw_cosine(
            memories,
            search_mode="hybrid_rrf_decay",
            collection="discussions",
            query_embedding=[0.1] * 768,
            query_filter=None,
            search_params=None,
        )
        assert memories[0]["raw_score"] == 0.80
        assert memories[1]["raw_score"] == 0.0  # top-by-rank, no dense neighbor

    def test_raw_query_failure_degrades_to_zero(self):
        s = self._search()

        def _boom(**kw):
            raise RuntimeError("qdrant down")

        s.client = SimpleNamespace(query_points=_boom)
        memories = [{"id": "a", "score": 0.95}]
        s._attach_raw_cosine(
            memories,
            search_mode="hybrid_rrf_decay",
            collection="discussions",
            query_embedding=[0.1] * 768,
            query_filter=None,
            search_params=None,
        )
        assert memories[0]["raw_score"] == 0.0


# ---------------------------------------------------------------------------
# F-1 (Q2): compute_relevance_signals — floor + margin discrimination
# ---------------------------------------------------------------------------


class TestRelevanceSignals:
    def test_on_topic_passes(self):
        cfg = _gate_config()
        results = [_result(0.95, 0.86), _result(0.90, 0.74)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["floor_pass"] is True
        assert sig["margin_pass"] is True
        assert sig["would_inject"] is True

    def test_same_domain_off_topic_blocked_despite_banded_095(self):
        """The F-1 reproducer: banded top-1 is 0.95 (would clear every
        per-collection threshold) but every raw cosine is below the floor, so the
        absolute gate correctly injects nothing."""
        cfg = _gate_config(floor=0.78)
        results = [_result(0.95, 0.745), _result(0.90, 0.74), _result(0.85, 0.73)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["best_raw"] == 0.745
        assert sig["floor_pass"] is False
        assert sig["would_inject"] is False

    def test_tiny_margin_blocked(self):
        """High top-1 with a tiny gap to top-2 is an ambiguous/distractor
        retrieval regardless of the absolute number (Q2 margin gate)."""
        cfg = _gate_config(floor=0.78, margin_min=0.05)
        results = [_result(0.95, 0.90), _result(0.92, 0.88)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["floor_pass"] is True
        assert sig["margin"] == pytest.approx(0.02, abs=1e-6)
        assert sig["margin_pass"] is False
        assert sig["would_inject"] is False

    def test_single_result_bypasses_margin(self):
        cfg = _gate_config(floor=0.78)
        results = [_result(0.95, 0.85)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["margin_pass"] is True
        assert sig["would_inject"] is True

    def test_empty_results(self):
        cfg = _gate_config()
        sig = compute_relevance_signals([], cfg, now=_now())
        assert sig["best_raw"] == 0.0
        assert sig["would_inject"] is False


# ---------------------------------------------------------------------------
# F-2 (Q4): freshness cap gates a stale top-1
# ---------------------------------------------------------------------------


class TestFreshnessGate:
    def test_stale_top1_blocked_when_cap_enabled(self):
        cfg = _gate_config(floor=0.78, max_age_days=45)
        # Otherwise-injectable: high raw, good margin — but top-1 is 60 days old.
        results = [_result(0.95, 0.88, age_days=60), _result(0.90, 0.74, age_days=2)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["floor_pass"] is True
        assert sig["margin_pass"] is True
        assert sig["top_age_days"] == pytest.approx(60.0, abs=0.01)
        assert sig["freshness_pass"] is False
        assert sig["would_inject"] is False

    def test_fresh_top1_passes_with_cap(self):
        cfg = _gate_config(floor=0.78, max_age_days=45)
        results = [_result(0.95, 0.88, age_days=10), _result(0.90, 0.74)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["freshness_pass"] is True
        assert sig["would_inject"] is True

    def test_cap_disabled_ignores_age(self):
        cfg = _gate_config(floor=0.78, max_age_days=0)
        results = [_result(0.95, 0.88, age_days=400), _result(0.90, 0.74)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["freshness_pass"] is True
        assert sig["would_inject"] is True

    def test_missing_stored_at_does_not_block(self):
        cfg = _gate_config(floor=0.78, max_age_days=45)
        r = _result(0.95, 0.88)
        r.pop("stored_at")
        sig = compute_relevance_signals([r, _result(0.90, 0.74)], cfg, now=_now())
        assert sig["top_age_days"] is None
        assert sig["freshness_pass"] is True


# ---------------------------------------------------------------------------
# F-3 (Q3): drift is a suppressor, not a budget amplifier
# ---------------------------------------------------------------------------


class TestDriftSuppressor:
    def test_high_drift_below_floor_does_not_amplify(self):
        """Gate enabled + below-floor best raw + high drift → drift contribution
        is zeroed, so the budget does not grow on an off-topic pivot."""
        cfg = _budget_config(injection_absolute_gate_enabled=True)
        results = [{"score": 0.95}]
        high_drift = {"topic_drift": 1.0}
        suppressed = compute_adaptive_budget(
            best_score=0.95,
            results=results,
            session_state=high_drift,
            config=cfg,
            best_raw_score=0.50,  # below floor 0.78
        )
        # Legacy comparison: same inputs with the gate OFF (drift amplifies).
        cfg_off = _budget_config(injection_absolute_gate_enabled=False)
        legacy = compute_adaptive_budget(
            best_score=0.95,
            results=results,
            session_state=high_drift,
            config=cfg_off,
            best_raw_score=0.50,
        )
        assert suppressed < legacy

    def test_above_floor_keeps_amplification(self):
        cfg = _budget_config(injection_absolute_gate_enabled=True)
        results = [{"score": 0.95}]
        high_drift = {"topic_drift": 1.0}
        gated = compute_adaptive_budget(
            best_score=0.95,
            results=results,
            session_state=high_drift,
            config=cfg,
            best_raw_score=0.90,  # above floor → drift still amplifies
        )
        cfg_off = _budget_config(injection_absolute_gate_enabled=False)
        legacy = compute_adaptive_budget(
            best_score=0.95,
            results=results,
            session_state=high_drift,
            config=cfg_off,
            best_raw_score=0.90,
        )
        assert gated == legacy

    def test_legacy_behavior_when_raw_score_absent(self):
        cfg = _budget_config(injection_absolute_gate_enabled=True)
        results = [{"score": 0.95}]
        gated = compute_adaptive_budget(
            best_score=0.95,
            results=results,
            session_state={"topic_drift": 1.0},
            config=cfg,
        )
        cfg_off = _budget_config(injection_absolute_gate_enabled=False)
        legacy = compute_adaptive_budget(
            best_score=0.95,
            results=results,
            session_state={"topic_drift": 1.0},
            config=cfg_off,
        )
        assert gated == legacy


# ---------------------------------------------------------------------------
# Production-size discrimination: banded ~0.95 vs absolute raw spread
# ---------------------------------------------------------------------------


class TestProductionSizeDiscrimination:
    def _banded_band(self, n):
        """Mimic search.py min-max: top→0.95, worst→0.5 across n results."""
        if n == 1:
            return [0.75]
        return [round(0.95 - (0.45 * i / (n - 1)), 4) for i in range(n)]

    def test_off_topic_set_all_banded_high_but_gate_skips(self):
        cfg = _gate_config(floor=0.78, margin_min=0.05)
        bands = self._banded_band(12)
        # Single-domain off-topic neighborhood: raw cosines cluster ~0.72-0.75,
        # all below the 0.78 store baseline floor.
        raws = [
            0.75,
            0.745,
            0.74,
            0.738,
            0.735,
            0.73,
            0.728,
            0.725,
            0.72,
            0.71,
            0.70,
            0.69,
        ]
        results = [_result(b, r) for b, r in zip(bands, raws, strict=False)]
        # The banded gate would inject (top banded 0.95 clears any threshold)...
        assert results[0]["score"] == 0.95
        # ...but the absolute gate skips: no candidate clears the floor.
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["floor_pass"] is False
        assert sig["would_inject"] is False

    def test_on_topic_present_in_large_set_injects(self):
        cfg = _gate_config(floor=0.78, margin_min=0.05)
        bands = self._banded_band(12)
        # One genuinely on-topic item (0.87) above a same-domain tail (~0.72).
        raws = [
            0.87,
            0.73,
            0.728,
            0.725,
            0.72,
            0.718,
            0.715,
            0.71,
            0.705,
            0.70,
            0.69,
            0.68,
        ]
        results = [_result(b, r) for b, r in zip(bands, raws, strict=False)]
        sig = compute_relevance_signals(results, cfg, now=_now())
        assert sig["best_raw"] == 0.87
        assert sig["floor_pass"] is True
        assert sig["margin"] >= 0.05
        assert sig["would_inject"] is True


# ---------------------------------------------------------------------------
# F-5 (BUG-302): reject record carries reject-time remaining snapshot
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _silence_observability(monkeypatch):
    monkeypatch.setattr("memory.injection.emit_trace_event", None, raising=False)
    import memory.metrics_push as _mpush

    monkeypatch.setattr(
        _mpush, "push_retrieval_reject_metric_async", lambda *a, **k: None
    )


class TestBug302RejectTimeRemaining:
    def test_remaining_is_reject_time_not_final(self):
        """The case the post-loop formula gets wrong: a smaller item loads AFTER
        the over-budget reject (greedy skip-and-continue), so the final remaining
        is smaller than the remaining that actually triggered the reject. The
        reject record must carry the reject-time snapshot."""
        big_content = "word " * 60  # loads first
        handoff_content = "word " * 40  # rejected (doesn't fit)
        small_content = "word " * 8  # loads AFTER the reject

        t_big = count_tokens(big_content)
        t_handoff = count_tokens(handoff_content)
        t_small = count_tokens(small_content)

        # Budget fits big + small but NOT big + handoff. handoff > small ensures
        # the handoff is rejected while the trailing small item still fits.
        budget = t_big + t_small + 1
        assert t_handoff > t_small  # precondition

        results = [
            {
                "id": "big",
                "content": big_content,
                "score": 0.95,
                "type": "session",
                "collection": "discussions",
            },
            {
                "id": "h",
                "content": handoff_content,
                "score": 0.90,
                "type": "agent_handoff",
                "collection": "discussions",
            },
            {
                "id": "small",
                "content": small_content,
                "score": 0.85,
                "type": "decision",
                "collection": "discussions",
            },
        ]

        _selected, tokens_used, meta = select_results_greedy(
            results, budget=budget, return_meta=True, tier=2
        )

        rej = next(r for r in meta["rejects"] if r["reason"] == "budget_exceeded")
        reject_time_remaining = budget - t_big  # free budget when handoff evaluated
        final_remaining = budget - tokens_used

        # The snapshot is the reject-time value, which differs from final remaining
        # because the small item loaded afterwards.
        assert rej["remaining"] == reject_time_remaining
        assert final_remaining < reject_time_remaining
        # Self-evident: the rejected candidate is larger than what was free.
        assert rej["tokens"] > rej["remaining"]

    def test_non_budget_rejects_have_no_remaining(self):
        results = [
            {
                "id": "a",
                "content": "dup",
                "score": 0.9,
                "type": "decision",
                "collection": "discussions",
            },
            {
                "id": "b",
                "content": "dup",
                "score": 0.9,
                "type": "decision",
                "collection": "discussions",
            },
        ]
        _sel, _tok, meta = select_results_greedy(
            results, budget=10_000, return_meta=True, tier=2
        )
        dedup = [r for r in meta["rejects"] if r["reason"] == "dedup"]
        assert dedup
        assert "remaining" not in dedup[0]
