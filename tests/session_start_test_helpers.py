"""Test helpers for SessionStart hook.

This module imports the actual functions from the hook script
so we can test them in isolation.

Once .claude/hooks/scripts/session_start.py is implemented,
these imports will work.
"""

import os
import sys

# Add hooks scripts to path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "scripts")
)

# Import actual V2 functions from session_start.py
try:
    from session_start import (
        get_conversation_context,
        inject_with_priority,
        log_empty_session,
        parse_hook_input,
        retrieve_session_summaries,
    )

    # TD-167: estimate_tokens removed, replaced by count_tokens from memory.chunking.truncation
    from memory.chunking.truncation import count_tokens as estimate_tokens  # noqa: F401

    # Create adapter functions for old test API
    def build_session_query(project_name, cwd):
        """Adapter: V2 uses first_user_prompt from session summaries."""
        return f"recent implementation patterns and decisions for {project_name}"

    def format_context(results, project_name, token_budget=2000):
        """Adapter: Format context with tiered relevance display.

        Implements AC 3.3.1 tiered formatting:
        - High tier (>=0.90): Full content display
        - Medium tier (0.50-0.90): Truncated to 500 chars
        - Below 0.20: Excluded (completely irrelevant)
        """
        if not results:
            return ""

        # Filter out below-threshold results (< 20%)
        filtered = [r for r in results if r.get("score", 0) >= 0.20]

        if not filtered:
            return f"## Relevant Memories for {project_name}\n"

        # Sort by score descending
        sorted_results = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)

        # Separate into tiers
        high_tier = [r for r in sorted_results if r.get("score", 0) >= 0.90]
        medium_tier = [r for r in sorted_results if 0.50 <= r.get("score", 0) < 0.90]

        # Token budget tracking (approximate: 4 chars = 1 token)
        tokens_used = 0

        lines = [f"## Relevant Memories for {project_name}\n"]

        # Format high tier
        if high_tier:
            lines.append("### High Relevance (>90%)\n")
            for memory in high_tier:
                entry = format_memory_entry(memory, truncate=False)
                entry_tokens = len(entry) // 4
                if tokens_used + entry_tokens > token_budget:
                    break
                lines.append(entry + "\n")
                tokens_used += entry_tokens

        # Format medium tier
        if medium_tier:
            lines.append("### Medium Relevance (50-90%)\n")
            for memory in medium_tier:
                entry = format_memory_entry(memory, truncate=True, max_chars=500)
                entry_tokens = len(entry) // 4
                if tokens_used + entry_tokens > token_budget:
                    break
                lines.append(entry + "\n")
                tokens_used += entry_tokens

        return "\n".join(lines)

    def _type_to_collection(memory_type):
        """Map memory type to collection name for display."""
        type_map = {
            "implementation": "implementations",
            "best_practice": "best_practices",
            "pattern": "best_practices",
            "session": "sessions",
        }
        return type_map.get(memory_type, "agent-memory")

    def format_memory_entry(memory, truncate=False, max_chars=500):
        """Adapter: V2 formatting for single memory.

        Format: **type** (score%) [source_hook] [collection]
        ```
        content
        ```
        """
        content = memory.get("content", "")
        score = memory.get("score", 0) or 0  # Handle None
        memory_type = memory.get("type", "unknown")
        source_hook = memory.get("source_hook", "")
        memory.get("collection", "")

        # Map type to display collection
        display_collection = _type_to_collection(memory_type)

        # Apply truncation if requested
        if truncate and len(content) > max_chars:
            content = content[:max_chars] + "..."

        # Format entry with code block
        score_str = f" ({int(score * 100)}%)" if score > 0 else " (0%)"
        source_str = f" {source_hook}" if source_hook else ""

        result = f"**{memory_type}**{score_str}{source_str} [{display_collection}]\n```\n{content}\n```"
        return result

    def log_session_retrieval(session_id, project, query, results, duration_ms):
        """Adapter: V2 uses log_empty_session() for structured logging."""
        import logging

        logger = logging.getLogger("ai_memory.hooks")

        # Calculate relevance counts
        high_relevance = sum(1 for r in results if r.get("score", 0) >= 0.9)
        medium_relevance = sum(1 for r in results if 0.5 <= r.get("score", 0) < 0.9)

        logger.info(
            "session_retrieval_completed",
            extra={
                "session_id": session_id,
                "project": project,
                "query_preview": query[:100] if query else "",
                "results_count": len(results),
                "high_relevance_count": high_relevance,
                "medium_relevance_count": medium_relevance,
                "duration_ms": round(duration_ms, 2),
            },
        )

except ImportError:
    # Hook script doesn't exist yet - tests will fail as expected (RED phase)
    def parse_hook_input():
        raise NotImplementedError("session_start.py not implemented yet")

    def estimate_tokens(content):
        raise NotImplementedError("session_start.py not implemented yet")

    def inject_with_priority(session_summaries, other_memories, token_budget):
        raise NotImplementedError("session_start.py not implemented yet")

    def retrieve_session_summaries(client, project_name, limit=20):
        raise NotImplementedError("session_start.py not implemented yet")

    def get_conversation_context(config, session_id, project_name, limit=3):
        raise NotImplementedError("session_start.py not implemented yet")

    def log_empty_session(session_id, project, reason, query="", duration_ms=0.0):
        raise NotImplementedError("session_start.py not implemented yet")

    # Adapter stubs
    def build_session_query(project_name, cwd):
        raise NotImplementedError("session_start.py not implemented yet")

    def format_context(results, project_name, token_budget=2000):
        raise NotImplementedError("session_start.py not implemented yet")

    def format_memory_entry(memory, truncate=False, max_chars=500):
        raise NotImplementedError("session_start.py not implemented yet")

    def log_session_retrieval(session_id, project, query, results, duration_ms):
        raise NotImplementedError("session_start.py not implemented yet")
