#!/usr/bin/env python3
"""Automate sprint-status.yaml updates from git commit messages.

Implements ACT-002 (P0 Critical) from Epic 6 Retrospective.

Parses git commit messages for story completion patterns and updates
sprint-status.yaml automatically, preserving YAML structure and comments.

Patterns matched:
- "Story X.Y:" at start → mark story as 'done'
- "Story X.Y complete" anywhere → mark story as 'done'
- "WIP Story X.Y" or "[WIP] Story X.Y" → mark story as 'in-progress'

Usage:
    python scripts/update_sprint_status.py [--commits N] [--dry-run]

Options:
    --commits N    Number of recent commits to parse (default: 20)
    --dry-run      Show changes without writing to file
"""

import fcntl  # F2 Fix: File locking for concurrent safety
import logging
import re
import subprocess
import sys
from pathlib import Path

from ruamel.yaml import YAML

# Configure structured logging per project conventions
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("bmad.scripts.sprint_status")


# Story pattern regexes
STORY_DONE_START = re.compile(r"^Story\s+(\d+)\.(\d+):", re.IGNORECASE)
STORY_DONE_ANYWHERE = re.compile(r"Story\s+(\d+)\.(\d+)\s+complete", re.IGNORECASE)
STORY_WIP = re.compile(r"(?:WIP|\[WIP\])\s+Story\s+(\d+)\.(\d+)", re.IGNORECASE)


