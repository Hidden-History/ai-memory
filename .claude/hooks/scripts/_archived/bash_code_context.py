#!/usr/bin/env python3
"""PreToolUse Hook - Retrieve code patterns before Bash execution.

Provides Claude with relevant implementation patterns when file paths
are detected in bash commands. This is code CONTEXT, not error detection.

Signal: File paths detected in bash command
Action: Query code-patterns WHERE type="implementation"

Requirements:
- Parse tool_input JSON from Claude Code hook input
- Detect working directory and extract file context from command
- Search code-patterns collection for actual code patterns
- Priority 1: Exact file path matches
- Priority 2: Similar files by language/framework
- Inject up to 3 relevant code-patterns into context
- Output goes to stdout (displayed before tool execution)
- Must complete in <500ms
- Exit 0 always (graceful degradation)

Hook Configuration:
    PreToolUse with matcher "Bash"

Architecture:
    PreToolUse → Parse command → Extract file context → Search code-patterns
    → Prioritize by file_path → Format for display → Output to stdout

Performance:
    - Target: <500ms (NFR-P1)
    - No background forking needed (PreToolUse is informational)
    - Limit search to 3 results for speed
    - Cache Qdrant client connection

Exit Codes:
    - 0: Success (or graceful degradation on error)
"""

import json
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
INSTALL_DIR = os.environ.get(
    "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
)
sys.path.insert(0, os.path.join(INSTALL_DIR, "src"))

# CR-2 FIX: Use consolidated logging and metrics from hooks_common
from memory.config import COLLECTION_CODE_PATTERNS
from memory.hooks_common import get_metrics, log_to_activity, setup_hook_logging

logger = setup_hook_logging()

# CR-2 FIX: Use consolidated metrics import
memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = (
    get_metrics()
)

# Import activity logging (TECH-DEBT-014)
from memory.activity_log import log_error_context_retrieval

# Language detection by file extension
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
}


def extract_file_paths(command: str) -> list[str]:
    """Extract file paths from bash command.

    Args:
        command: Bash command being executed

    Returns:
        List of file paths found in the command

    Examples:
        - "pytest tests/test_auth.py" → ["tests/test_auth.py"]
        - "python src/main.py --verbose" → ["src/main.py"]
        - "ls -la" → []
    """
    file_paths = []

    # Split command into tokens
    tokens = command.split()

    for token in tokens:
        # Skip flags
        if token.startswith("-"):
            continue

        # Check if token looks like a file path
        # Contains / or . and has file extension
        if ("/" in token or "." in token) and not token.endswith(("/", ".")):
            # Remove quotes if present
            token = token.strip("\"'")

            # Check if has recognized extension
            from pathlib import Path

            ext = Path(token).suffix
            if ext in LANGUAGE_MAP:
                file_paths.append(token)

    return file_paths


def detect_language(file_path: str) -> str | None:
    """Detect programming language from file extension.

    Args:
        file_path: Path to file

    Returns:
        Language name if detected, None otherwise

    Examples:
        - "src/main.py" → "python"
        - "tests/test.ts" → "typescript"
        - "README.md" → "markdown"
    """

    ext = Path(file_path).suffix.lower()
    return LANGUAGE_MAP.get(ext)


def format_implementation(impl: dict, index: int) -> str:
    """Format a single implementation for display.

    Args:
        impl: Implementation dict with content, score, file_path, language, created_at
        index: 1-based index for numbering

    Returns:
        Formatted string for stdout display
    """
    score = impl.get("score", 0)
    file_path = impl.get("file_path", "unknown")
    language = impl.get("language", "")
    framework = impl.get("framework", "")
    created_at = impl.get("created_at", "")
    content = impl.get("content", "")

    # Build header with relevance score
    header = f"{index}. **implementation** ({score:.0%}) - {created_at} [code-patterns]"

    # Add file path
    file_line = f"   File: {file_path}"

    # Add language and framework
    tech_parts = []
    if language:
        tech_parts.append(f"Language: {language}")
    if framework:
        tech_parts.append(f"Framework: {framework}")
    tech_line = f"   {' | '.join(tech_parts)}" if tech_parts else ""

    # Add content preview (first 150 chars)
    content_preview = content[:150].replace("\n", " ").strip()
    if len(content) > 150:
        content_preview += "..."
    pattern_line = f"   Pattern: {content_preview}"

    parts = [header, file_line]
    if tech_line:
        parts.append(tech_line)
    parts.append(pattern_line)

    return "\n".join(parts)


