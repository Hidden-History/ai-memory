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

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

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
    log_error,
    log_session_start,
)
from memory.config import (
    COLLECTION_CODE_PATTERNS,
    COLLECTION_CONVENTIONS,
    COLLECTION_DISCUSSIONS,
    get_config,
)
from memory.filters import (
    filter_low_value_content,
    is_duplicate_message,
    smart_truncate,
)
from memory.health import check_qdrant_health
from memory.logging_config import configure_logging
from memory.metrics_push import track_hook_duration
from memory.project import detect_project
from memory.qdrant_client import get_qdrant_client

# Configure structured logging (Story 6.2)
# Log to stderr since stdout is reserved for context injection
handler = logging.StreamHandler(sys.stderr)
from memory.logging_config import StructuredFormatter

handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("ai_memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from memory.metrics import (
        hook_duration_seconds,
        memory_retrievals_total,
        retrieval_duration_seconds,
    )
except ImportError:
    # Graceful degradation if metrics unavailable
    logger.warning("metrics_module_unavailable")
    memory_retrievals_total = None
    retrieval_duration_seconds = None
    hook_duration_seconds = None

# TECH-DEBT-067: V2.0 token tracking metrics
try:
    from memory.metrics import context_injection_tokens, tokens_consumed_total
except ImportError:
    tokens_consumed_total = None
    context_injection_tokens = None


