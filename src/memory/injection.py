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

import json
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
    MemoryConfig,
)
from memory.intent import IntentType, detect_intent, get_target_collection
from memory.search import MemorySearch
from memory.triggers import (
    detect_best_practices_keywords,
    detect_decision_keywords,
    detect_session_history_keywords,
)

__all__ = [
    "InjectionSessionState",
    "RouteTarget",
    "compute_adaptive_budget",
    "compute_topic_drift",
    "format_injection_output",
    "init_session_state",
    "log_injection_event",
    "retrieve_bootstrap_context",
    "route_collections",
    "select_results_greedy",
]

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
        tmp_path.rename(path)  # Atomic on POSIX

    def reset_after_compact(self) -> None:
        """Reset injected IDs after compaction (context window cleared).

        Called when SessionStart fires with trigger=compact.
        Previous injections are no longer in Claude's context window.
        Keep last_query_embedding and topic_drift (conversation continues).
        """
        self.injected_point_ids = []

    @staticmethod
    def _state_path(session_id: str) -> Path:
        """Get path to session state file."""
        # Sanitize session_id: alphanumeric + dash/underscore only, max 64 chars
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', session_id)[:64]
        if not safe_id:
            safe_id = "unknown"
        return Path(f"/tmp/ai-memory-{safe_id}-injection-state.json")


def retrieve_bootstrap_context(
    search_client: MemorySearch,
    project_name: str,
    config: MemoryConfig,
) -> list[dict]:
    """Retrieve bootstrap context for session startup.

    Searches conventions (shared) + recent discussions (project-scoped).
    Uses decay scoring for recency-aware ranking.

    Bootstrap content (priority order):
    1. Project conventions — rules and guidelines (shared, no group_id)
    2. Recent decisions — most recent architecture/pattern decisions (30 days)
    3. Active task context — agent handoff/memory (7 days)

    Args:
        search_client: MemorySearch instance
        project_name: Project group_id for filtering
        config: Memory configuration

    Returns:
        List of result dicts sorted by relevance score, ready for greedy fill.
    """
    results = []

    # 1. Conventions (shared, no group_id filter)
    conventions = search_client.search(
        query="project conventions rules guidelines standards",
        collection=COLLECTION_CONVENTIONS,
        group_id=None,  # Shared across projects
        limit=5,
        fast_mode=True,
    )
    results.extend(conventions)

    # 2. Recent decisions (project-scoped)
    decisions = search_client.search(
        query="recent decisions architecture patterns",
        collection=COLLECTION_DISCUSSIONS,
        group_id=project_name,
        limit=3,
        memory_type=["decision"],
        fast_mode=True,
    )
    results.extend(decisions)

    # 3. Active agent context (project-scoped, last 7 days)
    agent_context = search_client.search(
        query="active task current work session handoff",
        collection=COLLECTION_DISCUSSIONS,
        group_id=project_name,
        limit=2,
        memory_type=["agent_handoff", "agent_memory"],
        fast_mode=True,
    )
    results.extend(agent_context)

    # Sort all results by score (decay-weighted) for greedy fill
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
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
    # Normalize to [0, 1] range. Score is already 0-1 from cosine similarity.
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


def select_results_greedy(
    results: list[dict],
    budget: int,
    excluded_ids: list[str] | None = None,
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
    excluded = set(excluded_ids or [])
    selected = []
    tokens_used = 0

    for result in results:
        point_id = str(result.get("id", ""))

        # Skip already-injected points
        if point_id in excluded:
            continue

        content = result.get("content", "")
        if not content.strip():
            continue

        # Count tokens accurately
        result_tokens = count_tokens(content)

        # Check if this result fits in remaining budget
        if tokens_used + result_tokens <= budget:
            selected.append(result)
            tokens_used += result_tokens
        else:
            # Skip-and-continue: try next smaller result
            # (AD-6: don't truncate, don't stop — keep trying)
            continue

    return selected, tokens_used


def format_injection_output(
    results: list[dict],
    tier: int,
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
    return f"<retrieved_context>\n{body}\n</retrieved_context>"


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
