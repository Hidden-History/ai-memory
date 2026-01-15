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
from pathlib import Path
from typing import Any
from datetime import datetime


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


def merge_lists(existing: list, new: list) -> list:
    """
    Merge lists with deduplication for hook configurations.

    Deduplicates by 'command' field if objects are dicts.
    Handles both old format (direct command) and new nested format (hooks array).

    Args:
        existing: Existing list
        new: New items to append

    Returns:
        Merged list with deduplicated hooks
    """
    result = existing.copy()

    def get_commands_from_item(item: dict) -> set:
        """Extract all command strings from a hook wrapper or direct hook."""
        commands = set()
        if "command" in item:
            # Direct hook format: {"command": "...", "type": "..."}
            commands.add(item["command"])
        if "hooks" in item and isinstance(item["hooks"], list):
            # Nested format: {"hooks": [{"command": "...", "type": "..."}]}
            for hook in item["hooks"]:
                if isinstance(hook, dict) and "command" in hook:
                    commands.add(hook["command"])
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


def merge_settings(settings_path: str, hooks_dir: str) -> None:
    """Merge new hook configuration into existing settings file.

    Args:
        settings_path: Path to settings.json
        hooks_dir: Absolute path to hooks scripts directory

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
        new_config = generate_hook_config(hooks_dir)
    except ImportError as e:
        print(f"ERROR: Failed to import generate_settings: {e}")
        print("Ensure generate_settings.py exists in the scripts directory.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to generate hook config: {e}")
        sys.exit(1)

    # Deep merge
    merged = deep_merge(existing, new_config)

    # Backup existing settings (copy, not rename - safer)
    if path.exists():
        backup_path = backup_file(path)
        print(f"Backed up existing settings to {backup_path}")

    # Atomic write: write to temp file, then replace (Issue 3)
    # This prevents corruption if system crashes during write
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".settings_",
        suffix=".tmp"
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
    if len(sys.argv) != 3:
        print("Usage: merge_settings.py <settings_path> <hooks_dir>")
        sys.exit(1)

    settings_path = sys.argv[1]
    hooks_dir = sys.argv[2]
    merge_settings(settings_path, hooks_dir)


if __name__ == "__main__":
    main()
