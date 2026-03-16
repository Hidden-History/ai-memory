#!/usr/bin/env python3
"""Tier 2 Per-Turn Context Injection — UserPromptSubmit retrieval hook.

Supersedes unified_keyword_trigger.py. Provides always-on semantic retrieval
with confidence gating, adaptive token budgets, and collection routing.

Keyword-triggered retrieval (decisions, sessions, best practices) is preserved
as a sub-path within the routing logic — zero regression from the replaced hook.

Architecture: SPEC-012, AD-6, BP-076, BP-089

Exit Codes:
- 0: Success (normal completion, context or empty)
- Non-zero: Never (graceful degradation — always exit 0)

Performance: <500ms total (NFR-P1, NFR-P5)
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4, §7.7
# SDK VERSION: V3 ONLY. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import contextlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    get_config,
)
from memory.health import check_qdrant_health

# SPEC-021: Trace buffer for retrieval instrumentation
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None
from memory.injection import (
    InjectionSessionState,
    compute_adaptive_budget,
    compute_topic_drift,
    format_injection_output,
    log_injection_event,
    route_collections,
    select_results_greedy,
)
from memory.logging_config import StructuredFormatter
from memory.metrics_push import push_hook_metrics_async
from memory.project import detect_project
from memory.qdrant_client import get_qdrant_client
from memory.search import MemorySearch

handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks.tier2")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

TRACE_CONTENT_MAX = 10000  # Max chars for Langfuse input/output fields


def main() -> int:
    start_time = time.perf_counter()
    _wall_start = datetime.now(tz=timezone.utc)
    project_name = "unknown"

    try:
        # Parse hook input
        raw_input = sys.stdin.read()
        hook_input = json.loads(raw_input)
        prompt = hook_input.get("prompt", "")
        session_id = hook_input.get("session_id", "unknown")
        cwd = hook_input.get("cwd", os.getcwd())

        if not prompt or not prompt.strip():
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "",
                        }
                    }
                )
            )
            return 0

        # Detect project
        project_name = detect_project(cwd)
        config = get_config()

        # SPEC-021: Propagate trace context so library function trace events
        # (search.py, injection.py) link to the same Langfuse trace.
        # Root span ID creates a valid OTel parent so child spans nest
        # under one trace (without it, INVALID_SPAN_ID causes separate traces).
        from uuid import uuid4 as _uuid4

        _tier2_trace_id = _uuid4().hex
        _tier2_root_span_id = _uuid4().hex
        os.environ["LANGFUSE_TRACE_ID"] = _tier2_trace_id
        os.environ["LANGFUSE_ROOT_SPAN_ID"] = _tier2_root_span_id
        if session_id and session_id != "unknown":
            os.environ["CLAUDE_SESSION_ID"] = session_id

        # Check if injection is enabled
        if not config.injection_enabled:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "",
                        }
                    }
                )
            )
            return 0

        # Health check (graceful degradation)
        client = get_qdrant_client(config)
        if not check_qdrant_health(client):
            logger.warning("tier2_qdrant_unavailable")
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "",
                        }
                    }
                )
            )
            return 0

        # BUG-171: Skip injection for slash commands (invocations, not queries)
        if re.match(r"^/[\w:./-]+", prompt.strip()):
            logger.info(
                "tier2_skip_command",
                extra={"prompt": prompt[:80], "session_id": session_id},
            )
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "",
                        }
                    }
                )
            )
            return 0

        # Load session state
        state = InjectionSessionState.load(session_id)
        state.turn_count += 1
        # H-3: Clear cross-turn access_count dedup set at start of new turn
        if state.turn_count != state._last_turn_count:
            state.access_count_incremented_this_turn = []
            state._last_turn_count = state.turn_count

        # Route to target collections
        target_collections = route_collections(prompt)
        collection_names = [c.collection for c in target_collections]

        # Search across routed collections
        search_client = MemorySearch(config)
        all_results = []
        current_embedding = None
        try:
            for route in target_collections:
                gid = None if route.shared else project_name

                # PLAN-010 (P10-9): Filter discussions to high-value types only
                search_kwargs = {
                    "query": prompt,
                    "collection": route.collection,
                    "group_id": gid,
                    "limit": config.max_retrievals,
                    "fast_mode": True,
                }
                if route.collection == COLLECTION_DISCUSSIONS:
                    search_kwargs["memory_type"] = [
                        "decision",
                        "guideline",
                        "session",
                        "agent_insight",
                        "agent_handoff",
                        "agent_memory",
                    ]

                # F13/TD-243: Move type exclusion to Qdrant-level must_not filter
                # (replaces Python post-filtering for efficiency).
                # error_pattern excluded at Qdrant query layer instead of post-processing.
                if route.collection == COLLECTION_CODE_PATTERNS:
                    search_kwargs["must_not_types"] = ["error_pattern"]
                    search_kwargs["exclude_expired_freshness"] = (
                        True  # WP-2: Belt-and-suspenders pre-filter (Spec §4.5.3)
                    )
                # H-3: Pass cross-turn dedup list so access_count is incremented once per turn
                search_kwargs["_access_count_dedup"] = state.access_count_incremented_this_turn
                results = search_client.search(**search_kwargs)
                for r in results:
                    r["collection"] = route.collection  # Tag with source collection
                all_results.extend(results)

            # Compute topic drift BEFORE closing (uses embedding_client)
            try:
                current_embedding = search_client.embedding_client.embed([prompt])[0]
            except Exception:
                logger.warning("tier2_drift_embed_failed")
        except Exception as search_err:
            # SPEC-021: context_retrieval span on failure path
            if emit_trace_event:
                try:
                    emit_trace_event(
                        event_type="context_retrieval",
                        data={
                            "input": prompt[:TRACE_CONTENT_MAX],
                            "output": f"Search error: {type(search_err).__name__}: {search_err!s}",
                            "metadata": {
                                "query_length": len(prompt),
                                "collections_searched": collection_names,
                                "error": type(search_err).__name__,
                                "results_considered": 0,
                                "results_selected": 0,
                                "agent_name": os.environ.get(
                                    "CLAUDE_AGENT_NAME", "main"
                                ),
                                "agent_role": os.environ.get(
                                    "CLAUDE_AGENT_ROLE", "user"
                                ),
                            },
                        },
                        span_id=_tier2_root_span_id,
                        parent_span_id=None,
                        session_id=session_id,
                        project_id=project_name,
                        tags=["injection", "tier2"],
                        start_time=_wall_start,
                    )
                except Exception:
                    pass
            raise
        finally:
            search_client.close()

        # Sort by score descending
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        # WP-2: Apply freshness penalty to code-patterns results (Spec §4.2.5, §4.5.3)
        # Applied before gating — penalized scores affect both gating threshold and greedy selection
        _freshness_blocked_count = 0
        for _r in all_results:
            if _r.get("collection") != COLLECTION_CODE_PATTERNS:
                continue
            _fs = (_r.get("freshness_status") or "unknown").lower()
            _penalty = config.get_freshness_penalty(_fs)
            if _penalty == 1.0:
                continue
            _orig_score = _r["score"]
            _r["score"] = _r["score"] * _penalty
            if emit_trace_event:
                with contextlib.suppress(Exception):
                    emit_trace_event(
                        event_type="freshness_penalty_applied",
                        data={
                            "input": f"point_id={_r.get('id')} freshness_status={_fs}"[
                                :TRACE_CONTENT_MAX
                            ],
                            "output": f"score {_orig_score:.4f} → {_r['score']:.4f} (penalty={_penalty})"[
                                :TRACE_CONTENT_MAX
                            ],
                            "metadata": {
                                "point_id": str(_r.get("id")),
                                "freshness_status": _fs,
                                "original_score": round(_orig_score, 4),
                                "penalized_score": round(_r["score"], 4),
                                "penalty_factor": _penalty,
                            },
                        },
                        trace_id=_tier2_trace_id,
                        session_id=session_id,
                        project_id=project_name,
                        tags=["injection", "tier2"],
                    )
            if _penalty == 0.0 and _orig_score > 0.0:
                _freshness_blocked_count += 1

        # Re-sort after penalty application (penalized scores may have changed relative order)
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        # Soft confidence gate (4-tier: hard_skip / soft_skip / soft_gate / full)
        best_score = all_results[0].get("score", 0) if all_results else 0.0

        # WP-2: 4-tier per-collection gating (Spec §4.2.3)
        _best_collection = all_results[0].get("collection") if all_results else None
        _threshold_map = {
            COLLECTION_CONVENTIONS: config.injection_threshold_conventions,
            COLLECTION_CODE_PATTERNS: config.injection_threshold_code_patterns,
            COLLECTION_DISCUSSIONS: config.injection_threshold_discussions,
        }
        _conf_threshold = _threshold_map.get(
            _best_collection, config.injection_confidence_threshold
        )

        if best_score < config.injection_hard_floor:
            gating_mode = "hard_skip"
        elif best_score < _conf_threshold - 0.05:
            gating_mode = "soft_skip"
        elif best_score < _conf_threshold:
            gating_mode = "soft_gate"
        else:
            gating_mode = "full"

        if gating_mode in ("hard_skip", "soft_skip"):
            logger.info(
                "tier2_confidence_skip",
                extra={
                    "best_score": round(best_score, 4),
                    # Log the actual threshold that triggered this gating mode:
                    # hard_skip uses injection_hard_floor; soft_skip uses threshold-0.05
                    "threshold": (
                        config.injection_hard_floor
                        if gating_mode == "hard_skip"
                        else _conf_threshold - 0.05
                    ),
                    "gating_mode": gating_mode,
                    "session_id": session_id,
                    "turn": state.turn_count,
                },
            )
            log_injection_event(
                tier=2,
                trigger="UserPromptSubmit",
                project=project_name,
                session_id=session_id,
                results_considered=len(all_results),
                results_selected=0,
                tokens_used=0,
                budget=0,
                audit_dir=config.audit_dir,
                best_score=best_score,
                skipped_confidence=True,
                gating_mode=gating_mode,
                collections_searched=collection_names,
            )
            state.save()
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "",
                        }
                    }
                )
            )
            return 0

        drift = compute_topic_drift(current_embedding, state.last_query_embedding)

        # Compute adaptive budget
        budget = compute_adaptive_budget(
            best_score=best_score,
            results=all_results,
            session_state={"topic_drift": drift},
            config=config,
        )

        # Soft gating: halve budget for marginal confidence (threshold-0.05 to threshold)
        if gating_mode == "soft_gate":
            original_budget = budget
            budget = max(50, budget // 2)
            logger.info(
                "tier2_soft_gating",
                extra={
                    "best_score": round(best_score, 4),
                    "gating_mode": gating_mode,
                    "original_budget": original_budget,
                    "reduced_budget": budget,
                    "session_id": session_id,
                },
            )

        # Greedy fill with deduplication
        selected, tokens_used = select_results_greedy(
            results=all_results,
            budget=budget,
            excluded_ids=state.injected_point_ids,
            score_gap_threshold=config.injection_score_gap_threshold,
            project_id=project_name,
        )

        # WP-2: Push freshness-blocked counter if any results were blocked this turn
        if _freshness_blocked_count > 0:
            try:
                from memory.metrics_push import push_freshness_blocked_metrics_async

                push_freshness_blocked_metrics_async(
                    count=_freshness_blocked_count,
                    project=project_name,
                )
            except Exception:
                pass

        if not selected:
            logger.info(
                "tier2_no_results_after_dedup",
                extra={
                    "session_id": session_id,
                    "excluded_count": len(state.injected_point_ids),
                },
            )
            state.save()
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": "",
                        }
                    }
                )
            )
            return 0

        # Format output
        formatted = format_injection_output(selected, tier=2, project_id=project_name)

        # Update session state
        state.injected_point_ids.extend(str(r.get("id", "")) for r in selected)
        state.last_query_embedding = current_embedding
        state.topic_drift = drift
        state.total_tokens_injected += tokens_used
        state.save()

        # Audit log
        log_injection_event(
            tier=2,
            trigger="UserPromptSubmit",
            project=project_name,
            session_id=session_id,
            results_considered=len(all_results),
            results_selected=len(selected),
            tokens_used=tokens_used,
            budget=budget,
            audit_dir=config.audit_dir,
            best_score=best_score,
            skipped_confidence=False,
            gating_mode=gating_mode,
            gap_threshold=config.injection_score_gap_threshold,
            topic_drift=drift,
            collections_searched=collection_names,
        )

        # SPEC-021: context_retrieval span — retrieval pipeline complete
        # Uses root span_id so this becomes the parent of library-emitted spans
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="context_retrieval",
                    data={
                        "input": prompt[:TRACE_CONTENT_MAX],
                        "output": formatted[:TRACE_CONTENT_MAX],
                        "metadata": {
                            "query_length": len(prompt),
                            "collections_searched": collection_names,
                            "results_considered": len(all_results),
                            "results_selected": len(selected),
                            "tokens_used": tokens_used,
                            "budget": budget,
                            "best_score": round(best_score, 4),
                            "topic_drift": round(drift, 4),
                            "gating_mode": gating_mode,
                            "gap_threshold": config.injection_score_gap_threshold,
                            "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                            "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                        },
                    },
                    span_id=_tier2_root_span_id,
                    parent_span_id=None,
                    session_id=session_id,
                    project_id=project_name,
                    tags=["injection", "tier2"],
                    start_time=_wall_start,
                )
            except Exception:
                pass

        # Metrics
        duration_seconds = time.perf_counter() - start_time
        push_hook_metrics_async(
            hook_name="UserPromptSubmit_Tier2",
            duration_seconds=duration_seconds,
            success=True,
            project=project_name,
        )

        logger.info(
            "tier2_injection_complete",
            extra={
                "session_id": session_id,
                "turn": state.turn_count,
                "results_selected": len(selected),
                "tokens_used": tokens_used,
                "budget": budget,
                "best_score": round(best_score, 4),
                "drift": round(drift, 4),
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )

        # Output to Claude
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": formatted,
                    }
                }
            )
        )
        return 0

    except Exception as e:
        logger.error(
            "tier2_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )

        # SPEC-021: context_retrieval span on outer failure path
        if emit_trace_event:
            try:
                _prompt_val = prompt if "prompt" in dir() else ""  # type: ignore[name-defined]
                emit_trace_event(
                    event_type="context_retrieval",
                    data={
                        "input": _prompt_val[:TRACE_CONTENT_MAX] if _prompt_val else "",
                        "output": f"Outer exception: {type(e).__name__}: {e!s}",
                        "metadata": {
                            "query_length": len(_prompt_val),
                            "error": type(e).__name__,
                            "results_considered": 0,
                            "results_selected": 0,
                            "agent_name": os.environ.get("CLAUDE_AGENT_NAME", "main"),
                            "agent_role": os.environ.get("CLAUDE_AGENT_ROLE", "user"),
                        },
                    },
                    span_id=_tier2_root_span_id if "_tier2_root_span_id" in dir() else None,  # type: ignore[name-defined]
                    parent_span_id=None,
                    session_id=session_id if "session_id" in dir() else "unknown",  # type: ignore[name-defined]
                    project_id=project_name,
                    tags=["injection", "tier2"],
                    start_time=_wall_start if "_wall_start" in dir() else None,  # type: ignore[name-defined]
                )
            except Exception:
                pass

        # Push failure metrics
        try:
            duration_seconds = time.perf_counter() - start_time
            push_hook_metrics_async(
                hook_name="UserPromptSubmit_Tier2",
                duration_seconds=duration_seconds,
                success=False,
                project=project_name,
            )
        except Exception:
            pass

        try:
            state.save()
        except Exception:
            pass

        # Graceful degradation — never block Claude
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": "",
                    }
                }
            )
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
