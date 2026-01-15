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

import sys
import json
import os
import logging
import time
from datetime import datetime, UTC
from typing import Optional

# Add src to path for system python3 execution
# Check for development mode (local src/ directory) first
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
local_src = os.path.join(project_root, "src")

if os.path.exists(local_src):
    # Development mode: use local src/
    sys.path.insert(0, local_src)
else:
    # Installed mode: use installed src/
    sys.path.insert(0, os.path.expanduser("~/.bmad-memory/src"))

from memory.search import MemorySearch
from memory.config import get_config
from memory.qdrant_client import get_qdrant_client
from memory.health import check_qdrant_health
from memory.project import detect_project
from memory.logging_config import configure_logging

# Configure structured logging (Story 6.2)
# Log to stderr since stdout is reserved for context injection
handler = logging.StreamHandler(sys.stderr)
from memory.logging_config import StructuredFormatter
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger("bmad.memory.hooks")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

# Import metrics for Prometheus instrumentation (Story 6.1, AC 6.1.3)
try:
    from memory.metrics import memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds
except ImportError:
    # Graceful degradation if metrics unavailable
    logger.warning("metrics_module_unavailable")
    memory_retrievals_total = None
    retrieval_duration_seconds = None
    hook_duration_seconds = None


def main():
    """Retrieve and output relevant memories for Claude context.

    CRITICAL: stdout becomes Claude's context. All diagnostics go to stderr.
    CRITICAL: Always exit 0 - never block Claude startup (FR30, NFR-R1).
    """
    start_time = time.perf_counter()

    try:
        # Parse hook input (SessionStart provides cwd, session_id)
        hook_input = parse_hook_input()

        # Extract context
        cwd = hook_input.get("cwd", os.getcwd())
        session_id = hook_input.get("session_id", "unknown")
        project_name = detect_project(cwd)  # FR13 - automatic project detection

        # Check Qdrant health (graceful degradation if down)
        config = get_config()
        client = get_qdrant_client(config)
        if not check_qdrant_health(client):
            log_empty_session(
                session_id=session_id,
                project=project_name,
                reason="qdrant_unavailable"
            )

            # Metrics: Retrieval failed due to Qdrant unavailable (Story 6.1, AC 6.1.3)
            if memory_retrievals_total:
                memory_retrievals_total.labels(collection="combined", status="failed").inc()

            print("")  # Empty context - Claude continues without memories
            sys.exit(0)

        # Build query from project context
        query = build_session_query(project_name, cwd)

        # Search both collections (FR10, FR11)
        search = MemorySearch(config)

        try:
            # Search implementations (project-filtered, FR10)
            implementations = search.search(
                query=query,
                collection="implementations",
                group_id=project_name,  # Filter by project
                limit=config.max_retrievals,
                score_threshold=config.similarity_threshold
            )

            # Search best_practices (shared, FR11)
            best_practices = search.search(
                query=query,
                collection="best_practices",
                group_id=None,  # Shared across all projects
                limit=3,  # Fewer best practices to not overwhelm
                score_threshold=config.similarity_threshold
            )

            # Combine results
            all_results = implementations + best_practices

            if not all_results:
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_empty_session(
                    session_id=session_id,
                    project=project_name,
                    reason="no_memories",
                    query=query,
                    duration_ms=duration_ms
                )

                # Metrics: Retrieval returned empty results (Story 6.1, AC 6.1.3)
                if memory_retrievals_total:
                    memory_retrievals_total.labels(collection="combined", status="empty").inc()

                print("")  # Empty context
                sys.exit(0)

            # Format for Claude context (FR12, tiered injection)
            formatted = format_context(all_results, project_name, config.token_budget)

            # Log retrieval stats for debugging
            duration_ms = (time.perf_counter() - start_time) * 1000
            duration_seconds = duration_ms / 1000.0
            log_session_retrieval(
                session_id=session_id,
                project=project_name,
                query=query,
                results=all_results,
                duration_ms=duration_ms
            )

            # Metrics: Successful retrieval (Story 6.1, AC 6.1.3)
            if memory_retrievals_total:
                memory_retrievals_total.labels(collection="combined", status="success").inc()
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_seconds)
            if hook_duration_seconds:
                hook_duration_seconds.labels(hook_type="SessionStart").observe(duration_seconds)

            # Output to stdout (becomes Claude's context)
            print(formatted)
            sys.exit(0)

        finally:
            search.close()  # Clean up resources

    except Exception as e:
        # CRITICAL: Never crash or block Claude (FR30, NFR-R4)
        logger.error("retrieval_failed", extra={"error": str(e)})

        # Metrics: Retrieval failed with exception (Story 6.1, AC 6.1.3)
        if memory_retrievals_total:
            memory_retrievals_total.labels(collection="combined", status="failed").inc()
        if hook_duration_seconds:
            duration_seconds = (time.perf_counter() - start_time) / 1000.0
            hook_duration_seconds.labels(hook_type="SessionStart").observe(duration_seconds)

        print("")  # Empty context on error
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


