#!/usr/bin/env python3
"""Memory Filtering Module

This module provides two filtering systems:

1. Implementation Pattern Filtering (Phase A)
   - ImplementationFilter class for code pattern capture
   - Used by post_tool_capture.py hook

2. Conversation Filtering (TECH-DEBT-047-050)
   - filter_low_value_content() - removes UI menus, separators
   - smart_truncate() - sentence/word boundary truncation
   - is_duplicate_message() - 5-minute window deduplication
   - Used by session_start.py for context injection quality

Environment Variables:
- BMAD_FILTER_MIN_LINES: Minimum lines to store (default: 10)
- BMAD_FILTER_SKIP_EXTENSIONS: Additional extensions to skip (comma-separated)
"""

import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Set

from qdrant_client.models import Filter, FieldCondition, MatchValue

from datetime import datetime, timedelta, UTC

from .config import get_config
from .qdrant_client import get_qdrant_client

__all__ = [
    "ImplementationFilter",
    "filter_low_value_content",
    "smart_truncate",
    "is_duplicate_message",
]

logger = logging.getLogger("bmad.memory.filters")


class ImplementationFilter:
    """Filter for implementation patterns before storage.

    Prevents junk accumulation by filtering out:
    - Small changes (< min_lines_changed)
    - Non-code files (.md, .txt, .json, etc.)
    - Generated/build directories (node_modules/, venv/, etc.)
    - Insignificant content (no functions, classes, or imports)

    Example:
        >>> filter = ImplementationFilter()
        >>> filter.should_store("README.md", "# Title", "Write")
        False
        >>> filter.should_store("app.py", "def foo():\\n    pass", "Write")
        True
    """

    def __init__(self):
        """Initialize filter with environment-based configuration."""
        # Load min_lines from environment (default: 10)
        self.min_lines = int(os.environ.get('BMAD_FILTER_MIN_LINES', '10'))

        # Load skip extensions (with user overrides)
        self.skip_extensions = self._load_skip_extensions()

        # Path patterns to skip (generated/build directories)
        self.skip_path_patterns = [
            "node_modules/",
            "venv/",
            ".venv/",
            "env/",
            ".git/",
            "__pycache__/",
            ".pytest_cache/",
            "dist/",
            "build/",
            ".next/",
            ".nuxt/",
            "target/",  # Rust
            "vendor/",  # PHP/Go
            ".terraform/",
            "coverage/",
            ".coverage/",
        ]

        # Maximum content length before truncation
        self.max_content_length = 5000

        logger.debug(
            "filter_initialized",
            extra={
                "min_lines": self.min_lines,
                "skip_extensions_count": len(self.skip_extensions),
                "skip_path_patterns_count": len(self.skip_path_patterns),
            }
        )

    def _load_skip_extensions(self) -> Set[str]:
        """Load skip extensions with user overrides from environment.

        Returns:
            Set of extensions to skip (including dot, e.g., ".md")
        """
        # Default extensions to skip
        defaults = {
            ".md", ".txt", ".json", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".lock",
            ".log", ".svg", ".png", ".jpg", ".jpeg", ".gif",
            ".pdf", ".zip", ".tar", ".gz",
        }

        # Check for user overrides (extends defaults, doesn't replace)
        user_extensions = os.environ.get('BMAD_FILTER_SKIP_EXTENSIONS', '')
        if user_extensions:
            for ext in user_extensions.split(','):
                ext = ext.strip()
                if ext and not ext.startswith('.'):
                    ext = '.' + ext
                if ext:
                    defaults.add(ext)

        return defaults

    def should_store(self, file_path: str, content: str, tool_name: str) -> bool:
        """Determine if this implementation should be stored.

        Applies all filtering criteria in order:
        1. Check file extension (fast reject)
        2. Check path patterns (fast reject)
        3. Check content significance (important - even short significant code matters)
        4. Check line count (only if not already significant)

        Args:
            file_path: Path to the file being edited/written
            content: Content of the change
            tool_name: Tool that made the change (Edit, Write, NotebookEdit)

        Returns:
            True if content should be stored, False otherwise
        """
        # Filter 1: Skip by file extension
        file_ext = Path(file_path).suffix.lower()
        if file_ext in self.skip_extensions:
            logger.debug(
                "filter_skip_extension",
                extra={
                    "file_path": file_path,
                    "extension": file_ext,
                    "tool_name": tool_name,
                }
            )
            return False

        # Filter 2: Skip by path pattern (generated dirs)
        normalized_path = file_path.replace('\\', '/')
        for pattern in self.skip_path_patterns:
            if pattern in normalized_path:
                logger.debug(
                    "filter_skip_path_pattern",
                    extra={
                        "file_path": file_path,
                        "pattern": pattern,
                        "tool_name": tool_name,
                    }
                )
                return False

        # Filter 3: Check content significance FIRST
        # Rationale: A compact function definition (8 lines) is more valuable
        # than 15 lines of variable assignments. Significance trumps line count.
        is_significant = self.is_significant(content)

        # Filter 4: Check line count (only applies if content is NOT significant)
        lines = content.split('\n')
        line_count = len(lines)

        if not is_significant and line_count < self.min_lines:
            logger.debug(
                "filter_skip_below_min_lines",
                extra={
                    "file_path": file_path,
                    "lines": line_count,
                    "min_lines": self.min_lines,
                    "tool_name": tool_name,
                }
            )
            return False

        # If content is insignificant, reject regardless of line count
        if not is_significant:
            logger.debug(
                "filter_skip_not_significant",
                extra={
                    "file_path": file_path,
                    "lines": line_count,
                    "tool_name": tool_name,
                }
            )
            return False

        # All filters passed - store this content
        logger.debug(
            "filter_pass",
            extra={
                "file_path": file_path,
                "lines": line_count,
                "is_significant": is_significant,
                "tool_name": tool_name,
            }
        )
        return True

    def is_significant(self, content: str) -> bool:
        """Check if content contains significant patterns.

        Significance criteria (any ONE of these = significant):
        - Function definition: def, function, func
        - Class definition: class
        - Import block: 3+ consecutive import/from lines
        - Major structural patterns (interface, struct, trait, etc.)

        Args:
            content: Content to check for significance

        Returns:
            True if content is significant, False otherwise
        """
        lines = content.split('\n')

        # Pattern 1: Function definitions
        function_patterns = [
            r'\bdef\s+\w+\s*\(',           # Python: def foo(
            r'\bfunction\s+\w+\s*\(',      # JavaScript: function foo(
            r'\bfunc\s+\w+\s*\(',          # Go: func foo(
            r'\bfn\s+\w+\s*\(',            # Rust: fn foo(
            r'^\s*\w+\s*:\s*function\s*\(',  # Object methods
        ]

        for pattern in function_patterns:
            if re.search(pattern, content, re.MULTILINE):
                logger.debug("significance_detected", extra={"reason": "function_definition"})
                return True

        # Pattern 2: Class definitions
        class_patterns = [
            r'\bclass\s+\w+',              # Python/JS/Java: class Foo
            r'\binterface\s+\w+',          # TypeScript: interface Foo
            r'\bstruct\s+\w+',             # Go/Rust: struct Foo
            r'\btrait\s+\w+',              # Rust: trait Foo
            r'\benum\s+\w+',               # Multiple languages
        ]

        for pattern in class_patterns:
            if re.search(pattern, content, re.MULTILINE):
                logger.debug("significance_detected", extra={"reason": "class_definition"})
                return True

        # Pattern 3: Import block (3+ consecutive lines)
        import_count = 0
        max_consecutive_imports = 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('import ') or stripped.startswith('from '):
                import_count += 1
                max_consecutive_imports = max(max_consecutive_imports, import_count)
            else:
                import_count = 0

        if max_consecutive_imports >= 3:
            logger.debug("significance_detected", extra={"reason": "import_block", "count": max_consecutive_imports})
            return True

        # Pattern 4: Decorator usage (Python)
        if re.search(r'^\s*@\w+', content, re.MULTILINE):
            logger.debug("significance_detected", extra={"reason": "decorator"})
            return True

        # No significant patterns found
        return False

    def is_duplicate(self, content_hash: str, collection: str) -> bool:
        """Check if content_hash already exists in collection.

        Uses Qdrant scroll with filter on content_hash field.
        Fails open: Returns False if check itself fails (better to allow
        potential duplicate than lose memory).

        Args:
            content_hash: SHA256 hash to check (format: "sha256:...")
            collection: Qdrant collection name to check

        Returns:
            True if hash exists (duplicate), False otherwise

        Note:
            This is a lightweight check using only content_hash.
            Does NOT check group_id - that's handled by storage.py
            when the actual store operation happens.
        """
        try:
            config = get_config()
            qdrant_client = get_qdrant_client(config)

            # Query by content_hash field
            results = qdrant_client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="content_hash",
                            match=MatchValue(value=content_hash),
                        )
                    ]
                ),
                limit=1,
            )

            if results[0]:  # results is tuple: (records, next_page_offset)
                logger.debug(
                    "duplicate_found",
                    extra={
                        "content_hash": content_hash,
                        "collection": collection,
                        "existing_id": str(results[0][0].id),
                    }
                )
                return True

            return False

        except Exception as e:
            # Structured exception handling (addresses review feedback on error specificity)
            # Instead of catching all exceptions, we now handle specific cases.
            from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException

            if isinstance(e, (UnexpectedResponse, ResponseHandlingException)):
                logger.error(
                    "qdrant_connection_failed_during_dedup",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "content_hash": content_hash,
                        "collection": collection,
                    }
                )
            elif isinstance(e, ValueError):
                logger.warning(
                    "invalid_hash_format_in_dedup",
                    extra={
                        "content_hash": content_hash,
                        "collection": collection,
                    }
                )
            else:
                # Unexpected error - log as critical for investigation
                logger.critical(
                    "unexpected_dedup_failure",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "content_hash": content_hash,
                        "collection": collection,
                    }
                )

            # Fail open: Allow storage if check fails (graceful degradation)
            return False

    def truncate_content(self, content: str) -> str:
        """Truncate content to max_content_length if needed.

        Args:
            content: Content to potentially truncate

        Returns:
            Original content or truncated version with marker
        """
        if len(content) <= self.max_content_length:
            return content

        truncated = content[:self.max_content_length - 12] + " [TRUNCATED]"

        logger.info(
            "content_truncated",
            extra={
                "original_length": len(content),
                "truncated_length": len(truncated),
            }
        )

        return truncated


