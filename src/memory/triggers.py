"""Trigger detection for Memory System V2.0 Phase 3.

Automatic triggers that retrieve relevant memories when specific signals are detected.

Architecture:
- Error detection: Recognizes error patterns in conversation
- New file: Detects file creation in PreToolUse hooks
- First edit: Tracks first edit per file per session
- Decision keywords: Detects user questions about past decisions

Configuration:
- TRIGGER_CONFIG defines enabled triggers and their parameters
- Session state tracked in-memory with thread safety
- Automatic cleanup prevents unbounded growth
"""

import logging
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("ai_memory.triggers")

# Session state tracking with thread safety and cleanup
# Maps session_id -> set of file paths edited in that session
_session_edited_files: dict[str, set[str]] = {}
_session_last_access: dict[str, datetime] = {}
_session_lock = threading.RLock()

# Session cleanup configuration
MAX_SESSIONS = 100
SESSION_TTL = timedelta(hours=24)


# Trigger configuration from spec Section 9.2
TRIGGER_CONFIG = {
    "error_detection": {
        "enabled": True,
        "patterns": [
            # Only structured error patterns to avoid false positives
            # Removed: "failed", "error", "bug" (too broad - match normal conversation)
            "Error:",
            "Exception:",
            "Traceback",
            "FAILED:",  # All-caps for test failures
            "error:",  # Lowercase structured form
        ],
        "collection": "code-patterns",
        "type_filter": "error_fix",
        "max_results": 3,
    },
    "new_file": {
        "enabled": True,
        "collection": "conventions",
        "type_filter": ["naming", "structure"],
        "max_results": 2,
    },
    "first_edit": {
        "enabled": True,
        "collection": "code-patterns",
        "type_filter": None,  # Search all types - implementation patterns are relevant to first edits
        "max_results": 3,
    },
    "decision_keywords": {
        "enabled": True,
        "patterns": [
            # Decision recall
            "why did we",
            "why do we",
            "what was decided",
            "what did we decide",
            # Memory recall - natural language
            "remember when",
            "remember the decision",
            "remember what",
            "remember how",
            "do you remember",
            "recall when",
            "recall the",
            "recall how",
            # Session/history references
            "last session",
            "previous session",
            "earlier we",
            "before we",
            "previously",
            "last time we",
            "what did we do",
            "where did we leave off",
        ],
        "collection": "discussions",
        "type_filter": None,  # Search ALL discussion types (decision, session, blocker, preference, user_message, agent_response)
        "max_results": 3,
    },
    "session_history_keywords": {
        "enabled": True,
        "patterns": [
            # Project status queries
            "what have we done",
            "what did we work on",
            "project status",
            "where were we",
            "what's the status",
            # Continuation patterns
            "continue from",
            "pick up where",
            "continue where",
            # Remaining work
            "what's left to do",
            "remaining work",
            "what's next for",
            "what's next on",
            "what's next in the",
            "next steps",
            "todo",
            "tasks remaining",
        ],
        "collection": "discussions",
        "type_filter": "session",  # Session summaries
        "max_results": 3,
    },
    "best_practices_keywords": {
        "enabled": True,
        "patterns": [
            "best practice",
            "best practices",
            "coding standard",
            "coding standards",
            "convention",
            "conventions for",
            "what's the pattern",
            "what is the pattern",
            "how should i",
            "how do i",
            "what's the right way",
            "what is the right way",
            "naming convention",
            "style guide",
            # Added 2026-01-19: More natural language triggers
            # NOTE: "research" alone removed (CRIT-1) - too broad, caused false positives
            "research the pattern",
            "research best practice",
            "should i use",
            "what's recommended",
            "what is recommended",
            "recommended approach",
            "preferred approach",
            "preferred way",
            # Added 2026-01-24: Additional research patterns
            "look up",
            "find out about",
            "what do the docs say",
            "industry standard",
            "common pattern",
        ],
        "collection": "conventions",
        "type_filter": None,  # All types in conventions
        "max_results": 3,
    },
    "read_context": {
        "enabled": True,
        "collection": "conventions",
        "type_filter": None,
        "max_results": 3,
    },
}


