#!/usr/bin/env python3
"""Merge BMAD hook configuration with existing Claude settings.

2026 Best Practices Applied:
- Custom deep merge using recursion (no external dependencies per AC 7.2.3)
- List append strategy for hooks arrays (Dynaconf-inspired)
- Deduplication by command field
- Timestamped backups before modification (copy, not rename)
- Atomic writes using tempfile + os.replace pattern

Exit codes:
  0 = Success
  1 = Error (missing arguments, file errors)

Sources:
- AC 7.2.3 (Custom deep merge requirement)
- https://www.dynaconf.com/merging/ (merge strategies)
- https://pypi.org/project/jsonmerge/ (reference implementation)
- https://sahmanish20.medium.com/better-file-writing-in-python-embrace-atomic-updates (atomic writes)
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def deep_merge(base: dict, overlay: dict) -> dict:
    """
    Deep merge overlay into base, preserving existing values.

    Strategy for hooks (list):
    - Append new entries
    - Deduplicate by 'command' field

    2026 Best Practice: Custom implementation for precise control
    Source: https://pypi.org/project/jsonmerge/

    Args:
        base: Base dictionary (will NOT be modified)
        overlay: Overlay dictionary to merge in

    Returns:
        New dictionary with merged content
    """
    result = base.copy()

    for key, value in overlay.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                # Recurse for nested dicts
                result[key] = deep_merge(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                # Append to lists, deduplicate hooks by command
                result[key] = merge_lists(result[key], value)
            else:
                # Preserve existing non-dict/list values
                result[key] = value
        else:
            result[key] = value

    return result


def normalize_hook_command(command: str) -> str:
    """
    Normalize a hook command for deduplication comparison.

    Extracts the script filename from commands that may use either:
    - Venv Python (TECH-DEBT-135): "$AI_MEMORY_INSTALL_DIR/.venv/bin/python" ".../.claude/hooks/scripts/session_start.py"
    - Legacy python3: python3 "$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/session_start.py"
    - Absolute paths: python3 "/path/to/install/.claude/hooks/scripts/session_start.py"

    This allows deduplication to work regardless of path format or Python interpreter.

    Args:
        command: The command string from a hook configuration

    Returns:
        Normalized command identifier (script filename for BMAD hooks, original for others)

    BUG-039 Fix: Enables deduplication when paths differ in format but reference same script.
    TECH-DEBT-135: Extended to handle venv Python path format.
    """
    import re

    # Pattern to match BMAD hook commands with either interpreter format
    # Matches both:
    #   python3 "path/.claude/hooks/scripts/scriptname.py"
    #   "$.../.venv/bin/python" "path/.claude/hooks/scripts/scriptname.py"
    # Captures the script filename
    pattern = r"\.claude/hooks/scripts/([^\"]+?)(?:\"|$)"
    match = re.search(pattern, command)
    if match:
        # Return just the script name as the normalized identifier
        # e.g., "session_start.py" instead of full path
        return f"bmad-hook:{match.group(1)}"

    # For non-BMAD hooks, return the original command
    return command


def _hook_cmd(script_name: str) -> str:
    """Generate gracefully-degrading hook command. Exits 0 if installation missing.

    NOTE: Duplicated in generate_settings.py — keep in sync.
    """
    script = f"$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/{script_name}"
    python = "$AI_MEMORY_INSTALL_DIR/.venv/bin/python"
    return f'[ -f "{script}" ] && "{python}" "{script}" || true'


def merge_lists(existing: list, new: list) -> list:
    """
    Merge lists with deduplication for hook configurations.

    Deduplicates by 'command' field if objects are dicts.
    Handles both old format (direct command) and new nested format (hooks array).
    Uses normalized paths to detect duplicates even when path formats differ.

    Args:
        existing: Existing list
        new: New items to append

    Returns:
        Merged list with deduplicated hooks
    """
    result = existing.copy()

    def get_commands_from_item(item: dict) -> set:
        """Extract all normalized command identifiers from a hook wrapper or direct hook.

        BUG-039 Fix: Uses normalize_hook_command() to ensure commands are compared
        regardless of whether they use $AI_MEMORY_INSTALL_DIR or absolute paths.
        """
        commands = set()
        if "command" in item:
            # Direct hook format: {"command": "...", "type": "..."}
            commands.add(normalize_hook_command(item["command"]))
        if "hooks" in item and isinstance(item["hooks"], list):
            # Nested format: {"hooks": [{"command": "...", "type": "..."}]}
            for hook in item["hooks"]:
                if isinstance(hook, dict) and "command" in hook:
                    commands.add(normalize_hook_command(hook["command"]))
        return commands

    # Build set of existing commands for O(1) lookup
    existing_commands = set()
    for item in existing:
        if isinstance(item, dict):
            existing_commands.update(get_commands_from_item(item))

    for item in new:
        if isinstance(item, dict):
            item_commands = get_commands_from_item(item)
            # Only add if none of its commands already exist
            if not item_commands.intersection(existing_commands):
                result.append(item)
                existing_commands.update(item_commands)
        else:
            # Non-dict items: simple append
            result.append(item)

    return result


def _upgrade_hook_commands(settings: dict) -> dict:
    """Upgrade old unguarded hook commands to guarded format.

    Scans all hooks in settings. If a command references .claude/hooks/scripts/
    but does NOT contain '|| true', replaces it with the guarded format.
    This ensures existing users get upgraded commands when re-running the installer.
    """
    import re

    hooks = settings.get("hooks", {})
    for _hook_type, wrappers in hooks.items():
        if not isinstance(wrappers, list):
            continue
        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                continue
            # Check direct command format (no nested hooks array)
            if "command" in wrapper:
                cmd = wrapper["command"]
                if ".claude/hooks/scripts/" in cmd and "|| true" not in cmd:
                    match = re.search(r"\.claude/hooks/scripts/([^\"]+?)(?:\"|$)", cmd)
                    if match:
                        wrapper["command"] = _hook_cmd(match.group(1))
            # Check nested hooks array format
            hook_list = wrapper.get("hooks", [])
            for hook in hook_list:
                if not isinstance(hook, dict) or "command" not in hook:
                    continue
                cmd = hook["command"]
                if ".claude/hooks/scripts/" in cmd and "|| true" not in cmd:
                    match = re.search(r"\.claude/hooks/scripts/([^\"]+?)(?:\"|$)", cmd)
                    if match:
                        hook["command"] = _hook_cmd(match.group(1))
    return settings


def backup_file(path: Path) -> Path:
    """Create timestamped backup of file using copy (safer than rename).

    Args:
        path: Path to file to backup

    Returns:
        Path to backup file

    Raises:
        FileNotFoundError: If file doesn't exist

    2026 Best Practice: Copy first, don't rename.
    If merge fails after backup but before write, user still has original.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_suffix(f".json.backup.{timestamp}")
    shutil.copy2(path, backup_path)  # copy2 preserves metadata
    return backup_path