def estimate_tokens(content: str) -> int:
    """Estimate token count from content.

    Uses ~3 chars per token (conservative estimate for 2026).
    Previous 4 chars/token was optimistic and caused budget overruns.
    This accounts for markdown syntax, technical terms, and formatting overhead.

    Args:
        content: Text content to estimate tokens for

    Returns:
        Estimated token count (conservative ceiling estimate)
    """
    if not content:
        return 0
    # Conservative estimate: 3 chars per token (2026 best practice)
    # Prevents budget overruns with technical/markdown content
    return (len(content) + 2) // 3  # +2 for ceiling behavior


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
        tokens_used += estimate_tokens(header)  # Account for header tokens
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
            summary_tokens = estimate_tokens(formatted_summary)

            # Check if adding this summary would exceed summary budget
            if tokens_used + summary_tokens > summary_budget:
                # LOW-9 fix: Add granular per-item logging
                logger.debug(
                    "summary_skipped_budget_exceeded",
                    extra={
                        "summary_preview": (
                            content[:50] + "..." if len(content) > 50 else content
                        ),
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
                tokens_used += estimate_tokens(user_header)

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
                    prompt_tokens = estimate_tokens(formatted_prompt)
                    if tokens_used + prompt_tokens <= summary_budget:
                        result.append(formatted_prompt)
                        tokens_used += prompt_tokens

            # Add recent agent responses from rich summary
            last_agent_responses = most_recent.get("last_agent_responses", [])
            if last_agent_responses and tokens_used < summary_budget:
                agent_header = "\n## Agent Context Summary\n"
                result.append(agent_header)
                tokens_used += estimate_tokens(agent_header)

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
                    response_tokens = estimate_tokens(formatted_response)
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
        tokens_used += estimate_tokens(header)  # Account for header tokens
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
            memory_tokens = estimate_tokens(formatted_memory)

            # Check if adding this memory would exceed total budget
            if tokens_used + memory_tokens > token_budget:
                # LOW-9 fix: Add granular per-item logging
                logger.debug(
                    "memory_skipped_budget_exceeded",
                    extra={
                        "memory_preview": (
                            content[:50] + "..." if len(content) > 50 else content
                        ),
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


def retrieve_session_summaries(
    client, project_name: str, limit: int = 20
) -> list[dict]:
    """Retrieve session summaries from discussions collection.

    Extracts shared retrieval logic used by both get_conversation_context()
    and main() to avoid code duplication (TECH-DEBT-047 fix).

    Args:
        client: Qdrant client instance
        project_name: Project group_id for filtering
        limit: Max summaries to retrieve (default 20, then sorted/sliced)

    Returns:
        List of summary dicts sorted by timestamp (most recent first).
        Returns empty list if no summaries found or on error.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from memory.config import TYPE_SESSION

    try:
        summary_filter = Filter(
            must=[
                FieldCondition(key="group_id", match=MatchValue(value=project_name)),
                FieldCondition(key="type", match=MatchValue(value=TYPE_SESSION)),
            ]
        )

        summary_results = client.scroll(
            collection_name=COLLECTION_DISCUSSIONS,
            scroll_filter=summary_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            timeout=2,  # 2s timeout to stay within <3s SLA
        )

        if not summary_results[0]:
            return []

        summaries = []
        for point in summary_results[0]:
            payload = point.payload
            summaries.append(
                {
                    "content": payload.get("content", ""),
                    "timestamp": payload.get(
                        "created_at", payload.get("timestamp", "")
                    ),
                    "type": payload.get("type", "session"),
                    "first_user_prompt": payload.get("first_user_prompt", ""),
                    "last_user_prompts": payload.get("last_user_prompts", []),
                    "last_agent_responses": payload.get("last_agent_responses", []),
                    "session_metadata": payload.get("session_metadata", {}),
                }
            )

        # Sort by timestamp descending (most recent first)
        summaries.sort(key=lambda s: s.get("timestamp", ""), reverse=True)
        return summaries

    except Exception as e:
        logger.warning(
            "retrieve_session_summaries_failed",
            extra={"project_name": project_name, "error": str(e)},
        )
        return []


def get_conversation_context(
    config, session_id: str, project_name: str, limit: int = 3
) -> str:
    """Retrieve rich session summaries for post-compaction context injection.

    V2.1 Simplified Architecture:
    - Only queries session summaries (type=session) from discussions collection
    - Rich summaries contain: first_user_prompt, last_user_prompts, last_agent_responses
    - No need to query individual user_message/agent_response records
    - Supports both resume and compact triggers

    Args:
        config: MemoryConfig instance with connection settings
        session_id: Current session identifier
        project_name: Current project name (group_id) for filtering
        limit: Maximum session summaries to retrieve (default 3)

    Returns:
        Formatted markdown string with session context,
        or empty string if no summaries found.

    Token Budget: ~4000 tokens default (per BP-039), configurable via config.token_budget
    """
    try:
        client = get_qdrant_client(config)

        # Use shared retrieval helper (TECH-DEBT-047 refactor)
        summaries = retrieve_session_summaries(client, project_name, limit=20)

        if not summaries:
            return ""

        # Take only the requested limit
        recent_summaries = summaries[:limit]

        if not recent_summaries:
            return ""

        lines = []

        # Format each summary with its rich context
        lines.append("## Session Summaries\n")

        for summary in recent_summaries:
            content = summary.get("content", "")
            timestamp = summary.get("timestamp", "")

            # Extract time from ISO timestamp
            time_str = ""
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M")
                except (ValueError, AttributeError):
                    time_str = ""

            prefix = f"**Summary [{time_str}]:**" if time_str else "**Summary:**"
            lines.append(f"{prefix} {content}\n")

        # V2.1: Extract rich context from most recent summary
        most_recent = recent_summaries[0] if recent_summaries else {}

        # Add recent user messages from the rich summary
        last_user_prompts = most_recent.get("last_user_prompts", [])
        if last_user_prompts:
            lines.append("\n## Recent User Messages\n")
            for prompt_data in last_user_prompts:
                content = (
                    prompt_data.get("content", "")
                    if isinstance(prompt_data, dict)
                    else str(prompt_data)
                )
                # Filter and truncate
                filtered_content = filter_low_value_content(content)
                if filtered_content.strip():
                    if len(filtered_content) > 2000:
                        filtered_content = smart_truncate(filtered_content, 2000)
                    lines.append(f"**User:** {filtered_content}\n")

        # Add recent agent responses from the rich summary
        last_agent_responses = most_recent.get("last_agent_responses", [])
        if last_agent_responses:
            lines.append("\n## Agent Context Summary\n")
            for response_data in last_agent_responses:
                content = (
                    response_data.get("content", "")
                    if isinstance(response_data, dict)
                    else str(response_data)
                )
                # Filter and truncate agent responses more aggressively
                filtered_content = filter_low_value_content(content)
                if filtered_content.strip():
                    if len(filtered_content) > 500:
                        filtered_content = smart_truncate(filtered_content, 500)
                    lines.append(f"**Agent:** {filtered_content}\n")

        return "\n".join(lines)

    except Exception as e:
        # Graceful degradation - conversation context is optional
        logger.warning(
            "conversation_context_failed",
            extra={"session_id": session_id, "error": str(e)},
        )
        return ""


def main():
    """Retrieve and output relevant memories for Claude context.

    CRITICAL: stdout becomes Claude's context. All diagnostics go to stderr.
    CRITICAL: Always exit 0 - never block Claude startup (FR30, NFR-R1).
    """
    start_time = time.perf_counter()

    with track_hook_duration("session_start"):
        try:
            # Parse hook input (SessionStart provides cwd, session_id)
            hook_input = parse_hook_input()

            # Extract context
            cwd = hook_input.get("cwd", os.getcwd())
            session_id = hook_input.get("session_id", "unknown")
            trigger = hook_input.get(
                "source", "startup"
            )  # startup, resume, compact, clear
            project_name = detect_project(cwd)  # FR13 - automatic project detection

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
            client = get_qdrant_client(config)
            if not check_qdrant_health(client):
                log_empty_session(
                    session_id=session_id,
                    project=project_name,
                    reason="qdrant_unavailable",
                )

                # Metrics: Retrieval failed due to Qdrant unavailable (Story 6.1, AC 6.1.3)
                # TECH-DEBT-012: Changed from "combined" to "discussions"
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_DISCUSSIONS, status="failed"
                    ).inc()

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
                sys.exit(0)

            # V2.0 Phase 5: Inject on resume and compact (conversation continuity)
            # startup/clear: No injection - we don't know context yet or user wants fresh start
            if trigger in ["startup", "clear"]:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "v2_no_injection",
                    extra={
                        "trigger": trigger,
                        "session_id": session_id,
                        "project": project_name,
                        "reason": "V2.0 injects on resume and compact only",
                        "duration_ms": round(duration_ms, 2),
                    },
                )

                # User notification - V2.0 behavior
                print(
                    f"🧠 AI Memory V2.0: No injection on {trigger} (fresh start) [{duration_ms:.0f}ms]",
                    file=sys.stderr,
                )

                # Empty context JSON - no injection on startup/resume/clear
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

            # On resume or compact: Inject conversation context to restore working memory
            logger.info(
                "v2_context_injection",
                extra={
                    "trigger": trigger,
                    "session_id": session_id,
                    "project": project_name,
                },
            )

            # TECH-DEBT-047: Priority-based injection
            # Phase 1: Retrieve session summaries (60% of budget)
            # Phase 2: Retrieve other memories - decisions, patterns, conventions (40% of budget)

            # Retrieve session summaries using shared helper (TECH-DEBT-047 refactor)
            session_summaries = retrieve_session_summaries(
                client, project_name, limit=20
            )
            # Take top 5 most recent
            session_summaries = session_summaries[:5]

            # Retrieve other memories (decisions, patterns, conventions)
            other_memories = []
            # Track memory counts per collection for metrics (BUG-021 fix)
            memories_per_collection = {
                COLLECTION_DISCUSSIONS: 0,
                COLLECTION_CODE_PATTERNS: 0,
                COLLECTION_CONVENTIONS: 0,
            }
            try:
                from memory.search import MemorySearch

                # Build a query from the most recent session summary
                query = "recent implementation patterns and decisions"  # More specific default
                if session_summaries:
                    first_summary = session_summaries[0]
                    # Try multiple fields for better query relevance
                    query = (
                        first_summary.get("first_user_prompt")
                        or first_summary.get("content", "")[:200]  # Use content preview
                        or "recent implementation patterns"
                    )

                # Search for relevant memories across collections
                searcher = MemorySearch(config)

                # Search decisions from discussions (type=decision)
                decisions = searcher.search(
                    query=query,
                    collection=COLLECTION_DISCUSSIONS,
                    group_id=project_name,
                    limit=3,
                    memory_type="decision",
                    fast_mode=True,  # Use fast mode for triggers
                )
                other_memories.extend(decisions)
                memories_per_collection[COLLECTION_DISCUSSIONS] = len(decisions)
                # Track retrieval metric for discussions
                if memory_retrievals_total and decisions:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_DISCUSSIONS, status="success"
                    ).inc(len(decisions))

                # Search patterns from code-patterns
                patterns = searcher.search(
                    query=query,
                    collection=COLLECTION_CODE_PATTERNS,
                    group_id=project_name,
                    limit=3,
                    fast_mode=True,
                )
                other_memories.extend(patterns)
                memories_per_collection[COLLECTION_CODE_PATTERNS] = len(patterns)
                # Track retrieval metric for code-patterns
                if memory_retrievals_total and patterns:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_CODE_PATTERNS, status="success"
                    ).inc(len(patterns))

                # Search conventions (no group_id filter - shared)
                conventions = searcher.search(
                    query=query,
                    collection=COLLECTION_CONVENTIONS,
                    group_id=None,  # Shared across projects
                    limit=2,
                    fast_mode=True,
                )
                other_memories.extend(conventions)
                memories_per_collection[COLLECTION_CONVENTIONS] = len(conventions)
                # Track retrieval metric for conventions
                if memory_retrievals_total and conventions:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_CONVENTIONS, status="success"
                    ).inc(len(conventions))

                searcher.close()

            except Exception as e:
                logger.warning(
                    "other_memories_retrieval_failed",
                    extra={"session_id": session_id, "error": str(e)},
                )
                other_memories = []

            # Use priority injection (TECH-DEBT-047)
            conversation_context = inject_with_priority(
                session_summaries=session_summaries,
                other_memories=other_memories,
                token_budget=config.token_budget,
            )

            # Calculate duration for logging
            duration_ms = (time.perf_counter() - start_time) * 1000
            duration_seconds = duration_ms / 1000.0

            # V2.0 resume/compact behavior: Output conversation context only (no general memory search)
            if conversation_context:
                # CR-3.5 HIGH FIX: Validate token budget before injection
                context_char_count = len(conversation_context)
                # Rough token estimate: 1 token ≈ 4 chars
                estimated_tokens = context_char_count // 4
                token_budget = config.token_budget

                if estimated_tokens > token_budget:
                    # Context exceeds budget - truncate to fit
                    target_chars = token_budget * 4
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
                        conversation_context[:200] if conversation_context else ""
                    ),
                )

                # Metrics: Successful conversation context injection
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_DISCUSSIONS, status="success"
                    ).inc()
                if hook_duration_seconds:
                    hook_duration_seconds.labels(hook_type="SessionStart").observe(
                        duration_seconds
                    )

                # TECH-DEBT-067: Track token usage
                if context_injection_tokens:
                    token_count = estimate_tokens(conversation_context)
                    context_injection_tokens.labels(
                        hook_type="SessionStart", collection=COLLECTION_DISCUSSIONS
                    ).observe(token_count)
                if tokens_consumed_total:
                    token_count = estimate_tokens(conversation_context)
                    tokens_consumed_total.labels(
                        operation="injection", direction="output", project=project_name
                    ).inc(token_count)

                # TECH-DEBT-070: Push metrics to Pushgateway (async to avoid latency)
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

                # Output conversation context to Claude
                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": conversation_context,
                    }
                }
                print(json.dumps(output))
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

                # User notification - no conversation context
                print(
                    f"🧠 AI Memory V2.0: No conversation context available [{duration_ms:.0f}ms]",
                    file=sys.stderr,
                )

                # Metrics: Empty conversation context
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_DISCUSSIONS, status="empty"
                    ).inc()

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
                sys.exit(0)

        except Exception as e:
            # CRITICAL: Never crash or block Claude (FR30, NFR-R4)
            logger.error("retrieval_failed", extra={"error": str(e)})

            # Metrics: Retrieval failed with exception (Story 6.1, AC 6.1.3)
            # TECH-DEBT-012: Changed from "combined" to "discussions"
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_DISCUSSIONS, status="failed"
                ).inc()
            if hook_duration_seconds:
                duration_ms = (time.perf_counter() - start_time) * 1000
                duration_seconds = duration_ms / 1000.0
                hook_duration_seconds.labels(hook_type="SessionStart").observe(
                    duration_seconds
                )

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
