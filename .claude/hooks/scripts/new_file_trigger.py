#!/usr/bin/env python3
"""PreToolUse Hook - Retrieve conventions when creating new files.

Memory System V2.0 Phase 3: Trigger System
Automatically retrieves naming and structure conventions when Claude creates a new file.

Signal Detection:
    - PreToolUse hook for Write tool
    - File does not exist yet (is_new_file check)

Action:
    - Search conventions collection
    - Filter by type IN (naming, structure)
    - Inject up to 2 conventions to stdout

Configuration:
    - Hook: PreToolUse with matcher "Write"
    - Collection: conventions
    - Type filter: ["naming", "structure"]
    - Max results: 2

Architecture:
    PreToolUse (Write) → Check file exists → is_new_file() → Search conventions
    → Format results → Output to stdout → Claude sees context

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
INSTALL_DIR = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# Configure structured logging using shared utility
from memory.config import COLLECTION_CONVENTIONS
from memory.hooks_common import setup_hook_logging, log_to_activity, get_metrics
from memory.metrics_push import track_hook_duration

logger = setup_hook_logging()

# CR-2 FIX: Use consolidated metrics import
memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = get_metrics()

# Display formatting constants
MAX_CONTENT_CHARS = 400  # Maximum characters to show in context output


def format_convention(convention: dict, index: int) -> str:
    """Format a single convention for display.

    Args:
        convention: Convention dict with content, score, type
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    content = convention.get("content", "")
    score = convention.get("score", 0)
    conv_type = convention.get("type", "unknown")

    # Build header with relevance
    header = f"{index}. **{conv_type}** ({score:.0%}) [conventions]"

    # Truncate content if too long
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "..."

    return f"{header}\n{content}\n"


def main() -> int:
    """PreToolUse hook entry point.

    Reads hook input from stdin, detects new file creation,
    searches conventions collection, and outputs to stdout.

    Returns:
        Exit code: Always 0 (graceful degradation)
    """
    start_time = time.perf_counter()

    with track_hook_duration("new_file_trigger"):
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

            # Validate this is a Write tool
            if tool_name != "Write":
                logger.debug("not_write_tool", extra={"tool_name": tool_name})
                return 0

            # Extract file path from tool_input
            file_path = tool_input.get("file_path", "")

            if not file_path:
                logger.debug("no_file_path", extra={"tool_name": tool_name})
                return 0

            # Check if this is a new file (trigger condition)
            from memory.triggers import is_new_file, TRIGGER_CONFIG

            if not is_new_file(file_path):
                # File already exists - not a new file creation
                logger.debug("file_exists_skipping_trigger", extra={"file_path": file_path})
                return 0

            # File is new - retrieve conventions
            # Safe config access with defaults for robustness
            config = TRIGGER_CONFIG.get("new_file", {})
            if not config.get("enabled", False):
                logger.debug("new_file_trigger_disabled")
                return 0

            # Build query based on file type
            file_ext = Path(file_path).suffix.lower()
            language_map = {
                ".py": "Python",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".go": "Go",
                ".rs": "Rust",
                ".java": "Java",
                ".sql": "SQL",
                ".sh": "Bash",
                ".yaml": "YAML",
                ".yml": "YAML",
            }
            language = language_map.get(file_ext, "code")
            query = f"Naming and structure conventions for {language} files"

            # Search conventions collection
            from memory.search import MemorySearch
            from memory.config import get_config
            from memory.health import check_qdrant_health
            from memory.qdrant_client import get_qdrant_client
            from memory.project import detect_project

            mem_config = get_config()
            client = get_qdrant_client(mem_config)

            # Check Qdrant health
            if not check_qdrant_health(client):
                logger.warning("qdrant_unavailable")
                if memory_retrievals_total:
                    memory_retrievals_total.labels(collection=COLLECTION_CONVENTIONS, status="failed").inc()
                return 0

            # Detect project for logging
            project_name = detect_project(cwd)

            # Search for relevant conventions
            search = MemorySearch(mem_config)
            try:
                results = search.search(
                    query=query,
                    collection=COLLECTION_CONVENTIONS,
                    group_id=None,  # Conventions are shared
                    limit=config.get("max_results", 2),
                    score_threshold=mem_config.similarity_threshold,
                    memory_type=config.get("type_filter", ["naming", "structure"])
                )

                if not results:
                    # No relevant conventions found
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    log_to_activity(f"📝 NewFile: No conventions found for {file_path}", INSTALL_DIR)
                    logger.debug("no_conventions_found", extra={
                        "file_path": file_path,
                        "query": query,
                        "duration_ms": round(duration_ms, 2)
                    })
                    if memory_retrievals_total:
                        memory_retrievals_total.labels(collection=COLLECTION_CONVENTIONS, status="empty").inc()

                    # Push trigger metrics even when no results
                    from memory.metrics_push import push_trigger_metrics_async
                    push_trigger_metrics_async(
                        trigger_type="new_file",
                        status="empty",
                        project=project_name,
                        results_count=0,
                        duration_seconds=duration_ms / 1000.0
                    )
                    return 0

                # Format for stdout display
                output_parts = []
                output_parts.append("\n" + "="*70)
                output_parts.append("📝 FILE CREATION CONVENTIONS")
                output_parts.append("="*70)
                output_parts.append(f"New File: {file_path}")
                output_parts.append(f"Language: {language}")
                output_parts.append("")

                for i, convention in enumerate(results, 1):
                    output_parts.append(format_convention(convention, i))

                output_parts.append("="*70 + "\n")

                # Output to stdout (Claude sees this before tool execution)
                print("\n".join(output_parts))

                # Log success
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(f"📝 NewFile conventions retrieved for {file_path} [{duration_ms:.0f}ms]", INSTALL_DIR)
                logger.info("new_file_conventions_retrieved", extra={
                    "file_path": file_path,
                    "language": language,
                    "results_count": len(results),
                    "duration_ms": round(duration_ms, 2),
                    "project": project_name
                })

                # Metrics
                if memory_retrievals_total:
                    memory_retrievals_total.labels(collection=COLLECTION_CONVENTIONS, status="success").inc()
                if retrieval_duration_seconds:
                    retrieval_duration_seconds.observe(duration_ms / 1000.0)
                if hook_duration_seconds:
                    hook_duration_seconds.labels(hook_type="PreToolUse_NewFile").observe(duration_ms / 1000.0)

                # Push trigger metrics to Pushgateway
                from memory.metrics_push import push_trigger_metrics_async
                push_trigger_metrics_async(
                    trigger_type="new_file",
                    status="success",
                    project=project_name,
                    results_count=len(results),
                    duration_seconds=duration_ms / 1000.0
                )

                return 0

            finally:
                search.close()

        except Exception as e:
            # Catch-all error handler - always gracefully degrade
            logger.error("hook_failed", extra={
                "error": str(e),
                "error_type": type(e).__name__
            })

            # Metrics
            if memory_retrievals_total:
                memory_retrievals_total.labels(collection=COLLECTION_CONVENTIONS, status="failed").inc()
            if hook_duration_seconds:
                duration_seconds = time.perf_counter() - start_time
                hook_duration_seconds.labels(hook_type="PreToolUse_NewFile").observe(duration_seconds)

            # Push failure metrics
            from memory.metrics_push import push_trigger_metrics_async
            push_trigger_metrics_async(
                trigger_type="new_file",
                status="failed",
                project=project_name if 'project_name' in dir() else "unknown",
                results_count=0,
                duration_seconds=duration_seconds
            )

            return 0  # Always exit 0 - graceful degradation


if __name__ == "__main__":
    sys.exit(main())