def get_git_commits(num_commits: int = 20) -> list[str]:
    """Fetch recent git commit messages.

    Args:
        num_commits: Number of recent commits to retrieve (1-500)

    Returns:
        List of commit messages (one line each)

    Raises:
        ValueError: If num_commits is out of valid range
        subprocess.CalledProcessError: If git command fails
    """
    # F1 Fix: Validate num_commits to prevent DoS via resource exhaustion
    if not isinstance(num_commits, int) or num_commits < 1 or num_commits > 500:
        raise ValueError("num_commits must be an integer between 1 and 500")

    try:
        # F3 Fix: Stream commits line-by-line to prevent memory exhaustion
        process = subprocess.Popen(
            ["git", "log", "--oneline", f"-{num_commits}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        commits = []
        # Stream line by line instead of loading all into memory at once
        for line in process.stdout:
            line = line.strip()
            if line:  # Skip empty lines
                commits.append(line)

        # Wait for process to complete and check return code
        return_code = process.wait()
        if return_code != 0:
            stderr_output = process.stderr.read()
            raise subprocess.CalledProcessError(
                return_code, "git log", stderr=stderr_output
            )

        return commits

    except subprocess.CalledProcessError as e:
        logger.error(
            "git_command_failed", extra={"command": "git log", "error": str(e)}
        )
        raise


def parse_story_updates(commits: list[str]) -> dict[str, str]:
    """Parse commit messages for story status updates.

    Args:
        commits: List of git commit messages (format: "hash message")

    Returns:
        Dict mapping story_id (e.g. "6-5") to new status ("done" or "in-progress")

    Examples:
        >>> parse_story_updates(["abc1234 Story 6.5: Complete feature"])
        {'6-5': 'done'}
        >>> parse_story_updates(["def5678 WIP Story 7.1 implementation"])
        {'7-1': 'in-progress'}
    """
    updates: dict[str, str] = {}

    for commit in commits:
        if not commit.strip():
            continue

        # Extract message portion (skip git hash prefix)
        # Format: "abc1234 Message here"
        parts = commit.split(None, 1)  # Split on first whitespace
        if len(parts) < 2:
            continue
        message = parts[1]

        # Check for "Story X.Y:" at start of message (done)
        match = STORY_DONE_START.search(message)
        if match:
            epic, story = match.groups()
            story_id = f"{epic}-{story}"
            updates[story_id] = "done"
            logger.info(
                "pattern_matched",
                extra={
                    "pattern": "done_start",
                    "story_id": story_id,
                    "commit": commit[:60],
                },
            )
            continue

        # Check for "Story X.Y complete" anywhere in message (done)
        match = STORY_DONE_ANYWHERE.search(message)
        if match:
            epic, story = match.groups()
            story_id = f"{epic}-{story}"
            updates[story_id] = "done"
            logger.info(
                "pattern_matched",
                extra={
                    "pattern": "done_anywhere",
                    "story_id": story_id,
                    "commit": commit[:60],
                },
            )
            continue

        # Check for WIP patterns in message (in-progress)
        match = STORY_WIP.search(message)
        if match:
            epic, story = match.groups()
            story_id = f"{epic}-{story}"
            # Only set to in-progress if not already marked done
            if story_id not in updates or updates[story_id] != "done":
                updates[story_id] = "in-progress"
                logger.info(
                    "pattern_matched",
                    extra={
                        "pattern": "wip",
                        "story_id": story_id,
                        "commit": commit[:60],
                    },
                )

    return updates


def update_sprint_status_yaml(
    yaml_path: Path,
    updates: dict[str, str],
    dry_run: bool = False,
    strict: bool = False,
) -> tuple[int, int]:
    """Update sprint-status.yaml with story status changes.

    Uses ruamel.yaml to preserve comments and formatting.

    Args:
        yaml_path: Path to sprint-status.yaml
        updates: Dict of story_id → new_status
        dry_run: If True, don't write changes to file
        strict: If True, raise ValueError when stories are not found (F15)

    Returns:
        Tuple of (stories_updated, stories_not_found)

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValueError: If YAML file is malformed or story not found (strict mode)
    """
    # F13 Fix: Remove explicit existence check to avoid TOCTOU vulnerability
    # Rely on exception handling instead

    # F2 Fix: File locking to prevent concurrent modification
    # Acquire lock before read-modify-write operation
    lock_path = yaml_path.with_suffix(".lock")
    lock_file = None

    try:
        # Create lock file
        lock_file = open(lock_path, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)  # Exclusive lock
        logger.debug("lock_acquired", extra={"lock_path": str(lock_path)})

        # Load YAML with comment preservation
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False

        try:
            with open(yaml_path) as f:
                data = yaml.load(f)
        except FileNotFoundError:
            logger.error("yaml_file_not_found", extra={"path": str(yaml_path)})
            raise FileNotFoundError(f"sprint-status.yaml not found at {yaml_path}")
        except Exception as e:
            logger.error(
                "yaml_parse_failed", extra={"path": str(yaml_path), "error": str(e)}
            )
            raise ValueError(f"Failed to parse YAML: {e}")

        if not data or "epics" not in data:
            logger.error(
                "yaml_invalid_structure",
                extra={"path": str(yaml_path), "has_epics": "epics" in (data or {})},
            )
            raise ValueError("YAML file missing 'epics' key")

        # Track updates
        updated_count = 0
        not_found_count = 0
        updated_stories: set[str] = set()

        # Apply updates
        for story_id, new_status in updates.items():
            # Parse story_id (e.g., "6-5" → epic "epic-6", story key "6-5-...")
            parts = story_id.split("-")
            if len(parts) < 2:
                logger.warning("invalid_story_id", extra={"story_id": story_id})
                continue

            epic_num = parts[0]
            epic_key = f"epic-{epic_num}"

            # Find epic
            if epic_key not in data["epics"]:
                logger.warning(
                    "epic_not_found", extra={"epic_key": epic_key, "story_id": story_id}
                )
                not_found_count += 1
                continue

            epic = data["epics"][epic_key]
            if "stories" not in epic:
                logger.warning(
                    "epic_has_no_stories",
                    extra={"epic_key": epic_key, "story_id": story_id},
                )
                not_found_count += 1
                continue

            # Find story (key starts with story_id pattern)
            story_found = False
            for story_key, story_data in epic["stories"].items():
                # Match story keys like "6-5-retrieval-session-logs"
                if story_key.startswith(story_id + "-") or story_key == story_id:
                    current_status = story_data.get("status", "unknown")

                    # Skip if already at target status
                    if current_status == new_status:
                        logger.info(
                            "status_unchanged",
                            extra={"story_key": story_key, "status": current_status},
                        )
                        story_found = True
                        break

                    # Skip if trying to move backwards (done → in-progress)
                    if current_status == "done" and new_status != "done":
                        logger.info(
                            "status_skip_backward",
                            extra={
                                "story_key": story_key,
                                "current": current_status,
                                "proposed": new_status,
                            },
                        )
                        story_found = True
                        break

                    # Update status
                    story_data["status"] = new_status
                    updated_count += 1
                    updated_stories.add(story_key)
                    logger.info(
                        "status_updated",
                        extra={
                            "story_key": story_key,
                            "old_status": current_status,
                            "new_status": new_status,
                        },
                    )
                    story_found = True
                    break

            if not story_found:
                logger.warning(
                    "story_not_found",
                    extra={"story_id": story_id, "epic_key": epic_key},
                )
                not_found_count += 1

        # Write back to file if not dry-run
        if not dry_run and updated_count > 0:
            # F14 Fix: Atomic write using temp file to prevent corruption
            temp_path = yaml_path.with_suffix(".yaml.tmp")
            try:
                # Write to temp file first
                with open(temp_path, "w") as f:
                    yaml.dump(data, f)
                # Atomic rename (overwrites only if write succeeded)
                temp_path.replace(yaml_path)
                logger.info(
                    "yaml_written",
                    extra={"path": str(yaml_path), "stories_updated": updated_count},
                )
            except Exception as e:
                # Clean up temp file on error
                if temp_path.exists():
                    temp_path.unlink()
                logger.error(
                    "yaml_write_failed", extra={"path": str(yaml_path), "error": str(e)}
                )
                raise
        elif dry_run and updated_count > 0:
            logger.info(
                "dry_run_complete",
                extra={
                    "would_update": updated_count,
                    "stories": sorted(updated_stories),
                },
            )

        # F15 Fix: Strict mode errors on story not found
        if strict and not_found_count > 0:
            raise ValueError(
                f"Strict mode: {not_found_count} story ID(s) not found in YAML"
            )

        return updated_count, not_found_count

    finally:
        # F2 Fix: Always release lock
        if lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            # Clean up lock file
            if lock_path.exists():
                lock_path.unlink()
            logger.debug("lock_released", extra={"lock_path": str(lock_path)})


def main() -> int:
    """Main entry point for sprint-status updater.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Update sprint-status.yaml from git commits"
    )
    parser.add_argument(
        "--commits",
        type=int,
        default=20,
        help="Number of recent commits to parse (default: 20)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show changes without writing to file"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Error if any story IDs are not found (F15 - for CI enforcement)",
    )
    args = parser.parse_args()

    # Determine project root and YAML path
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    yaml_path = (
        project_root
        / "_bmad-output"
        / "implementation-artifacts"
        / "sprint-status.yaml"
    )

    try:
        # Fetch commits
        logger.info("fetching_commits", extra={"num_commits": args.commits})
        commits = get_git_commits(args.commits)

        # Parse for story updates
        updates = parse_story_updates(commits)

        if not updates:
            logger.info("no_updates_found", extra={"commits_scanned": len(commits)})
            return 0

        logger.info(
            "updates_parsed", extra={"total_updates": len(updates), "updates": updates}
        )

        # Apply updates to YAML
        updated, not_found = update_sprint_status_yaml(
            yaml_path, updates, dry_run=args.dry_run, strict=args.strict
        )

        # Summary
        logger.info(
            "update_complete",
            extra={
                "stories_updated": updated,
                "stories_not_found": not_found,
                "dry_run": args.dry_run,
            },
        )

        return 0

    except FileNotFoundError as e:
        logger.error("file_not_found", extra={"error": str(e)})
        return 1
    except ValueError as e:
        logger.error("invalid_data", extra={"error": str(e)})
        return 1
    except subprocess.CalledProcessError as e:
        logger.error("git_error", extra={"error": str(e)})
        return 1
    except Exception as e:
        logger.error(
            "unexpected_error", extra={"error": str(e), "type": type(e).__name__}
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
