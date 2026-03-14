#!/usr/bin/env python3
# .claude/hooks/scripts/session_start.py
"""SessionStart hook - retrieves relevant memories for context injection.

THE MAGIC MOMENT - This is where Claude "remembers" across sessions!

Architecture Reference: architecture.md:864-941 (SessionStart Hook)
Best Practices (2026):
- https://code.claude.com/docs/en/hooks (Claude Code Hooks Reference)
- https://python-client.qdrant.tech/ (Qdrant Python Client 1.16+)
- https://signoz.io/guides/python-logging-best-practices/ (Structured Logging 2025)
"""

# LANGFUSE: Uses trace buffer (Path A). See LANGFUSE-INTEGRATION-SPEC.md §3.1, §4, §7.7
# SDK VERSION: V3 ONLY. Do NOT use Langfuse() constructor, start_span(), or start_generation().
# CONSTANT: TRACE_CONTENT_MAX = 10000 (no other value permitted)

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Add src to path for system python3 execution
# Use INSTALL_DIR to find installed module (fixes path calculation bug)
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
local_src = os.path.join(INSTALL_DIR, "src")

# Always use INSTALL_DIR for src path (multi-project support)
sys.path.insert(0, local_src)

from memory.activity_log import (
    log_conversation_context_injection,
)
from memory.chunking.truncation import count_tokens
from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    get_config,
)
from memory.filters import (
    filter_low_value_content,
    smart_truncate,
)
from memory.health import check_qdrant_health
from memory.metrics_push import (
    push_session_injection_metrics_async,
    track_hook_duration,
)
from memory.project import detect_project
from memory.qdrant_client import get_qdrant_client

# SPEC-021: Trace buffer for retrieval instrumentation
try:
    from memory.trace_buffer import emit_trace_event
except ImportError:
    emit_trace_event = None

TRACE_CONTENT_MAX = 10000  # Max chars for Langfuse input/output fields

# Configure structured logging (Story 6.2)
# Log to stderr since stdout is reserved for context injection
handler = logging.StreamHandler(sys.stderr)
from memory.logging_config import StructuredFormatter

handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Note: Inline metrics removed - using push_* functions from metrics_push module instead
# See TECH-DEBT-070 for push-based metrics architecture