def detect_error_signal(text: str) -> str | None:
    """Detect error patterns in text and return error signature.

    Scans text for error patterns from TRIGGER_CONFIG["error_detection"]["patterns"].
    Returns the detected error pattern as a signature for searching similar fixes.

    Args:
        text: Text to scan for error patterns (e.g., conversation text, tool output)

    Returns:
        Error signature if detected, None otherwise

    Examples:
        >>> detect_error_signal("TypeError: expected str")
        'TypeError: expected str'
        >>> detect_error_signal("Error: Connection refused")
        'Error: Connection refused'
        >>> detect_error_signal("Everything works fine")
        None
    """
    if not text or not text.strip():
        return None

    # Check for structured exception patterns FIRST (e.g., "TypeError:", "ValueError:")
    # These take priority over generic "Error:" pattern
    exc_match = re.search(r"\b(\w+(?:Error|Exception)):\s*(.+?)(?:\n|$)", text)
    if exc_match:
        exc_type = exc_match.group(1)
        exc_msg = exc_match.group(2).strip()[:100]
        signature = f"{exc_type}: {exc_msg}"
        logger.debug(
            "error_signal_detected",
            extra={"exception_type": exc_type, "signature": signature[:50]},
        )
        return signature

    # Check for Traceback
    if "Traceback" in text:
        # Try to find the last exception line
        lines = text.split("\n")
        for line in reversed(lines):
            if re.match(r"^\w+(?:Error|Exception):", line.strip()):
                signature = line.strip()[:150]
                logger.debug(
                    "error_signal_detected",
                    extra={"pattern": "Traceback", "signature": signature[:50]},
                )
                return signature
        # If no exception line found, return generic traceback message
        logger.debug("error_signal_detected", extra={"pattern": "Traceback"})
        return "Traceback detected"

    # Check remaining structured patterns
    config = TRIGGER_CONFIG.get("error_detection", {})
    patterns = config.get("patterns", ["Error:", "Exception:", "FAILED:"])

    for pattern in patterns:
        if pattern in text:
            # Extract text after pattern
            idx = text.find(pattern)
            signature = text[idx:].split("\n")[0].strip()[:150]
            if signature:
                logger.debug(
                    "error_signal_detected",
                    extra={"pattern": pattern, "signature": signature[:50]},
                )
                return signature

    return None


def detect_best_practices_keywords(text: str) -> str | None:
    """Detect best practices keywords in text and extract topic.

    Scans text for best practices patterns from TRIGGER_CONFIG["best_practices_keywords"]["patterns"].
    Extracts the topic/subject of the query for targeted search.

    Args:
        text: Text to scan for best practices keywords (e.g., user prompt)

    Returns:
        Extracted topic if detected, None otherwise

    Examples:
        >>> detect_best_practices_keywords("What are the best practices for Python logging?")
        'Python logging'
        >>> detect_best_practices_keywords("What's the naming convention for hooks?")
        'hooks'
        >>> detect_best_practices_keywords("How do I implement authentication?")
        'implement authentication'
    """
    if not text:
        return None

    config = TRIGGER_CONFIG.get("best_practices_keywords", {})
    if not config.get("enabled", False):
        return None

    patterns = config.get("patterns", [])
    text_lower = text.lower()

    for pattern in patterns:
        if pattern in text_lower:
            # Extract topic after the pattern
            pattern_pos = text_lower.find(pattern)
            if pattern_pos != -1:
                # Get text after pattern - find end of pattern word (handle "practices" vs "practice")
                after_pos = pattern_pos + len(pattern)
                # Skip any trailing 's' or 'es' that might be part of pluralization
                while after_pos < len(text) and text[after_pos].lower() in "es":
                    after_pos += 1
                after_pattern = text[after_pos:].strip()

                # Clean up common filler words
                for filler in [
                    "for",
                    "in",
                    "to",
                    "the",
                    "a",
                    "an",
                    "about",
                    "on",
                    "with",
                ]:
                    if after_pattern.lower().startswith(filler + " "):
                        after_pattern = after_pattern[len(filler) + 1 :]
                # Remove question mark if present
                topic = after_pattern.rstrip("?").strip()

                if topic:
                    logger.debug(
                        "best_practices_keyword_detected",
                        extra={"pattern": pattern, "topic": topic[:50]},
                    )
                    return topic
                else:
                    # Pattern matched but no topic - use surrounding context
                    # Try to get words before the pattern
                    before_pattern = text[:pattern_pos].strip().split()[-3:]
                    if before_pattern:
                        logger.debug(
                            "best_practices_keyword_detected_context",
                            extra={"pattern": pattern, "using_context": True},
                        )
                        return " ".join(before_pattern)

    return None


