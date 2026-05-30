"""Project detection module for automatic memory scoping.

This module provides functions to automatically detect and normalize project
identifiers from working directory paths, enabling project-scoped memory
isolation without manual configuration.

Example:
    >>> from memory.project import detect_project
    >>> project = detect_project("/home/user/projects/my-app")
    >>> print(project)  # Output: "my-app"
"""

import configparser
import hashlib
import logging
import os
import re
from pathlib import Path

# Configure logger for structured logging
logger = logging.getLogger(__name__)

# Constants
MAX_PROJECT_NAME_LENGTH = 50

# Per-workspace project-identity marker file (BUG-314 / BP-166 OQ-3). A committed
# workspace-root file declaring the project id, read by resolve_project_id between
# the env override and git-remote detection. Works in every invocation context
# (terminal, run-with-env.sh wrapper, Claude Code) — unlike .claude/settings.json
# env, which only reaches Claude-Code-launched processes.
PROJECT_MARKER_FILENAME = ".ai-memory-project"

# Maximum directory levels to walk upward when searching for the git root
# (.git/config) or the .ai-memory-project marker. Both walks share this bound so
# a marker (or git config) high in a shared tree — e.g. one dropped in $HOME — is
# not silently inherited by every marker-less child workspace far below it
# (BUG-314 review). Keep this constant the single source for both walk depths.
_MAX_WALK_DEPTH = 20


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


def normalize_org_repo_slug(org_repo: str) -> str | None:
    """Normalize an owner/repo slug while preserving the slash separator."""
    raw = (org_repo or "").strip()
    if not raw or "/" not in raw:
        return None

    owner, repo = raw.split("/", 1)
    owner_norm = normalize_project_name(owner)
    repo_norm = normalize_project_name(repo)
    if not owner_norm or not repo_norm:
        return None
    return f"{owner_norm}/{repo_norm}"


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


