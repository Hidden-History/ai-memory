#!/usr/bin/env python3
"""
Recovery script for AI Memory hook guards.

Fixes two issues in existing .claude/settings.json files that cannot be
propagated by the installer's merge_settings.py (which deduplicates by command):

  BUG-066: Adds guard wrappers ([ -f ... ] && ... || true) to hook commands
           so deleting ~/.ai-memory doesn't break Claude Code.
  BUG-078: Narrows SessionStart matcher from "startup|resume|compact|clear"
           to "resume|compact".

Usage:
    python scripts/recover_hook_guards.py /path/to/project/.claude/settings.json
    python scripts/recover_hook_guards.py /path/to/project/.claude/settings.json --apply
    python scripts/recover_hook_guards.py --scan
    python scripts/recover_hook_guards.py --scan --apply
"""

import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime


# --- Helpers ----------------------------------------------------------------


def _hook_cmd(script_name: str) -> str:
    """Generate gracefully-degrading hook command. Exits 0 if installation missing."""
    script = f"$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/{script_name}"
    python = "$AI_MEMORY_INSTALL_DIR/.venv/bin/python"
    return f'[ -f "{script}" ] && "{python}" "{script}" || true'


def _fix_cmd(cmd: str) -> str:
    """Replace unguarded hook command with guarded format."""
    if ".claude/hooks/scripts/" in cmd and "|| true" not in cmd:
        m = re.search(r'\.claude/hooks/scripts/([^"]+?)(?:"|$)', cmd)
        if m:
            return _hook_cmd(m.group(1))
    return cmd


# --- Core logic -------------------------------------------------------------


def process_settings(original: dict) -> tuple:
    """
    Apply BUG-066 (guard commands) and BUG-078 (matcher fix) to settings.

    Returns:
        (modified_settings, commands_guarded, matchers_fixed)
    """
    settings = json.loads(json.dumps(original))  # deep copy

    commands_guarded = 0
    matchers_fixed = 0

    for hook_type, wrappers in settings.get("hooks", {}).items():
        if not isinstance(wrappers, list):
            continue
        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                continue

            # Fix 1: Guard hook commands (BUG-066)
            if "command" in wrapper:
                new = _fix_cmd(wrapper["command"])
                if new != wrapper["command"]:
                    wrapper["command"] = new
                    commands_guarded += 1
            for hook in wrapper.get("hooks", []):
                if isinstance(hook, dict) and "command" in hook:
                    new = _fix_cmd(hook["command"])
                    if new != hook["command"]:
                        hook["command"] = new
                        commands_guarded += 1

            # Fix 2: SessionStart matcher (BUG-078)
            if (
                hook_type == "SessionStart"
                and wrapper.get("matcher") == "startup|resume|compact|clear"
            ):
                wrapper["matcher"] = "resume|compact"
                matchers_fixed += 1

    return settings, commands_guarded, matchers_fixed


# --- Safety checks ----------------------------------------------------------


def _check_structure(orig: dict, modified: dict, path: str = "") -> list:
    """Verify structure preserved (same keys, same list lengths, no extra keys)."""
    issues = []
    for k, v in orig.items():
        p = f"{path}.{k}" if path else k
        if k not in modified:
            issues.append(f"MISSING KEY: {p}")
        elif isinstance(v, dict) and isinstance(modified[k], dict):
            issues.extend(_check_structure(v, modified[k], p))
        elif isinstance(v, list) and isinstance(modified[k], list):
            if len(v) != len(modified[k]):
                issues.append(
                    f"LIST LENGTH CHANGED: {p} ({len(v)} -> {len(modified[k])})"
                )
            for i, (a, b) in enumerate(zip(v, modified[k])):
                if isinstance(a, dict) and isinstance(b, dict):
                    issues.extend(_check_structure(a, b, f"{p}[{i}]"))
    # L1: Check for extra keys added to modified (bidirectional check)
    for k in modified:
        if k not in orig:
            p = f"{path}.{k}" if path else k
            issues.append(f"EXTRA KEY: {p}")
    return issues


def _get_non_command_values(d: dict, path: str = "") -> dict:
    """Extract all field values except 'command' and 'matcher' for comparison."""
    values = {}
    for k, v in d.items():
        p = f"{path}.{k}" if path else k
        if isinstance(v, dict):
            values.update(_get_non_command_values(v, p))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    values.update(_get_non_command_values(item, f"{p}[{i}]"))
        elif k not in ("command", "matcher"):
            values[p] = v
    return values