def detect_decision_keywords(text: str) -> str | None:
    """Detect decision-related keywords in text and extract topic.

    Scans text for decision question patterns from TRIGGER_CONFIG["decision_keywords"]["patterns"].
    Extracts the topic/subject of the decision question for targeted search.

    Args:
        text: Text to scan for decision keywords (e.g., user prompt)

    Returns:
        Extracted decision topic if detected, None otherwise

    Examples:
        >>> detect_decision_keywords("Why did we choose port 26350 for Qdrant?")
        'choose port 26350 for Qdrant'
        >>> detect_decision_keywords("What was decided about the authentication approach?")
        'about the authentication approach'
        >>> detect_decision_keywords("How do I implement auth?")
        None
    """
    if not text:
        return None

    config = TRIGGER_CONFIG["decision_keywords"]
    patterns = config["patterns"]

    # Check for decision keywords (case-insensitive)
    text_lower = text.lower()
    for pattern in patterns:
        if pattern in text_lower:
            # Extract topic after the pattern
            pattern_pos = text_lower.find(pattern)
            if pattern_pos != -1:
                # Get text after pattern
                after_pattern = text[pattern_pos + len(pattern) :].strip()
                # Remove question mark if present
                topic = after_pattern.rstrip("?").strip()

                # If no topic extracted but pattern matched, use full text as fallback
                if topic:
                    logger.debug(
                        "decision_keyword_detected",
                        extra={"pattern": pattern, "topic": topic[:50]},
                    )
                    return topic
                else:
                    # Pattern matched but no topic - use full query as fallback
                    logger.debug(
                        "decision_keyword_detected_no_topic",
                        extra={"pattern": pattern, "using_fallback": True},
                    )
                    return text.rstrip("?").strip()

    return None


def detect_session_history_keywords(text: str) -> str | None:
    """Detect session history keywords in text and extract topic.

    Scans text for session/project history patterns from
    TRIGGER_CONFIG["session_history_keywords"]["patterns"].
    Extracts the topic/subject for targeted session summary search.

    Args:
        text: Text to scan for session history keywords (e.g., user prompt)

    Returns:
        Extracted topic if detected, None otherwise

    Examples:
        >>> detect_session_history_keywords("What have we done on the memory system?")
        'on the memory system'
        >>> detect_session_history_keywords("Where were we with the SDK integration?")
        'with the SDK integration'
        >>> detect_session_history_keywords("What's the project status?")
        'project status'
    """
    if not text:
        return None

    config = TRIGGER_CONFIG.get("session_history_keywords", {})
    if not config:
        return None

    patterns = config.get("patterns", [])

    # Check for session history keywords (case-insensitive)
    text_lower = text.lower()
    for pattern in patterns:
        if pattern in text_lower:
            # Extract topic after the pattern
            pattern_pos = text_lower.find(pattern)
            if pattern_pos != -1:
                # Get text after pattern
                after_pattern = text[pattern_pos + len(pattern) :].strip()
                # Remove question mark if present
                topic = after_pattern.rstrip("?").strip()

                # If no topic extracted but pattern matched, use pattern as topic
                if topic:
                    logger.debug(
                        "session_history_keyword_detected",
                        extra={"pattern": pattern, "topic": topic[:50]},
                    )
                    return topic
                else:
                    # Pattern matched but no topic - use pattern itself as topic
                    logger.debug(
                        "session_history_keyword_detected_no_topic",
                        extra={"pattern": pattern, "using_pattern": True},
                    )
                    return pattern

    return None


def _cleanup_old_sessions() -> None:
    """Remove sessions older than TTL or if over max count.

    Must be called with _session_lock held.
    Prevents unbounded growth of session tracking dict.
    """
    now = datetime.now()

    # Remove expired sessions (older than SESSION_TTL)
    expired = [
        sid for sid, ts in _session_last_access.items() if now - ts > SESSION_TTL
    ]
    for sid in expired:
        _session_edited_files.pop(sid, None)
        _session_last_access.pop(sid, None)

    # Remove oldest sessions if over MAX_SESSIONS limit
    while len(_session_edited_files) >= MAX_SESSIONS:
        oldest_sid = min(_session_last_access.items(), key=lambda x: x[1])[0]
        _session_edited_files.pop(oldest_sid, None)
        _session_last_access.pop(oldest_sid, None)

    if expired or len(_session_edited_files) > MAX_SESSIONS:
        logger.debug(
            "session_cleanup",
            extra={
                "expired_count": len(expired),
                "total_sessions": len(_session_edited_files),
            },
        )