def main() -> int:
    """PreToolUse hook entry point.

    Reads hook input from stdin, extracts file paths from bash commands,
    searches code-patterns collection for relevant code patterns,
    prioritizes by file path match, and outputs to stdout.

    Priority 1: Exact file path matches
    Priority 2: Similar files by language/framework

    Returns:
        Exit code: Always 0 (graceful degradation)
    """
    start_time = time.perf_counter()

    try:
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

        # Validate this is a Bash tool
        if tool_name != "Bash":
            logger.debug("not_bash_tool", extra={"tool_name": tool_name})
            return 0

        # Extract command from tool_input
        command = tool_input.get("command", "")

        if not command:
            # No command - nothing to do
            logger.debug("no_command")
            return 0

        # Extract file paths from command
        file_paths = extract_file_paths(command)

        if not file_paths:
            # No file paths in command - skip retrieval
            logger.debug("no_file_paths_in_command", extra={"command": command[:50]})
            return 0

        # Use first file path as primary target
        target_file_path = file_paths[0]

        # Detect language from file path
        language = detect_language(target_file_path)

        # Search code-patterns collection for implementation patterns
        # Import here to avoid circular dependencies
        from memory.config import get_config
        from memory.health import check_qdrant_health
        from memory.project import detect_project
        from memory.qdrant_client import get_qdrant_client
        from memory.search import MemorySearch

        config = get_config()
        client = get_qdrant_client(config)

        # Check Qdrant health (graceful degradation if down)
        if not check_qdrant_health(client):
            logger.warning("qdrant_unavailable")
            if memory_retrievals_total:
                memory_retrievals_total.labels(
                    collection=COLLECTION_CODE_PATTERNS, status="failed"
                ).inc()
            return 0

        # Detect project for group filtering
        project_name = detect_project(cwd)

        # Search for relevant code-patterns
        search = MemorySearch(config)
        results = []

        try:
            # FIX #10: Removed misleading comment about file path filtering
            # Current implementation: Fetch recent implementations, then fall back to language-based search
            # TODO (tech debt): Add file_path payload filtering when MemorySearch supports it
            results = search.search(
                query="",  # No semantic search - get recent implementations
                collection=COLLECTION_CODE_PATTERNS,
                group_id=project_name,
                limit=3,
                score_threshold=0.0,
                memory_type="implementation",
            )

            # Priority 2: Fallback to similar files by language
            if not results and language:
                results = search.search(
                    query=f"{language} implementation patterns",
                    collection=COLLECTION_CODE_PATTERNS,
                    group_id=project_name,
                    limit=3,
                    score_threshold=0.4,
                    memory_type="implementation",
                )

            if not results:
                # No relevant code-patterns found - graceful degradation
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_to_activity(
                    f"🔧 CodeContext: No relevant code-patterns found for {target_file_path}",
                    INSTALL_DIR,
                )
                logger.debug(
                    "no_code_patterns_found",
                    extra={
                        "command": command[:50],
                        "file_path": target_file_path,
                        "language": language,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                if memory_retrievals_total:
                    memory_retrievals_total.labels(
                        collection=COLLECTION_CODE_PATTERNS, status="empty"
                    ).inc()
                return 0

            # Format for stdout display
            # This output will be shown to Claude BEFORE the tool executes
            output_parts = []
            output_parts.append("\n" + "=" * 70)
            output_parts.append("## Code Context for Bash Command")
            output_parts.append("=" * 70)
            output_parts.append(f"File: {target_file_path}")
            if language:
                output_parts.append(f"Language: {language}")
            output_parts.append("")

            for i, impl in enumerate(results, 1):
                output_parts.append(format_implementation(impl, i))
                output_parts.append("")

            output_parts.append("=" * 70 + "\n")

            # Output to stdout (Claude sees this before tool execution)
            print("\n".join(output_parts))

            # Log success with user visibility
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_to_activity(
                f"🔧 CodeContext loaded {len(results)} code-patterns for {target_file_path} [{duration_ms:.0f}ms]",
                INSTALL_DIR,
            )

            # TECH-DEBT-014: Comprehensive logging with implementation results
            log_error_context_retrieval(
                target_file_path, language, results, duration_ms
            )

            logger.info(
                "code_patterns_retrieved",
                extra={
                    "command": command[:50],
                    "file_path": target_file_path,
                    "language": language,
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
                    hook_type="PreToolUse_CodeContext"
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
                collection=COLLECTION_CODE_PATTERNS, status="failed"
            ).inc()
        if hook_duration_seconds:
            duration_seconds = time.perf_counter() - start_time
            hook_duration_seconds.labels(hook_type="PreToolUse_CodeContext").observe(
                duration_seconds
            )

        return 0  # Always exit 0 - graceful degradation


if __name__ == "__main__":
    sys.exit(main())
