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

# TD-338: _hook_cmd() centralised in hook_utils to eliminate duplication
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hook_utils import _hook_cmd, get_langfuse_env_section, normalize_matcher

# Hook script names that must always be removed from settings.json regardless of
# whether the file still exists on disk. Add deprecated/renamed scripts here so
# stale references are purged even during fresh installs (before the scripts dir
# is created) and even if an old copy of the script file lingers.
_DEAD_HOOK_SCRIPTS: frozenset[str] = frozenset(
    {
        "unified_keyword_trigger.py",  # BUG-250: renamed to context_injection_tier2.py
    }
)


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
                # Preserve existing scalar values (base wins — user customizations not overwritten)
                pass  # Keep result[key] unchanged
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

    # Matcher normalization: _normalize_session_start_matcher() strips vestigial
    # 'startup' trigger on upgrade (v2.2.0+ DEC-054). update_parzival_settings.py
    # manages env vars only — it does NOT touch hook matchers.

    return settings


def _remove_dead_hooks(settings: dict, install_dir: str | None = None) -> dict:
    """Remove hook entries whose script files no longer exist.

    After template updates, old hook scripts may be archived or deleted
    but their entries persist in settings.json due to the append-only
    merge strategy. This sweep removes dead references.

    Args:
        settings: The merged settings dict (mutated in-place).
        install_dir: AI Memory install directory. If None, reads from
                     AI_MEMORY_INSTALL_DIR env var or defaults to ~/.ai-memory.

    Returns:
        The settings dict with dead hook entries removed.
    """
    import re

    if install_dir is None:
        install_dir = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )

    scripts_dir = Path(install_dir) / ".claude" / "hooks" / "scripts"
    # Do NOT return early when scripts_dir is missing — _DEAD_HOOK_SCRIPTS entries
    # must be purged even during fresh install before the scripts dir is created.
    # Filesystem-existence checks are guarded by scripts_dir.exists() below.

    hooks = settings.get("hooks", {})
    removed_count = 0

    for hook_type, wrappers in list(hooks.items()):
        if not isinstance(wrappers, list):
            continue

        # Filter: keep entries whose scripts exist (or are not BMAD hook scripts)
        live_wrappers = []
        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                live_wrappers.append(wrapper)
                continue

            # Case 1: nested hooks array — filter individual dead sub-hooks
            if "hooks" in wrapper and isinstance(wrapper["hooks"], list):
                live_sub_hooks = []
                for hook in wrapper["hooks"]:
                    if not isinstance(hook, dict) or "command" not in hook:
                        live_sub_hooks.append(hook)
                        continue
                    match = re.search(
                        r'\.claude/hooks/scripts/([^"]+?)(?:"|$)', hook["command"]
                    )
                    if match:
                        script_name = match.group(1)
                        script_path = (
                            Path(install_dir)
                            / ".claude"
                            / "hooks"
                            / "scripts"
                            / script_name
                        )
                        if script_name in _DEAD_HOOK_SCRIPTS or (
                            scripts_dir.exists() and not script_path.exists()
                        ):
                            reason = (
                                "deprecated script"
                                if script_name in _DEAD_HOOK_SCRIPTS
                                else f"script not found at {script_path}"
                            )
                            print(f"  Removing dead hook: {script_name} ({reason})")
                            removed_count += 1
                            continue  # Drop only this dead sub-hook
                    live_sub_hooks.append(hook)
                # Keep wrapper only if it still has live hooks
                if live_sub_hooks:
                    updated = dict(wrapper)
                    updated["hooks"] = live_sub_hooks
                    live_wrappers.append(updated)
                continue

            # Case 2: direct command format — remove wrapper if script is dead
            if "command" in wrapper:
                match = re.search(
                    r'\.claude/hooks/scripts/([^"]+?)(?:"|$)', wrapper["command"]
                )
                if match:
                    script_name = match.group(1)
                    script_path = (
                        Path(install_dir)
                        / ".claude"
                        / "hooks"
                        / "scripts"
                        / script_name
                    )
                    if script_name in _DEAD_HOOK_SCRIPTS or (
                        scripts_dir.exists() and not script_path.exists()
                    ):
                        reason = (
                            "deprecated script"
                            if script_name in _DEAD_HOOK_SCRIPTS
                            else f"script not found at {script_path}"
                        )
                        print(f"  Removing dead hook: {script_name} ({reason})")
                        removed_count += 1
                        continue  # Drop dead wrapper

            live_wrappers.append(wrapper)

        hooks[hook_type] = live_wrappers

    if removed_count > 0:
        print(f"  Cleaned up {removed_count} dead hook reference(s)")

    return settings


