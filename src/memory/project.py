"""Project detection module for automatic memory scoping.

This module provides functions to automatically detect and normalize project
identifiers from working directory paths, enabling project-scoped memory
isolation without manual configuration.

Example:
    >>> from memory.project import detect_project
    >>> project = detect_project("/home/user/projects/my-app")
    >>> print(project)  # Output: "my-app"
"""

import hashlib
import logging
import os
import re
from pathlib import Path

# Configure logger for structured logging
logger = logging.getLogger(__name__)

# Constants
MAX_PROJECT_NAME_LENGTH = 50


def normalize_project_name(name: str) -> str:
    """Normalize project name for consistent group_id.

    Applies the following transformations:
    - Converts to lowercase
    - Replaces spaces and special characters with hyphens
    - Removes leading/trailing hyphens
    - Collapses consecutive hyphens
    - Truncates to 50 characters
    - Returns "unnamed-project" for empty results

    Args:
        name: Raw project name to normalize

    Returns:
        Normalized project name suitable for use as Qdrant group_id

    Example:
        >>> normalize_project_name("My Project v2.0")
        'my-project-v2-0'
    """
    if not name or not name.strip():
        logger.warning("empty_project_name", extra={"fallback": "unnamed-project"})
        return "unnamed-project"

    # Convert to lowercase
    normalized = name.lower()

    # Replace special characters and spaces with hyphens
    # Keep alphanumeric and hyphens only
    normalized = re.sub(r"[^a-z0-9-]", "-", normalized)

    # Collapse multiple consecutive hyphens to single hyphen
    normalized = re.sub(r"-+", "-", normalized)

    # Remove leading/trailing hyphens
    normalized = normalized.strip("-")

    # Truncate to maximum length
    if len(normalized) > MAX_PROJECT_NAME_LENGTH:
        logger.debug(
            "project_name_truncated",
            extra={
                "original_length": len(normalized),
                "truncated_length": MAX_PROJECT_NAME_LENGTH,
            },
        )
        normalized = normalized[:MAX_PROJECT_NAME_LENGTH].rstrip("-")

    # Final validation - ensure not empty after cleaning
    if not normalized:
        logger.warning(
            "normalized_to_empty",
            extra={"original": name, "fallback": "unnamed-project"},
        )
        return "unnamed-project"

    return normalized


def get_project_hash(cwd: str) -> str:
    """Get a hash-based project identifier for uniqueness.

    Uses SHA256 hash of the absolute path to ensure true uniqueness
    across different projects that might share the same directory name.

    Args:
        cwd: Working directory path (absolute or relative)

    Returns:
        12-character lowercase hexadecimal hash of the absolute path

    Example:
        >>> get_project_hash("/home/user/my-app")
        'a1b2c3d4e5f6'
    """
    try:
        # Resolve to absolute path for consistent hashing
        abs_path = Path(cwd).resolve()
        path_str = str(abs_path)

        # Generate SHA256 hash
        hash_obj = hashlib.sha256(path_str.encode("utf-8"))
        hash_hex = hash_obj.hexdigest()

        # Return first 12 characters (sufficient for uniqueness)
        return hash_hex[:12]

    except (OSError, ValueError) as e:
        logger.error("project_hash_failed", extra={"cwd": cwd, "error": str(e)})
        # Return deterministic fallback based on input
        fallback = hashlib.sha256(str(cwd).encode("utf-8")).hexdigest()[:12]
        return fallback