def inject_with_priority(
    session_summaries: list[dict], other_memories: list[dict], token_budget: int
) -> str:
    """Inject memories with priority ordering (TECH-DEBT-047).

    Session summaries get first claim on token budget (60%), followed by
    other memories (40%). This ensures recent conversation context takes
    priority over older decisions/patterns.

    Args:
        session_summaries: List of session summary dicts with content, timestamp, type
        other_memories: List of other memory dicts (decisions, patterns, conventions)
        token_budget: Total token budget for injection

    Returns:
        Formatted markdown string with prioritized context injection.

    Priority allocation:
        - 60% of budget for session summaries (conversation context)
        - 40% of budget for other memories (decisions, patterns, conventions)

    Example:
        >>> summaries = [{"content": "Implemented feature X", "timestamp": "2026-01-21T10:00:00Z", "type": "session"}]
        >>> memories = [{"content": "Decision: Use Qdrant", "type": "decision", "score": 0.85}]
        >>> result = inject_with_priority(summaries, memories, token_budget=2000)
        >>> "Implemented feature X" in result
        True
        >>> "Decision: Use Qdrant" in result
        True
    """
    # Validate token budget (TECH-DEBT-047 LOW-10 fix)
    if token_budget <= 0:
        logger.warning(
            "inject_with_priority_invalid_budget", extra={"budget": token_budget}
        )
        return ""

    result = []
    tokens_used = 0

    # Phase 1: Session summaries (60% of budget, highest priority)
    summary_budget = int(token_budget * 0.6)
    logger.debug(
        "priority_injection_phase1_summaries",
        extra={
            "summary_budget": summary_budget,
            "summary_count": len(session_summaries),
        },
    )

    if session_summaries:
        header = "## Session Summaries\n"
        result.append(header)
        tokens_used += count_tokens(header)  # Account for header tokens
        summaries_added = 0

        for summary in session_summaries:
            content = summary.get("content", "")
            timestamp = summary.get("timestamp", "")

            # Apply filter_low_value_content (TECH-DEBT-047 AC)
            # LOW-8 fix: Add error handling for filter failures
            try:
                filtered_content = filter_low_value_content(content)
            except Exception as e:
                logger.warning("filter_failed_using_original", extra={"error": str(e)})
                filtered_content = content  # Fallback to unfiltered

            if not filtered_content.strip():
                continue  # Skip empty after filtering

            # Smart truncate if needed
            try:
                if len(filtered_content) > 2000:
                    filtered_content = smart_truncate(filtered_content, 2000)
            except Exception as e:
                logger.warning("smart_truncate_failed", extra={"error": str(e)})
                # Fall back to simple truncation
                if len(filtered_content) > 2000:
                    filtered_content = filtered_content[:2000] + "..."

            # Format the summary once (to estimate full size including markdown overhead)
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M")
                except (ValueError, AttributeError):
                    time_str = ""

            prefix = f"**Summary [{time_str}]:**" if time_str else "**Summary:**"
            formatted_summary = f"{prefix} {filtered_content}\n"

            # Estimate tokens for full formatted summary (includes markdown overhead)
            summary_tokens = count_tokens(formatted_summary)

            # Check if adding this summary would exceed summary budget
            if tokens_used + summary_tokens > summary_budget:
                # LOW-9 fix: Add granular per-item logging
                logger.debug(
                    "summary_skipped_budget_exceeded",
                    extra={
                        "summary_content": content,
                        "summary_tokens": summary_tokens,
                        "budget_remaining": summary_budget - tokens_used,
                        "summary_index": summaries_added,
                        "tokens_used": tokens_used,
                        "summary_budget": summary_budget,
                    },
                )
                break  # Stop adding summaries

            # Add formatted summary
            result.append(formatted_summary)
            tokens_used += summary_tokens
            summaries_added += 1

        logger.info(
            "priority_injection_phase1_complete",
            extra={
                "summaries_added": summaries_added,
                "tokens_used": tokens_used,
                "summary_budget": summary_budget,
            },
        )

        # BUG-026 FIX: Extract rich context from most recent summary
        # V2.1 Architecture stores first_user_prompt, last_user_prompts, last_agent_responses
        if session_summaries:
            most_recent = session_summaries[0]

            # Add recent user messages from rich summary
            last_user_prompts = most_recent.get("last_user_prompts", [])
            if last_user_prompts and tokens_used < summary_budget:
                user_header = "\n## Recent User Messages\n"
                result.append(user_header)
                tokens_used += count_tokens(user_header)

                for prompt_data in last_user_prompts:
                    if tokens_used >= summary_budget:
                        break
                    content = (
                        prompt_data.get("content", "")
                        if isinstance(prompt_data, dict)
                        else str(prompt_data)
                    )
                    if not content or not content.strip():
                        continue

                    # Filter and truncate
                    try:
                        filtered_content = filter_low_value_content(content)
                    except Exception:
                        filtered_content = content
                    if not filtered_content.strip():
                        continue
                    if len(filtered_content) > 1000:
                        try:
                            filtered_content = smart_truncate(filtered_content, 1000)
                        except Exception:
                            filtered_content = filtered_content[:1000] + "..."

                    formatted_prompt = f"**User:** {filtered_content}\n"
                    prompt_tokens = count_tokens(formatted_prompt)
                    if tokens_used + prompt_tokens <= summary_budget:
                        result.append(formatted_prompt)
                        tokens_used += prompt_tokens

            # Add recent agent responses from rich summary
            last_agent_responses = most_recent.get("last_agent_responses", [])
            if last_agent_responses and tokens_used < summary_budget:
                agent_header = "\n## Agent Context Summary\n"
                result.append(agent_header)
                tokens_used += count_tokens(agent_header)

                for response_data in last_agent_responses:
                    if tokens_used >= summary_budget:
                        break
                    content = (
                        response_data.get("content", "")
                        if isinstance(response_data, dict)
                        else str(response_data)
                    )
                    if not content or not content.strip():
                        continue

                    # Filter and truncate more aggressively for agent responses
                    try:
                        filtered_content = filter_low_value_content(content)
                    except Exception:
                        filtered_content = content
                    if not filtered_content.strip():
                        continue
                    if len(filtered_content) > 500:
                        try:
                            filtered_content = smart_truncate(filtered_content, 500)
                        except Exception:
                            filtered_content = filtered_content[:500] + "..."

                    formatted_response = f"**Agent:** {filtered_content}\n"
                    response_tokens = count_tokens(formatted_response)
                    if tokens_used + response_tokens <= summary_budget:
                        result.append(formatted_response)
                        tokens_used += response_tokens

            logger.info(
                "priority_injection_rich_context_added",
                extra={
                    "user_prompts_available": len(last_user_prompts),
                    "agent_responses_available": len(last_agent_responses),
                    "tokens_used_after_rich": tokens_used,
                    "summary_budget": summary_budget,
                },
            )

    # Phase 2: Other memories (fixed 40% allocation)
    # Fixed 40% allocation for other memories (Phase 2)
    fixed_other_budget = int(token_budget * 0.4)
    # But respect global limit - don't exceed total budget
    max_other_tokens = token_budget - tokens_used
    other_budget = min(fixed_other_budget, max_other_tokens)

    logger.debug(
        "priority_injection_phase2_other_memories",
        extra={
            "fixed_budget": fixed_other_budget,
            "effective_budget": other_budget,
            "other_count": len(other_memories),
            "tokens_used_by_summaries": tokens_used,
        },
    )

    if other_memories and other_budget > 0:
        header = "\n## Related Memories\n"
        result.append(header)
        tokens_used += count_tokens(header)  # Account for header tokens
        memories_added = 0

        for memory in other_memories:
            content = memory.get("content", "")
            memory_type = memory.get("type", "unknown")
            score = memory.get("score", 0.0)

            # Apply filter_low_value_content
            # LOW-8 fix: Add error handling for filter failures
            try:
                filtered_content = filter_low_value_content(content)
            except Exception as e:
                logger.warning("filter_failed_using_original", extra={"error": str(e)})
                filtered_content = content  # Fallback to unfiltered

            if not filtered_content.strip():
                continue

            # Smart truncate if needed (other memories get 500 char limit)
            try:
                if len(filtered_content) > 500:
                    filtered_content = smart_truncate(filtered_content, 500)
            except Exception as e:
                logger.warning("smart_truncate_failed", extra={"error": str(e)})
                # Fall back to simple truncation
                if len(filtered_content) > 500:
                    filtered_content = filtered_content[:500] + "..."

            # Format memory once (to estimate full size including markdown overhead)
            score_str = f" ({int(score * 100)}%)" if score > 0 else ""
            formatted_memory = f"\n**{memory_type}{score_str}:** {filtered_content}\n"

            # Estimate tokens for full formatted memory (includes markdown overhead)
            memory_tokens = count_tokens(formatted_memory)

            # Check if adding this memory would exceed total budget
            if tokens_used + memory_tokens > token_budget:
                # LOW-9 fix: Add granular per-item logging
                logger.debug(
                    "memory_skipped_budget_exceeded",
                    extra={
                        "memory_content": content,
                        "memory_type": memory_type,
                        "memory_tokens": memory_tokens,
                        "budget_remaining": token_budget - tokens_used,
                        "tokens_used": tokens_used,
                        "token_budget": token_budget,
                        "memories_added": memories_added,
                    },
                )
                break  # Stop adding memories

            # Add formatted memory
            result.append(formatted_memory)
            tokens_used += memory_tokens
            memories_added += 1

        logger.info(
            "priority_injection_phase2_complete",
            extra={
                "memories_added": memories_added,
                "tokens_used": tokens_used,
                "token_budget": token_budget,
            },
        )

    logger.info(
        "priority_injection_complete",
        extra={
            "total_tokens_used": tokens_used,
            "token_budget": token_budget,
            "utilization_pct": (
                int((tokens_used / token_budget) * 100) if token_budget > 0 else 0
            ),
        },
    )

    return "\n".join(result)


