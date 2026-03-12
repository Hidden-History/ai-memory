"""Unit tests for PLAN-015 Phase B WP-2: Tier 2 Injection Improvements.

Covers:
- Group 1: 4-tier per-collection gating thresholds (Spec §4.2.3)
- Group 2: Freshness penalty application logic (Spec §4.2.5, §4.5.3)
- Group 3: search.py exclude_expired_freshness parameter (Spec §4.5.3)
"""

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import FieldCondition, MatchValue

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    MemoryConfig,
)
from memory.search import MemorySearch


# =============================================================================
# Helpers
# =============================================================================


def _make_config(**overrides) -> MagicMock:
    """Create a mock MemoryConfig with WP-2 threshold fields."""
    cfg = MagicMock(spec=MemoryConfig)
    cfg.injection_hard_floor = 0.45
    cfg.injection_threshold_code_patterns = 0.55
    cfg.injection_threshold_discussions = 0.60
    cfg.injection_threshold_conventions = 0.65
    cfg.injection_confidence_threshold = 0.60  # fallback for unknown collections
    cfg.max_retrievals = 10
    cfg.similarity_threshold = 0.40
    cfg.hybrid_search_enabled = False
    cfg.decay_enabled = False
    cfg.hnsw_ef_fast = 64
    cfg.hnsw_ef_accurate = 128

    # Default penalty map used by Group 2 tests
    _penalties = {
        "fresh": 1.0,
        "aging": 0.9,
        "stale": 0.0,
        "expired": 0.0,
        "unverified": 1.0,
        "unknown": 0.8,
    }
    cfg.get_freshness_penalty.side_effect = lambda status: _penalties.get(status, 0.8)

    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_result(
    collection: str,
    score: float,
    freshness_status: str | None = None,
    rid: str = "test-id",
) -> dict:
    """Create a mock search result dict."""
    r: dict = {"id": rid, "score": score, "collection": collection, "content": "x"}
    if freshness_status is not None:
        r["freshness_status"] = freshness_status
    return r


def _compute_gating_mode(results: list[dict], config: MagicMock) -> str:
    """Replicate the 4-tier gating logic from context_injection_tier2.py."""
    best_score = results[0].get("score", 0) if results else 0.0
    _best_collection = results[0].get("collection") if results else None
    _threshold_map = {
        COLLECTION_CONVENTIONS: config.injection_threshold_conventions,
        COLLECTION_CODE_PATTERNS: config.injection_threshold_code_patterns,
        COLLECTION_DISCUSSIONS: config.injection_threshold_discussions,
    }
    _conf_threshold = _threshold_map.get(
        _best_collection, config.injection_confidence_threshold
    )

    if best_score < config.injection_hard_floor:
        return "hard_skip"
    elif best_score < _conf_threshold - 0.05:
        return "soft_skip"
    elif best_score < _conf_threshold:
        return "soft_gate"
    else:
        return "full"


def _apply_freshness_penalties(results: list[dict], config: MagicMock) -> int:
    """Replicate the freshness penalty loop from context_injection_tier2.py.

    Returns count of results blocked (penalty == 0.0 and original score > 0.0).
    Only results with a positive original score count as "blocked" — pre-existing
    0.0 scores were already excluded by other filters, not by freshness.
    """
    blocked_count = 0
    for r in results:
        if r.get("collection") != COLLECTION_CODE_PATTERNS:
            continue
        fs = (r.get("freshness_status") or "unverified").lower()
        penalty = config.get_freshness_penalty(fs)
        if penalty == 1.0:
            continue
        orig_score = r["score"]
        r["score"] = r["score"] * penalty
        if penalty == 0.0 and orig_score > 0.0:
            blocked_count += 1
    return blocked_count


# =============================================================================
# Group 1: 4-tier per-collection gating thresholds
# =============================================================================