def merge_settings(
    settings_path: str, hooks_dir: str, project_name: str = "default"
) -> None:
    """Merge new hook configuration into existing settings file.

    Args:
        settings_path: Path to settings.json
        hooks_dir: Absolute path to hooks scripts directory
        project_name: Name of the project for AI_MEMORY_PROJECT_ID (default: "default")

    Side effects:
        - Creates backup of existing settings.json
        - Writes merged settings to settings_path (atomically)

    2026 Best Practices:
        - Atomic write using tempfile + os.replace
        - Graceful error handling for import
    """
    path = Path(settings_path)

    # Load existing settings
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
    else:
        existing = {}

    # Generate new hook config with error handling (Issue 5: graceful degradation)
    try:
        from generate_settings import generate_hook_config

        new_config = generate_hook_config(hooks_dir, project_name)
    except ImportError as e:
        print(f"ERROR: Failed to import generate_settings: {e}")
        print("Ensure generate_settings.py exists in the scripts directory.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to generate hook config: {e}")
        sys.exit(1)

    # Deep merge
    merged = deep_merge(existing, new_config)
    # BUG-066: upgrade old unguarded hooks to guarded format.
    # Note: _upgrade_hook_commands mutates in-place. Safe because
    # merged is the only reference used after this point.
    merged = _upgrade_hook_commands(merged)

    # Backup existing settings (copy, not rename - safer)
    if path.exists():
        backup_path = backup_file(path)
        print(f"Backed up existing settings to {backup_path}")

    # Atomic write: write to temp file, then replace (Issue 3)
    # This prevents corruption if system crashes during write
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".settings_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(merged, f, indent=2)
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    print(f"Updated {settings_path}")
    print(f"Added/updated hooks: {list(new_config['hooks'].keys())}")


def main():
    """Main entry point for CLI invocation."""
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Usage: merge_settings.py <settings_path> <hooks_dir> [project_name]")
        sys.exit(1)

    settings_path = sys.argv[1]
    hooks_dir = sys.argv[2]
    project_name = sys.argv[3] if len(sys.argv) == 4 else "default"
    merge_settings(settings_path, hooks_dir, project_name)


if __name__ == "__main__":
    main()
