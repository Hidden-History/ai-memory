#!/usr/bin/env python3
"""PreToolUse Hook - Retrieve relevant best practices (ON-DEMAND ONLY).

IMPORTANT: As of TECH-DEBT-012, this hook is NOT auto-triggered on Edit/Write.
It is only invoked:
1. By review agents (code-review, adversarial-review, security-auditor)
2. Manually via /best-practices skill (future)
3. When BMAD_BEST_PRACTICES_EXPLICIT=true environment variable is set

This reduces noise from constant best practice injection during regular coding.

Shows Claude relevant coding standards, patterns, and practices to maintain
consistency and quality across the codebase.

Requirements (from request):
- Parse tool_input JSON from Claude Code hook input
- Extract file path and detect component/domain from path
- Search conventions collection using semantic search
- Inject up to 3 relevant practices into context
- Output goes to stdout (displayed before tool execution)
- Must complete in <500ms
- Exit 0 always (graceful degradation)

Hook Configuration:
    Invoked manually by review agents or explicit skill calls only

Architecture:
    PreToolUse → Check explicit mode → Parse file_path → Detect component → Search conventions
    → Format for display → Output to stdout → Claude sees context → Tool executes

Performance:
    - Target: <500ms (NFR-P1)
    - No background forking needed (PreToolUse is informational)
    - Limit search to 3 results for speed
    - Cache Qdrant client connection

Exit Codes:
    - 0: Success (or graceful degradation on error)
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Setup Python path using shared utility (CR-4 Wave 2)
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    + "/src",
)
from memory.hooks_common import (
    LANGUAGE_MAP,
    PREVIEW_MAX_CHARS,
    get_metrics,
    log_to_activity,
    setup_hook_logging,
    setup_python_path,
)

INSTALL_DIR = setup_python_path()

# Configure structured logging using shared utility (CR-4 Wave 2)
from memory.config import COLLECTION_CONVENTIONS, VALID_AGENTS

logger = setup_hook_logging("ai_memory.hooks")

# Import metrics using shared utility (CR-4 Wave 2)
memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = (
    get_metrics()
)


def detect_component_from_path(file_path: str) -> Tuple[str, str]:
    """Extract component and domain from file path.

    Uses path segments to infer what part of the system is being modified.
    This helps retrieve relevant best practices for that specific area.

    Args:
        file_path: Absolute or relative file path from tool_input

    Returns:
        Tuple of (component, domain) strings

    Examples:
        - "src/auth/login.py" → ("auth", "security")
        - "src/database/migrations/001.sql" → ("database", "data")
        - "src/api/routes/users.py" → ("api", "backend")
        - "tests/unit/test_auth.py" → ("testing", "quality")
        - ".claude/hooks/scripts/session_start.py" → ("hooks", "infrastructure")
        - "docker/docker-compose.yml" → ("docker", "infrastructure")
    """
    # Extract relevant path parts to avoid project name pollution
    # Strategy: Find 'src', 'lib', 'app' marker and use path from there, or just last 2 parts
    # e.g., /path/to/project/src/config_parser.py → src/config_parser.py
    parts = Path(file_path).parts

    # Find common source markers
    source_markers = {
        "src",
        "lib",
        "app",
        "tests",
        "test",
        "scripts",
        ".claude",
        "docker",
    }
    marker_idx = None
    for i, part in enumerate(parts):
        if part.lower() in source_markers:
            marker_idx = i
            break

    if marker_idx is not None:
        # Use path from source marker onwards
        relevant_parts = parts[marker_idx:]
    else:
        # Fallback: use last 2 components (parent dir + filename)
        relevant_parts = parts[-2:] if len(parts) > 2 else parts

    path_lower = "/".join(relevant_parts).lower()

    # Component detection rules (most specific first)
    component_rules = {
        # Core system components
        "auth": ["auth", "authentication", "login", "oauth", "jwt"],
        "database": ["database", "db", "migrations", "models", "schema"],
        "api": ["api", "routes", "endpoints", "rest", "graphql"],
        "frontend": ["frontend", "ui", "components", "views", "pages"],
        "backend": ["backend", "server", "services"],
        "testing": ["test", "tests", "spec", "e2e", "integration"],
        "hooks": ["hooks", ".claude/hooks"],
        "docker": ["docker", "compose", "dockerfile"],
        "monitoring": ["monitoring", "metrics", "prometheus", "grafana"],
        "memory": ["memory", "qdrant", "embeddings", "search"],
    }

    # Domain detection rules
    domain_rules = {
        "security": ["auth", "security", "encryption", "jwt", "oauth"],
        "data": ["database", "db", "models", "schema", "migrations"],
        "backend": ["api", "server", "backend", "services"],
        "frontend": ["frontend", "ui", "components", "react", "vue"],
        "infrastructure": ["docker", "k8s", "kubernetes", "terraform", "deploy"],
        "quality": ["test", "tests", "spec", "qa"],
        "observability": ["monitoring", "metrics", "logging", "tracing"],
    }

    # Find matching component
    component = "general"
    for comp, keywords in component_rules.items():
        if any(keyword in path_lower for keyword in keywords):
            component = comp
            break

    # Find matching domain
    domain = "general"
    for dom, keywords in domain_rules.items():
        if any(keyword in path_lower for keyword in keywords):
            domain = dom
            break

    return component, domain


def build_query(file_path: str, component: str, domain: str, tool_name: str) -> str:
    """Build semantic search query from file context.

    Creates a query that will find relevant best practices for the file
    being modified, incorporating component, domain, and file type.

    Args:
        file_path: Path to file being modified
        component: Detected component (auth, database, api, etc.)
        domain: Detected domain (security, data, backend, etc.)
        tool_name: Tool being used (Edit, Write)

    Returns:
        Query string optimized for semantic search

    Examples:
        - "Best practices for auth Python code security"
        - "Best practices for database migrations data"
        - "Best practices for testing Python quality"
    """
    # Extract file extension for language/framework detection
    ext = Path(file_path).suffix.lower()

    # Use shared language map (CR-4.13)
    language = LANGUAGE_MAP.get(ext, "code")

    # Build query parts
    query_parts = ["Best practices for"]

    # Add component if not general
    if component != "general":
        query_parts.append(component)

    # Add language/file type
    query_parts.append(language)

    # Add domain context if not general
    if domain != "general":
        query_parts.append(domain)

    return " ".join(query_parts)


def format_best_practice(practice: dict, index: int) -> str:
    """Format a single best practice for display.

    Args:
        practice: Best practice dict with content, score, tags, component
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    content = practice.get("content", "")
    score = practice.get("score", 0)
    component = practice.get("component", "general")
    tags = practice.get("tags", [])

    # Build header line
    header_parts = [f"{index}. [{component}]"]
    if tags:
        # Show first 3 tags
        tag_str = ", ".join(tags[:3])
        header_parts.append(f"({tag_str})")
    header_parts.append(f"- Relevance: {score:.0%}")

    header = " ".join(header_parts)

    # Truncate content if too long (keep it concise for PreToolUse)
    # CR-4.12: Use shared constant instead of magic number
    if len(content) > PREVIEW_MAX_CHARS:
        content = content[:PREVIEW_MAX_CHARS] + "..."

    return f"{header}\n{content}\n"


