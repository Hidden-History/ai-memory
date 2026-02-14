"""Exponential decay scoring for temporal awareness in memory search.

Implements SPEC-001: time-aware ranking where newer memories score higher.
Different content types decay at different rates (code changes fast,
conventions change slowly). Decay is computed server-side by Qdrant's
Formula Query API -- zero additional latency, single round-trip.

Formula:
    final_score = (0.7 * semantic_similarity) + (0.3 * temporal_score)
    temporal_score = 0.5 ^ (age_in_days / half_life_days)

References:
    - SPEC-001-decay-scoring.md (PLAN-006)
    - BP-060 (Solving Freshness in RAG)
"""

from __future__ import annotations

from datetime import datetime, timezone

from qdrant_client import models

# Verify qdrant-client version supports FormulaQuery API
if not hasattr(models, "FormulaQuery"):
    raise ImportError(
        "qdrant-client >= 1.14.0 required for decay scoring. "
        "Run: pip install 'qdrant-client>=1.14.0'"
    )

from .config import MemoryConfig


def compute_decay_score(
    stored_at: datetime,
    half_life_days: float,
    now: datetime | None = None,
    semantic_weight: float = 0.7,
    semantic_score: float = 1.0,
) -> float:
    """Compute fused score with exponential decay.

    Pure function for testing and offline analysis. NOT used at query time
    (Qdrant computes decay natively via FormulaQuery).

    Args:
        stored_at: When the memory was stored (UTC).
        half_life_days: Days until temporal score reaches 0.5.
        now: Current time (UTC). Defaults to utcnow().
        semantic_weight: Weight for semantic component (0.0-1.0).
        semantic_score: Cosine similarity score (0.0-1.0).

    Returns:
        Fused score in range [0.0, 1.0].
    """
    if now is None:
        now = datetime.now(timezone.utc)

    age_days = max((now - stored_at).total_seconds() / 86400, 0.0)
    temporal_score = 0.5 ** (age_days / half_life_days)
    temporal_weight = 1.0 - semantic_weight

    return semantic_weight * semantic_score + temporal_weight * temporal_score


def resolve_half_life(
    content_type: str,
    collection: str,
    config: MemoryConfig,
) -> float:
    """Resolve half-life in days using hierarchical config.

    Resolution order:
        1. Type override (config.decay_type_overrides)
        2. Collection default (config.decay_half_life_* fields)
        3. Global default (21 days)

    Args:
        content_type: The memory's type field value.
        collection: The Qdrant collection name.
        config: MemoryConfig instance.

    Returns:
        Half-life in days.
    """
    # Level 1: Type override (most specific)
    overrides = config.get_decay_type_overrides()
    if content_type in overrides:
        return float(overrides[content_type])

    # Level 2: Collection default
    collection_defaults = {
        "code-patterns": config.decay_half_life_code_patterns,
        "discussions": config.decay_half_life_discussions,
        "conventions": config.decay_half_life_conventions,
        "jira-data": config.decay_half_life_jira_data,
    }
    if collection in collection_defaults:
        return float(collection_defaults[collection])

    # Level 3: Global default
    return 21.0


def resolve_half_life_seconds(
    content_type: str,
    collection: str,
    config: MemoryConfig,
) -> int:
    """Resolve half-life as seconds (for Qdrant scale parameter).

    Convenience wrapper. build_decay_formula() uses inline conversion
    for performance (avoids per-group function call overhead).
    """
    return int(resolve_half_life(content_type, collection, config) * 86400)