def _extract_org_repo_from_remote_url(remote_url: str) -> str | None:
    """Extract org/repo slug from a git remote URL.

    Handles both HTTPS and SSH remote URL formats:
    - https://github.com/org/repo.git  -> "org/repo"
    - https://github.com/org/repo      -> "org/repo"
    - git@github.com:org/repo.git      -> "org/repo"
    - git@gitlab.com:org/repo.git      -> "org/repo"
    - https://gitlab.com/org/repo.git  -> "org/repo"

    Args:
        remote_url: The raw git remote URL string

    Returns:
        Lowercase "org/repo" slug, or None if the URL cannot be parsed
    """
    remote_url = remote_url.strip()
    if not remote_url:
        return None

    # SSH format: git@host:org/repo.git or git@host:org/repo
    ssh_match = re.match(r"^git@[^:]+:([^/]+/[^/]+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return normalize_org_repo_slug(ssh_match.group(1))

    # HTTPS format: https://host/org/repo.git or https://host/org/repo
    https_match = re.match(r"^https?://[^/]+/([^/]+/[^/]+?)(?:\.git)?$", remote_url)
    if https_match:
        return normalize_org_repo_slug(https_match.group(1))

    return None


def _detect_project_from_git_remote(cwd_path: Path) -> str | None:
    """Detect project identifier from the git remote origin URL.

    Walks up from the given directory to find a .git directory, then reads
    the remote.origin.url from .git/config and extracts the org/repo slug.

    Args:
        cwd_path: Resolved Path object for the working directory

    Returns:
        Normalized "org/repo" project ID (e.g. "hidden-history/ai-memory"),
        or None if no git remote is available or parseable.
    """
    # Walk up the directory tree to find the git root
    search_path = cwd_path
    git_config_path: Path | None = None
    for _ in range(_MAX_WALK_DEPTH):  # limit traversal depth
        candidate = search_path / ".git" / "config"
        if candidate.is_file():
            git_config_path = candidate
            break
        parent = search_path.parent
        if parent == search_path:
            break
        search_path = parent

    if git_config_path is None:
        return None

    try:
        config = configparser.ConfigParser(strict=False)
        config.read(str(git_config_path))
        remote_url = config.get('remote "origin"', "url", fallback=None)
        if not remote_url:
            return None

        org_repo = _extract_org_repo_from_remote_url(remote_url)
        if org_repo is None:
            logger.debug(
                "git_remote_url_not_parseable",
                extra={"remote_url": remote_url},
            )
            return None

        # Normalize each component separately, keeping "/" as separator
        parts = org_repo.split("/", 1)
        if len(parts) != 2:
            return None
        org_norm = normalize_project_name(parts[0])
        repo_norm = normalize_project_name(parts[1])
        if not org_norm or not repo_norm:
            return None

        return f"{org_norm}/{repo_norm}"

    except (configparser.Error, OSError, ValueError) as e:
        logger.debug(
            "git_remote_detection_failed",
            extra={"git_config": str(git_config_path), "error": str(e)},
        )
        return None


def detect_project(cwd: str | None = None) -> str:
    """Detect project identifier from environment variable or git remote.

    Detection priority (PLAN-028 P1B / W-09, DEC-PM302-D1 + DEC-PM302-D2 Q-5):
    1. AI_MEMORY_PROJECT_ID environment variable (highest priority)
    2. Edge-case sentinels for anomalous cwds (root/home/temp)
    3. Git remote org/repo slug (auto-detected from .git/config)
    4. **Fail-loud**: raises ValueError if none of the above resolve.

    The directory-basename fallback was removed (Q-5 strict-remove per W-09): a
    silent guess based on the parent directory name is the cross-project
    contamination vector PLAN-028 P1B exists to close. Callers MUST either set
    AI_MEMORY_PROJECT_ID explicitly or run inside a directory whose git
    remote can be resolved.

    The edge-case sentinels at root/home/temp paths remain for now and are
    tracked for follow-up cleanup (see ``oversight/tech-debt/`` for the
    "special-case sentinels" TD).

    Args:
        cwd: Working directory path. If None, uses os.getcwd()

    Returns:
        Normalized project identifier suitable for group_id filtering.

    Raises:
        ValueError: If no AI_MEMORY_PROJECT_ID env var is set, the cwd is not
            an edge-case sentinel, and no git remote can be detected. Callers
            should pre-set AI_MEMORY_PROJECT_ID for non-git contexts.

    Example:
        >>> os.environ['AI_MEMORY_PROJECT_ID'] = 'my-project'
        >>> detect_project("/any/directory")
        'my-project'
        >>> del os.environ['AI_MEMORY_PROJECT_ID']
        >>> detect_project("/")
        'root-project'
    """
    # 1. Check environment variable first (highest priority)
    env_project = os.getenv("AI_MEMORY_PROJECT_ID")
    if env_project and env_project.strip():
        project_name = normalize_org_repo_slug(env_project) or normalize_project_name(
            env_project
        )
        logger.debug(
            "using_env_project",
            extra={"env_value": env_project, "normalized": project_name},
        )
        return project_name

    # 2. Directory-based detection (git remote then folder name)
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

        # 2a. Try git remote origin URL (org/repo slug) — more stable than folder name
        git_project = _detect_project_from_git_remote(cwd_path)
        if git_project:
            logger.debug(
                "project_detected_from_git_remote",
                extra={"cwd": abs_path, "project": git_project},
            )
            return git_project

        # 2b. No basename fallback — fail loud per W-09 / DEC-PM302-D2 Q-5.
        # The directory-basename fallback was removed: it silently produced a
        # guessed group_id (e.g. "ai-memory-w09" for a worktree, "tmp-build-foo"
        # for a build dir), which is precisely the cross-project contamination
        # vector PLAN-028 P1B exists to close.
        logger.error(
            "project_detection_failed",
            extra={
                "cwd": abs_path,
                "reason": (
                    "no AI_MEMORY_PROJECT_ID env var, no git remote, "
                    "and cwd is not an edge-case sentinel"
                ),
            },
        )
        raise ValueError(
            f"project detection failed for cwd={abs_path!r}: "
            "set AI_MEMORY_PROJECT_ID, run from a directory with a git remote, "
            "or pass an explicit group_id"
        )

    except OSError as e:
        # Path resolution itself failed - fail loud per W-09.
        logger.error(
            "path_resolution_failed",
            extra={"cwd": cwd, "error": str(e)},
        )
        raise ValueError(
            f"project detection failed: path resolution error for cwd={cwd!r}: {e}"
        ) from e


def _warn_on_env_cwd_mismatch(cwd: str | None) -> None:
    """Warn (never raise) when the env project id disagrees with the cwd's git slug.

    BUG-314 / BP-166 OQ-1: on an env != cwd disagreement we prefer the explicit
    per-invocation env signal but surface the disagreement loudly so a stale or
    foreign-workspace ``AI_MEMORY_PROJECT_ID`` cannot silently misfile memory. This
    is best-effort observability only: a cwd with no resolvable git remote (the
    normal case when the env is set) is NOT a disagreement and is silent.
    """
    env_project = os.getenv("AI_MEMORY_PROJECT_ID")
    if not (env_project and env_project.strip()):
        return
    env_id = normalize_org_repo_slug(env_project) or normalize_project_name(env_project)
    try:
        cwd_path = Path(cwd or os.getcwd()).resolve(strict=False)
        cwd_id = _detect_project_from_git_remote(cwd_path)
    except (OSError, ValueError):
        cwd_id = None
    if cwd_id and cwd_id != env_id:
        logger.warning(
            "project_env_cwd_mismatch",
            extra={
                "env_project": env_id,
                "cwd_project": cwd_id,
                "resolved": env_id,
                "note": "preferring per-invocation AI_MEMORY_PROJECT_ID over cwd git slug",
            },
        )


def _read_project_marker(cwd: str | None) -> str | None:
    """Read the project id from a ``.ai-memory-project`` marker file.

    Walks up from ``cwd`` for at most :data:`_MAX_WALK_DEPTH` levels looking for
    the marker (the same bound as the git-remote walk, so a marker high in a
    shared tree is not silently inherited by distant child workspaces — BUG-314).
    The file is a single project id; ``#`` comment lines and blank lines are
    ignored so the file can carry a friendly header. Returns the normalized id,
    or ``None`` if no marker is found or it has no id line.

    Block-inheritance (intentional): the FIRST marker encountered while walking
    up wins — and a marker that is present but contains only comment/blank lines
    terminates the walk (returns ``None``) rather than continuing to an ancestor.
    A present-but-empty marker is therefore a deliberate "stop here, do not
    inherit a parent's id" stub; the caller then falls through to git detection /
    fail-loud rather than borrowing a far-ancestor's project id.
    """
    try:
        start = Path(cwd or os.getcwd()).resolve(strict=False)
    except (OSError, ValueError):
        return None
    for directory in [start, *start.parents][:_MAX_WALK_DEPTH]:
        marker = directory / PROJECT_MARKER_FILENAME
        if not marker.is_file():
            continue
        try:
            lines = marker.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            resolved = normalize_org_repo_slug(stripped) or normalize_project_name(
                stripped
            )
            logger.debug(
                "project_marker_used",
                extra={"marker": str(marker), "resolved": resolved},
            )
            return resolved
        return None  # marker present but comment/blank only → stop, do not inherit
    return None


def resolve_project_id(
    cwd: str | None = None, *, explicit: str | None = None, warn: bool = True
) -> str:
    """Single source of project-scope resolution (BUG-314 / BP-166 F3).

    Every read + write + wrapper entry point resolves the ``group_id`` through this
    one helper so the precedence cannot drift per-file. It adds the explicit-arg
    tier and the per-workspace marker-file tier on top of the env-first
    :func:`detect_project`, and warns (non-fatally) on an env vs cwd disagreement.

    Precedence (most specific wins; fail-loud if none):
        1. ``explicit`` — CLI flag / direct caller arg (highest)
        2. ``AI_MEMORY_PROJECT_ID`` env — per-invocation / live override
        3. ``.ai-memory-project`` marker file — per-workspace committed declaration
        4. ``detect_project(cwd)`` — git-remote slug / edge sentinels
        5. raise ``ValueError`` — never guess a default

    The marker sits between env and git: a per-workspace committed declaration that
    is more specific than the git remote but yields to a live env override. It works
    in every invocation context (terminal, ``run-with-env.sh``, Claude Code).

    Args:
        cwd: Working directory used for marker lookup and git-remote detection.
        explicit: Caller-supplied id (e.g. a ``--group-id`` flag) that overrides
            env, marker, and cwd. Empty/whitespace is treated as unset.
        warn: When ``True`` (default, interactive/CLI path) an env-set resolution
            also runs the env-vs-cwd disagreement check (:func:`_warn_on_env_cwd_mismatch`),
            which performs a git-remote stat-walk. High-frequency capture hooks
            (chat/post-work store), which fire on every event and target <50ms,
            pass ``warn=False`` to skip that per-call filesystem walk. The
            resolved id is identical either way — only the best-effort warning is
            suppressed on the hot path.

    Returns:
        Normalized project identifier suitable for ``group_id`` filtering.

    Raises:
        ValueError: If no explicit id, no ``AI_MEMORY_PROJECT_ID``, no marker file,
            and no git remote resolve (delegated to :func:`detect_project`).
    """
    if explicit and explicit.strip():
        return normalize_org_repo_slug(explicit) or normalize_project_name(explicit)

    env_project = os.getenv("AI_MEMORY_PROJECT_ID")
    if env_project and env_project.strip():
        # Surface an env!=cwd disagreement; prefer the per-invocation env signal.
        # Skipped on the hot path (warn=False) to avoid a per-call git stat-walk.
        if warn:
            _warn_on_env_cwd_mismatch(cwd)
        return normalize_org_repo_slug(env_project) or normalize_project_name(
            env_project
        )

    marker_id = _read_project_marker(cwd)
    if marker_id:
        return marker_id

    # git-remote slug / edge sentinels / fail-loud (env already handled above).
    return detect_project(cwd)
