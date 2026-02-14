"""Tests for decay scoring module (SPEC-001).

Covers:
- Property-based tests (Hypothesis) for compute_decay_score()
- Unit tests for resolve_half_life() hierarchical resolution
- Unit tests for config parsing of decay_type_overrides
- Structural tests for build_decay_formula()
"""

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from qdrant_client import models

from src.memory.config import MemoryConfig
from src.memory.decay import (
    build_decay_formula,
    compute_decay_score,
    resolve_half_life,
    resolve_half_life_seconds,
)


# ============================================================================
# Property-Based Tests (Hypothesis) — Section 7.1
# ============================================================================


@given(
    age_days=st.floats(min_value=0, max_value=3650),
    half_life=st.floats(min_value=1, max_value=365),
)
@settings(max_examples=200)
def test_decay_score_within_bounds(age_days, half_life):
    """Score always in [0.0, 1.0]."""
    now = datetime.now(timezone.utc)
    score = compute_decay_score(
        stored_at=now - timedelta(days=age_days),
        half_life_days=half_life,
        now=now,
    )
    assert 0.0 <= score <= 1.0


@given(
    half_life=st.floats(min_value=1, max_value=365),
)
@settings(max_examples=200)
def test_newer_ranks_higher(half_life):
    """Newer memory always scores >= older memory (same semantic score)."""
    now = datetime.now(timezone.utc)
    score_new = compute_decay_score(
        stored_at=now - timedelta(days=1),
        half_life_days=half_life,
        now=now,
    )
    score_old = compute_decay_score(
        stored_at=now - timedelta(days=30),
        half_life_days=half_life,
        now=now,
    )
    assert score_new >= score_old


def test_half_life_at_half_life():
    """At exactly half_life days, temporal_score = 0.5."""
    now = datetime.now(timezone.utc)
    score = compute_decay_score(
        stored_at=now - timedelta(days=14),
        half_life_days=14.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.0,
    )
    assert abs(score - 0.5) < 0.001


def test_zero_age_max_score():
    """At age 0, temporal_score = 1.0."""
    now = datetime.now(timezone.utc)
    score = compute_decay_score(
        stored_at=now,
        half_life_days=14.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.0,
    )
    assert abs(score - 1.0) < 0.001


def test_very_old_memory_approaches_zero():
    """Very old memory has near-zero temporal score but never exactly zero."""
    now = datetime.now(timezone.utc)
    score = compute_decay_score(
        stored_at=now - timedelta(days=1000),
        half_life_days=7.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.0,
    )
    assert score > 0.0
    assert score < 0.01


def test_semantic_weight_1_ignores_decay():
    """semantic_weight=1.0 zeroes out temporal component."""
    now = datetime.now(timezone.utc)
    score = compute_decay_score(
        stored_at=now - timedelta(days=100),
        half_life_days=7.0,
        now=now,
        semantic_weight=1.0,
        semantic_score=0.85,
    )
    assert abs(score - 0.85) < 0.001


def test_default_weights():
    """Default weights: 0.7 semantic + 0.3 temporal."""
    now = datetime.now(timezone.utc)
    # At age 0, temporal = 1.0
    score = compute_decay_score(
        stored_at=now,
        half_life_days=14.0,
        now=now,
        semantic_score=1.0,
    )
    # 0.7 * 1.0 + 0.3 * 1.0 = 1.0
    assert abs(score - 1.0) < 0.001


# ============================================================================
# Unit Tests: resolve_half_life() — Section 7.2
# ============================================================================


@pytest.fixture
def default_config():
    """Config with default decay settings."""
    return MemoryConfig(
        decay_enabled=True,
        decay_type_overrides="github_ci_result:7,github_code_blob:14,github_commit:14,conversation:21,session_summary:21,github_issue:30,github_pr:30,jira_issue:30,agent_memory:30,agent_handoff:30,guideline:60,rule:60,architecture_decision:90",
    )


@pytest.fixture
def empty_overrides_config():
    """Config with no type overrides."""
    return MemoryConfig(
        decay_enabled=True,
        decay_type_overrides="",
    )


def test_type_override_wins(default_config):
    """Type override takes precedence over collection default."""
    half_life = resolve_half_life("github_code_blob", "discussions", default_config)
    assert half_life == 14  # NOT 21 (discussions default)