def _detect_agent_id() -> str:
    """Detect agent ID from environment variables.

    Detection chain: PARZIVAL_AGENT_ID > AI_MEMORY_AGENT_ID > BMAD_AGENT_NAME > "default"
    Used for agent-scoped memory retrieval on compact (PLAN-015 §4.1).
    """
    _raw = (
        os.environ.get("PARZIVAL_AGENT_ID")
        or os.environ.get("AI_MEMORY_AGENT_ID")
        or os.environ.get("BMAD_AGENT_NAME")
        or "default"
    )
    return _raw.strip() or "default"


def cleanup_dedup_lock(lock_path: str) -> None:
    """Clean up session dedup lock file (BUG-020).

    Best-effort removal — silently ignores missing files or permission errors.
    """
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except OSError:
        pass


def main():
    """Retrieve and output relevant memories for Claude context.

    CRITICAL: stdout becomes Claude's context. All diagnostics go to stderr.
    CRITICAL: Always exit 0 - never block Claude startup (FR30, NFR-R1).
    """
    start_time = time.perf_counter()

    with track_hook_duration("SessionStart"):
        try:
            # Parse hook input (SessionStart provides cwd, session_id)
            hook_input = parse_hook_input()

            # Extract context
            cwd = hook_input.get("cwd", os.getcwd())
            session_id = hook_input.get("session_id", "unknown")
            trigger = hook_input.get("source", "unknown")  # resume, compact, clear
            project_name = detect_project(cwd)  # FR13 - automatic project detection

            # BUG-020: Deduplication lock to prevent double execution
            import tempfile

            lock_key = f"{session_id}_{trigger}"
            lock_dir = os.path.join(tempfile.gettempdir(), "ai-memory-locks")
            os.makedirs(lock_dir, exist_ok=True)
            lock_file_path = os.path.join(lock_dir, f"session_start_{lock_key}.lock")

            # Check if lock exists and is recent (within 5 seconds)
            try:
                if os.path.exists(lock_file_path):
                    lock_age = time.time() - os.path.getmtime(lock_file_path)
                    if lock_age < 5.0:
                        logger.info(
                            "session_start_dedup_skipped",
                            extra={
                                "session_id": session_id,
                                "trigger": trigger,
                                "lock_age_seconds": lock_age,
                                "pid": os.getpid(),
                            },
                        )
                        if emit_trace_event:
                            try:
                                emit_trace_event(
                                    event_type="context_retrieval",
                                    data={
                                        "input": f"Session {trigger}: {project_name}",
                                        "output": f"Skipped: dedup lock active (age: {lock_age:.1f}s)",
                                        "metadata": {
                                            "trigger": trigger,
                                            "skipped_reason": "dedup_lock",
                                            "lock_age_seconds": round(lock_age, 2),
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
                                    session_id=session_id,
                                    project_id=project_name,
                                    tags=["injection", "tier1", "bootstrap"],
                                )
                            except Exception:
                                pass
                        # Output empty context so Claude proceeds normally
                        print(
                            json.dumps(
                                {
                                    "hookSpecificOutput": {
                                        "hookEventName": "SessionStart",
                                        "additionalContext": "",
                                    }
                                }
                            )
                        )
                        sys.exit(0)

                # Acquire lock - write current PID
                with open(lock_file_path, "w") as lf:
                    lf.write(str(os.getpid()))
            except OSError:
                # Lock mechanism failure should never block Claude startup
                logger.debug("dedup_lock_failed", extra={"error": "OSError"})

            # BUG-020 DEBUG: Log every hook invocation to detect duplicates
            logger.debug(
                "session_start_invoked",
                extra={
                    "session_id": session_id,
                    "trigger": trigger,
                    "project": project_name,
                    "pid": os.getpid(),
                    "hook_input": hook_input,
                },
            )

            # Check Qdrant health (graceful degradation if down)
            config = get_config()

            if trigger == "resume":
                # DEC-054: No injection on resume — Claude restores session natively
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "v2_resume_no_injection",
                    extra={
                        "trigger": trigger,
                        "session_id": session_id,
                        "project": project_name,
                        "duration_ms": round(duration_ms, 2),
                    },
                )

                # User notification
                print(
                    f"🧠 AI Memory V2.2: Resume (no injection) [{duration_ms:.0f}ms]",
                    file=sys.stderr,
                )

                # Langfuse trace event for resume path
                if emit_trace_event is not None:
                    try:
                        from uuid import uuid4 as _uuid4

                        _resume_trace_id = _uuid4().hex
                        _resume_root_span_id = _uuid4().hex
                        os.environ["LANGFUSE_TRACE_ID"] = _resume_trace_id
                        os.environ["LANGFUSE_ROOT_SPAN_ID"] = _resume_root_span_id
                        if session_id and session_id != "unknown":
                            os.environ["CLAUDE_SESSION_ID"] = session_id

                        emit_trace_event(
                            event_type="session_bootstrap",
                            data={
                                "input": f"Session resume: {project_name}",
                                "output": "No injection — resume (DEC-054)",
                                "metadata": {
                                    "session_type": "resume",
                                    "result_count": 0,
                                    "tokens_injected": 0,
                                    "budget": config.token_budget,
                                    "summary": "Resume: no injection per DEC-054",
                                    "agent_name": os.environ.get(
                                        "CLAUDE_AGENT_NAME", "main"
                                    ),
                                    "agent_role": os.environ.get(
                                        "CLAUDE_AGENT_ROLE", "user"
                                    ),
                                },
                            },
                            span_id=_resume_root_span_id,
                            parent_span_id=None,
                            session_id=session_id,
                            project_id=project_name,
                            tags=["injection", "resume"],
                        )
                    except Exception:
                        pass

                # Empty context JSON
                print(
                    json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "SessionStart",
                                "additionalContext": "",
                            }
                        }
                    )
                )

                cleanup_dedup_lock(lock_file_path)

                sys.exit(0)

            client = get_qdrant_client(config)
            if not check_qdrant_health(client):
                log_empty_session(
                    session_id=session_id,
                    project=project_name,
                    reason="qdrant_unavailable",
                )

                if emit_trace_event:
                    try:
                        emit_trace_event(
                            event_type="context_retrieval",
                            data={
                                "input": f"Session {trigger}: {project_name}",
                                "output": "Qdrant unavailable — graceful degradation",
                                "metadata": {
                                    "trigger": trigger,
                                    "error": "qdrant_unavailable",
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
                            session_id=session_id,
                            project_id=project_name,
                            tags=["injection", "tier1", "bootstrap"],
                        )
                    except Exception:
                        pass

                # Empty context JSON - Claude continues without memories
                print(
                    json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "SessionStart",
                                "additionalContext": "",
                            }
                        }
                    )
                )

                cleanup_dedup_lock(lock_file_path)

                sys.exit(0)

            # V2.0.6 SPEC-012: Progressive Context Injection (AD-6 override of Core Arch V2)
            # clear: No injection - user wants fresh start, delete injection state
            # startup: REMOVED (v2.2.0) — bootstrap moved to aim-parzival-bootstrap skill
            # resume: No injection — Claude restores session natively (DEC-054)
            # compact: Session restore — rich summary only (DEC-055/056)

            if trigger == "clear":
                # User wants fresh start — delete injection state and skip injection
                from memory.injection import InjectionSessionState

                state_path = InjectionSessionState._state_path(session_id)
                state_path.unlink(missing_ok=True)

                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "v2_clear_no_injection",
                    extra={
                        "trigger": trigger,
                        "session_id": session_id,
                        "project": project_name,
                        "duration_ms": round(duration_ms, 2),
                    },
                )

                # User notification
                print(
                    f"🧠 AI Memory V2.0: Fresh start (no injection) [{duration_ms:.0f}ms]",
                    file=sys.stderr,
                )

                # Empty context JSON
                print(
                    json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "SessionStart",
                                "additionalContext": "",
                            }
                        }
                    )
                )

                cleanup_dedup_lock(lock_file_path)

                sys.exit(0)

            # On compact: Inject conversation context to restore working memory (DEC-055/056)
            # SPEC-021: Propagate trace context for compact path
            from uuid import uuid4 as _uuid4

            _compact_trace_id = _uuid4().hex
            _compact_root_span_id = _uuid4().hex
            os.environ["LANGFUSE_TRACE_ID"] = _compact_trace_id
            os.environ["LANGFUSE_ROOT_SPAN_ID"] = _compact_root_span_id
            if session_id and session_id != "unknown":
                os.environ["CLAUDE_SESSION_ID"] = session_id

            logger.info(
                "v2_compact_context_injection",
                extra={
                    "trigger": trigger,
                    "session_id": session_id,
                    "project": project_name,
                },
            )

            # TECH-DEBT-047: Priority-based injection
            # Phase 1: Retrieve session summaries (60% of budget)
            # Phase 2: Retrieve other memories (40% of budget)

            if config.parzival_enabled:
                # PARZIVAL PATH: Deterministic retrieval, decisions only
                from memory.search import MemorySearch

                searcher = MemorySearch(config)
                try:
                    # Session summaries via deterministic get_recent
                    try:
                        _retrieval_start = time.perf_counter()
                        session_summary_results = searcher.get_recent(
                            collection=COLLECTION_DISCUSSIONS,
                            group_id=project_name,
                            memory_type=["session"],
                            agent_id="parzival",
                            limit=3,
                        )
                        session_summaries = []
                        for r in session_summary_results:
                            session_summaries.append(
                                {
                                    "content": r.get("content", ""),
                                    "timestamp": r.get(
                                        "created_at", r.get("timestamp", "")
                                    ),
                                    "type": r.get("type", "session"),
                                    "first_user_prompt": r.get("first_user_prompt", ""),
                                    "last_user_prompts": r.get("last_user_prompts", []),
                                    "last_agent_responses": r.get(
                                        "last_agent_responses", []
                                    ),
                                    "session_metadata": r.get("session_metadata", {}),
                                }
                            )
                        # TD-228: Trace event for Parzival session summaries retrieval
                        if emit_trace_event:
                            try:
                                _retrieval_ms = (
                                    time.perf_counter() - _retrieval_start
                                ) * 1000
                                emit_trace_event(
                                    event_type="memory_retrieval_session_summaries",
                                    data={
                                        "input": f"get_recent(discussions, type=session, agent_id=parzival, limit=3) for {project_name}",
                                        "output": f"Retrieved {len(session_summaries)} session summaries",
                                        "metadata": {
                                            "trigger": trigger,
                                            "collection": COLLECTION_DISCUSSIONS,
                                            "memory_type": "session",
                                            "method": "get_recent",
                                            "result_count": len(session_summaries),
                                            "retrieval_ms": round(_retrieval_ms, 2),
                                            "parzival_enabled": True,
                                            "agent_name": os.environ.get(
                                                "CLAUDE_AGENT_NAME", "main"
                                            ),
                                            "agent_role": os.environ.get(
                                                "CLAUDE_AGENT_ROLE", "user"
                                            ),
                                        },
                                    },
                                    session_id=session_id,
                                    project_id=project_name,
                                    tags=["injection", "tier1", "bootstrap"],
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(
                            "parzival_session_summaries_retrieval_failed",
                            extra={"session_id": session_id, "error": str(e)},
                        )
                        session_summaries = []

                    # Other memories: decisions ONLY (no conventions, no patterns)
                    other_memories = []
                    memories_per_collection = {
                        COLLECTION_DISCUSSIONS: 0,
                        COLLECTION_CODE_PATTERNS: 0,
                        COLLECTION_CONVENTIONS: 0,
                    }
                    try:
                        _retrieval_start = time.perf_counter()
                        decisions = searcher.get_recent(
                            collection=COLLECTION_DISCUSSIONS,
                            group_id=project_name,
                            memory_type=["decision"],
                            agent_id="parzival",
                            limit=5,
                        )
                        other_memories.extend(decisions)
                        memories_per_collection[COLLECTION_DISCUSSIONS] = len(decisions)
                        # TD-228: Trace event for Parzival decisions retrieval
                        if emit_trace_event:
                            try:
                                _retrieval_ms = (
                                    time.perf_counter() - _retrieval_start
                                ) * 1000
                                emit_trace_event(
                                    event_type="memory_retrieval_decisions",
                                    data={
                                        "input": f"get_recent(discussions, type=decision, agent_id=parzival, limit=5) for {project_name}",
                                        "output": f"Retrieved {len(decisions)} decisions",
                                        "metadata": {
                                            "trigger": trigger,
                                            "collection": COLLECTION_DISCUSSIONS,
                                            "memory_type": "decision",
                                            "method": "get_recent",
                                            "result_count": len(decisions),
                                            "retrieval_ms": round(_retrieval_ms, 2),
                                            "parzival_enabled": True,
                                            "agent_name": os.environ.get(
                                                "CLAUDE_AGENT_NAME", "main"
                                            ),
                                            "agent_role": os.environ.get(
                                                "CLAUDE_AGENT_ROLE", "user"
                                            ),
                                        },
                                    },
                                    session_id=session_id,
                                    project_id=project_name,
                                    tags=["injection", "tier1", "bootstrap"],
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(
                            "other_memories_retrieval_failed",
                            extra={"session_id": session_id, "error": str(e)},
                        )
                finally:
                    searcher.close()

                # TASK-034: Re-inject Parzival constraints after compact
                # Ensures behavioral constraints survive context compaction
                try:
                    from memory.injection import load_parzival_constraints

                    _constraints = load_parzival_constraints(os.getcwd())
                    if _constraints:
                        _parzival_constraints_context = f"\n\n{_constraints}"
                    else:
                        _parzival_constraints_context = ""
                except Exception:
                    _parzival_constraints_context = ""

                # Clear injected point dedup state after compact
                try:
                    from memory.injection import InjectionSessionState

                    _parz_compact_state = InjectionSessionState.load(session_id)
                    _parz_compact_state.reset_after_compact()
                    _parz_compact_state.save()
                except Exception:
                    pass  # Non-fatal: dedup state clearing is best-effort

            else:
                # NON-PARZIVAL PATH: Agent-scoped compact restore (PLAN-015 §4.1, DEC-055)
                from memory.injection import InjectionSessionState
                from memory.search import MemorySearch

                # Detect agent identity for scoped retrieval
                _compact_agent_id = _detect_agent_id()

                # Load state to determine summary count (1st compact = 1, 2nd+ = 2)
                _compact_state = InjectionSessionState.load(session_id)
                _summary_limit = 1 if _compact_state.compact_count == 0 else 2

                # Defensive initialization — ensures variables are always defined
                # even if the try block fails partway through (Fix 4)
                session_summaries = []
                decisions = []

                searcher = MemorySearch(config)
                try:
                    _retrieval_start = time.perf_counter()

                    # Build get_recent kwargs — add agent_id filter for named agents
                    _summary_kwargs: dict = {
                        "collection": COLLECTION_DISCUSSIONS,
                        "group_id": project_name,
                        "memory_type": ["session"],
                        "limit": _summary_limit,
                    }
                    if _compact_agent_id not in ("default", "parzival"):
                        _summary_kwargs["agent_id"] = _compact_agent_id

                    session_summary_results = searcher.get_recent(**_summary_kwargs)
                    session_summaries = []
                    for r in session_summary_results:
                        session_summaries.append(
                            {
                                "content": r.get("content", ""),
                                "timestamp": r.get(
                                    "created_at", r.get("timestamp", "")
                                ),
                                "type": r.get("type", "session"),
                                "first_user_prompt": r.get("first_user_prompt", ""),
                                "last_user_prompts": r.get("last_user_prompts", []),
                                "last_agent_responses": r.get(
                                    "last_agent_responses", []
                                ),
                                "session_metadata": r.get("session_metadata", {}),
                            }
                        )

                    # TD-228: Per-search trace for session summaries (compact path)
                    if emit_trace_event:
                        try:
                            emit_trace_event(
                                event_type="memory_retrieval_sessions",
                                data={
                                    "input": f"get_recent(discussions, type=session, agent_id={_compact_agent_id!r}, limit={_summary_limit}) for {project_name}",
                                    "output": f"Retrieved {len(session_summaries)} session summaries",
                                    "metadata": {
                                        "trigger": trigger,
                                        "collection": COLLECTION_DISCUSSIONS,
                                        "query_type": "session",
                                        "method": "get_recent",
                                        "agent_id": _compact_agent_id,
                                        "limit": _summary_limit,
                                        "result_count": len(session_summaries),
                                        "top_results": [
                                            {
                                                "type": s.get("type", "session"),
                                                "content_preview": s.get("content", "")[:200],
                                            }
                                            for s in session_summaries[:5]
                                        ],
                                    },
                                },
                                session_id=session_id,
                                project_id=project_name,
                                tags=["injection", "compact"],
                            )
                        except Exception:
                            pass

                    # Retrieve decisions (PLAN-015 §4.1 — non-Parzival gets max 3)
                    _decision_kwargs: dict = {
                        "collection": COLLECTION_DISCUSSIONS,
                        "group_id": project_name,
                        "memory_type": ["decision"],
                        "limit": 3,
                    }
                    if _compact_agent_id not in ("default", "parzival"):
                        _decision_kwargs["agent_id"] = _compact_agent_id

                    try:
                        _decision_results = searcher.get_recent(**_decision_kwargs)
                        decisions = []
                        for r in _decision_results:
                            decisions.append(
                                {
                                    "content": r.get("content", ""),
                                    "timestamp": r.get(
                                        "created_at", r.get("timestamp", "")
                                    ),
                                    "type": r.get("type", "decision"),
                                    "score": r.get("score", 0.0),
                                }
                            )
                    except Exception as e:
                        logger.warning(
                            "compact_decisions_retrieval_failed",
                            extra={"session_id": session_id, "error": str(e)},
                        )
                        decisions = []

                    # TD-228: Per-search trace for decisions (compact path)
                    if emit_trace_event:
                        try:
                            emit_trace_event(
                                event_type="memory_retrieval_decisions",
                                data={
                                    "input": f"get_recent(discussions, type=decision, agent_id={_compact_agent_id!r}, limit=3) for {project_name}",
                                    "output": f"Retrieved {len(decisions)} decisions",
                                    "metadata": {
                                        "trigger": trigger,
                                        "collection": COLLECTION_DISCUSSIONS,
                                        "query_type": "decision",
                                        "method": "get_recent",
                                        "agent_id": _compact_agent_id,
                                        "limit": 3,
                                        "result_count": len(decisions),
                                        "top_results": [
                                            {
                                                "type": d.get("type", "decision"),
                                                "score": round(d.get("score", 0.0), 4),
                                                "content_preview": d.get("content", "")[:200],
                                            }
                                            for d in decisions[:5]
                                        ],
                                    },
                                },
                                session_id=session_id,
                                project_id=project_name,
                                tags=["injection", "compact"],
                            )
                        except Exception:
                            pass

                    _retrieval_ms = (time.perf_counter() - _retrieval_start) * 1000

                    # TD-228 compatible trace event
                    if emit_trace_event:
                        try:
                            emit_trace_event(
                                event_type="memory_retrieval_session_summaries",
                                data={
                                    "input": f"compact restore for agent={_compact_agent_id}, limit={_summary_limit}",
                                    "output": f"Retrieved {len(session_summaries)} summaries, {len(decisions)} decisions",
                                    "metadata": {
                                        "trigger": trigger,
                                        "collection": COLLECTION_DISCUSSIONS,
                                        "method": "get_recent",
                                        "agent_id": _compact_agent_id,
                                        "compact_count": _compact_state.compact_count,
                                        "summary_limit": _summary_limit,
                                        "result_count": len(session_summaries),
                                        "decisions_count": len(decisions),
                                        "retrieval_ms": round(_retrieval_ms, 2),
                                        "parzival_enabled": False,
                                    },
                                },
                                session_id=session_id,
                                project_id=project_name,
                                tags=["injection", "tier1", "bootstrap"],
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(
                        "compact_session_summaries_retrieval_failed",
                        extra={"session_id": session_id, "error": str(e)},
                    )
                    session_summaries = []
                    decisions = []
                finally:
                    searcher.close()

                # Update compact state — increment compact_count, clear injected IDs
                _compact_state.reset_after_compact()
                _compact_state.save()

                other_memories = decisions
                memories_per_collection = {
                    COLLECTION_DISCUSSIONS: len(decisions),
                    COLLECTION_CODE_PATTERNS: 0,
                    COLLECTION_CONVENTIONS: 0,
                }

            # Use priority injection (TECH-DEBT-047)
            conversation_context = inject_with_priority(
                session_summaries=session_summaries,
                other_memories=other_memories,
                token_budget=config.token_budget,
            )

            # Calculate duration for logging
            duration_ms = (time.perf_counter() - start_time) * 1000
            duration_seconds = duration_ms / 1000.0

            # V2.2 compact behavior: Output conversation context only (no general memory search)
            if conversation_context:
                # CR-3.5 HIGH FIX: Validate token budget before injection
                context_char_count = len(conversation_context)
                # Conservative token estimate: 1 token ≈ 3 chars (matches count_tokens())
                estimated_tokens = (context_char_count + 2) // 3
                token_budget = config.token_budget

                if estimated_tokens > token_budget:
                    # Context exceeds budget - truncate to fit
                    target_chars = token_budget * 3
                    conversation_context = (
                        conversation_context[:target_chars]
                        + f"\n\n... [truncated - exceeded token budget of {token_budget} tokens]"
                    )
                    logger.warning(
                        "context_truncated_budget_exceeded",
                        extra={
                            "session_id": session_id,
                            "project": project_name,
                            "original_chars": context_char_count,
                            "truncated_chars": target_chars,
                            "token_budget": token_budget,
                            "estimated_tokens": estimated_tokens,
                        },
                    )

                # Log successful conversation context retrieval
                message_count = conversation_context.count(
                    "**User"
                ) + conversation_context.count("**Agent")
                summary_count = conversation_context.count("**Summary")
                total_count = message_count + summary_count

                # TD-228: Greedy-fill trace event for compact injection
                if emit_trace_event:
                    try:
                        _gf_input_count = len(session_summaries) + len(other_memories)
                        _gf_tokens_est = (len(conversation_context) + 2) // 3
                        _gf_dropped = max(0, _gf_input_count - total_count)
                        emit_trace_event(
                            event_type="greedy_fill",
                            data={
                                "input": f"inject_with_priority: {_gf_input_count} candidates, budget={config.token_budget} tokens",
                                "output": f"Selected {total_count} items ({summary_count} summaries, {message_count} messages), dropped {_gf_dropped}",
                                "metadata": {
                                    "trigger": trigger,
                                    "input_count": _gf_input_count,
                                    "selected_count": total_count,
                                    "dropped_count": _gf_dropped,
                                    "summary_count": summary_count,
                                    "message_count": message_count,
                                    "tokens_used_est": _gf_tokens_est,
                                    "budget": config.token_budget,
                                    "budget_used_pct": (
                                        round(_gf_tokens_est / config.token_budget * 100, 1)
                                        if config.token_budget > 0
                                        else 0
                                    ),
                                },
                            },
                            session_id=session_id,
                            project_id=project_name,
                            tags=["injection", "compact"],
                        )
                    except Exception:
                        pass

                logger.info(
                    "conversation_context_injected",
                    extra={
                        "session_id": session_id,
                        "project": project_name,
                        "message_count": message_count,
                        "summary_count": summary_count,
                        "duration_ms": round(duration_ms, 2),
                        "final_chars": len(conversation_context),
                    },
                )

                # User notification - conversation context injected
                print(
                    f"🧠 AI Memory V2.0: Conversation context restored ({total_count} items: {summary_count} summaries, {message_count} messages) [{duration_ms:.0f}ms]",
                    file=sys.stderr,
                )

                # BUG-020 DEBUG: Log counts before activity log write
                logger.debug(
                    "pre_activity_log",
                    extra={
                        "session_id": session_id,
                        "trigger": trigger,
                        "message_count": message_count,
                        "summary_count": summary_count,
                        "total_count": total_count,
                        "pid": os.getpid(),
                    },
                )

                # Activity log for visibility (V2.0 - log what was actually injected)
                log_conversation_context_injection(
                    project=project_name,
                    trigger=trigger,
                    message_count=message_count,
                    summary_count=summary_count,
                    duration_ms=duration_ms,
                    context_preview=(
                        conversation_context if conversation_context else ""
                    ),
                )

                # TECH-DEBT-070: Push metrics to Pushgateway (async to avoid latency)
                token_count = count_tokens(conversation_context)
                from memory.metrics_push import (
                    push_context_injection_metrics_async,
                    push_token_metrics_async,
                )

                # BUG-021 fix: Push context injection metrics per collection
                # Distribute tokens proportionally based on memory counts
                total_memories = sum(memories_per_collection.values()) + len(
                    session_summaries
                )
                if total_memories > 0:
                    # Session summaries go to discussions collection
                    session_tokens = int(
                        token_count * len(session_summaries) / total_memories
                    )
                    if session_tokens > 0:
                        push_context_injection_metrics_async(
                            hook_type="SessionStart",
                            collection=COLLECTION_DISCUSSIONS,
                            project=project_name,
                            token_count=session_tokens,
                        )
                    # Other memories by their source collection
                    for collection, count in memories_per_collection.items():
                        if count > 0:
                            collection_tokens = int(
                                token_count * count / total_memories
                            )
                            if collection_tokens > 0:
                                push_context_injection_metrics_async(
                                    hook_type="SessionStart",
                                    collection=collection,
                                    project=project_name,
                                    token_count=collection_tokens,
                                )
                else:
                    # Fallback: all tokens to discussions
                    push_context_injection_metrics_async(
                        hook_type="SessionStart",
                        collection=COLLECTION_DISCUSSIONS,
                        project=project_name,
                        token_count=token_count,
                    )

                push_token_metrics_async(
                    operation="injection",
                    direction="output",
                    project=project_name,
                    token_count=token_count,
                )

                # TECH-DEBT-089: Push session injection duration for NFR-P3 tracking
                push_session_injection_metrics_async(project_name, duration_seconds)

                # SPEC-021: context_retrieval span — resume/compact retrieval detail
                if emit_trace_event:
                    try:
                        collections_searched = [COLLECTION_DISCUSSIONS]
                        if memories_per_collection.get(COLLECTION_CODE_PATTERNS, 0) > 0:
                            collections_searched.append(COLLECTION_CODE_PATTERNS)
                        if memories_per_collection.get(COLLECTION_CONVENTIONS, 0) > 0:
                            collections_searched.append(COLLECTION_CONVENTIONS)
                        emit_trace_event(
                            event_type="context_retrieval",
                            data={
                                "input": f"Session {trigger} retrieval: {project_name}",
                                "output": f"Injected {total_count} items ({summary_count} summaries, {message_count} messages)",
                                "metadata": {
                                    "trigger": trigger,
                                    "collections_searched": collections_searched,
                                    "results_considered": len(session_summaries)
                                    + sum(memories_per_collection.values()),
                                    "results_selected": total_count,
                                    "summary_count": summary_count,
                                    "memory_counts": {
                                        k: v
                                        for k, v in memories_per_collection.items()
                                        if v > 0
                                    },
                                    "tokens_used": token_count,
                                    "budget": config.token_budget,
                                    "results_detail": [
                                        {
                                            "type": s.get("type", "session_summary"),
                                            "tokens": (
                                                count_tokens(s.get("content", ""))
                                                if s.get("content")
                                                else 0
                                            ),
                                        }
                                        for s in session_summaries[:10]
                                    ]
                                    + [
                                        {
                                            "type": m.get("type", "unknown"),
                                            "collection": m.get(
                                                "collection", "unknown"
                                            ),
                                            "score": round(m.get("score", 0), 4),
                                            "tokens": (
                                                count_tokens(m.get("content", ""))
                                                if m.get("content")
                                                else 0
                                            ),
                                        }
                                        for m in other_memories[:10]
                                    ],
                                    "agent_name": os.environ.get(
                                        "CLAUDE_AGENT_NAME", "main"
                                    ),
                                    "agent_role": os.environ.get(
                                        "CLAUDE_AGENT_ROLE", "user"
                                    ),
                                },
                            },
                            session_id=session_id,
                            project_id=project_name,
                            tags=["injection", "tier1", "bootstrap"],
                        )
                    except Exception:
                        pass

                # SPEC-021: Langfuse trace for session restore (root span)
                if emit_trace_event:
                    try:
                        emit_trace_event(
                            event_type="session_bootstrap",
                            data={
                                "input": f"Session {trigger}: {project_name}",
                                "output": conversation_context[:TRACE_CONTENT_MAX],
                                "metadata": {
                                    "session_type": trigger,
                                    "result_count": total_count,
                                    "tokens_injected": token_count,
                                    "budget": config.token_budget,
                                    "summary": f"Injected {token_count} tokens from {total_count} results",
                                    "result_types": [
                                        s.get("type", "session_summary")
                                        for s in session_summaries[:10]
                                    ]
                                    + [
                                        m.get("type", "unknown")
                                        for m in other_memories[:10]
                                    ],
                                    "result_scores": [
                                        0.0 for _ in session_summaries[:10]
                                    ]
                                    + [
                                        round(m.get("score", 0), 4)
                                        for m in other_memories[:10]
                                    ],
                                    "agent_name": os.environ.get(
                                        "CLAUDE_AGENT_NAME", "main"
                                    ),
                                    "agent_role": os.environ.get(
                                        "CLAUDE_AGENT_ROLE", "user"
                                    ),
                                },
                            },
                            span_id=_compact_root_span_id,
                            parent_span_id=None,
                            session_id=session_id,
                            project_id=project_name,
                            tags=["injection", "tier1", "bootstrap"],
                        )
                    except Exception:
                        logger.debug("trace_event_failed_session_restore")

                # Output conversation context to Claude
                # TECH-DEBT-115: Add <retrieved_context> delimiters per BP-039 §1
                formatted_context = (
                    f"<retrieved_context>\n{conversation_context}\n</retrieved_context>"
                )

                # TASK-034: Append Parzival constraints after compact
                if config.parzival_enabled:
                    try:
                        _constraints_ctx = _parzival_constraints_context
                    except NameError:
                        _constraints_ctx = ""
                    if _constraints_ctx:
                        formatted_context += f"\n\n<parzival_constraints>{_constraints_ctx}\n</parzival_constraints>"

                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": formatted_context,
                    }
                }
                print(json.dumps(output))

                cleanup_dedup_lock(lock_file_path)

                sys.exit(0)
            else:
                # No conversation context available (new session or no prior conversation)
                logger.warning(
                    "no_conversation_context",
                    extra={
                        "session_id": session_id,
                        "project": project_name,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                if emit_trace_event:
                    try:
                        emit_trace_event(
                            event_type="context_retrieval",
                            data={
                                "input": f"Session {trigger} retrieval: {project_name}",
                                "output": "No conversation context available",
                                "metadata": {
                                    "trigger": trigger,
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
                            session_id=session_id,
                            project_id=project_name,
                            tags=["injection", "tier1", "bootstrap"],
                        )
                    except Exception:
                        pass

                # User notification - no conversation context
                print(
                    f"🧠 AI Memory V2.0: No conversation context available [{duration_ms:.0f}ms]",
                    file=sys.stderr,
                )

                # Empty context JSON
                print(
                    json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "SessionStart",
                                "additionalContext": "",
                            }
                        }
                    )
                )

                cleanup_dedup_lock(lock_file_path)

                sys.exit(0)

        except Exception as e:
            # CRITICAL: Never crash or block Claude (FR30, NFR-R4)
            logger.error("retrieval_failed", extra={"error": str(e)})

            if emit_trace_event:
                try:
                    _trigger = trigger if "trigger" in dir() else "unknown"
                    _project = project_name if "project_name" in dir() else "unknown"
                    _session = session_id if "session_id" in dir() else "unknown"
                    emit_trace_event(
                        event_type="context_retrieval",
                        data={
                            "input": f"Session {_trigger}: {_project}",
                            "output": f"Fatal error: {type(e).__name__}: {e!s}",
                            "metadata": {
                                "trigger": _trigger,
                                "error": type(e).__name__,
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
                        session_id=_session,
                        project_id=_project,
                        tags=["injection", "tier1", "bootstrap"],
                    )
                except Exception:
                    pass

            # Empty context JSON on error
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "SessionStart",
                            "additionalContext": "",
                        }
                    }
                )
            )
            sys.exit(0)  # Always exit 0


