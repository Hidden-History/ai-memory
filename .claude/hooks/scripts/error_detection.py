#!/usr/bin/env python3
"""PostToolUse Hook - Retrieve error_fix patterns when errors detected.

Memory System V2.0 TRIGGER 1: Error Detection
Automatically retrieves similar error fixes when bash commands fail.

Signal Detection:
    - PostToolUse hook for Bash tool
    - Exit code != 0 OR error patterns in output

Action:
    - Extract error signature
    - Search code-patterns collection
    - Filter by type="error_fix"
    - Inject up to 3 similar fixes to stdout

Configuration:
    - Hook: PostToolUse with matcher "Bash"
    - Collection: code-patterns
    - Type filter: "error_fix"
    - Max results: 3

Exit Codes:
    - 0: Success (or graceful degradation)
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

from memory.config import COLLECTION_CODE_PATTERNS, get_config
from memory.hooks_common import (
    extract_error_signature,
    get_metrics,
    log_to_activity,
    setup_hook_logging,
)
from memory.project import detect_project
from memory.search import MemorySearch

logger = setup_hook_logging()

# CR-2 FIX: Use consolidated metrics import
memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = (
    get_metrics()
)


def detect_error(tool_response: dict) -> bool:
    """Detect if bash output contains error indicators.

    Args:
        tool_response: Tool response dict with stdout/stderr fields

    Returns:
        True if error detected, False otherwise
    """
    exit_code = tool_response.get("exitCode")
    # Claude Code sends stdout/stderr separately, not combined "output"
    stdout = tool_response.get("stdout", "")
    stderr = tool_response.get("stderr", "")
    output = stderr if stderr else stdout  # Prefer stderr for error detection

    # Exit code check (most reliable)
    if exit_code is not None and exit_code != 0:
        return True

    # Error pattern check
    # FIX #2: Added "bug" pattern per spec (TRIGGER 1 line 1071)
    error_patterns = [
        r"(?i)\berror\b",
        r"(?i)\bexception\b",
        r"(?i)\btraceback\b",
        r"(?i)\bfailed\b",
        r"(?i)\bfatal\b",
        r"(?i)\bbug\b",  # SPEC REQUIREMENT
    ]
    for pattern in error_patterns:
        if re.search(pattern, output):
            return True

    return False


def format_error_fix(fix: dict, index: int) -> str:
    """Format a single error fix for display (no truncation).

    Args:
        fix: Error fix dict with content, score, metadata
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    content = fix.get("content", "")
    score = fix.get("score", 0)
    fix_type = fix.get("type", "error_fix")
    file_path = fix.get("file_path", "")

    # Build header with relevance
    header = f"{index}. **{fix_type}** ({score:.0%}) [code-patterns]"
    if file_path:
        header += f"\n   From: {file_path}"

    # No truncation - show full content
    return f"{header}\n{content}\n"


def main() -> int:
    """PostToolUse hook entry point.

    Detects errors in Bash tool output and retrieves similar fixes from memory.

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

        # Validate Bash tool
        if hook_input.get("tool_name") != "Bash":
            logger.debug(
                "not_bash_tool", extra={"tool_name": hook_input.get("tool_name")}
            )
            return 0

        tool_response = hook_input.get("tool_response", {})

        # Check for error
        if not detect_error(tool_response):
            # No error detected - normal completion
            return 0

        # Extract error signature for search
        # Claude Code sends stdout/stderr separately
        stdout = tool_response.get("stdout", "")
        stderr = tool_response.get("stderr", "")
        output = stderr if stderr else stdout
        error_signature = extract_error_signature(output)

        # Search for similar error fixes
        config = get_config()
        search = MemorySearch(config)
        cwd = hook_input.get("cwd", os.getcwd())
        project_name = detect_project(cwd)

        try:
            results = search.search(
                query=error_signature,
                collection=COLLECTION_CODE_PATTERNS,
                group_id=project_name,
                limit=3,
                score_threshold=0.5,
                memory_type="error_fix",
            )

            if not results:
                # No similar fixes found - log for visibility
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(
                    f"🔧 ErrorDetection: Error detected but no similar fixes found [{duration_ms:.0f}ms]",
                    INSTALL_DIR,
                )
                logger.debug(
                    "no_error_fixes_found", extra={"error": error_signature[:50]}
                )

                # Push trigger metrics even when no results
                from memory.metrics_push import push_trigger_metrics_async

                push_trigger_metrics_async(
                    trigger_type="error_detection",
                    status="empty",
                    project=project_name,
                    results_count=0,
                    duration_seconds=duration_ms / 1000.0,
                )
                return 0

            # Format and output
            # FIX #9: Add truncation indicator consistently
            error_display = error_signature[:100]
            if len(error_signature) > 100:
                error_display += "..."

            output_parts = ["\n" + "=" * 70]
            output_parts.append("🔧 SIMILAR ERROR FIXES FOUND")
            output_parts.append("=" * 70)
            output_parts.append(f"Current error: {error_display}")
            output_parts.append("")

            for i, fix in enumerate(results, 1):
                output_parts.append(format_error_fix(fix, i))

            output_parts.append("=" * 70 + "\n")

            print("\n".join(output_parts))

            duration_ms = (time.perf_counter() - start_time) * 1000
            log_to_activity(
                f"🔧 ErrorFixes retrieved {len(results)} similar fixes [{duration_ms:.0f}ms]",
                INSTALL_DIR,
            )
            logger.info(
                "error_fixes_retrieved",
                extra={
                    "results_count": len(results),
                    "duration_ms": round(duration_ms, 2),
                    "error_signature": error_signature[:50],
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
                    hook_type="PostToolUse_ErrorDetection",
                    status="success",
                    project=project_name,
                ).observe(duration_ms / 1000.0)

            # Push trigger metrics to Pushgateway
            from memory.metrics_push import push_trigger_metrics_async

            push_trigger_metrics_async(
                trigger_type="error_detection",
                status="success",
                project=project_name,
                results_count=len(results),
                duration_seconds=duration_ms / 1000.0,
            )

        finally:
            search.close()

        return 0

    except Exception as e:
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
            proj = project_name if "project_name" in dir() else "unknown"
            hook_duration_seconds.labels(
                hook_type="PostToolUse_ErrorDetection",
                status="error",
                project=proj,
            ).observe(duration_seconds)

        # Push failure metrics
        from memory.metrics_push import push_trigger_metrics_async

        push_trigger_metrics_async(
            trigger_type="error_detection",
            status="failed",
            project=project_name if "project_name" in dir() else "unknown",
            results_count=0,
            duration_seconds=duration_seconds,
        )

        return 0  # Graceful degradation


if __name__ == "__main__":
    sys.exit(main())
