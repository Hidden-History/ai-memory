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

# TD-518: Aggregation imports for chunked retrieval reassembly.
from qdrant_client.models import FieldCondition, Filter, MatchValue

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
        shared: Deprecated — always False after PLAN-028 P1 (W-01). All
                collections including conventions are now project-scoped.
                Retained for backward compatibility with hook consumers.
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


def _aggregate_chunked_result(client, result: dict) -> dict:
    """Aggregate sibling chunks of a chunked retrieval result via scroll-and-concat.

    TD-518 (F-001): When a retrieval result is a single chunk of a multi-chunk
    emit (e.g., a long agent_handoff that was chunked at store time),
    dense-vector retrieval scores chunks individually and returns only the
    highest-scoring chunk — which may be a small trailer fragment carrying
    <1% of the intended payload. This helper scrolls the discussions
    collection for siblings sharing ``(group_id, type, created_at)``, sorts
    them by ``chunking_metadata.chunk_index`` ascending, and concatenates
    ``content`` into a single aggregated string.

    Type-agnostic: triggers on any chunked result whose
    ``chunking_metadata.total_chunks`` is greater than 1, regardless of
    ``memory_type``. Composes with future emit types that ever chunk.

    Collection-aware (TD-518): the scroll target collection is
    extracted from ``result.get("collection", COLLECTION_DISCUSSIONS)``, so
    chunked emits routed to non-discussions collections (e.g., a future
    type stored in ``code-patterns`` or ``conventions``) are handled
    correctly. Default falls back to ``COLLECTION_DISCUSSIONS`` for
    backward-compatibility with any caller whose result dict lacks the
    ``collection`` key.

    Drift signal (TD-518): the aggregated result preserves the
    original advertised count separately from the count actually
    concatenated, so diagnostic tools can detect partial aggregation
    without parsing logs:

    - ``chunking_metadata.total_chunks_advertised``: original N from the
      trigger chunk's metadata
    - ``chunking_metadata.total_chunks``: K, the count of siblings actually
      found and concatenated (matches TECH-DEBT-518 Fix Design item 5)

    Complete reassembly: ``total_chunks_advertised == total_chunks``.
    Partial drift: ``total_chunks_advertised > total_chunks`` (also emits
    ``bootstrap_aggregation_partial`` WARN).

    Failure handling: on any scroll failure, missing match keys, or no
    siblings found, logs a structured warning and returns the original
    result unchanged. Bootstrap is never made worse than today.

    Args:
        client: Qdrant client (e.g., ``MemorySearch.client``).
        result: A single retrieval result dict including payload fields
            (``group_id``, ``type``, ``created_at``/``timestamp``,
            ``collection``, ``chunking_metadata``, ``content``).

    Returns:
        Aggregated result dict with ``content`` reassembled from siblings
        and ``chunking_metadata.aggregated_from_chunks`` set to True for
        diagnostic visibility. On failure, returns ``result`` unchanged.

    References:
        TECH-DEBT-518 §"Fix Design" item 5
        Chunking-Strategy-V2 §3.3
    """
    metadata = result.get("chunking_metadata") or {}
    total_chunks = metadata.get("total_chunks", 1)
    if not isinstance(total_chunks, int) or total_chunks <= 1:
        # Whole-emit (or absent metadata): bypass aggregation, no extra cost.
        return result

    group_id = result.get("group_id")
    memory_type = result.get("type")
    created_at = result.get("created_at") or result.get("timestamp")

    if not (group_id and memory_type and created_at):
        logger.warning(
            "bootstrap_aggregation_skipped",
            extra={
                "reason": "missing_match_keys",
                "has_group_id": bool(group_id),
                "has_type": bool(memory_type),
                "has_created_at": bool(created_at),
                "total_chunks": total_chunks,
            },
        )
        return result

    # Extract collection from result; default to discussions for
    # backward-compatibility with any caller whose result dict lacks the key.
    # The `or`-fallthrough is intentional and defensive: it falls back for
    # BOTH missing key (None) AND empty-string value (e.g., from a buggy
    # upstream serialization that produces `result["collection"] = ""`).
    # Silent degradation to discussions is preferred over letting Qdrant
    # raise on `scroll(collection_name="")` — the helper's contract is
    # "never crash bootstrap"; an upstream bug surfaces via the WARN
    # `bootstrap_aggregation_no_siblings` log if discussions has no
    # matching keys.
    target_collection = result.get("collection") or COLLECTION_DISCUSSIONS

    try:
        filter_conditions = [
            FieldCondition(key="group_id", match=MatchValue(value=group_id)),
            FieldCondition(key="type", match=MatchValue(value=memory_type)),
            FieldCondition(key="created_at", match=MatchValue(value=created_at)),
        ]
        # Generous limit absorbs metadata drift; 37-chunk Session 44 case fits easily.
        scroll_limit = max(total_chunks * 2, 100)
        points, _next_offset = client.scroll(
            collection_name=target_collection,
            scroll_filter=Filter(must=filter_conditions),
            limit=scroll_limit,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as exc:
        logger.warning(
            "bootstrap_aggregation_failed",
            extra={
                "error": str(exc),
                "type": memory_type,
                "total_chunks": total_chunks,
            },
        )
        return result

    if not points:
        logger.warning(
            "bootstrap_aggregation_no_siblings",
            extra={"type": memory_type, "expected_chunks": total_chunks},
        )
        return result

    # Sort siblings by chunk_index ascending. Missing index sorts to end so
    # mis-tagged chunks land last and don't disrupt the ordered prefix.
    def _chunk_idx(point) -> int:
        cm = (getattr(point, "payload", None) or {}).get("chunking_metadata") or {}
        idx = cm.get("chunk_index")
        return idx if isinstance(idx, int) else 99999

    sorted_points = sorted(points, key=_chunk_idx)

    aggregated_content = "".join(
        ((getattr(p, "payload", None) or {}).get("content") or "")
        for p in sorted_points
    )

    if len(sorted_points) < total_chunks:
        logger.warning(
            "bootstrap_aggregation_partial",
            extra={
                "type": memory_type,
                "found_chunks": len(sorted_points),
                "expected_chunks": total_chunks,
            },
        )

    aggregated = dict(result)
    aggregated["content"] = aggregated_content
    # TD-518: dual-field shape — preserve advertised count separately from
    # actual concatenated count so partial-drift is observable in result
    # metadata, not just in WARN logs.
    aggregated["chunking_metadata"] = {
        **metadata,
        "chunk_type": "whole_aggregated",
        "total_chunks_advertised": total_chunks,
        "total_chunks": len(sorted_points),
        "aggregated_from_chunks": True,
    }
    return aggregated


def retrieve_bootstrap_context(
    search_client: MemorySearch,
    project_name: str,
    config: MemoryConfig,
) -> tuple[list[dict], dict]:
    """Retrieve bootstrap context for Parzival session startup.

    Uses layered priority retrieval (no score-sorting):
    1. Last handoff (DETERMINISTIC) — agent_id=parzival, limit=1
    2. Recent decisions (DETERMINISTIC) — limit=5
    3. Recent insights (SEMANTIC) — agent_id=parzival, limit=3
    4. GitHub enrichment (SEMANTIC) — since last handoff timestamp

    Caller is responsible for gating on config.parzival_enabled.

    Layer 1 applies a per-tier ceiling check (config.handoff_ceiling_tokens)
    AFTER chunk aggregation but BEFORE results extension: oversized handoffs
    are excluded and the rejection is signaled via the returned meta dict
    (BP-158 P2 typed-sentinel pattern). The bootstrap consumer surfaces a
    FALLBACK-NEEDED marker when meta.fallback_signaled is True.

    Args:
        search_client: MemorySearch instance
        project_name: Project group_id for filtering
        config: Memory configuration

    Returns:
        Tuple of (results, meta) where results is the list of result dicts
        in layer priority order ready for greedy fill, and meta is a dict
        carrying {fallback_signaled, rejects} populated by the Layer 1
        ceiling pre-filter (BP-158 P2).
    """
    _trace_start = datetime.now(tz=timezone.utc)
    results = []
    _decisions_count = 0
    _agent_count = 0
    _github_count = 0

    # BP-158 P2: meta dict carries the C-3 ceiling rejection signal so the
    # bootstrap consumer can emit a FALLBACK-NEEDED marker without the
    # caller needing to compute it independently.
    meta: dict = {"fallback_signaled": False, "rejects": []}

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
        # TD-518 (F-001): If the retrieved chunk is part of a multi-chunk emit,
        # aggregate siblings via scroll-and-concat so cross-session continuity
        # delivers the full handoff body rather than a fragment.
        if last_handoff:
            last_handoff[0] = _aggregate_chunked_result(
                search_client.client, last_handoff[0]
            )
            # BUG-297 / BP-158 §5: Layer 1 per-tier ceiling pre-filter.
            # Aggregated handoff body that exceeds handoff_ceiling_tokens
            # is rejected at retrieval time so the downstream greedy fill
            # never silently drops it on bootstrap_token_budget grounds.
            # Rejection is signaled via meta.fallback_signaled so the
            # bootstrap skill can emit the FALLBACK-NEEDED marker.
            handoff_body = last_handoff[0].get("content", "") or ""
            handoff_tokens = count_tokens(handoff_body)
            if handoff_tokens > config.handoff_ceiling_tokens:
                # No score field: L1 retrieval is deterministic (get_recent
                # by recency, not similarity), so a similarity score is
                # semantically inert here. Greedy-fill rejects on semantic
                # layers remain score-bearing.
                reject_record = {
                    "type": "agent_handoff",
                    "tokens": handoff_tokens,
                    "reason": "ceiling_exceeded",
                    "tier": "1_bootstrap",
                    "collection": COLLECTION_DISCUSSIONS,
                }
                meta["rejects"].append(reject_record)
                meta["fallback_signaled"] = True
                with contextlib.suppress(Exception):
                    logger.warning(
                        "retrieval_budget_reject",
                        extra={
                            "reason": "ceiling_exceeded",
                            "tier": "1_bootstrap",
                            "collection": COLLECTION_DISCUSSIONS,
                            "type": "agent_handoff",
                            "tokens": handoff_tokens,
                            "ceiling": config.handoff_ceiling_tokens,
                        },
                    )
                try:
                    from memory.metrics_push import (
                        push_retrieval_reject_metric_async,
                    )

                    push_retrieval_reject_metric_async(
                        reason="ceiling_exceeded",
                        tier="1_bootstrap",
                        collection=COLLECTION_DISCUSSIONS,
                    )
                except Exception:
                    pass
                # Exclude the oversized handoff from results so downstream
                # greedy fill operates only on snippet-class layers.
                last_handoff = []
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

    return results, meta


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
        List of RouteTarget tuples with collection. All collections including
        conventions are project-scoped (PLAN-028 P1 W-01).
    """
    routes = []

    # 1. Check keyword triggers first (backward compat)
    decision_topic = detect_decision_keywords(prompt)
    session_topic = detect_session_history_keywords(prompt)
    bp_topic = detect_best_practices_keywords(prompt)

    if decision_topic:
        routes.append(RouteTarget(COLLECTION_DISCUSSIONS))
    if session_topic:
        routes.append(RouteTarget(COLLECTION_DISCUSSIONS))
    if bp_topic:
        routes.append(RouteTarget(COLLECTION_CONVENTIONS))  # project-scoped per W-01

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
        routes.append(RouteTarget(COLLECTION_CODE_PATTERNS))
        return routes

    # 3. Use existing intent detection
    intent = detect_intent(prompt)

    if intent == IntentType.UNKNOWN:
        # 4. Unknown → cascade: discussions first, then code-patterns, then conventions
        return [
            RouteTarget(COLLECTION_DISCUSSIONS),
            RouteTarget(COLLECTION_CODE_PATTERNS),
            RouteTarget(COLLECTION_CONVENTIONS),  # project-scoped per W-01
        ]

    target = get_target_collection(intent)
    return [RouteTarget(target)]


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
    *,
    tier: int = 1,
    return_meta: bool = False,
) -> tuple[list[dict], int] | tuple[list[dict], int, dict]:
    """Select results using greedy fill until budget exhausted.

    Per AD-6: No truncation of individual results. Each chunk is fully
    included or fully excluded. Skip-and-continue for oversized results.

    Args:
        results: Search results sorted by score descending
        budget: Token budget to fill
        excluded_ids: Point IDs to skip (already injected)
        score_gap_threshold: Score-gap multiplier for BUG-173 filter
        project_id: Project group_id for trace attribution
        tier: 1 for bootstrap (Tier 1), 2 for per-turn injection (Tier 2).
            Maps to retrieval-reject Prometheus counter label per BP-158 P3.
        return_meta: When False (default), returns the legacy 2-tuple shape
            so existing callers are unaffected. When True, returns a 3-tuple
            (selected, tokens_used, meta) where meta is a dict carrying
            {fallback_signaled, rejects, budget, tokens_used}. BP-158 P2
            typed-sentinel pattern: fallback_signaled is True iff any
            budget-rejected result was of type "agent_handoff".

    Returns:
        Tuple of (selected_results, total_tokens_used) when return_meta=False,
        else (selected_results, total_tokens_used, meta) per above.
    """
    _trace_start = datetime.now(tz=timezone.utc)
    excluded = set(excluded_ids or [])
    selected = []
    _selected_token_counts: list[int] = []
    tokens_used = 0
    _dedup_skipped = 0
    _score_gap_skipped = 0

    # BP-158 P1: per-reject record accumulator for the typed-sentinel meta.
    rejects: list[dict] = []
    tier_label = "1_bootstrap" if tier == 1 else "2_injection"
    fallback_signaled = False

    def _record_reject(
        result: dict,
        reason: str,
        result_tokens: int | None = None,
    ) -> None:
        """Accumulate a reject record and emit observability (log + counter).

        Wrapped in try/except per BP-158 P1 — observability never raises.
        Uniform shape across budget_exceeded, score_gap, dedup so meta.rejects
        is debuggable end-to-end.
        """
        nonlocal fallback_signaled
        result_type = result.get("type", "unknown")
        collection_label = result.get("collection", "unknown") or "unknown"
        rejects.append(
            {
                "type": result_type,
                "tokens": result_tokens,
                "score": result.get("score", 0),
                "reason": reason,
                "tier": tier_label,
                "collection": collection_label,
            }
        )
        # BP-158 P2: only budget/ceiling rejection of handoff-class results
        # signals fallback. Score-gap and dedup of handoff are not fallback
        # triggers (Layer 1 is deterministic limit=1; dedup of handoff means
        # a fresher copy was already accepted).
        if reason in ("budget_exceeded", "ceiling_exceeded") and (
            result_type == "agent_handoff"
        ):
            fallback_signaled = True
        with contextlib.suppress(Exception):
            logger.warning(
                "retrieval_budget_reject",
                extra={
                    "reason": reason,
                    "tier": tier_label,
                    "collection": collection_label,
                    "type": result_type,
                    "tokens": result_tokens,
                    "score": result.get("score", 0),
                    "budget": budget,
                    "tokens_used": tokens_used,
                },
            )
        try:
            from memory.metrics_push import push_retrieval_reject_metric_async

            push_retrieval_reject_metric_async(
                reason=reason,
                tier=tier_label,
                collection=collection_label,
            )
        except Exception:
            pass

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
            _record_reject(result, "dedup")
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
            _record_reject(result, "score_gap")
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
            # BUG-297 / BP-158 P1: emit structured observability so this
            # silent-drop class is no longer silent. fallback_signaled fires
            # when an agent_handoff is the rejected result.
            _record_reject(result, "budget_exceeded", result_tokens=result_tokens)
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

    if return_meta:
        meta = {
            "fallback_signaled": fallback_signaled,
            "rejects": rejects,
            "budget": budget,
            "tokens_used": tokens_used,
        }
        return selected, tokens_used, meta
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