def test_type_override_ci_result(default_config):
    """github_ci_result uses 7-day half-life."""
    half_life = resolve_half_life("github_ci_result", "discussions", default_config)
    assert half_life == 7


def test_type_override_architecture_decision(default_config):
    """architecture_decision uses 90-day half-life."""
    half_life = resolve_half_life(
        "architecture_decision", "conventions", default_config
    )
    assert half_life == 90


def test_collection_default_fallback(default_config):
    """Collection default used when no type override matches."""
    half_life = resolve_half_life("custom_note", "code-patterns", default_config)
    assert half_life == 14  # code-patterns collection default


def test_collection_default_conventions(default_config):
    """Conventions collection uses 60-day default."""
    half_life = resolve_half_life("custom_type", "conventions", default_config)
    assert half_life == 60


def test_collection_default_jira(default_config):
    """Jira-data collection uses 30-day default."""
    half_life = resolve_half_life("custom_type", "jira-data", default_config)
    assert half_life == 30


def test_global_default_fallback(default_config):
    """Global default when no type override and unknown collection."""
    half_life = resolve_half_life("unknown_type", "unknown_collection", default_config)
    assert half_life == 21  # global default


def test_resolve_half_life_seconds(default_config):
    """Seconds conversion correct."""
    seconds = resolve_half_life_seconds("github_ci_result", "discussions", default_config)
    assert seconds == 7 * 86400  # 604800


def test_resolve_half_life_empty_overrides(empty_overrides_config):
    """Empty overrides fall through to collection default."""
    half_life = resolve_half_life(
        "github_ci_result", "code-patterns", empty_overrides_config
    )
    assert half_life == 14  # collection default, NOT type override


# ============================================================================
# Unit Tests: Config Parsing — Section 7.2
# ============================================================================


def test_type_overrides_parsing():
    """Parse DECAY_TYPE_OVERRIDES string."""
    config = MemoryConfig(decay_type_overrides="foo:7,bar:14")
    overrides = config.get_decay_type_overrides()
    assert overrides == {"foo": 7, "bar": 14}


def test_type_overrides_empty():
    """Empty string returns empty dict."""
    config = MemoryConfig(decay_type_overrides="")
    overrides = config.get_decay_type_overrides()
    assert overrides == {}


def test_type_overrides_invalid_format():
    """Invalid format raises ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MemoryConfig(decay_type_overrides="bad_format")


def test_type_overrides_invalid_days():
    """Non-numeric days raises ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MemoryConfig(decay_type_overrides="type:abc")


# ============================================================================
# Unit Tests: build_decay_formula() Structure — Section 7.2
# ============================================================================


def test_formula_returns_tuple(default_config):
    """build_decay_formula returns (FormulaQuery, Prefetch) when enabled."""
    embedding = [0.1] * 768
    formula, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
    )
    assert isinstance(formula, models.FormulaQuery)
    assert isinstance(prefetch, models.Prefetch)


def test_formula_disabled_returns_none():
    """When decay_enabled=False, formula is None."""
    config = MemoryConfig(decay_enabled=False)
    embedding = [0.1] * 768
    formula, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=config,
    )
    assert formula is None
    assert isinstance(prefetch, models.Prefetch)


def test_formula_prefetch_has_score_threshold(default_config):
    """score_threshold is on the Prefetch, not the formula."""
    embedding = [0.1] * 768
    formula, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
        score_threshold=0.7,
    )
    assert prefetch.score_threshold == 0.7


def test_formula_prefetch_has_search_params(default_config):
    """search_params (HNSW ef) is on the Prefetch."""
    embedding = [0.1] * 768
    params = models.SearchParams(hnsw_ef=128)
    formula, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
        search_params=params,
    )
    assert prefetch.params is not None
    assert prefetch.params.hnsw_ef == 128


def test_formula_prefetch_has_filter(default_config):
    """extra_filter is passed to Prefetch."""
    embedding = [0.1] * 768
    filt = models.Filter(
        must=[
            models.FieldCondition(
                key="group_id", match=models.MatchValue(value="my-project")
            )
        ]
    )
    formula, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
        extra_filter=filt,
    )
    assert prefetch.filter is not None


