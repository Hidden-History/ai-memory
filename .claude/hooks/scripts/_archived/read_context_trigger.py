#!/usr/bin/env python3
"""PostToolUse Hook - Retrieve best practices when review agents read files.

Memory System V2.0 Phase 3: Trigger System
Automatically retrieves relevant best practices when Claude reads files,
particularly before review agents (TEA, code-review) edit files.

Signal Detection:
    - PostToolUse hook for Read tool
    - File path and type extracted
    - Uses detect_read_context() for analysis

Action:
    - Search conventions collection
    - Filter by file type and component
    - Inject up to 3 relevant best practices to stdout

Configuration:
    - Hook: PostToolUse with matcher "Read"
    - Collection: conventions
    - Max results: 3

Architecture:
    PostToolUse (Read) → Extract file_path + tool_name → detect_read_context()
    → Search conventions → Format results → Output to stdout → Claude sees context

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
from memory.config import COLLECTION_CONVENTIONS
from memory.hooks_common import get_metrics, log_to_activity, setup_hook_logging

logger = setup_hook_logging()

# CR-2 FIX: Use consolidated metrics import
memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = (
    get_metrics()
)

# Display formatting constants
MAX_CONTENT_CHARS = 400  # Maximum characters to show in context output


def format_best_practice(practice: dict, index: int) -> str:
    """Format a single best practice for display.

    Args:
        practice: Practice dict with content, score, type
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    content = practice.get("content", "")
    score = practice.get("score", 0)
    practice_type = practice.get("type", "guideline")
    tags = practice.get("tags", [])

    # Build header with relevance
    header = f"{index}. **{practice_type}** ({score:.0%}) [conventions]"
    if tags:
        header += f" - {', '.join(tags[:3])}"

    # Truncate content if too long
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "..."

    return f"{header}\n{content}\n"


def main() -> int:
    """PostToolUse hook entry point.

    Reads hook input from stdin, detects Read tool usage with file context,
    searches conventions collection, and outputs to stdout.

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

        # Validate this is a Read tool
        if tool_name != "Read":
            logger.debug("not_read_tool", extra={"tool_name": tool_name})
            return 0

        # Extract file path from tool_input
        file_path = tool_input.get("file_path", "")
        if file_path:
            file_path = os.path.normpath(os.path.abspath(file_path))

        if not file_path:
            logger.debug("no_file_path", extra={"tool_name": tool_name})
            return 0

        # Detect read context (trigger condition)
        from memory.triggers import detect_read_context

        context = detect_read_context(file_path, tool_name)
        if not context.get("should_trigger", False):
            # No trigger - skip retrieval
            logger.debug(
                "read_context_no_trigger",
                extra={
                    "file_path": file_path,
                    "file_type": context.get("file_type", ""),
                    "tool_name": tool_name,
                },
            )
            return 0

        # Read context detected - retrieve conventions
        file_type = context.get("file_type", "")
        component = context.get("component", "")
        search_query = context.get("search_query", "")

        # Search conventions collection
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
                    collection=COLLECTION_CONVENTIONS, status="failed"
                ).inc()
            return 0

        # Detect project for logging
        project_name = detect_project(cwd)

        # Search for relevant best practices
        search = MemorySearch(mem_config)
        try:
            # Get limit from trigger config
            from memory.triggers import TRIGGER_CONFIG

            limit = TRIGGER_CONFIG.get("read_context", {}).get("max_results", 3)

            # CR-2 FIX: Add smart type filtering based on file context
            # Code files (py, js, etc.) → rule, guideline
            # Config files (yaml, json, etc.) → structure, naming
            code_extensions = [
                "py",
                "js",
                "ts",
                "tsx",
                "jsx",
                "go",
                "rs",
                "java",
                "cpp",
                "c",
                "rb",
                "php",
            ]
            if file_type in code_extensions:
                type_filter = ["rule", "guideline"]
            else:
                type_filter = ["structure", "naming"]

            # Conventions are shared across projects (group_id=None)
            results = search.search(
                query=search_query,
                collection=COLLECTION_CONVENTIONS,
                group_id=None,  # Conventions are global
                limit=limit,
                score_threshold=mem_config.similarity_threshold,
                memory_type=type_filter,  # CR-2 FIX: Smart type filtering
            )

            if not results:
                # No relevant practices found
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(
                    f"📖 ReadContext: No results for {file_type} in {component or 'root'}",
                    INSTALL_DIR,
                )
                logger.debug(
                    "no_best_practices_found",
                    extra={
                        "file_path": file_path,
                        "file_type": file_type,
                        "component": component,
                        "query": search_query[:50],
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_CONVENTIONS, status="empty"
                    ).inc()
                return 0

            # Format for stdout display
            output_parts = []
            output_parts.append("\n" + "=" * 70)
            output_parts.append("📖 RELEVANT CONVENTIONS (Read Context)")
            output_parts.append("=" * 70)

            # Use relative path if shorter
            try:
                rel_path = os.path.relpath(file_path, cwd)
                display_path = rel_path if len(rel_path) < len(file_path) else file_path
            except ValueError:
                display_path = file_path

            output_parts.append(f"File: {display_path}")
            output_parts.append(f"Type: {file_type}")
            if component:
                output_parts.append(f"Component: {component}")
            output_parts.append("")

            for i, practice in enumerate(results, 1):
                output_parts.append(format_best_practice(practice, i))

            output_parts.append("=" * 70 + "\n")

            # Output to stdout (Claude sees this after Read execution)
            print("\n".join(output_parts))

            # Log success
            duration_ms = (time.perf_counter() - start_time) * 1000
            display_path = f"{file_type} in {component}" if component else file_type
            log_to_activity(
                f"📖 ReadContext retrieved for {display_path} [{duration_ms:.0f}ms]",
                INSTALL_DIR,
            )
            logger.info(
                "read_context_conventions_retrieved",
                extra={
                    "file_path": file_path,
                    "file_type": file_type,
                    "component": component,
                    "results_count": len(results),
                    "duration_ms": round(duration_ms, 2),
                    "project": project_name,
                },
            )

            # Metrics
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CONVENTIONS, status="success"
                ).inc()
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_ms / 1000.0)
            if hook_duration_seconds:
                hook_duration_seconds.labels(
                    hook_type="PostToolUse_ReadContext"
                ).observe(duration_ms / 1000.0)

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
                collection=COLLECTION_CONVENTIONS, status="failed"
            ).inc()
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="PostToolUse_ReadContext").observe(
                duration_seconds
            )

        return 0  # Always exit 0 - graceful degradation


if __name__ == "__main__":
    sys.exit(main())