def build_session_query(project_name: str, cwd: str) -> str:
    """Build a query string from project context.

    Creates semantic query based on project name, directory, and detected
    project type (package.json, pyproject.toml, etc.).

    Args:
        project_name: Project identifier (directory basename)
        cwd: Current working directory path

    Returns:
        Query string for semantic search (e.g., "Working on bmad-memory-module Python project")

    Future Enhancement (Post-MVP):
        - Add recent git commit analysis
        - Include recently modified file types
        - Detect framework from dependencies
    """
    query_parts = [
        f"Working on {project_name}",
        f"in directory {cwd}"
    ]

    # Detect project type from common config files
    project_indicators = {
        "package.json": "JavaScript/TypeScript",
        "pyproject.toml": "Python",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "pom.xml": "Java Maven",
        "build.gradle": "Java Gradle"
    }

    for filename, lang_type in project_indicators.items():
        if os.path.exists(os.path.join(cwd, filename)):
            query_parts.append(f"using {lang_type}")
            break

    return " ".join(query_parts)


def format_context(
    results: list[dict],
    project_name: str,
    token_budget: int = 2000
) -> str:
    """Format memories into tiered context for Claude.

    Implements tiered injection per Architecture specs:
    - High Relevance (>90%): Full content
    - Medium Relevance (78-90%): Truncated to 500 chars
    - Below 78%: Excluded

    Args:
        results: List of search results with score, type, content
        project_name: Project identifier for header
        token_budget: Maximum tokens for context (default 2000)

    Returns:
        Markdown-formatted string for Claude's context

    Architecture Reference: architecture.md:864-941 (Tiered Context Injection)
    """
    if not results:
        return ""

    # Configurable thresholds (can be env vars in future)
    # Note: Aligned with SIMILARITY_THRESHOLD=0.4 (TECH-DEBT-002)
    HIGH_THRESHOLD = 0.90
    MEDIUM_THRESHOLD = 0.50
    LOW_THRESHOLD = 0.40  # Matches search threshold

    # Separate by relevance tier
    high_relevance = [r for r in results if r.get("score", 0) >= HIGH_THRESHOLD]
    medium_relevance = [r for r in results if MEDIUM_THRESHOLD <= r.get("score", 0) < HIGH_THRESHOLD]
    low_relevance = [r for r in results if LOW_THRESHOLD <= r.get("score", 0) < MEDIUM_THRESHOLD]

    output_parts = []
    current_tokens = 0  # Simplified token counting (word-based approximation)

    # Header
    header = f"## Relevant Memories for {project_name}\n"
    output_parts.append(header)
    current_tokens += len(header.split())

    # High relevance tier: full content
    if high_relevance:
        output_parts.append("\n### High Relevance (>90%)")
        for mem in high_relevance:
            if current_tokens >= token_budget:
                break

            entry = format_memory_entry(mem, truncate=False)
            entry_tokens = len(entry.split())

            if current_tokens + entry_tokens <= token_budget:
                output_parts.append(entry)
                current_tokens += entry_tokens

    # Medium relevance tier: truncated content
    if medium_relevance and current_tokens < token_budget:
        output_parts.append("\n### Medium Relevance (50-90%)")
        for mem in medium_relevance:
            if current_tokens >= token_budget:
                break

            entry = format_memory_entry(mem, truncate=True, max_chars=500)
            entry_tokens = len(entry.split())

            if current_tokens + entry_tokens <= token_budget:
                output_parts.append(entry)
                current_tokens += entry_tokens

    # Low relevance tier: highly truncated (TECH-DEBT-002 workaround)
    if low_relevance and current_tokens < token_budget:
        output_parts.append("\n### Low Relevance (20-50%)")
        for mem in low_relevance:
            if current_tokens >= token_budget:
                break

            entry = format_memory_entry(mem, truncate=True, max_chars=300)
            entry_tokens = len(entry.split())

            if current_tokens + entry_tokens <= token_budget:
                output_parts.append(entry)
                current_tokens += entry_tokens

    return "\n".join(output_parts)


