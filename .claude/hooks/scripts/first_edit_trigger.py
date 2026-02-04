#!/usr/bin/env python3
"""PreToolUse Hook - Retrieve patterns on first edit to a file in session.

Memory System V2.0 Phase 3: Trigger System
Automatically retrieves file-specific patterns when Claude first edits a file in a session.
Subsequent edits to the same file in the same session are skipped to avoid noise.

Signal Detection:
    - PreToolUse hook for Edit tool
    - File NOT in session's edited files set
    - Uses is_first_edit_in_session() for tracking

Action:
    - Search code-patterns collection
    - Filter by type="file_pattern"
    - Query based on file path
    - Inject up to 3 patterns to stdout

Configuration:
    - Hook: PreToolUse with matcher "Edit"
    - Collection: code-patterns
    - Type filter: "file_pattern"
    - Max results: 3

Architecture:
    PreToolUse (Edit) → Extract file_path + session_id → is_first_edit_in_session()
    → Search code-patterns → Format results → Output to stdout → Claude sees context

Exit Codes:
    - 0: Success (or graceful degradation)
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Configure structured logging using shared utility
from memory.config import COLLECTION_CODE_PATTERNS
from memory.hooks_common import get_metrics, log_to_activity, setup_hook_logging

logger = setup_hook_logging()

# CR-2 FIX: Use consolidated metrics import
memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = (
    get_metrics()
)

# Display formatting constants
MAX_CONTENT_CHARS = 400  # Maximum characters to show in context output
SESSION_ID_DISPLAY_LEN = 8  # Standard truncation for session IDs


def format_pattern(pattern: dict, index: int) -> str:
    """Format a single file pattern for display.

    Args:
        pattern: Pattern dict with content, score, file_path
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    content = pattern.get("content", "")
    score = pattern.get("score", 0)
    pattern_type = pattern.get("type", "unknown")
    pattern_file_path = pattern.get("file_path", "")

    # Build header with relevance
    header = f"{index}. **{pattern_type}** ({score:.0%}) [code-patterns]"
    if pattern_file_path:
        header += f"\n   From: {pattern_file_path}"

    # Truncate content if too long
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "..."

    return f"{header}\n{content}\n"


