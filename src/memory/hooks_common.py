"""Common utilities for Claude Code hooks.

Shared functionality across hook scripts to reduce duplication.
Consolidated from Phase B code review (CR-1.2, CR-1.4, CR-1.7, CR-1.13).
"""

import logging
import os
import random
import sys
from pathlib import Path
from typing import List, Optional

# Shared constants (CR-4 Wave 2 DRY consolidation)
# Language detection map - replaces duplicate in 4+ files
LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React",
    ".tsx": "React TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".sql": "SQL",
    ".sh": "Bash",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".md": "Markdown",
}

# Preview/truncation constants
PREVIEW_MAX_CHARS = 400  # For best_practices_retrieval.py format_best_practice()


def setup_python_path() -> str:
    """Setup Python path for hook imports.

    Consolidated from CR-1.7 (duplicated across 6 hook scripts).

    Returns:
        AI Memory installation directory path

    Note:
        Must be called before importing memory modules.
    """
    install_dir = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))
    sys.path.insert(0, os.path.join(install_dir, "src"))
    return install_dir


def setup_hook_logging(logger_name: str = "ai_memory.hooks") -> logging.Logger:
    """Configure structured logging for hook scripts.

    Args:
        logger_name: Name for the logger instance

    Returns:
        Configured logger instance

    Note:
        - Logs to stderr (stdout reserved for Claude context)
        - Uses StructuredFormatter for consistent log format
        - Sets INFO level by default
    """
    from memory.logging_config import StructuredFormatter

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def _rotate_log_if_needed(log_file: Path, max_lines: int = 500, keep_lines: int = 450) -> None:
    """Rotate log file if it exceeds max_lines.

    Only checks ~2% of the time to minimize I/O overhead.
    Keeps last keep_lines when rotating.

    Args:
        log_file: Path to the log file to check/rotate
        max_lines: Maximum lines before rotation (default: 500)
        keep_lines: Lines to keep after rotation (default: 450)

    Note:
        - Probabilistic check (2% of calls) for efficiency
        - Fails silently on error (graceful degradation)
    """
    # Only check occasionally (2% of calls) to minimize overhead
    if random.random() > 0.02:
        return

    try:
        if not log_file.exists():
            return

        with open(log_file, 'r') as f:
            lines = f.readlines()

        if len(lines) > max_lines:
            # Keep only the last keep_lines
            with open(log_file, 'w') as f:
                f.writelines(lines[-keep_lines:])
    except Exception:
        pass  # Graceful degradation