def format_memory_entry(
    memory: dict,
    truncate: bool = False,
    max_chars: int = 500
) -> str:
    """Format a single memory entry for context injection.

    Includes source collection attribution per AC 3.2.4.

    Args:
        memory: Memory dict with type, score, content, source_hook, collection
        truncate: Whether to truncate long content
        max_chars: Maximum characters if truncating

    Returns:
        Formatted markdown string for single memory with collection attribution
    """
    memory_type = memory.get("type", "unknown")
    score = memory.get("score") or 0  # Handle None gracefully, default to 0
    content = memory.get("content", "")
    source = memory.get("source_hook", "unknown")
    collection = memory.get("collection", "unknown")  # AC 3.2.4: Collection attribution

    # Truncate if needed (medium relevance)
    if truncate and len(content) > max_chars:
        content = content[:max_chars] + "..."

    # Format with collection attribution (AC 3.2.4)
    return f"""
**{memory_type}** ({score:.0%}) - via {source} [{collection}]
```
{content}
```
"""


def log_session_retrieval(
    session_id: str,
    project: str,
    query: str,
    results: list[dict],
    duration_ms: float
):
    """Log comprehensive session retrieval details for debugging.

    Enhanced for Story 6.5 with additional diagnostic fields.

    Args:
        session_id: Unique session identifier from Claude Code
        project: Project name (group_id)
        query: Full query string used for search
        results: List of retrieved memory dicts with score, type, id
        duration_ms: Total retrieval time in milliseconds

    Best Practices (2026):
    - Use structured logging with extras dict
    - Never use f-strings in log messages
    - Include correlation IDs (session_id)
    - Log to stderr (stdout reserved for context injection)
    - JSON format for machine parsing

    References:
    - https://www.carmatec.com/blog/python-logging-best-practices-complete-guide/
    - https://signoz.io/guides/python-logging-best-practices/
    """
    # Calculate relevance tier counts for debugging
    # Thresholds aligned with format_context(): HIGH >= 0.90, MEDIUM 0.50-0.90, LOW < 0.50
    high_relevance_count = sum(1 for r in results if r.get("score", 0) >= 0.90)
    medium_relevance_count = sum(1 for r in results if 0.50 <= r.get("score", 0) < 0.90)
    low_relevance_count = sum(1 for r in results if r.get("score", 0) < 0.50)

    # Count by memory type for analysis
    type_counts = {}
    for r in results:
        mem_type = r.get("type", "unknown")
        type_counts[mem_type] = type_counts.get(mem_type, 0) + 1

    # Count by source hook for provenance tracking
    source_counts = {}
    for r in results:
        source = r.get("source_hook", "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1

    logger.info("session_retrieval_completed", extra={
        "session_id": session_id,
        "project": project,
        "query_preview": query[:100],  # First 100 chars for brevity
        "query_length": len(query),
        "results_count": len(results),

        # Relevance tier breakdown (FR29 diagnostic data)
        "high_relevance_count": high_relevance_count,  # >= 90%
        "medium_relevance_count": medium_relevance_count,  # 50-90%
        "low_relevance_count": low_relevance_count,  # < 50%

        # Top results for quick debugging
        "memory_ids": [r.get("id", "unknown") for r in results[:5]],
        "scores": [round(r.get("score", 0), 3) for r in results[:5]],

        # Type and source distribution
        "type_distribution": type_counts,
        "source_distribution": source_counts,

        # Collections searched
        "collections_searched": ["implementations", "best_practices"],

        # Performance tracking
        "duration_ms": round(duration_ms, 2),

        # Timestamp (ISO 8601 format with Z suffix per best practice)
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    })

    # Optionally log to dedicated session file
    if os.getenv("SESSION_LOG_ENABLED", "false").lower() == "true":
        try:
            from memory.session_logger import log_to_session_file

            log_to_session_file({
                "session_id": session_id,
                "project": project,
                "query_preview": query[:100],
                "results_count": len(results),
                "high_relevance_count": high_relevance_count,
                "medium_relevance_count": medium_relevance_count,
                "type_distribution": type_counts,
                "source_distribution": source_counts,
                "duration_ms": round(duration_ms, 2)
            })
        except ImportError:
            # Graceful degradation if session_logger unavailable
            pass


def log_empty_session(
    session_id: str,
    project: str,
    reason: str,
    query: str = "",
    duration_ms: float = 0.0
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
    logger.warning("session_retrieval_empty", extra={
        "session_id": session_id,
        "project": project,
        "reason": reason,
        "query_preview": query[:100] if query else "",
        "duration_ms": round(duration_ms, 2),
        "timestamp": datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    })

    # Also log to session file if enabled
    if os.getenv("SESSION_LOG_ENABLED", "false").lower() == "true":
        try:
            from memory.session_logger import log_to_session_file

            log_to_session_file({
                "session_id": session_id,
                "project": project,
                "reason": reason,
                "results_count": 0,
                "duration_ms": round(duration_ms, 2)
            })
        except ImportError:
            # Graceful degradation if session_logger unavailable
            pass


if __name__ == "__main__":
    main()
