"""Progressive Context Injection — Core Module (SPEC-012).

Provides two-tier context injection:
- Tier 1 (Bootstrap): SessionStart injects conventions + recent decisions (2-3K tokens)
- Tier 2 (Per-turn): UserPromptSubmit injects adaptive context (500-1500 tokens)

Architecture: AD-6, BP-076 (Progressive Staged Context Injection), BP-089 (Adaptive Token Budgets)

Key Features:
- Confidence gating: Skip injection when retrieval score < threshold
- Adaptive budgets: Variable token allocation based on quality/density/drift signals
- Collection routing: Keyword/intent/file-path detection routes to target collections
- Greedy fill: No individual result truncation, skip-and-continue for oversized
- Session state: Deduplication across tiers and turns
- Topic drift: Cosine distance between query embeddings

References:
- SPEC-012: Progressive Context Injection
- BP-076: Progressive staged injection reduces token waste by 60-75%
- BP-089: Adaptive budgets improve accuracy 5-15%
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4
# SDK VERSION: V4. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import contextlib
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import numpy as np

from memory.chunking.truncation import count_tokens
from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    COLLECTION_GITHUB,
    MemoryConfig,
)
from memory.embeddings import EmbeddingError
from memory.intent import IntentType, detect_intent, get_target_collection
from memory.qdrant_client import QdrantUnavailable
from memory.search import MemorySearch
from memory.triggers import (
    detect_best_practices_keywords,
    detect_decision_keywords,
    detect_session_history_keywords,
)

# SPEC-021: Trace buffer for injection instrumentation
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000  # Max chars for trace output fields

__all__ = [
    "InjectionSessionState",
    "RouteTarget",
    "compute_adaptive_budget",
    "compute_topic_drift",
    "format_injection_output",
    "init_session_state",
    "load_parzival_constraints",
    "log_injection_event",
    "retrieve_bootstrap_context",
    "route_collections",
    "select_results_greedy",
]

logger = logging.getLogger("ai_memory.injection")

# ARCHITECTURE NOTE: Do NOT add @observe decorator to functions in this module.
# These functions are called from hook scripts (OS subprocess boundaries) and Docker
# services. @observe creates orphaned Langfuse traces when OTel context doesn't cross
# process boundaries. Use emit_trace_event() with explicit session_id instead.
# See LANGFUSE-INTEGRATION-SPEC.md §4.3

# File path patterns that indicate code-related queries
_FILE_PATH_RE = re.compile(
    r"(?:"
    r"[a-zA-Z_][\w/\\.-]*\.(?:py|ts|tsx|js|jsx|go|rs|java|cpp|c|h|rb|php|css|html|yaml|yml|json|toml|md|sh|sql)"
    r"|/(?:src|lib|tests?|scripts?|docker|hooks?)/"
    r")",
    re.IGNORECASE,
)


class RouteTarget(NamedTuple):
    """Target collection for Tier 2 routing.

    Attributes:
        collection: Collection name to search
        shared: True = no group_id filter (conventions), False = project-scoped
    """

    collection: str
    shared: bool = False


@dataclass
class InjectionSessionState:
    """Cross-turn state for injection deduplication and topic drift.

    Stored as JSON in temp file. Auto-cleaned by OS.
    Max size: ~50KB (768 floats + a few hundred UUIDs).

    Attributes:
        session_id: Session identifier
        injected_point_ids: List of Qdrant point IDs already injected
        last_query_embedding: 768-dim embedding of previous user prompt
        topic_drift: Cosine distance from previous query (0=same, 1=different)
        turn_count: Number of UserPromptSubmit turns processed
        total_tokens_injected: Cumulative tokens injected across all turns
    """

    session_id: str
    injected_point_ids: list[str] = field(default_factory=list)
    last_query_embedding: list[float] | None = None
    topic_drift: float = 0.5
    turn_count: int = 0
    total_tokens_injected: int = 0
    error_state: dict | None = field(default=None)
    compact_count: int = 0
    # H-3: Cross-turn access_count dedup — tracks which point IDs had access_count
    # incremented this turn. Cleared when turn_count advances. Prevents double-counting
    # when multiple search() calls in the same turn return overlapping results.
    access_count_incremented_this_turn: list[str] = field(default_factory=list)
    _last_turn_count: int = 0  # Internal: tracks turn_count for dedup set clearing

    @classmethod
    def load(cls, session_id: str) -> "InjectionSessionState":
        """Load session state from temp file.

        Args:
            session_id: Session identifier

        Returns:
            InjectionSessionState instance, or fresh state if file missing/corrupted
        """
        path = cls._state_path(session_id)
        try:
            if path.exists():
                data = json.loads(path.read_text())
                return cls(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass  # Corrupted state — start fresh
        return cls(session_id=session_id)

    def save(self) -> None:
        """Persist session state to temp file (atomic write).

        Uses atomic rename to prevent corruption from concurrent writes.
        """
        path = self._state_path(self.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(asdict(self), default=str))
        import os

        os.replace(str(tmp_path), str(path))  # Cross-platform atomic replace

    def reset_after_compact(self) -> None:
        """Reset injected IDs after compaction (context window cleared).

        Called when SessionStart fires with trigger=compact.
        - CLEARS: injected_point_ids (context window is gone)
        - PRESERVES: last_query_embedding, topic_drift, error_state (conversation continues)
        - INCREMENTS: compact_count (tracks which compact in this session)
        - UNCHANGED: turn_count, total_tokens_injected (accumulate across compacts per spec)
        """
        self.injected_point_ids = []
        self.compact_count += 1

    @staticmethod
    def _state_path(session_id: str) -> Path:
        """Get path to session state file."""
        # Sanitize session_id: alphanumeric + dash/underscore only, max 64 chars
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)[:64]
        if not safe_id:
            safe_id = "unknown"
        return Path(f"/tmp/ai-memory-{safe_id}-injection-state.json")


def _build_github_enrichment(
    search_client: MemorySearch,
    config: MemoryConfig,
    project_name: str,
    last_session_date: str | None,
) -> list[dict]:
    """Query recent GitHub activity since last session.

    Args:
        search_client: MemorySearch instance.
        config: MemoryConfig instance.
        project_name: Project group_id for scoping.
        last_session_date: ISO 8601 timestamp of last handoff's `timestamp` field.
            If None, skips enrichment (no baseline to compare against).

    Returns:
        List of search result dicts for recent GitHub activity.
        Limited to 10 results, ~500-800 tokens.
    """
    if not last_session_date:
        return []

    if not config.github_sync_enabled:
        return []

    recent_github = search_client.search(
        query="merged pull request new issue opened closed",
        collection=COLLECTION_GITHUB,
        group_id=project_name,
        limit=10,
        source="github",
        memory_type=[
            "github_pr",
            "github_issue",
            "github_commit",
        ],
        fast_mode=True,
    )

    # Filter to items stored after last session
    filtered = []
    try:
        # Python 3.10 compat: fromisoformat() doesn't support "Z" suffix until 3.11
        baseline_dt = datetime.fromisoformat(last_session_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return []

    for result in recent_github:
        result_timestamp = result.get("timestamp", "")
        if not result_timestamp:
            continue
        try:
            result_dt = datetime.fromisoformat(result_timestamp.replace("Z", "+00:00"))
            if result_dt > baseline_dt:
                filtered.append(result)
        except (ValueError, TypeError):
            continue

    return filtered[:10]


def retrieve_bootstrap_context(
    search_client: MemorySearch,
    project_name: str,
    config: MemoryConfig,
) -> list[dict]:
    """Retrieve bootstrap context for Parzival session startup.

    Uses layered priority retrieval (no score-sorting):
    1. Last handoff (DETERMINISTIC) — agent_id=parzival, limit=1
    2. Recent decisions (DETERMINISTIC) — limit=5
    3. Recent insights (SEMANTIC) — agent_id=parzival, limit=3
    4. GitHub enrichment (SEMANTIC) — since last handoff timestamp

    Caller is responsible for gating on config.parzival_enabled.

    Args:
        search_client: MemorySearch instance
        project_name: Project group_id for filtering
        config: Memory configuration

    Returns:
        List of result dicts in layer priority order, ready for greedy fill.
    """
    _trace_start = datetime.now(tz=timezone.utc)
    results = []
    _decisions_count = 0
    _agent_count = 0
    _github_count = 0

    # LAYERED PRIORITY RETRIEVAL for Parzival sessions
    # No conventions — they are noise for PM oversight
    last_handoff = []

    # Layer 1: Last handoff (DETERMINISTIC — most recent, not most similar)
    try:
        last_handoff = search_client.get_recent(
            collection=COLLECTION_DISCUSSIONS,
            group_id=project_name,
            memory_type=["agent_handoff"],
            agent_id="parzival",
            limit=1,
        )
        results.extend(last_handoff)
    except (QdrantUnavailable, ConnectionError, TimeoutError) as e:
        logger.warning(
            "bootstrap_handoff_unavailable",
            extra={"error": str(e)},
        )

    # Layer 2: Recent decisions (DETERMINISTIC — newest, not most similar)
    try:
        decisions = search_client.get_recent(
            collection=COLLECTION_DISCUSSIONS,
            group_id=project_name,
            memory_type=["decision"],
            limit=5,
        )
        results.extend(decisions)
        _decisions_count = len(decisions)
    except (QdrantUnavailable, ConnectionError, TimeoutError) as e:
        logger.warning(
            "bootstrap_decisions_unavailable",
            extra={"error": str(e)},
        )

    # Layer 3: Recent insights (SEMANTIC — relevance matters)
    try:
        insights = search_client.search(
            query="key insight learning pattern important",
            collection=COLLECTION_DISCUSSIONS,
            group_id=project_name,
            limit=3,
            memory_type=["agent_insight"],
            agent_id="parzival",
            fast_mode=True,
        )
        results.extend(insights)
        _agent_count = len(last_handoff) + len(insights)
    except (QdrantUnavailable, EmbeddingError, ConnectionError, TimeoutError) as e:
        logger.warning(
            "bootstrap_insights_unavailable",
            extra={"error": str(e)},
        )

    # Layer 4: GitHub enrichment (SEMANTIC — same as before)
    last_session_date = None
    if last_handoff:
        last_session_date = last_handoff[0].get("timestamp")
    try:
        github_enrichment = _build_github_enrichment(
            search_client,
            config,
            project_name,
            last_session_date,
        )
        results.extend(github_enrichment)
        _github_count = len(github_enrichment)
    except (QdrantUnavailable, EmbeddingError, ConnectionError, TimeoutError) as e:
        logger.warning(
            "bootstrap_github_unavailable",
            extra={"error": str(e)},
        )

    # DO NOT sort by score — layer order IS the priority
    # Greedy fill processes Layer 1 first, then Layer 2, etc.

    # SPEC-021: Emit bootstrap retrieval trace event
    if emit_trace_event:
        try:
            # Build content preview: show what was actually retrieved
            _result_previews = "\n---\n".join(
                f"[{r.get('type','?')}|{r.get('collection','?')}|{round(r.get('score',0)*100)}%] {r.get('content','')[:500]}"
                for r in results[:20]
            )
            emit_trace_event(
                event_type="bootstrap_retrieval",
                data={
                    "input": f"Bootstrap retrieval for project: {project_name}, parzival_enabled: {config.parzival_enabled}",
                    "output": (
                        _result_previews[:TRACE_CONTENT_MAX]
                        if _result_previews
                        else "No bootstrap results"
                    ),
                    "metadata": {
                        "project_name": project_name,
                        "parzival_enabled": config.parzival_enabled,
                        "decisions_count": _decisions_count,
                        "agent_context_count": _agent_count,
                        "github_enrichment_count": _github_count,
                        "total_results": len(results),
                        "per_result_scores": [
                            {
                                "type": r.get("type", "unknown"),
                                "score": r.get("score", 0),
                                "collection": r.get("collection", "unknown"),
                            }
                            for r in results[:20]
                        ],
                        "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                        "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                    },
                },
                project_id=project_name,
                session_id=os.environ.get("CLAUDE_SESSION_ID"),
                start_time=_trace_start,
                end_time=datetime.now(tz=timezone.utc),
                tags=["injection", "bootstrap"],
            )
        except Exception:
            pass

    return results


def route_collections(
    prompt: str,
) -> list[RouteTarget]:
    """Route prompt to target collection(s) for Tier 2 injection.

    Priority order:
    1. Keyword triggers (backward-compat with unified_keyword_trigger)
    2. File path detection (code-patterns)
    3. Intent detection (HOW/WHAT/WHY)
    4. Unknown → cascade all collections

    Args:
        prompt: User's message text

    Returns:
        List of RouteTarget tuples with collection and shared flag.
        shared=True means no group_id filter (conventions).
    """
    routes = []

    # 1. Check keyword triggers first (backward compat)
    decision_topic = detect_decision_keywords(prompt)
    session_topic = detect_session_history_keywords(prompt)
    bp_topic = detect_best_practices_keywords(prompt)

    if decision_topic:
        routes.append(RouteTarget(COLLECTION_DISCUSSIONS, shared=False))
    if session_topic:
        routes.append(RouteTarget(COLLECTION_DISCUSSIONS, shared=False))
    if bp_topic:
        routes.append(RouteTarget(COLLECTION_CONVENTIONS, shared=True))

    if routes:
        # Deduplicate by collection name (e.g., both decision + session → discussions)
        seen = set()
        unique = []
        for r in routes:
            if r.collection not in seen:
                seen.add(r.collection)
                unique.append(r)
        return unique

    # 2. Check for file paths → code-patterns
    if _FILE_PATH_RE.search(prompt):
        routes.append(RouteTarget(COLLECTION_CODE_PATTERNS, shared=False))
        return routes

    # 3. Use existing intent detection
    intent = detect_intent(prompt)

    if intent == IntentType.UNKNOWN:
        # 4. Unknown → cascade: discussions first, then code-patterns, then conventions
        return [
            RouteTarget(COLLECTION_DISCUSSIONS, shared=False),
            RouteTarget(COLLECTION_CODE_PATTERNS, shared=False),
            RouteTarget(COLLECTION_CONVENTIONS, shared=True),
        ]

    target = get_target_collection(intent)
    return [RouteTarget(target, shared=(target == COLLECTION_CONVENTIONS))]


def compute_adaptive_budget(
    best_score: float,
    results: list[dict],
    session_state: dict,
    config: MemoryConfig,
) -> int:
    """Compute adaptive token budget for Tier 2 injection.

    Three weighted signals determine budget within [floor, ceiling]:
    - quality_signal (50%): Best retrieval score (higher = more budget)
    - density_signal (30%): Proportion of results above threshold
    - session_signal (20%): Topic drift from previous query

    Args:
        best_score: Highest score from search results
        results: All search results (for density calculation)
        session_state: Session state dict with last_query_embedding
        config: Memory configuration with budget floor/ceiling

    Returns:
        Token budget as integer in [floor, ceiling] range.

    References:
        BP-089: TALE (ACL 2025): adaptive budgets improve accuracy 5-15%
        BP-089: TARG: unconditional retrieval hurts accuracy
        Competitive: Cursor, Continue.dev, Cody all use variable budgets
    """
    floor = config.injection_budget_floor
    ceiling = config.injection_budget_ceiling

    # Signal 1: Quality (50%) — higher best score = more budget
    # Score is 0-1: cosine similarity for dense paths, normalized for hybrid/RRF paths.
    quality_signal = min(1.0, max(0.0, best_score))

    # Signal 2: Density (30%) — proportion of results above threshold
    if results:
        above_threshold = sum(
            1
            for r in results
            if r.get("score", 0) >= config.injection_confidence_threshold
        )
        density_signal = above_threshold / len(results)
    else:
        density_signal = 0.0

    # Signal 3: Session drift (20%) — topic drift from previous query
    # High drift = new topic = more context needed = higher budget
    drift_signal = session_state.get("topic_drift", 0.5)  # Default 0.5 (neutral)

    # Weighted combination
    combined = (
        config.injection_quality_weight * quality_signal
        + config.injection_density_weight * density_signal
        + config.injection_drift_weight * drift_signal
    )

    # Map to budget range
    budget = floor + int((ceiling - floor) * combined)
    return max(floor, min(ceiling, budget))


def compute_topic_drift(
    current_embedding: list[float],
    previous_embedding: list[float] | None,
) -> float:
    """Compute topic drift between current and previous query.

    Uses cosine distance (1 - cosine_similarity) so higher = more drift.

    Args:
        current_embedding: 768-dim embedding of current user prompt
        previous_embedding: 768-dim embedding of previous user prompt,
            or None if first turn

    Returns:
        Drift score in [0, 1]. 0 = same topic, 1 = completely different.
        Returns 0.5 (neutral) if no previous embedding.

    Performance:
        numpy dot product on 768-dim vectors is <0.01ms. Negligible.
    """
    if previous_embedding is None:
        return 0.5  # Neutral — first turn

    current = np.array(current_embedding)
    previous = np.array(previous_embedding)

    # Cosine similarity
    dot = np.dot(current, previous)
    norm = np.linalg.norm(current) * np.linalg.norm(previous)

    if norm == 0:
        return 0.5

    similarity = dot / norm
    # Drift = 1 - similarity (higher drift = more context needed)
    return max(0.0, min(1.0, 1.0 - similarity))


# BUG-173: Per-result score gap filter threshold. Results scoring below
# best_score * this value are filtered as low-relevance noise.
# 0.7 (30% gap) chosen based on BUG-173 Langfuse trace analysis:
# best=99%, noise=82% → 82/99=0.83 passes at 0.7 but fails at 0.85.
# Now configurable via INJECTION_SCORE_GAP_THRESHOLD env var (default 0.7).
_SCORE_GAP_THRESHOLD_DEFAULT = 0.7


def select_results_greedy(
    results: list[dict],
    budget: int,
    excluded_ids: list[str] | None = None,
    score_gap_threshold: float = _SCORE_GAP_THRESHOLD_DEFAULT,
    project_id: str | None = None,
) -> tuple[list[dict], int]:
    """Select results using greedy fill until budget exhausted.

    Per AD-6: No truncation of individual results. Each chunk is fully
    included or fully excluded. Skip-and-continue for oversized results.

    Args:
        results: Search results sorted by score descending
        budget: Token budget to fill
        excluded_ids: Point IDs to skip (already injected)

    Returns:
        Tuple of (selected_results, total_tokens_used).
    """
    _trace_start = datetime.now(tz=timezone.utc)
    excluded = set(excluded_ids or [])
    selected = []
    _selected_token_counts: list[int] = []
    tokens_used = 0
    _dedup_skipped = 0
    _score_gap_skipped = 0

    # BUG-172: Content-hash deduplication for cross-type duplicates
    seen_hashes: set[str] = set()

    # BUG-173: Score gap filter — skip results >30% below best
    # Exclude deterministic results (score=1.0) from gap calculation
    # since they are not comparable to semantic similarity scores
    semantic_scores = [r.get("score", 0) for r in results if r.get("score", 0) < 1.0]
    best_score = max(semantic_scores) if semantic_scores else 0.0

    for result in results:
        point_id = str(result.get("id", ""))

        # Skip already-injected points
        if point_id in excluded:
            continue

        content = result.get("content", "")
        if not content.strip():
            continue

        # BUG-172: Skip duplicate content (same text stored under different types)
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        if content_hash in seen_hashes:
            _dedup_skipped += 1
            continue
        seen_hashes.add(content_hash)

        # BUG-173: Skip results with score gap from best exceeding threshold
        # NOTE (PLAN-015 WP-2 / Spec §4.2.5 step 3): Freshness-blocked results (score=0.0)
        # do NOT need an explicit skip here. Defense-in-depth coverage:
        #   1. Gating (best_score<0.45 → hard_skip) prevents reaching this when ALL results are 0.0.
        #   2. The `best_score > 0` guard below ensures 0.0-scored items are caught by gap filter
        #      when any positive-scored result exists (0.0 < positive_score x threshold -> skip).
        # The caller (context_injection_tier2.py) applies freshness penalty upstream so that
        # post-penalty scores drive both gating and this selection. Do NOT add penalty logic here.
        result_score = result.get("score", 0)
        if best_score > 0 and result_score < best_score * score_gap_threshold:
            _score_gap_skipped += 1
            continue

        # Count tokens accurately
        result_tokens = count_tokens(content)

        # Check if this result fits in remaining budget
        if tokens_used + result_tokens <= budget:
            selected.append(result)
            _selected_token_counts.append(result_tokens)
            tokens_used += result_tokens
        else:
            # Skip-and-continue: try next smaller result
            # (AD-6: don't truncate, don't stop — keep trying)
            continue

    # SPEC-021: Emit greedy fill trace event
    if emit_trace_event:
        try:
            _utilization_pct = int(tokens_used / budget * 100) if budget > 0 else 0
            # Build content preview of what was selected
            _selected_previews = "\n---\n".join(
                f"[{r.get('type','?')}|{round(r.get('score',0)*100)}%|{tc}tok] {r.get('content','')[:400]}"
                for r, tc in zip(selected, _selected_token_counts, strict=False)
            )
            emit_trace_event(
                event_type="greedy_fill",
                data={
                    "input": f"Greedy fill: {len(results)} candidates, budget: {budget} tokens, excluded: {len(excluded)}",
                    "output": (
                        _selected_previews[:TRACE_CONTENT_MAX]
                        if _selected_previews
                        else "No results selected"
                    ),
                    "metadata": {
                        "budget": budget,
                        "tokens_used": tokens_used,
                        "utilization_pct": _utilization_pct,
                        "results_considered": len(results),
                        "results_selected": len(selected),
                        "excluded_count": len(excluded),
                        "dedup_skipped": _dedup_skipped,
                        "score_gap_skipped": _score_gap_skipped,
                        "gap_threshold": score_gap_threshold,
                        "selected_detail": [
                            {
                                "type": r.get("type", "unknown"),
                                "score": r.get("score", 0),
                                "tokens": tc,
                            }
                            for r, tc in zip(
                                selected, _selected_token_counts, strict=False
                            )
                        ],
                        "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                        "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                    },
                },
                project_id=project_id,
                session_id=os.environ.get("CLAUDE_SESSION_ID"),
                start_time=_trace_start,
                end_time=datetime.now(tz=timezone.utc),
                tags=["injection", "greedy_fill"],
            )
        except Exception:
            pass

    return selected, tokens_used


def format_injection_output(
    results: list[dict],
    tier: int,
    project_id: str | None = None,
) -> str:
    """Format selected results for Claude context injection.

    Output uses <retrieved_context> delimiters (existing pattern from
    session_start.py:962, TECH-DEBT-115, BP-039 §1).

    Args:
        results: Selected results to format
        tier: Injection tier (1 or 2) for audit trail

    Returns:
        Formatted markdown string wrapped in <retrieved_context> tags.
    """
    _trace_start = datetime.now(tz=timezone.utc)

    if not results:
        return ""

    lines = []

    for result in results:
        content = result.get("content", "")
        result_type = result.get("type", "unknown")
        score = result.get("score", 0)
        collection = result.get("collection", "unknown")

        # Compact attribution header
        score_pct = int(score * 100)
        lines.append(f"**[{result_type}|{collection}|{score_pct}%]** {content}\n")

    body = "\n".join(lines)
    formatted = f"<retrieved_context>\n{body}\n</retrieved_context>"

    # SPEC-021: Emit format injection trace event
    if emit_trace_event:
        with contextlib.suppress(Exception):
            emit_trace_event(
                event_type="format_injection",
                data={
                    "input": f"Format {len(results)} results for tier {tier}",
                    "output": formatted[:TRACE_CONTENT_MAX],
                    "metadata": {
                        "tier": tier,
                        "result_count": len(results),
                        "output_chars": len(formatted),
                        "result_types": [r.get("type", "unknown") for r in results],
                        "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                        "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                    },
                },
                project_id=project_id,
                session_id=os.environ.get("CLAUDE_SESSION_ID"),
                start_time=_trace_start,
                end_time=datetime.now(tz=timezone.utc),
                tags=["injection", "format"],
            )

    return formatted


def log_injection_event(
    tier: int,
    trigger: str,
    project: str,
    session_id: str,
    results_considered: int,
    results_selected: int,
    tokens_used: int,
    budget: int,
    audit_dir: Path,
    best_score: float = 0.0,
    skipped_confidence: bool = False,
    topic_drift: float = 0.0,
    collections_searched: list[str] | None = None,
    gap_threshold: float = 0.7,
    gating_mode: str = "full",
) -> None:
    """Log injection event to .audit/logs/injection-log.jsonl.

    Per AD-6: "All injection events logged to .audit/ (what was injected,
    scores, tokens used). Enables tuning of confidence threshold, budget,
    and routing heuristics."

    Args:
        tier: Injection tier (1 or 2)
        trigger: Hook trigger type
        project: Project group_id
        session_id: Session identifier
        results_considered: Total results from search
        results_selected: Results that passed greedy fill
        tokens_used: Actual tokens injected
        budget: Token budget that was computed
        audit_dir: Path to .audit/ directory
        best_score: Best retrieval score
        skipped_confidence: True if injection was skipped due to low confidence
        topic_drift: Topic drift signal value
        collections_searched: Collections that were queried
        gap_threshold: Score gap threshold used for greedy fill filtering
        gating_mode: Confidence gating path taken ("skip", "soft", or "full")
    """
    log_path = Path(audit_dir) / "logs" / "injection-log.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tier": tier,
        "trigger": trigger,
        "project": project,
        "session_id": session_id,
        "results_considered": results_considered,
        "results_selected": results_selected,
        "tokens_used": tokens_used,
        "budget": budget,
        "utilization_pct": int((tokens_used / budget) * 100) if budget > 0 else 0,
        "best_score": round(best_score, 4),
        "skipped_confidence": skipped_confidence,
        "topic_drift": round(topic_drift, 4),
        "collections_searched": collections_searched or [],
        "gap_threshold": round(gap_threshold, 4),
        "gating_mode": gating_mode,
    }

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except (OSError, PermissionError):
        pass  # Audit logging is best-effort, never blocks


def init_session_state(session_id: str, injected_ids: list[str]) -> None:
    """Initialize session injection state after Tier 1 bootstrap.

    Creates a new InjectionSessionState with the given injected point IDs
    and persists it for Tier 2 deduplication.

    Args:
        session_id: Current session identifier
        injected_ids: Point IDs injected by Tier 1
    """
    state = InjectionSessionState(
        session_id=session_id,
        injected_point_ids=injected_ids,
        turn_count=0,
    )
    state.save()


def load_parzival_constraints(
    project_root: str,
    phase: str | None = None,
) -> str:
    """Load Parzival behavioral constraints from _ai-memory/pov/constraints/.

    Reads global constraints (always loaded) and optionally phase-specific
    constraints. Returns formatted markdown ready for injection.

    Args:
        project_root: Project root directory (where _ai-memory/ lives)
        phase: Optional phase name (e.g., 'execution', 'planning', 'discovery')

    Returns:
        Formatted markdown string with constraints, or empty string if not found.
    """
    constraints_dir = Path(project_root) / "_ai-memory" / "pov" / "constraints"

    if not constraints_dir.exists():
        return ""

    sections = []

    # Always load global constraints
    global_file = constraints_dir / "global" / "constraints.md"
    if global_file.exists():
        sections.append(global_file.read_text())

    # Optionally load phase-specific constraints
    phase_count = 0
    if phase:
        import re

        phase = re.sub(r"[^a-zA-Z0-9_-]", "", phase)
        phase_file = constraints_dir / phase / "constraints.md"
        if phase_file.exists():
            sections.append(phase_file.read_text())
            phase_count = 1

    if not sections:
        return ""

    result = "\n\n---\n\n".join(sections)
    global_count = 1 if (constraints_dir / "global" / "constraints.md").exists() else 0
    footer = f"\n\n---\nConstraints loaded: {global_count} global + {phase_count} phase-specific"

    return result + footer