def detect_read_context(file_path: str, tool_name: str) -> dict:
    """Detect context for Read operations and determine if trigger should fire.

    Analyzes file path to extract file type, component name, and directory context.
    Used by PostToolUse hook for Read tool to retrieve relevant best practices
    before review agents (TEA, code-review) edit files.

    Args:
        file_path: Path to file being read
        tool_name: Name of tool being used (should be "Read")

    Returns:
        Dict with:
            - should_trigger (bool): Whether to trigger retrieval
            - file_type (str): File extension without dot (e.g., "py", "md")
            - component (str): Component/directory name (e.g., "memory", "hooks")
            - search_query (str): Query string for searching conventions

    Examples:
        >>> detect_read_context("src/memory/storage.py", "Read")
        {'should_trigger': True, 'file_type': 'py', 'component': 'memory',
         'search_query': 'Best practices for Python files in memory component'}
        >>> detect_read_context("README.md", "Read")
        {'should_trigger': True, 'file_type': 'md', 'component': '',
         'search_query': 'Best practices for Markdown files'}
        >>> detect_read_context("test.py", "Edit")
        {'should_trigger': False, 'file_type': '', 'component': '', 'search_query': ''}
    """
    if not file_path or not tool_name:
        return {
            "should_trigger": False,
            "file_type": "",
            "component": "",
            "search_query": "",
        }

    # Only trigger for Read tool
    if tool_name != "Read":
        return {
            "should_trigger": False,
            "file_type": "",
            "component": "",
            "search_query": "",
        }

    # Check if file exists
    if not os.path.exists(file_path):
        return {
            "should_trigger": False,
            "file_type": "",
            "component": "",
            "search_query": "",
        }

    # Extract file extension
    file_extension = os.path.splitext(file_path)[1].lstrip(".")
    if not file_extension:
        # No extension - skip trigger
        return {
            "should_trigger": False,
            "file_type": "",
            "component": "",
            "search_query": "",
        }

    # Extract component from directory path
    try:
        path_parts = Path(file_path).parts
    except (ValueError, OSError) as e:
        logger.debug(
            "path_parsing_error", extra={"file_path": file_path, "error": str(e)}
        )
        path_parts = []

    component = ""

    # Common component directories to look for
    component_indicators = [
        "src",
        "tests",
        "scripts",
        "hooks",
        "memory",
        "docker",
        "monitoring",
        "lib",
        "pkg",
        "cmd",
        "app",
        "internal",
        "api",
        "components",
        "pages",
        "controllers",
        "models",
        "views",
        "services",
        "utils",
        "helpers",
    ]

    for i, part in enumerate(path_parts):
        if part in component_indicators and i + 1 < len(path_parts):
            # Next part after indicator is the component
            component = path_parts[i + 1]
            break
        elif part in component_indicators:
            component = part
            break

    # Build search query based on file type and component
    file_type_names = {
        "py": "Python",
        "md": "Markdown",
        "yaml": "YAML",
        "yml": "YAML",
        "json": "JSON",
        "sh": "Shell script",
        "js": "JavaScript",
        "ts": "TypeScript",
        "tsx": "TypeScript React",
        "jsx": "JavaScript React",
        "go": "Go",
        "rs": "Rust",
        "java": "Java",
        "cpp": "C++",
        "c": "C",
        "h": "C/C++ Header",
        "rb": "Ruby",
        "php": "PHP",
        "swift": "Swift",
        "kt": "Kotlin",
        "xml": "XML",
        "toml": "TOML",
        "ini": "INI",
        "css": "CSS",
        "html": "HTML",
        "sql": "SQL",
    }

    file_type_display = file_type_names.get(file_extension, file_extension.upper())

    if component:
        search_query = (
            f"Best practices for {file_type_display} files in {component} component"
        )
    else:
        search_query = f"Best practices for {file_type_display} files"

    result = {
        "should_trigger": True,
        "file_type": file_extension,
        "component": component,
        "search_query": search_query,
    }

    logger.debug(
        "read_context_detected",
        extra={
            "file_path": file_path,
            "file_type": file_extension,
            "component": component,
            "query": search_query[:50],
        },
    )

    return result