def log_to_activity(message: str, install_dir: Optional[str] = None) -> None:
    """Log message to activity log for user visibility.

    Consolidated from CR-1.2 (_log_to_activity duplicated across 4 files).
    Activity log provides user-visible feedback about memory operations.
    Located at $AI_MEMORY_INSTALL_DIR/logs/activity.log

    Args:
        message: Message to log (newlines will be escaped)
        install_dir: Optional AI Memory installation directory (auto-detected if None)

    Note:
        - Fails silently on error (graceful degradation)
        - Uses ISO 8601 timestamp format per CR-1.13
    """
    from datetime import datetime

    if install_dir is None:
        install_dir = os.environ.get('AI_MEMORY_INSTALL_DIR', os.path.expanduser('~/.ai-memory'))

    log_dir = Path(install_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "activity.log"

    # Rotate log file if needed (probabilistic check for efficiency)
    _rotate_log_if_needed(log_file)

    # CR-1.13: Standardized ISO 8601 timestamp
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Escape newlines for single-line output (Streamlit parses line-by-line)
    safe_message = message.replace('\n', '\\n')

    try:
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {safe_message}\n")
    except Exception:
        pass  # Graceful degradation


def get_hook_timeout() -> int:
    """Get timeout value from environment variable.

    Consolidated from CR-1.4 (duplicated in error_store_async.py, store_async.py).

    Returns:
        Timeout in seconds (default: 60)

    Environment Variables:
        HOOK_TIMEOUT: Timeout in seconds for background operations
    """
    try:
        timeout_str = os.getenv("HOOK_TIMEOUT", "60")
        return int(timeout_str)
    except ValueError:
        logger = logging.getLogger("ai_memory.hooks")
        logger.warning(
            "invalid_timeout_env",
            extra={"value": timeout_str, "using_default": 60}
        )
        return 60


def get_metrics():
    """Get Prometheus metrics objects or None if unavailable.

    Consolidated from CR-2 (duplicate metrics import in 7+ hook files).
    Eliminates 70+ lines of duplicate try/except blocks.

    Returns:
        Tuple of (memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds).
        Each element is None if metrics module unavailable.

    Example:
        >>> from memory.hooks_common import get_metrics
        >>> memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds = get_metrics()
        >>> if memory_retrievals_total:
        ...     memory_retrievals_total.labels(collection="code-patterns", status="success").inc()
    """
    logger = logging.getLogger("ai_memory.hooks")
    try:
        from memory.metrics import (
            memory_retrievals_total,
            retrieval_duration_seconds,
            hook_duration_seconds
        )
        return memory_retrievals_total, retrieval_duration_seconds, hook_duration_seconds
    except ImportError:
        logger.warning("metrics_module_unavailable")
        return None, None, None


def get_trigger_metrics():
    """Get V2.0 trigger-specific Prometheus metrics or None if unavailable.

    TECH-DEBT-067: New metrics for V2.0 trigger system.

    Returns:
        Tuple of (trigger_fires_total, trigger_results_returned).
        Each element is None if metrics module unavailable.

    Example:
        >>> from memory.hooks_common import get_trigger_metrics
        >>> trigger_fires_total, trigger_results_returned = get_trigger_metrics()
        >>> if trigger_fires_total:
        ...     trigger_fires_total.labels(trigger_type="decision_keywords", status="success", project="my-project").inc()
    """
    logger = logging.getLogger("ai_memory.hooks")
    try:
        from memory.metrics import (
            trigger_fires_total,
            trigger_results_returned
        )
        return trigger_fires_total, trigger_results_returned
    except ImportError:
        logger.warning("trigger_metrics_unavailable")
        return None, None


def get_token_metrics():
    """Get V2.0 token tracking Prometheus metrics or None if unavailable.

    TECH-DEBT-067: New metrics for V2.0 token usage tracking.

    Returns:
        Tuple of (tokens_consumed_total, context_injection_tokens).
        Each element is None if metrics module unavailable.

    Example:
        >>> from memory.hooks_common import get_token_metrics
        >>> tokens_consumed_total, context_injection_tokens = get_token_metrics()
        >>> if tokens_consumed_total:
        ...     tokens_consumed_total.labels(operation="injection", direction="output", project="my-project").inc(500)
    """
    logger = logging.getLogger("ai_memory.hooks")
    try:
        from memory.metrics import (
            tokens_consumed_total,
            context_injection_tokens
        )
        return tokens_consumed_total, context_injection_tokens
    except ImportError:
        logger.warning("token_metrics_unavailable")
        return None, None


def extract_error_signature(output: str, max_length: int = 200) -> str:
    """Extract searchable error signature from command output.

    FIX #5: Shared implementation to avoid duplication between hooks.

    This function looks for lines containing error keywords and returns
    the first match as the error signature. If no error keywords found,
    returns the last non-empty line (often contains the error).

    Args:
        output: Error output text from command
        max_length: Maximum length of returned signature

    Returns:
        Extracted error signature, truncated to max_length

    Example:
        >>> output = "File not found\\nError: invalid path /foo/bar"
        >>> extract_error_signature(output)
        'Error: invalid path /foo/bar'
    """
    lines = output.strip().split('\n')

    # Look for lines containing error keywords
    error_keywords = ['error', 'exception', 'failed', 'failure', 'fatal', 'traceback', 'bug']

    for line in lines:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in error_keywords):
            # Return first error line, truncated if too long
            return line.strip()[:max_length]

    # Fallback: return last non-empty line (often the error)
    for line in reversed(lines):
        if line.strip():
            return line.strip()[:max_length]

    return "Error detected in command output"


def read_transcript(transcript_path: str) -> List[dict]:
    """Read JSONL transcript file from Claude Code.

    Consolidated from CR-3.3 (duplicated in agent_response_capture.py and pre_compact_save.py).

    Args:
        transcript_path: Path to .jsonl transcript file (supports ~)

    Returns:
        List of transcript entries (dicts), empty list if file not found or errors

    Note:
        - Expands ~ in path automatically
        - Skips malformed JSON lines gracefully
        - Returns empty list on any errors (graceful degradation)
    """
    import json

    transcript_entries = []

    # Expand ~ in path
    expanded_path = os.path.expanduser(transcript_path)

    if not os.path.exists(expanded_path):
        logger = logging.getLogger("ai_memory.hooks")
        logger.warning(
            "transcript_not_found",
            extra={"path": transcript_path, "expanded": expanded_path}
        )
        return []

    try:
        with open(expanded_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        transcript_entries.append(entry)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
    except Exception as e:
        logger = logging.getLogger("ai_memory.hooks")
        logger.warning(
            "transcript_read_error",
            extra={"error": str(e), "path": expanded_path}
        )
        return []

    return transcript_entries