def main() -> int:
    """PreToolUse hook entry point.

    Reads hook input from stdin, extracts file path, searches best practices,
    and outputs relevant practices to stdout for Claude to see before tool execution.

    Returns:
        Exit code: Always 0 (graceful degradation)
    """
    start_time = time.perf_counter()

    try:
        # Check if explicitly invoked (not auto-triggered)
        # When auto-trigger is removed from settings.json, this script
        # will only be called by review agents or manual skills
        explicit_mode = (
            os.environ.get("BMAD_BEST_PRACTICES_EXPLICIT", "false").lower() == "true"
        )

        # If called without explicit flag and not by a review agent, exit silently
        # This is a safety check in case the hook is re-enabled accidentally
        if not explicit_mode:
            # Check for review agent context
            agent_type = os.environ.get("BMAD_AGENT_TYPE", "").lower()
            # CR-4.9: Use VALID_AGENTS from config + additional review-specific agents
            # TEA + review agents always check best practices (TECH-DEBT-015 pending: full redesign)
            review_agents = list(VALID_AGENTS) + [
                "code-review",
                "adversarial-review",
                "security-auditor",
                "code-reviewer",
            ]
            if agent_type not in review_agents:
                logger.debug(
                    "conventions_skipped_no_trigger", extra={"agent_type": agent_type}
                )
                return 0  # Silent exit - no injection

        # Parse hook input from stdin
        try:
            hook_input = json.load(sys.stdin)
        except json.JSONDecodeError:
            # Malformed JSON - graceful degradation
            logger.warning("malformed_hook_input")
            return 0

        # Extract context
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
        cwd = hook_input.get("cwd", os.getcwd())

        # Extract file path from tool_input
        # Edit has "file_path", Write has "file_path"
        file_path = tool_input.get("file_path", "")

        if not file_path:
            # No file path - nothing to do
            logger.debug("no_file_path", extra={"tool_name": tool_name})
            return 0

        # Detect component and domain from path
        component, domain = detect_component_from_path(file_path)

        # Build semantic query
        query = build_query(file_path, component, domain, tool_name)

        # Search conventions collection
        # Import here to avoid circular dependencies
        from memory.config import get_config
        from memory.health import check_qdrant_health
        from memory.project import detect_project
        from memory.qdrant_client import get_qdrant_client
        from memory.search import MemorySearch

        config = get_config()
        client = get_qdrant_client(config)

        # Detect project for metrics (required per §7.3 multi-tenancy)
        project_name = detect_project(cwd)

        # Check Qdrant health (graceful degradation if down)
        if not check_qdrant_health(client):
            logger.warning("qdrant_unavailable")
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CONVENTIONS,
                    status="failed",
                    project=project_name,
                ).inc()
            return 0

        # Search for relevant best practices
        search = MemorySearch(config)
        try:
            # Use SIMILARITY_THRESHOLD from config (typically 0.4) instead of hardcoded value
            # Best practices need reasonable relevance, but 0.5 was filtering too aggressively
            threshold = config.similarity_threshold

            results = search.search(
                query=query,
                collection=COLLECTION_CONVENTIONS,
                group_id=None,  # Conventions are shared across projects
                limit=3,  # Up to 3 relevant practices (requirement)
                score_threshold=threshold,
            )

            if not results:
                # No relevant practices found - log to activity file for visibility
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(
                    f"🔍 PreToolUse searched conventions for {file_path} (0 results) [{duration_ms:.0f}ms]"
                )
                logger.debug(
                    "no_conventions_found",
                    extra={
                        "file_path": file_path,
                        "component": component,
                        "domain": domain,
                        "query": query,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_CONVENTIONS,
                        status="empty",
                        project=project_name,
                    ).inc()
                return 0

            # Format for stdout display
            # This output will be shown to Claude BEFORE the tool executes
            output_parts = []
            output_parts.append("\n" + "=" * 70)
            output_parts.append("🎯 RELEVANT BEST PRACTICES")
            output_parts.append("=" * 70)
            output_parts.append(f"File: {file_path}")
            output_parts.append(f"Component: {component} | Domain: {domain}")
            output_parts.append("")

            for i, practice in enumerate(results, 1):
                output_parts.append(format_best_practice(practice, i))

            output_parts.append("=" * 70 + "\n")

            # Output to stdout (Claude sees this before tool execution)
            print("\n".join(output_parts))

            # Log success with user visibility
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_to_activity(
                f"🎯 Best practices retrieved (explicit) for {file_path} [{duration_ms:.0f}ms]"
            )
            logger.info(
                "conventions_retrieved",
                extra={
                    "file_path": file_path,
                    "component": component,
                    "domain": domain,
                    "results_count": len(results),
                    "duration_ms": round(duration_ms, 2),
                    "project": project_name,
                },
            )

            # Metrics
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CONVENTIONS,
                    status="success",
                    project=project_name,
                ).inc()
            if retrieval_duration_seconds:
                retrieval_duration_seconds.observe(duration_ms / 1000.0)
            if hook_duration_seconds:
                hook_duration_seconds.labels(
                    hook_type="PreToolUse", status="success", project=project_name
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
        proj = project_name if "project_name" in dir() else "unknown"
        if memory_retrievals_total:
            memory_retrievals_total.labels(
                collection=COLLECTION_CONVENTIONS,
                status="failed",
                project=proj,
            ).inc()
        if hook_duration_seconds:
            duration_seconds = (time.perf_counter() - start_time) / 1000.0
            hook_duration_seconds.labels(
                hook_type="PreToolUse", status="error", project=proj
            ).observe(duration_seconds)

        return 0  # Always exit 0 - graceful degradation


if __name__ == "__main__":
    sys.exit(main())