def parse_hook_input() -> dict:
    """Parse JSON input from Claude Code hook system.

    Returns:
        Dict with cwd, session_id, and other context fields.
        Returns empty dict if stdin is empty or malformed (graceful).
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Graceful degradation for malformed input (FR34)
        logger.warning("malformed_hook_input_using_defaults")
        return {}


def log_empty_session(
    session_id: str,
    project: str,
    reason: str,
    query: str = "",
    duration_ms: float = 0.0,
):
    """Log when session retrieval returns no results.

    Args:
        session_id: Session identifier
        project: Project name
        reason: One of "no_memories", "qdrant_unavailable", "below_threshold"
        query: Query string used (optional)
        duration_ms: Time spent attempting retrieval

    Reason codes:
        - "no_memories": No memories exist for this project yet
        - "qdrant_unavailable": Qdrant service is down/unreachable
        - "below_threshold": Memories exist but none above similarity threshold
    """
    logger.warning(
        "session_retrieval_empty",
        extra={
            "session_id": session_id,
            "project": project,
            "reason": reason,
            "query_preview": query[:100] if query else "",
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    )

    # Also log to session file if enabled
    if os.getenv("SESSION_LOG_ENABLED", "false").lower() == "true":
        try:
            from memory.session_logger import log_to_session_file

            log_to_session_file(
                {
                    "session_id": session_id,
                    "project": project,
                    "reason": reason,
                    "results_count": 0,
                    "duration_ms": round(duration_ms, 2),
                }
            )
        except ImportError:
            # Graceful degradation if session_logger unavailable
            pass


if __name__ == "__main__":
    main()
