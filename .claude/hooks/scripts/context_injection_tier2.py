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

import json
import logging
import os
import sys
import time

INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import get_config
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


def main() -> int:
    start_time = time.perf_counter()
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

        # Load session state
        state = InjectionSessionState.load(session_id)
        state.turn_count += 1

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

                results = search_client.search(
                    query=prompt,
                    collection=route.collection,
                    group_id=gid,
                    limit=config.max_retrievals,
                    fast_mode=True,
                )
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
                            "input": {"query_length": len(prompt), "collections_searched": collection_names},
                            "output": {"error": str(search_err), "results_considered": 0, "results_selected": 0},
                            "metadata": {
                                "collections_searched": collection_names,
                                "error": type(search_err).__name__,
                                "results_considered": 0,
                                "results_selected": 0,
                            },
                        },
                        session_id=session_id,
                        project_id=project_name,
                    )
                except Exception:
                    pass
            raise
        finally:
            search_client.close()

        # Sort by score descending
        all_results.sort(key=lambda r: r.get("score", 0), reverse=True)

        # Confidence gate
        best_score = all_results[0].get("score", 0) if all_results else 0.0

        if best_score < config.injection_confidence_threshold:
            # Skip injection — results not relevant enough
            logger.info(
                "tier2_confidence_skip",
                extra={
                    "best_score": round(best_score, 4),
                    "threshold": config.injection_confidence_threshold,
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

        # Greedy fill with deduplication
        selected, tokens_used = select_results_greedy(
            results=all_results,
            budget=budget,
            excluded_ids=state.injected_point_ids,
        )

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
        formatted = format_injection_output(selected, tier=2)

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
            topic_drift=drift,
            collections_searched=collection_names,
        )

        # SPEC-021: context_retrieval span — retrieval pipeline complete
        if emit_trace_event:
            try:
                emit_trace_event(
                    event_type="context_retrieval",
                    data={
                        "input": {"query_length": len(prompt), "collections_searched": collection_names},
                        "output": {"results_considered": len(all_results), "results_selected": len(selected), "tokens_used": tokens_used},
                        "metadata": {
                            "collections_searched": collection_names,
                            "results_considered": len(all_results),
                            "results_selected": len(selected),
                            "tokens_used": tokens_used,
                            "budget": budget,
                            "best_score": round(best_score, 4),
                            "topic_drift": round(drift, 4),
                        },
                    },
                    session_id=session_id,
                    project_id=project_name,
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
                emit_trace_event(
                    event_type="context_retrieval",
                    data={
                        "input": {"query_length": len(prompt) if "prompt" in dir() else 0},
                        "output": {"error": str(e), "results_considered": 0, "results_selected": 0},
                        "metadata": {"error": type(e).__name__, "results_considered": 0, "results_selected": 0},
                    },
                    session_id=session_id if "session_id" in dir() else "unknown",
                    project_id=project_name,
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