class TestFourTierGating:
    """Validate 4-tier gating logic against per-collection thresholds."""

    def setup_method(self):
        self.config = _make_config()

    def test_hard_skip_below_floor(self):
        """Score < injection_hard_floor (0.45) → hard_skip regardless of collection."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.30)]
        assert _compute_gating_mode(results, self.config) == "hard_skip"

    def test_soft_skip_below_collection_threshold_minus_05(self):
        """Score < threshold-0.05 (0.55-0.05=0.50) → soft_skip for code-patterns."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.48)]
        assert _compute_gating_mode(results, self.config) == "soft_skip"

    def test_soft_gate_between_threshold_minus_05_and_threshold(self):
        """Score in [threshold-0.05, threshold) → soft_gate for code-patterns."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.52)]
        assert _compute_gating_mode(results, self.config) == "soft_gate"

    def test_full_at_or_above_threshold(self):
        """Score >= threshold (0.55) → full for code-patterns."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.60)]
        assert _compute_gating_mode(results, self.config) == "full"

    def test_soft_gate_conventions_between_range(self):
        """Score in [0.60, 0.65) → soft_gate for conventions (threshold=0.65)."""
        results = [_make_result(COLLECTION_CONVENTIONS, score=0.62)]
        assert _compute_gating_mode(results, self.config) == "soft_gate"

    def test_full_above_conventions_threshold(self):
        """Score >= 0.65 → full for conventions."""
        results = [_make_result(COLLECTION_CONVENTIONS, score=0.67)]
        assert _compute_gating_mode(results, self.config) == "full"

    def test_empty_results_returns_hard_skip(self):
        """Empty results list → best_score=0.0 → hard_skip."""
        assert _compute_gating_mode([], self.config) == "hard_skip"

    def test_discussions_threshold_used_for_discussions_collection(self):
        """discussions threshold (0.60) is used when best collection is discussions."""
        # Score exactly at threshold → full
        results = [_make_result(COLLECTION_DISCUSSIONS, score=0.60)]
        assert _compute_gating_mode(results, self.config) == "full"

    def test_discussions_soft_gate(self):
        """Score in [0.55, 0.60) → soft_gate for discussions (threshold=0.60)."""
        results = [_make_result(COLLECTION_DISCUSSIONS, score=0.57)]
        assert _compute_gating_mode(results, self.config) == "soft_gate"

    def test_fallback_threshold_for_unknown_collection(self):
        """Unknown collection falls back to injection_confidence_threshold (0.60)."""
        results = [_make_result("github", score=0.57)]
        # github not in threshold_map → fallback=0.60; 0.57 ∈ [0.55, 0.60) → soft_gate
        assert _compute_gating_mode(results, self.config) == "soft_gate"


# =============================================================================
# Group 2: Freshness penalty application
# =============================================================================