def is_new_file(file_path: str) -> bool:
    """Check if file does not exist yet (new file being created).

    Used by PreToolUse hook for Write tool to detect new file creation.

    Args:
        file_path: Path to file being created

    Returns:
        True if file does not exist, False if file exists

    Examples:
        >>> is_new_file("/tmp/new_file.py")
        True
        >>> is_new_file("/etc/hosts")  # Existing file
        False
    """
    if not file_path:
        return False

    exists = os.path.exists(file_path)
    logger.debug(
        "new_file_check",
        extra={"file_path": file_path, "exists": exists, "is_new": not exists},
    )
    return not exists


def is_first_edit_in_session(file_path: str, session_id: str) -> bool:
    """Check if this is the first edit to a file in the current session.

    Tracks edited files per session to trigger retrieval only on first edit.
    Prevents repetitive retrievals for same file within a session.

    Session state is stored in-memory in _session_edited_files dict with thread safety.
    Automatic cleanup prevents unbounded growth (MAX_SESSIONS, SESSION_TTL).

    Args:
        file_path: Path to file being edited
        session_id: Current session identifier

    Returns:
        True if this is the first edit to the file in this session, False otherwise

    Examples:
        >>> is_first_edit_in_session("/src/main.py", "sess_123")
        True
        >>> is_first_edit_in_session("/src/main.py", "sess_123")  # Second call
        False
        >>> is_first_edit_in_session("/src/main.py", "sess_456")  # Different session
        True

    Note:
        Side effect: Adds file to session's edited set after returning True.
        This ensures subsequent calls for same file+session return False.
        Thread-safe with RLock.
    """
    if not file_path or not session_id:
        return False

    with _session_lock:
        # Run cleanup periodically to prevent unbounded growth
        _cleanup_old_sessions()

        # Initialize session tracking if not exists
        if session_id not in _session_edited_files:
            _session_edited_files[session_id] = set()
            _session_last_access[session_id] = datetime.now()

        # Update last access time
        _session_last_access[session_id] = datetime.now()

        # Check if file already edited in this session
        edited_files = _session_edited_files[session_id]
        is_first = file_path not in edited_files

        if is_first:
            # Mark as edited for this session
            edited_files.add(file_path)
            logger.debug(
                "first_edit_detected",
                extra={
                    "file_path": file_path,
                    "session_id": session_id,
                    "session_file_count": len(edited_files),
                },
            )
        else:
            logger.debug(
                "subsequent_edit_skipped",
                extra={
                    "file_path": file_path,
                    "session_id": session_id,
                    "session_file_count": len(edited_files),
                },
            )

        return is_first


def validate_keyword_patterns() -> list[str]:
    """Detect keyword pattern collisions per BP-040.

    Analyzes all keyword patterns in TRIGGER_CONFIG for substring collisions
    where one pattern contains another, which could cause unexpected trigger
    behavior (shorter pattern fires when longer was intended).

    Returns:
        List of collision warning strings. Empty list if no collisions.

    Examples:
        >>> warnings = validate_keyword_patterns()
        >>> # If "best practice" and "best practices" both exist:
        >>> # "Collision: 'best practice' overlaps with 'best practices'" in warnings
    """
    warnings = []
    all_patterns: list[tuple[str, str]] = []  # (pattern, trigger_name)

    for trigger_name, config in TRIGGER_CONFIG.items():
        patterns = config.get("patterns", [])
        for pattern in patterns:
            pattern_lower = pattern.lower()
            # Check for substring collisions with existing patterns
            for existing_pattern, existing_trigger in all_patterns:
                existing_lower = existing_pattern.lower()
                if pattern_lower != existing_lower:
                    if pattern_lower in existing_lower:
                        warnings.append(
                            f"Collision: '{pattern}' ({trigger_name}) is substring of "
                            f"'{existing_pattern}' ({existing_trigger})"
                        )
                    elif existing_lower in pattern_lower:
                        warnings.append(
                            f"Collision: '{existing_pattern}' ({existing_trigger}) is substring of "
                            f"'{pattern}' ({trigger_name})"
                        )
            all_patterns.append((pattern, trigger_name))

    return warnings


# TECH-DEBT-113: Run validation at module load (development check)
_collision_warnings = validate_keyword_patterns()
if _collision_warnings:
    logger.warning(
        "keyword_pattern_collisions_detected",
        extra={
            "collision_count": len(_collision_warnings),
            "warnings": _collision_warnings[:5],
        },
    )