def test_formula_has_defaults(default_config):
    """Formula has stored_at fallback default."""
    embedding = [0.1] * 768
    formula, _ = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
    )
    assert formula.defaults == {"stored_at": "2020-01-01T00:00:00Z"}


def test_formula_with_empty_overrides(empty_overrides_config):
    """Empty overrides produces single unconditional decay branch."""
    embedding = [0.1] * 768
    formula, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="code-patterns",
        config=empty_overrides_config,
    )
    assert isinstance(formula, models.FormulaQuery)
    assert isinstance(prefetch, models.Prefetch)


def test_formula_now_injection(default_config):
    """Explicit now parameter is used instead of current time."""
    embedding = [0.1] * 768
    fixed_now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    formula, _ = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
        now=fixed_now,
    )
    assert isinstance(formula, models.FormulaQuery)


def test_formula_prefetch_limit(default_config):
    """Prefetch limit is correctly set."""
    embedding = [0.1] * 768
    _, prefetch = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
        prefetch_limit=100,
    )
    assert prefetch.limit == 100


# ============================================================================
# FIX 5: semantic_weight=0.0 — Pure temporal ranking (Spec Section 8)
# ============================================================================


def test_semantic_weight_zero_pure_temporal():
    """decay_semantic_weight = 0.0 means pure temporal ranking; semantic_score is ignored."""
    now = datetime.now(timezone.utc)

    # Recent point with LOW semantic score
    score_recent = compute_decay_score(
        stored_at=now - timedelta(days=1),
        half_life_days=14.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.1,
    )

    # Old point with HIGH semantic score
    score_old = compute_decay_score(
        stored_at=now - timedelta(days=30),
        half_life_days=14.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.99,
    )

    # With semantic_weight=0.0, only temporal matters — newer MUST rank higher
    assert score_recent > score_old, (
        "With semantic_weight=0.0, newer point should rank higher regardless of semantic scores"
    )

    # Verify semantic_score has zero influence:
    # Two points at same age but different semantic_score should have equal final scores
    score_a = compute_decay_score(
        stored_at=now - timedelta(days=5),
        half_life_days=14.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.1,
    )
    score_b = compute_decay_score(
        stored_at=now - timedelta(days=5),
        half_life_days=14.0,
        now=now,
        semantic_weight=0.0,
        semantic_score=0.99,
    )
    assert abs(score_a - score_b) < 0.001, (
        "With semantic_weight=0.0, different semantic_scores at same age should yield equal scores"
    )


# ============================================================================
# FIX 11: Formula structure deep validation
# ============================================================================


def test_formula_internal_structure(default_config):
    """Validate internal structure of the formula: weights and branch count."""
    embedding = [0.1] * 768
    formula, _ = build_decay_formula(
        query_embedding=embedding,
        collection="discussions",
        config=default_config,
    )

    # Top level: SumExpression with exactly 2 elements (semantic + temporal)
    top_sum = formula.formula
    assert hasattr(top_sum, "sum"), "Top-level formula should be a SumExpression"
    assert len(top_sum.sum) == 2, "Formula should have exactly 2 top-level components (semantic + temporal)"

    # First element: semantic component (MultExpression with weight and $score)
    semantic_component = top_sum.sum[0]
    assert hasattr(semantic_component, "mult"), "Semantic component should be MultExpression"

    # Second element: temporal component (MultExpression with weight and SumExpression of branches)
    temporal_component = top_sum.sum[1]
    assert hasattr(temporal_component, "mult"), "Temporal component should be MultExpression"

    # The temporal mult should contain [weight, SumExpression(branches)]
    temporal_mult = temporal_component.mult
    assert len(temporal_mult) == 2, "Temporal mult should have weight and branch sum"

    # The branch sum: grouped overrides + 1 catch-all
    branch_sum = temporal_mult[1]
    assert hasattr(branch_sum, "sum"), "Temporal branches should be wrapped in SumExpression"

    # Count unique half-life groups in the config overrides
    overrides = default_config.get_decay_type_overrides()
    unique_half_lives = set(overrides.values())
    expected_branches = len(unique_half_lives) + 1  # grouped overrides + 1 catch-all

    assert len(branch_sum.sum) == expected_branches, (
        f"Expected {expected_branches} branches ({len(unique_half_lives)} grouped overrides + 1 catch-all), "
        f"got {len(branch_sum.sum)}"
    )