class TestFreshnessPenaltyApplication:
    """Validate freshness penalty logic applied to results before gating."""

    def setup_method(self):
        self.config = _make_config()

    def test_stale_code_pattern_score_set_to_zero(self):
        """code-patterns result with freshness_status=stale → score * 0.0 = 0."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.70, freshness_status="stale")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(0.0)

    def test_expired_code_pattern_score_set_to_zero(self):
        """code-patterns result with freshness_status=expired → score * 0.0 = 0."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.80, freshness_status="expired")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(0.0)

    def test_fresh_code_pattern_score_unchanged(self):
        """code-patterns result with freshness_status=fresh → penalty=1.0, no change."""
        original_score = 0.85
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=original_score, freshness_status="fresh")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(original_score)

    def test_unverified_code_pattern_score_unchanged(self):
        """code-patterns result with freshness_status=unverified → penalty=1.0, no change."""
        original_score = 0.75
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=original_score, freshness_status="unverified")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(original_score)

    def test_aging_code_pattern_score_multiplied_by_09(self):
        """code-patterns result with freshness_status=aging → score * 0.9."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.70, freshness_status="aging")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(0.70 * 0.9)

    def test_unknown_freshness_status_multiplied_by_08(self):
        """code-patterns result with freshness_status=unknown → score * 0.8."""
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=0.70, freshness_status="unknown")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(0.70 * 0.8)

    def test_none_freshness_status_treated_as_unverified(self):
        """code-patterns result with freshness_status=None → treated as 'unverified', unchanged."""
        original_score = 0.65
        results = [_make_result(COLLECTION_CODE_PATTERNS, score=original_score, freshness_status=None)]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(original_score)

    def test_conventions_stale_score_unchanged(self):
        """conventions result with freshness_status=stale → penalty NOT applied (wrong collection)."""
        original_score = 0.70
        results = [_make_result(COLLECTION_CONVENTIONS, score=original_score, freshness_status="stale")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(original_score)

    def test_discussions_stale_score_unchanged(self):
        """discussions result with freshness_status=stale → penalty NOT applied (wrong collection)."""
        original_score = 0.65
        results = [_make_result(COLLECTION_DISCUSSIONS, score=original_score, freshness_status="stale")]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(original_score)

    def test_blocked_count_incremented_for_zero_penalty(self):
        """stale and expired results (penalty=0.0) increment the blocked counter."""
        results = [
            _make_result(COLLECTION_CODE_PATTERNS, score=0.80, freshness_status="stale", rid="a"),
            _make_result(COLLECTION_CODE_PATTERNS, score=0.75, freshness_status="expired", rid="b"),
            _make_result(COLLECTION_CODE_PATTERNS, score=0.70, freshness_status="aging", rid="c"),
            _make_result(COLLECTION_CODE_PATTERNS, score=0.65, freshness_status="fresh", rid="d"),
        ]
        blocked = _apply_freshness_penalties(results, self.config)
        assert blocked == 2  # only stale and expired increment counter

    def test_mixed_collection_results_only_code_patterns_penalized(self):
        """Only code-patterns results are penalized; others are untouched."""
        cp_score = 0.80
        conv_score = 0.75
        disc_score = 0.70
        results = [
            _make_result(COLLECTION_CODE_PATTERNS, score=cp_score, freshness_status="stale", rid="cp"),
            _make_result(COLLECTION_CONVENTIONS, score=conv_score, freshness_status="stale", rid="conv"),
            _make_result(COLLECTION_DISCUSSIONS, score=disc_score, freshness_status="stale", rid="disc"),
        ]
        _apply_freshness_penalties(results, self.config)
        assert results[0]["score"] == pytest.approx(0.0)        # code-patterns penalized
        assert results[1]["score"] == pytest.approx(conv_score)  # unchanged
        assert results[2]["score"] == pytest.approx(disc_score)  # unchanged


# =============================================================================
# Group 3: search.py exclude_expired_freshness parameter
# =============================================================================


class TestSearchExcludeExpiredFreshness:
    """Validate exclude_expired_freshness filter is applied correctly in search()."""

    def _make_memory_search(self) -> MemorySearch:
        """Create a MemorySearch instance with all external clients mocked."""
        config = _make_config()
        config.hybrid_search_enabled = False
        config.decay_enabled = False
        config.hnsw_ef_fast = 64
        config.hnsw_ef_accurate = 128
        config.max_retrievals = 10
        config.similarity_threshold = 0.40

        search = MemorySearch.__new__(MemorySearch)
        search.config = config

        # Mock Qdrant client
        mock_qdrant = MagicMock()
        mock_response = MagicMock()
        mock_response.points = []
        mock_qdrant.query_points.return_value = mock_response
        search.client = mock_qdrant

        # Mock embedding client
        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [[0.0] * 768]
        search.embedding_client = mock_embedding

        return search

    def _get_must_not_conditions(self, search: MemorySearch, **kwargs) -> list:
        """Call search() and capture the Filter.must_not passed to Qdrant."""
        captured_filters: list = []

        original_query_points = search.client.query_points

        def capture_call(*args, **kw):
            # Capture the with_payload + query_filter from query_points or search calls
            # For plain dense path, it's passed via keyword 'query_filter'
            # For hybrid+decay it's inside prefetch. We inspect both.
            qf = kw.get("query_filter")
            if qf is not None:
                captured_filters.append(qf)
            return original_query_points(*args, **kw)

        search.client.query_points.side_effect = capture_call

        # Also patch search (qdrant legacy) calls
        search.client.search = MagicMock(return_value=[])

        try:
            search.search(**kwargs)
        except Exception:
            pass  # We only care about the filter captured, not the result

        return captured_filters

    def test_code_patterns_with_exclude_expired_adds_filter(self):
        """exclude_expired_freshness=True on code-patterns adds freshness_status='expired' must_not."""
        search = self._make_memory_search()
        captured = self._get_must_not_conditions(
            search,
            query="test query",
            collection=COLLECTION_CODE_PATTERNS,
            exclude_expired_freshness=True,
        )

        # Verify at least one query_points call was made with a filter
        assert len(captured) > 0, "No query_filter was captured from query_points call"
        qf = captured[0]
        must_not = qf.must_not or []
        freshness_conditions = [
            c
            for c in must_not
            if isinstance(c, FieldCondition)
            and c.key == "freshness_status"
            and hasattr(c.match, "value")
            and c.match.value == "expired"
        ]
        assert len(freshness_conditions) == 1, (
            f"Expected 1 freshness_status='expired' must_not condition, found {len(freshness_conditions)}. "
            f"must_not={must_not}"
        )

    def test_code_patterns_without_exclude_expired_no_filter(self):
        """exclude_expired_freshness=False on code-patterns does NOT add freshness filter."""
        search = self._make_memory_search()
        captured = self._get_must_not_conditions(
            search,
            query="test query",
            collection=COLLECTION_CODE_PATTERNS,
            exclude_expired_freshness=False,
        )

        # Either no filter at all, or filter has no freshness_status condition
        for qf in captured:
            must_not = qf.must_not or []
            freshness_conditions = [
                c
                for c in must_not
                if isinstance(c, FieldCondition) and c.key == "freshness_status"
            ]
            assert len(freshness_conditions) == 0, (
                "Expected no freshness_status must_not condition when "
                f"exclude_expired_freshness=False, found {freshness_conditions}"
            )

    def test_discussions_with_exclude_expired_no_filter_added(self):
        """exclude_expired_freshness=True on discussions does NOT add freshness filter (only code-patterns)."""
        search = self._make_memory_search()
        captured = self._get_must_not_conditions(
            search,
            query="test query",
            collection=COLLECTION_DISCUSSIONS,
            exclude_expired_freshness=True,
        )

        for qf in captured:
            must_not = qf.must_not or []
            freshness_conditions = [
                c
                for c in must_not
                if isinstance(c, FieldCondition) and c.key == "freshness_status"
            ]
            assert len(freshness_conditions) == 0, (
                "Expected no freshness_status filter for discussions collection, "
                f"found {freshness_conditions}"
            )

    def test_exclude_expired_default_is_false(self):
        """exclude_expired_freshness defaults to False — default call should not add filter."""
        search = self._make_memory_search()
        captured = self._get_must_not_conditions(
            search,
            query="test query",
            collection=COLLECTION_CODE_PATTERNS,
            # exclude_expired_freshness NOT passed → should default to False
        )

        for qf in captured:
            must_not = qf.must_not or []
            freshness_conditions = [
                c
                for c in must_not
                if isinstance(c, FieldCondition) and c.key == "freshness_status"
            ]
            assert len(freshness_conditions) == 0, (
                f"Default exclude_expired_freshness=False should not add filter. found {freshness_conditions}"
            )