def _normalize_session_start_matcher(settings: dict) -> dict:
    """Strip 'startup' and 'clear' from SessionStart hook matchers (v2.2.0+).

    v2.2.0 moved session bootstrap to agent-activated skills.
    Both 'startup' and 'clear' are vestigial triggers that cause unnecessary
    hook execution on new sessions (DEC-054: sessions start clean, DEC-055).
    """
    hooks = settings.get("hooks", {})
    for wrappers in hooks.values():
        if not isinstance(wrappers, list):
            continue
        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                continue
            # Check nested hooks for session_start.py
            for hook in wrapper.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                cmd = hook.get("command", "")
                if "session_start.py" in cmd:
                    matcher = wrapper.get("matcher", "")
                    new_matcher = normalize_matcher(matcher)
                    if new_matcher != matcher:
                        wrapper["matcher"] = new_matcher
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

    # TD-334: Ensure hooks_dir is absolute before any path derivation
    if not os.path.isabs(hooks_dir):
        hooks_dir = os.path.abspath(hooks_dir)

    # Generate new hook config with error handling (Issue 5: graceful degradation)
    try:
        from generate_settings import generate_hook_config, write_local_settings

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

    # Force-update system-managed env vars that must always match the current
    # install state.  deep_merge preserves existing scalars ("base wins") which
    # is correct for user customisations (SIMILARITY_THRESHOLD, LOG_LEVEL) but
    # wrong for values the installer controls.  PLAN-009 lowercases project IDs;
    # reinstalls must update old mixed-case values so verification passes and
    # Qdrant group_id / projects.d/ lookups stay consistent.
    #
    # Force-updated (installer-derived, must always reflect current install):
    #   AI_MEMORY_PROJECT_ID  — set by installer from project config (PLAN-009)
    #   AI_MEMORY_INSTALL_DIR — derived from hooks_dir path; must match actual install
    #   LANGFUSE_*            — toggled by LANGFUSE_ENABLED; all-or-nothing
    #
    # User-preserved (deep_merge "base wins" — NOT force-updated):
    #   QDRANT_HOST, QDRANT_PORT, EMBEDDING_HOST, EMBEDDING_PORT
    #   SIMILARITY_THRESHOLD, LOG_LEVEL
    #   PUSHGATEWAY_URL, PUSHGATEWAY_ENABLED
    if "env" not in merged:
        merged["env"] = {}
    merged["env"]["AI_MEMORY_PROJECT_ID"] = project_name
    # TD-334: AI_MEMORY_INSTALL_DIR must always reflect the actual install path.
    # hooks_dir format: /path/to/install/.claude/hooks/scripts (3 levels up = install_dir)
    merged["env"]["AI_MEMORY_INSTALL_DIR"] = str(Path(hooks_dir).parent.parent.parent)

    # Add Langfuse env vars if enabled (SPEC-019, SPEC-022) — via shared helper (TD-338)
    merged["env"].update(get_langfuse_env_section())

    # Security (fixes #38): ensure QDRANT_API_KEY is never present in settings.json.
    # It may have been written there by older installer versions. Strip it now so
    # that the committed file stays secret-free. The key is kept in
    # settings.local.json (gitignored) via write_local_settings() below.
    merged_env = merged.get("env", {})
    api_key_from_merged = merged_env.pop("QDRANT_API_KEY", None)
    # Prefer the live environment value (set by install.sh before invoking this
    # script); fall back to whatever was already in settings.local.json so that
    # re-running the installer without QDRANT_API_KEY in env doesn't wipe the key.
    api_key = os.environ.get("QDRANT_API_KEY", "") or api_key_from_merged or ""
    write_local_settings(Path(settings_path), api_key)

    # BUG-066: upgrade old unguarded hooks to guarded format.
    # Note: _upgrade_hook_commands mutates in-place. Safe because
    # merged is the only reference used after this point.
    merged = _upgrade_hook_commands(merged)
    # FAIL-001 fix: Remove hook entries whose scripts no longer exist
    merged = _remove_dead_hooks(merged)
    # FAIL-03 fix: Strip vestigial 'startup' and 'clear' from SessionStart matchers (DEC-054, DEC-055)
    merged = _normalize_session_start_matcher(merged)

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