def main() -> int:
    """PreToolUse hook entry point.

    Reads hook input from stdin, detects first edit to file in session,
    searches code-patterns collection, and outputs to stdout.

    Returns:
        Exit code: Always 0 (graceful degradation)
    """
    start_time = time.perf_counter()

    try:
        # Parse hook input from stdin
        try:
            hook_input = json.load(sys.stdin)
        except json.JSONDecodeError:
            logger.warning("malformed_hook_input")
            return 0

        # Extract context
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
        cwd = hook_input.get("cwd", os.getcwd())
        session_id = hook_input.get("session_id", "unknown")

        # Validate this is an Edit tool
        if tool_name != "Edit":
            logger.debug("not_edit_tool", extra={"tool_name": tool_name})
            return 0

        # Extract file path from tool_input
        file_path = tool_input.get("file_path", "")

        if not file_path:
            logger.debug("no_file_path", extra={"tool_name": tool_name})
            return 0

        # Check if this is the first edit to this file in this session (trigger condition)
        from memory.triggers import TRIGGER_CONFIG, is_first_edit_in_session

        if not is_first_edit_in_session(file_path, session_id):
            # Not first edit - skip retrieval
            logger.debug(
                "subsequent_edit_skipping_trigger",
                extra={"file_path": file_path, "session_id": session_id},
            )
            return 0

        # First edit detected - retrieve patterns
        # Safe config access with defaults for robustness
        config = TRIGGER_CONFIG.get("first_edit", {})
        if not config.get("enabled", False):
            logger.debug("first_edit_trigger_disabled")
            return 0

        # Build query based on file path
        query = f"File patterns for {file_path}"

        # Search code-patterns collection
        from memory.config import get_config
        from memory.health import check_qdrant_health
        from memory.project import detect_project
        from memory.qdrant_client import get_qdrant_client
        from memory.search import MemorySearch

        mem_config = get_config()
        client = get_qdrant_client(mem_config)

        # Check Qdrant health
        if not check_qdrant_health(client):
            logger.warning("qdrant_unavailable")
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CODE_PATTERNS, status="failed"
                ).inc()
            return 0

        # Detect project for filtering
        project_name = detect_project(cwd)

        # Search for relevant file patterns
        search = MemorySearch(mem_config)
        try:
            results = search.search(
                query=query,
                collection=COLLECTION_CODE_PATTERNS,
                group_id=project_name,  # Project-specific patterns
                limit=config.get("max_results", 3),
                score_threshold=mem_config.similarity_threshold,
                memory_type=config.get("type_filter", "file_pattern"),
            )

            if not results:
                # No relevant patterns found
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(
                    f"✏️ FirstEdit: No patterns found for {file_path}", INSTALL_DIR
                )
                logger.debug(
                    "no_patterns_found",
                    extra={
                        "file_path": file_path,
                        "query": query,
                        "session_id": session_id,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_CODE_PATTERNS, status="empty"
                    ).inc()

                # Push trigger metrics even when no results
                from memory.metrics_push import push_trigger_metrics_async

                push_trigger_metrics_async(
                    trigger_type="first_edit",
                    status="empty",
                    project=project_name,
                    results_count=0,
                    duration_seconds=duration_ms / 1000.0,
                )
                return 0

            # Format for stdout display
            output_parts = []
            output_parts.append("\n" + "=" * 70)
            output_parts.append("✏️ FILE PATTERNS (First Edit)")
            output_parts.append("=" * 70)
            output_parts.append(f"File: {file_path}")
            output_parts.append(f"Session: {session_id[:SESSION_ID_DISPLAY_LEN]}...")
            output_parts.append("")

            for i, pattern in enumerate(results, 1):
                output_parts.append(format_pattern(pattern, i))

            output_parts.append("=" * 70 + "\n")

            # Output to stdout (Claude sees this before tool execution)
            print("\n".join(output_parts))

            # Log success
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_to_activity(
                f"✏️ FirstEdit patterns retrieved for {file_path} [{duration_ms:.0f}ms]",
                INSTALL_DIR,
            )
            logger.info(
                "first_edit_patterns_retrieved",
                extra={
                    "file_path": file_path,
                    "session_id": session_id,
                    "results_count": len(results),
                    "duration_ms": round(duration_ms, 2),
                    "project": project_name,
                },
            )

            # Metrics
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CODE_PATTERNS, status="success"
                ).inc()
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_ms / 1000.0)
            if hook_duration_seconds:
                hook_duration_seconds.labels(
                    hook_type="PreToolUse_FirstEdit",
                    status="success",
                    project=project_name,
                ).observe(duration_ms / 1000.0)

            # Push trigger metrics to Pushgateway
            from memory.metrics_push import push_trigger_metrics_async

            push_trigger_metrics_async(
                trigger_type="first_edit",
                status="success",
                project=project_name,
                results_count=len(results),
                duration_seconds=duration_ms / 1000.0,
            )

        finally:
            search.close()

        return 0

    except Exception as e:
        # Catch-all error handler - always gracefully degrade
        logger.error(
            "hook_failed", extra={"error": str(e), "error_type": type(e).__name__}
        )

        # Metrics
        if memory_retrievals_total:
            memory_retrievals_total.labels(
                collection=COLLECTION_CODE_PATTERNS, status="failed"
            ).inc()
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(
                hook_type="PreToolUse_FirstEdit",
                status="error",
                project=project_name if "project_name" in dir() else "unknown",
            ).observe(duration_seconds)

        # Push failure metrics
        from memory.metrics_push import push_trigger_metrics_async

        push_trigger_metrics_async(
            trigger_type="first_edit",
            status="failed",
            project=project_name if "project_name" in dir() else "unknown",
            results_count=0,
            duration_seconds=duration_seconds,
        )

        return 0  # Always exit 0 - graceful degradation


if __name__ == "__main__":
    sys.exit(main())