def _run_safety_checks(
    original: dict, settings: dict, commands_guarded: int
) -> tuple:
    """
    Run all safety checks.

    Returns:
        (report_lines, all_passed)
    """
    lines = []
    all_passed = True

    # Verify env section untouched
    if settings.get("env") == original.get("env"):
        lines.append("ENV SECTION: IDENTICAL (safe)")
    else:
        lines.append("ENV SECTION: CHANGED (DANGER!)")
        all_passed = False

    # Verify $schema untouched
    if settings.get("$schema") == original.get("$schema"):
        lines.append("SCHEMA: IDENTICAL (safe)")
    else:
        lines.append("SCHEMA: CHANGED (DANGER!)")
        all_passed = False

    # Verify structure preserved
    issues = _check_structure(original, settings)
    if issues:
        for issue in issues:
            lines.append(f"STRUCTURE ISSUE: {issue}")
        all_passed = False
    else:
        lines.append("STRUCTURE: ALL KEYS AND LISTS PRESERVED (safe)")

    # Verify non-command, non-matcher fields identical
    orig_vals = _get_non_command_values(original)
    mod_vals = _get_non_command_values(settings)
    if orig_vals == mod_vals:
        lines.append("NON-COMMAND FIELDS: ALL IDENTICAL (safe)")
    else:
        for k in sorted(set(list(orig_vals.keys()) + list(mod_vals.keys()))):
            if orig_vals.get(k) != mod_vals.get(k):
                lines.append(
                    f"CHANGED NON-COMMAND: {k}: {orig_vals.get(k)} -> {mod_vals.get(k)}"
                )
        all_passed = False

    # Verify all hook commands now guarded
    unguarded = []
    for _hook_type, wrappers in settings.get("hooks", {}).items():
        if not isinstance(wrappers, list):
            continue
        for wrapper in wrappers:
            if not isinstance(wrapper, dict):
                continue
            if "command" in wrapper:
                if (
                    ".claude/hooks/scripts/" in wrapper["command"]
                    and "|| true" not in wrapper["command"]
                ):
                    unguarded.append(wrapper["command"][:60])
            for hook in wrapper.get("hooks", []):
                if isinstance(hook, dict) and "command" in hook:
                    if (
                        ".claude/hooks/scripts/" in hook["command"]
                        and "|| true" not in hook["command"]
                    ):
                        unguarded.append(hook["command"][:60])
    if unguarded:
        for cmd in unguarded:
            lines.append(f"STILL UNGUARDED: {cmd}...")
        all_passed = False
    else:
        lines.append(f"ALL HOOKS GUARDED: Yes ({commands_guarded} upgraded)")

    return lines, all_passed


# --- Scan mode --------------------------------------------------------------