def build_decay_formula(
    query_embedding: list[float],
    collection: str,
    config: MemoryConfig,
    extra_filter: models.Filter | None = None,
    prefetch_limit: int = 50,
    now: datetime | None = None,
    score_threshold: float | None = None,
    search_params: models.SearchParams | None = None,
) -> tuple[models.FormulaQuery | None, models.Prefetch]:
    """Build Qdrant Formula Query with type-routed exponential decay.

    Returns (formula, prefetch) tuple for use with client.query_points().
    When decay is disabled, returns (None, prefetch) -- caller uses simple query.

    The formula structure:
        sum([
            mult(semantic_weight, $score),
            mult(temporal_weight, sum([
                mult(condition_typeA, exp_decay(scale_A)),
                mult(condition_typeB, exp_decay(scale_B)),
                ...
                mult(catch_all, exp_decay(collection_default)),
            ]))
        ])

    Each condition evaluates to 1.0 (match) or 0.0 (no match).
    Exactly one branch activates per candidate.

    Args:
        query_embedding: Dense vector for semantic search.
        collection: Qdrant collection name (determines default half-life).
        config: MemoryConfig instance with decay settings.
        extra_filter: Additional Qdrant filter conditions.
        prefetch_limit: Number of candidates for semantic pre-filtering.
        now: Current time (UTC). Defaults to utcnow().
        score_threshold: Semantic similarity threshold (applied at prefetch).
        search_params: HNSW ef tuning parameters (applied at prefetch).

    Returns:
        Tuple of (FormulaQuery or None, Prefetch).
    """
    # Build prefetch (always needed -- handles semantic search + filtering)
    prefetch = models.Prefetch(
        query=query_embedding,
        limit=prefetch_limit,
        filter=extra_filter,
        score_threshold=score_threshold,
        params=search_params,
    )

    # Decay disabled -- return None formula, caller uses simple query path
    if not config.decay_enabled:
        return None, prefetch

    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Parse type overrides and group by resolved half-life (seconds)
    overrides = config.get_decay_type_overrides()
    half_life_groups: dict[int, list[str]] = {}
    all_explicit_types: list[str] = []

    for content_type, days in overrides.items():
        hl_seconds = days * 86400
        if hl_seconds not in half_life_groups:
            half_life_groups[hl_seconds] = []
        half_life_groups[hl_seconds].append(content_type)
        all_explicit_types.append(content_type)

    # Build condition-gated branches for explicit type overrides
    decay_branches: list[models.MultExpression | models.ExpDecayExpression] = []
    for hl_seconds, type_list in sorted(half_life_groups.items()):
        branch = models.MultExpression(
            mult=[
                models.FieldCondition(
                    key="type",
                    match=models.MatchAny(any=type_list),
                ),
                models.ExpDecayExpression(
                    exp_decay=models.DecayParamsExpression(
                        x=models.DatetimeKeyExpression(datetime_key="stored_at"),
                        target=models.DatetimeExpression(datetime=now_iso),
                        scale=float(hl_seconds),
                        midpoint=0.5,
                    )
                ),
            ]
        )
        decay_branches.append(branch)

    # Catch-all branch: types NOT in overrides use collection default half-life.
    # Use synthetic type name that won't match any real override, falls through to collection default.
    # NOTE: Points with an ABSENT `type` field get temporal_score=0.0 (Qdrant treats
    # missing fields as non-matching for both MatchAny and MatchExcept). This differs
    # from unknown types which DO match MatchExcept and receive the collection default
    # half-life. The semantic component (0.7 * $score) still contributes for absent-type
    # points, so they are returned but ranked lower. See TestPointWithoutTypeField.
    default_hl_days = resolve_half_life("__catchall__", collection, config)
    default_hl_seconds = int(default_hl_days * 86400)

    if all_explicit_types:
        catch_all = models.MultExpression(
            mult=[
                models.FieldCondition(
                    key="type",
                    # MatchExcept's Pydantic field is a reserved keyword "except".
                # except_= kwarg is rejected by Pydantic; model_validate is required.
                match=models.MatchExcept.model_validate(
                    {"except": all_explicit_types}
                ),
                ),
                models.ExpDecayExpression(
                    exp_decay=models.DecayParamsExpression(
                        x=models.DatetimeKeyExpression(datetime_key="stored_at"),
                        target=models.DatetimeExpression(datetime=now_iso),
                        scale=float(default_hl_seconds),
                        midpoint=0.5,
                    )
                ),
            ]
        )
        decay_branches.append(catch_all)
    else:
        # No explicit overrides -- single unconditional decay using collection default
        unconditional = models.ExpDecayExpression(
            exp_decay=models.DecayParamsExpression(
                x=models.DatetimeKeyExpression(datetime_key="stored_at"),
                target=models.DatetimeExpression(datetime=now_iso),
                scale=float(default_hl_seconds),
                midpoint=0.5,
            )
        )
        decay_branches.append(unconditional)

    # Assemble formula: semantic + temporal components
    semantic_w = config.decay_semantic_weight
    temporal_w = 1.0 - semantic_w

    formula = models.FormulaQuery(
        formula=models.SumExpression(
            sum=[
                models.MultExpression(mult=[semantic_w, "$score"]),
                models.MultExpression(
                    mult=[
                        temporal_w,
                        models.SumExpression(sum=decay_branches),
                    ]
                ),
            ]
        ),
        # Fallback for points missing stored_at — arbitrary old date ensures very low temporal score
        defaults={"stored_at": "2020-01-01T00:00:00Z"},
    )

    return formula, prefetch