# Conversation Content Filtering (TECH-DEBT-047-050)


def filter_low_value_content(content: str) -> str:
    """Filter out low-value content from conversation context.

    Removes:
    - UI menu patterns: [MH], [CH], [PS], etc.
    - Menu separator lines: ─────
    - Truncated ASCII diagram lines (ending with ...)

    Args:
        content: Content to filter

    Returns:
        Filtered content with low-value lines removed
    """
    lines = content.split('\n')
    filtered_lines = []

    # BMAD agent menu patterns - these appear in agent responses when
    # displaying interactive menus. They add noise without semantic value.
    # Patterns: [MH]=Main Hub, [CH]=Command Hub, [PS]=Parzival Start, etc.
    menu_patterns = [
        r'\[MH\]', r'\[CH\]', r'\[PS\]', r'\[DA\]', r'\[CR\]', r'\[DS\]', r'\[PM\]',
    ]

    for line in lines:
        # Skip menu separator lines
        if '─' in line and line.strip().startswith('─'):
            continue

        # Skip lines with menu command patterns
        skip_line = False
        for pattern in menu_patterns:
            if re.search(pattern, line):
                skip_line = True
                break

        if skip_line:
            continue

        # Skip truncated ASCII diagram lines (box-drawing chars + ...)
        if re.search(r'[┌┐└┘├┤┬┴┼│─].*\.\.\.$', line.strip()):
            continue

        filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def smart_truncate(content: str, max_length: int) -> str:
    """Truncate content at sentence or word boundaries.

    Priority:
    1. No truncation if content fits
    2. Truncate at sentence boundary (., !, ?)
    3. Truncate at word boundary
    4. Never cut mid-word

    Args:
        content: Content to truncate
        max_length: Maximum length (including ... marker)

    Returns:
        Truncated content with ... marker if truncated
    """
    if len(content) <= max_length:
        return content

    # Reserve space for ... marker
    target_length = max_length - 3

    # Try to truncate at sentence boundary
    sentence_endings = ['.', '!', '?']
    for ending in sentence_endings:
        # Find last sentence ending before target length
        pos = content.rfind(ending, 0, target_length)
        if pos > 0:
            # Include the punctuation mark
            return content[:pos + 1] + "..."

    # No sentence boundary found - truncate at word boundary
    truncated = content[:target_length]

    # Find last space
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]

    return truncated.rstrip() + "..."