def _find_settings_files(extra_search_paths: list | None = None) -> list:
    """
    Find settings.json files across all known AI Memory project installations.

    Search strategy (in order):
    1. Read ~/.ai-memory/installed_projects.json manifest (primary)
    2. Scan sibling directories of AI_MEMORY_INSTALL_DIR (fallback)
    3. Search any paths provided via --search-path argument
    4. Filter to files containing AI_MEMORY_INSTALL_DIR in env section
    """
    install_dir = os.path.expanduser("~/.ai-memory")

    env_file = os.path.join(install_dir, "docker", ".env")
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("AI_MEMORY_INSTALL_DIR="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        install_dir = os.path.expanduser(val)
                    break

    candidates = set()

    # --- Source 1: Manifest file (primary) ---
    manifest_path = os.path.join(install_dir, "installed_projects.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            for entry in manifest:
                if isinstance(entry, dict) and "path" in entry:
                    settings = os.path.join(entry["path"], ".claude", "settings.json")
                    if os.path.isfile(settings):
                        candidates.add(settings)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Could not read manifest {manifest_path}: {e}", file=sys.stderr)

    # --- Source 2: Sibling directories of install dir (fallback) ---
    parent_dir = os.path.dirname(install_dir)
    if os.path.isdir(parent_dir):
        try:
            for entry in os.listdir(parent_dir):
                candidate = os.path.join(parent_dir, entry, ".claude", "settings.json")
                if os.path.isfile(candidate):
                    candidates.add(candidate)
        except OSError:
            pass

    # --- Source 3: Extra search paths from --search-path ---
    for search_path in (extra_search_paths or []):
        search_path = os.path.expanduser(search_path)
        if os.path.isdir(search_path):
            try:
                for entry in os.listdir(search_path):
                    candidate = os.path.join(search_path, entry, ".claude", "settings.json")
                    if os.path.isfile(candidate):
                        candidates.add(candidate)
            except OSError:
                pass

    # --- Source 4: Install dir itself ---
    own = os.path.join(install_dir, ".claude", "settings.json")
    if os.path.isfile(own):
        candidates.add(own)

    # --- Filter: only files with AI_MEMORY_INSTALL_DIR in env section ---
    result = []
    for path in candidates:
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data.get("env"), dict) and "AI_MEMORY_INSTALL_DIR" in data["env"]:
                result.append(path)
        except (json.JSONDecodeError, OSError):
            continue

    return sorted(result)


# --- Backup -----------------------------------------------------------------


def _backup_file(path: str) -> str:
    """Create timestamped backup of file using copy (safer than rename)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path + f".backup.{timestamp}"
    # L3: Avoid collision if run twice within the same second
    if os.path.exists(backup_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = path + f".backup.{timestamp}"
    shutil.copy2(path, backup_path)
    return backup_path


# --- Process a single file --------------------------------------------------


def _process_file(path: str, apply: bool) -> int:
    """
    Process one settings.json file.

    Returns:
        0 = no changes needed, or changes applied successfully
        1 = changes needed but not applied (dry-run)
        2 = error (file not found, JSON parse error, safety check failed)
    """
    try:
        with open(path) as f:
            original = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}", file=sys.stderr)
        return 2

    # L4: Validate input is a Claude Code settings.json
    if not isinstance(original, dict):
        print(f"Error: {path} is not a JSON object", file=sys.stderr)
        return 2
    if "hooks" not in original:
        print(
            f"Error: {path} has no 'hooks' key — not a Claude Code settings.json?",
            file=sys.stderr,
        )
        return 2

    settings, commands_guarded, matchers_fixed = process_settings(original)
    total_changes = commands_guarded + matchers_fixed

    # Report
    print(f"=== {path} ===")
    print(f"Commands guarded: {commands_guarded}")
    print(f"Matchers fixed: {matchers_fixed}")

    # Safety checks
    check_lines, checks_passed = _run_safety_checks(
        original, settings, commands_guarded
    )
    for line in check_lines:
        print(line)

    if not checks_passed:
        print("SAFETY CHECKS FAILED -- aborting.", file=sys.stderr)
        return 2

    if total_changes == 0:
        print("No changes needed.")
        return 0

    if apply:
        backup_path = _backup_file(path)
        print(f"Backup: {backup_path}")
        # M1+M2+L2: Atomic write preserving permissions with trailing newline
        orig_mode = stat.S_IMODE(os.stat(path).st_mode)
        dir_name = os.path.dirname(os.path.abspath(path))
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(settings, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, orig_mode)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        parts = []
        if commands_guarded:
            parts.append(f"{commands_guarded} commands guarded")
        if matchers_fixed:
            parts.append(f"{matchers_fixed} matcher fixed")
        print(f"Applied: {path} ({', '.join(parts)})")
        return 0
    else:
        print("[DRY RUN] Would write changes. Use --apply to apply.")
        return 1


# --- Main -------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recovery script for AI Memory hook guards (BUG-066 + BUG-078)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Path to a single settings.json file",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan common project directories for settings.json files that need recovery",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes back to file(s). Default: dry-run, report only.",
    )
    parser.add_argument(
        "--search-path",
        action="append",
        default=None,
        dest="search_paths",
        help="Additional directory to search for projects (can be specified multiple times)",
    )
    args = parser.parse_args()

    if args.scan and args.path:
        parser.error("--scan and path are mutually exclusive")
    if not args.scan and not args.path:
        parser.error("provide a path or use --scan")

    if args.scan:
        files = _find_settings_files(extra_search_paths=args.search_paths)
        if not files:
            print("No ai-memory settings.json files found.")
            return 0
        print(f"Found {len(files)} ai-memory settings.json file(s):\n")
        worst = 0
        for path in files:
            rc = _process_file(path, args.apply)
            worst = max(worst, rc)
            print()
        return worst
    else:
        return _process_file(args.path, args.apply)


if __name__ == "__main__":
    sys.exit(main())