def detect_project(cwd: str | None = None) -> str:
    """Detect project identifier from environment variable or working directory.

    Detection priority:
    1. AI_MEMORY_PROJECT_ID environment variable (highest priority)
    2. Directory-based detection (fallback)

    Implements project detection strategy with special handling for edge cases:
    - Uses AI_MEMORY_PROJECT_ID env var if set (prevents pollution)
    - Falls back to directory name as project identifier
    - Handles root, home, and temp directories specially
    - Normalizes name for consistent group_id
    - Falls back to "unknown-project" on errors

    Args:
        cwd: Working directory path. If None, uses os.getcwd()

    Returns:
        Normalized project name suitable for group_id filtering

    Example:
        >>> os.environ['AI_MEMORY_PROJECT_ID'] = 'my-project'
        >>> detect_project("/any/directory")
        'my-project'
        >>> del os.environ['AI_MEMORY_PROJECT_ID']
        >>> detect_project("/home/user/projects/my-app")
        'my-app'
        >>> detect_project("/")
        'root-project'
    """
    # 1. Check environment variable first (highest priority)
    env_project = os.getenv("AI_MEMORY_PROJECT_ID")
    if env_project and env_project.strip():
        project_name = normalize_project_name(env_project)
        logger.debug(
            "using_env_project",
            extra={"env_value": env_project, "normalized": project_name},
        )
        return project_name

    # 2. Fall back to directory-based detection
    # Use current working directory if not provided
    if cwd is None:
        cwd = os.getcwd()
        logger.debug("using_current_directory", extra={"cwd": cwd})

    try:
        # Resolve path to handle symlinks and relative paths
        # Use strict=False to allow non-existent paths (will still resolve parent)
        cwd_path = Path(cwd).resolve(strict=False)

        # Note: Don't check path.exists() - Claude Code might pass paths that don't
        # exist on the filesystem (e.g. virtual paths, remote paths, or test paths).
        # Extract directory name regardless of existence.

        # Log symlink resolution if path changed
        if str(cwd_path) != str(Path(cwd)):
            logger.debug(
                "symlink_resolved", extra={"original": cwd, "resolved": str(cwd_path)}
            )

        # Get absolute path string for edge case detection
        abs_path = str(cwd_path)

        # Edge case: Root directory
        if abs_path == "/":
            logger.debug(
                "edge_case_detected", extra={"case": "root", "project": "root-project"}
            )
            return "root-project"

        # Edge case: Home directory
        home_path = Path.home()
        if cwd_path == home_path:
            logger.debug(
                "edge_case_detected", extra={"case": "home", "project": "home-project"}
            )
            return "home-project"

        # Edge case: Temp directories - only for direct children of /tmp or /var/tmp
        # Check for paths like /tmp/something but NOT /tmp/pytest-*/my-project
        # Strategy: Only treat as temp if it's a direct child with certain patterns
        parent_path = cwd_path.parent
        if parent_path == Path("/tmp") or parent_path == Path("/var/tmp"):
            # Direct child of temp directory - check if it looks like a temp dir
            # Common patterns: build-*, tmp-*, cache-*, etc.
            dir_name_lower = cwd_path.name.lower()
            temp_patterns = ["build", "tmp", "cache", "temp"]
            if any(pattern in dir_name_lower for pattern in temp_patterns):
                logger.debug(
                    "edge_case_detected",
                    extra={"case": "temp", "project": "temp-project"},
                )
                return "temp-project"

        # Special handling for /tmp and /var/tmp themselves
        if abs_path == "/tmp" or abs_path == "/var/tmp":
            logger.debug(
                "edge_case_detected",
                extra={"case": "temp_root", "project": "temp-project"},
            )
            return "temp-project"

        # Normal case: Extract directory name
        dir_name = cwd_path.name

        if not dir_name:
            # This shouldn't happen with resolve(), but handle defensively
            logger.warning(
                "empty_directory_name",
                extra={"cwd": cwd, "fallback": "unnamed-project"},
            )
            return "unnamed-project"

        # Normalize the directory name
        project_name = normalize_project_name(dir_name)

        logger.debug(
            "project_detected", extra={"cwd": abs_path, "project": project_name}
        )

        return project_name

    except (OSError, ValueError) as e:
        # Path resolution failed - log warning and return fallback
        logger.warning(
            "path_resolution_failed",
            extra={"cwd": cwd, "error": str(e), "fallback": "unknown-project"},
        )
        return "unknown-project"