def is_duplicate_message(
    content: str,
    timestamp: str,
    previous_messages: list[dict],
    window_minutes: int = 5  # Typical conversation turn is 2-3 min; 5 min catches immediate repeats without over-filtering
) -> bool:
    """Check if message is a duplicate within time window.

    Args:
        content: Message content to check
        timestamp: ISO format timestamp of current message
        previous_messages: List of previous messages with 'content' and 'timestamp'
        window_minutes: Time window for duplicate detection. Default 5 minutes
                       based on typical conversation cadence (2-3 min per turn).
                       Catches immediate repeats without filtering legitimate
                       similar questions asked hours apart.

    Returns:
        True if duplicate found within window, False otherwise

    Note:
        Currently uses exact content matching only. Near-duplicates
        (e.g., "How do I X?" vs "How can I X?") are not detected.
        Fuzzy matching was considered but adds complexity and latency
        for marginal benefit in typical conversation flows.
    """
    try:
        current_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        # Invalid timestamp - can't check duplicates
        return False

    for msg in previous_messages:
        msg_content = msg.get("content", "")
        msg_timestamp = msg.get("timestamp", "")

        # Check if content matches
        if msg_content != content:
            continue

        # Check if within time window
        try:
            msg_time = datetime.fromisoformat(msg_timestamp.replace('Z', '+00:00'))
            time_diff = abs((current_time - msg_time).total_seconds() / 60)

            if time_diff <= window_minutes:
                logger.debug(
                    "duplicate_message_detected",
                    extra={
                        "time_diff_minutes": round(time_diff, 2),
                        "window_minutes": window_minutes,
                    }
                )
                return True
        except (ValueError, AttributeError):
            # Invalid timestamp in previous message - skip
            continue

    return False
