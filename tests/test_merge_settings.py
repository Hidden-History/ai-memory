#!/usr/bin/env python3
"""
Unit tests for scripts/merge_settings.py

Tests deep merge logic for Claude Code settings.json.
Follows red-green-refactor cycle - these tests MUST fail initially.

2026 Best Practice: pytest with fixtures for test isolation
"""

import json
import sys
from datetime import datetime

import pytest


def test_deep_merge_basic():
    """Test basic dictionary merging."""
    from merge_settings import deep_merge

    base = {"a": 1, "b": 2}
    overlay = {"c": 3}

    result = deep_merge(base, overlay)

    assert result == {"a": 1, "b": 2, "c": 3}
    assert base == {"a": 1, "b": 2}, "Original dict must not be modified"


def test_deep_merge_nested_dicts():
    """Test deep merging of nested dictionaries."""
    from merge_settings import deep_merge

    base = {"level1": {"a": 1, "b": 2}}
    overlay = {"level1": {"c": 3}}

    result = deep_merge(base, overlay)

    assert result == {"level1": {"a": 1, "b": 2, "c": 3}}


def test_deep_merge_preserve_existing():
    """Test that existing values are preserved."""
    from merge_settings import deep_merge

    base = {"hooks": {"Custom": [{"type": "custom"}]}}
    overlay = {"hooks": {"SessionStart": [{"type": "command"}]}}

    result = deep_merge(base, overlay)

    assert "Custom" in result["hooks"], "Existing hooks must be preserved"
    assert "SessionStart" in result["hooks"], "New hooks must be added"


def test_deep_merge_list_append():
    """Test list merging appends new items."""
    from merge_settings import deep_merge

    base = {"items": [1, 2]}
    overlay = {"items": [3, 4]}

    result = deep_merge(base, overlay)

    assert len(result["items"]) == 4


def test_merge_lists_deduplication():
    """Test list merging deduplicates by command field."""
    from merge_settings import merge_lists

    existing = [
        {"command": "python3 /path/hook1.py", "type": "command"},
        {"command": "python3 /path/hook2.py", "type": "command"},
    ]
    new = [
        {"command": "python3 /path/hook1.py", "type": "command"},  # Duplicate
        {"command": "python3 /path/hook3.py", "type": "command"},  # New
    ]

    result = merge_lists(existing, new)

    assert len(result) == 3, "Must have 3 items (2 original + 1 new)"
    commands = [item["command"] for item in result]
    assert commands.count("python3 /path/hook1.py") == 1, "No duplicates"


def test_merge_lists_non_dict_items():
    """Test list merging with non-dict items."""
    from merge_settings import merge_lists

    existing = [1, 2, 3]
    new = [4, 5]

    result = merge_lists(existing, new)

    assert result == [1, 2, 3, 4, 5]


def test_backup_file_creates_timestamped_backup(tmp_path):
    """Test backup creates file with timestamp (using copy, not rename)."""
    from merge_settings import backup_file

    original = tmp_path / "settings.json"
    original.write_text('{"test": true}')

    backup_path = backup_file(original)

    assert backup_path.exists(), "Backup file must exist"
    assert original.exists(), "Original must still exist (copy, not rename)"
    assert ".backup." in backup_path.name, "Backup must have .backup. in name"
    # Verify backup has same content
    assert backup_path.read_text() == '{"test": true}'


def test_backup_file_timestamp_format(tmp_path):
    """Test backup timestamp format is YYYYMMDD_HHMMSS."""
    from merge_settings import backup_file

    original = tmp_path / "settings.json"
    original.write_text("{}")

    backup_path = backup_file(original)

    # Extract timestamp from filename
    # Format: settings.json.backup.20260113_143059
    parts = backup_path.name.split(".")
    timestamp = parts[-1]

    # Verify it parses as expected format
    datetime.strptime(timestamp, "%Y%m%d_%H%M%S")


def test_merge_settings_new_file(tmp_path):
    """Test merging when settings.json doesn't exist."""
    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    merge_settings(str(settings_path), hooks_dir)

    assert settings_path.exists()
    with open(settings_path) as f:
        config = json.load(f)

    assert "hooks" in config
    assert (
        len(config["hooks"]) == 6
    )  # SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PreCompact, Stop
    # Verify correct nested structure
    assert "hooks" in config["hooks"]["SessionStart"][0]
    assert "matcher" in config["hooks"]["PostToolUse"][0]


def test_merge_settings_existing_file(tmp_path):
    """Test merging with existing settings.json."""
    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    existing = {
        "custom_setting": True,
        "hooks": {"Custom": [{"hooks": [{"type": "custom"}]}]},
    }
    settings_path.write_text(json.dumps(existing))

    hooks_dir = "/test/hooks"
    merge_settings(str(settings_path), hooks_dir)

    with open(settings_path) as f:
        config = json.load(f)

    assert "custom_setting" in config, "Custom settings must be preserved"
    assert "Custom" in config["hooks"], "Existing hooks must be preserved"
    assert "SessionStart" in config["hooks"], "New hooks must be added"
    # Verify correct nested structure for new hooks
    assert "matcher" in config["hooks"]["PostToolUse"][0]


def test_merge_settings_creates_backup(tmp_path):
    """Test that backup is created before merge."""
    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"test": true}')

    hooks_dir = "/test/hooks"
    merge_settings(str(settings_path), hooks_dir)

    # Check for backup file
    backups = list(tmp_path.glob("settings.json.backup.*"))
    assert len(backups) == 1, "Exactly one backup must be created"


def test_merge_settings_deduplicates_hooks(tmp_path):
    """Test that duplicate hooks are not added when using BMAD path format."""
    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    # Existing config with BMAD-style path (will be normalized to bmad-hook:session_start.py)
    existing = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/session_start.py"',
                            "timeout": 30000,
                        }
                    ],
                }
            ]
        }
    }
    settings_path.write_text(json.dumps(existing))

    hooks_dir = "/test/.claude/hooks/scripts"
    merge_settings(str(settings_path), hooks_dir)

    with open(settings_path) as f:
        config = json.load(f)

    # Should not have duplicate SessionStart hook wrappers (same script, normalized)
    assert len(config["hooks"]["SessionStart"]) == 1
    # Should have exactly 1 hook in the wrapper
    assert len(config["hooks"]["SessionStart"][0]["hooks"]) == 1


def test_merge_settings_imports_generate_hook_config():
    """Test that merge_settings imports generate_hook_config correctly."""
    from merge_settings import merge_settings

    # This test verifies the import works (AC 7.2.3 requirement)
    # If import fails, the module won't load
    assert callable(merge_settings)


def test_main_requires_arguments():
    """Test main() exits with error if arguments missing."""
    from merge_settings import main

    sys.argv = ["merge_settings.py"]  # Missing args

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_main_success_message(tmp_path, capsys):
    """Test main() prints success message with hook list."""
    from merge_settings import main

    settings_path = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    sys.argv = ["merge_settings.py", str(settings_path), hooks_dir]
    main()

    captured = capsys.readouterr()
    assert "Updated" in captured.out
    assert "SessionStart" in captured.out
    assert "PostToolUse" in captured.out
    assert "Stop" in captured.out


class TestRemoveDeadHooks:
    """Test _remove_dead_hooks() cleanup logic (FAIL-001 fix)."""

    def test_removes_hook_with_missing_script(self, tmp_path):
        """Hook entries whose scripts don't exist should be removed."""
        from merge_settings import _remove_dead_hooks

        # Create a fake install dir with one live script
        scripts_dir = tmp_path / ".claude" / "hooks" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "live_script.py").touch()

        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "hooks": [
                            {
                                "command": f'[ -f "{scripts_dir}/live_script.py" ] && python "{scripts_dir}/live_script.py" || true',
                                "type": "command",
                            }
                        ]
                    },
                    {
                        "hooks": [
                            {
                                "command": f'[ -f "{scripts_dir}/dead_script.py" ] && python "{scripts_dir}/dead_script.py" || true',
                                "type": "command",
                            }
                        ]
                    },
                ]
            }
        }

        result = _remove_dead_hooks(settings, install_dir=str(tmp_path))

        # Live script should remain, dead script should be removed
        assert len(result["hooks"]["PostToolUse"]) == 1

    def test_preserves_non_bmad_hooks(self, tmp_path):
        """Non-BMAD hook commands should never be removed."""
        from merge_settings import _remove_dead_hooks

        scripts_dir = tmp_path / ".claude" / "hooks" / "scripts"
        scripts_dir.mkdir(parents=True)

        settings = {
            "hooks": {
                "PostToolUse": [
                    {"command": "echo 'custom hook'", "type": "command"},
                ]
            }
        }

        result = _remove_dead_hooks(settings, install_dir=str(tmp_path))
        assert len(result["hooks"]["PostToolUse"]) == 1

    def test_skips_when_scripts_dir_missing(self, tmp_path):
        """Non-deny-listed hooks with generic commands are preserved when scripts directory doesn't exist."""
        from merge_settings import _remove_dead_hooks

        settings = {"hooks": {"PostToolUse": [{"command": "something"}]}}
        result = _remove_dead_hooks(settings, install_dir=str(tmp_path))

        # Should return settings unchanged
        assert len(result["hooks"]["PostToolUse"]) == 1

    def test_handles_empty_hooks(self, tmp_path):
        """Should handle settings with no hooks gracefully."""
        from merge_settings import _remove_dead_hooks

        scripts_dir = tmp_path / ".claude" / "hooks" / "scripts"
        scripts_dir.mkdir(parents=True)

        result = _remove_dead_hooks({}, install_dir=str(tmp_path))
        assert result == {}

    def test_deny_list_removes_deprecated_script_even_when_file_exists(self, tmp_path):
        """BUG-250: _DEAD_HOOK_SCRIPTS entries removed even if the script file still exists."""
        from merge_settings import _remove_dead_hooks

        scripts_dir = tmp_path / ".claude" / "hooks" / "scripts"
        scripts_dir.mkdir(parents=True)
        # Create the deprecated script so the filesystem check would NOT flag it
        (scripts_dir / "unified_keyword_trigger.py").touch()

        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": f'"{tmp_path}/.venv/bin/python" "{tmp_path}/.claude/hooks/scripts/unified_keyword_trigger.py"',
                            }
                        ]
                    }
                ]
            }
        }

        result = _remove_dead_hooks(settings, install_dir=str(tmp_path))
        # Wrapper should be dropped because the sub-hook is in _DEAD_HOOK_SCRIPTS
        assert result["hooks"]["UserPromptSubmit"] == []

    def test_deny_list_removes_deprecated_script_when_scripts_dir_missing(
        self, tmp_path
    ):
        """BUG-250+F2: _DEAD_HOOK_SCRIPTS purged even before scripts dir is created (fresh install)."""
        from merge_settings import _remove_dead_hooks

        # Do NOT create scripts_dir — simulates fresh install state
        settings = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": f'"{tmp_path}/.venv/bin/python" "{tmp_path}/.claude/hooks/scripts/unified_keyword_trigger.py"',
                            }
                        ]
                    }
                ]
            }
        }

        result = _remove_dead_hooks(settings, install_dir=str(tmp_path))
        # Must still remove deny-listed entries even with no scripts dir
        assert result["hooks"]["UserPromptSubmit"] == []


# ---------------------------------------------------------------------------
# TD-334: AI_MEMORY_INSTALL_DIR force-update (Fix 5)
# ---------------------------------------------------------------------------


def test_merge_settings_install_dir_force_updates_stale_value(tmp_path):
    """TD-334: AI_MEMORY_INSTALL_DIR must override any stale value in existing settings."""
    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    existing = {
        "env": {
            "AI_MEMORY_INSTALL_DIR": "/old/stale/path",
            "AI_MEMORY_PROJECT_ID": "test-project",
        },
        "hooks": {},
    }
    settings_path.write_text(json.dumps(existing))

    # hooks_dir: install_dir/.claude/hooks/scripts → 3 levels up = install_dir
    install_dir = tmp_path / "install_v2"
    hooks_dir = str(install_dir / ".claude" / "hooks" / "scripts")

    merge_settings(str(settings_path), hooks_dir)

    with open(settings_path) as f:
        config = json.load(f)

    assert config["env"]["AI_MEMORY_INSTALL_DIR"] == str(install_dir)
    assert config["env"]["AI_MEMORY_INSTALL_DIR"] != "/old/stale/path"


def test_merge_settings_install_dir_not_preserved_by_deep_merge(tmp_path):
    """TD-334: AI_MEMORY_INSTALL_DIR is NOT preserved by deep_merge 'base wins' logic."""
    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    existing = {
        "env": {"AI_MEMORY_INSTALL_DIR": "/should/be/overridden"},
        "hooks": {},
    }
    settings_path.write_text(json.dumps(existing))

    install_dir = tmp_path / "new_install"
    hooks_dir = str(install_dir / ".claude" / "hooks" / "scripts")

    merge_settings(str(settings_path), hooks_dir)

    with open(settings_path) as f:
        config = json.load(f)

    # Force-update means the new value always wins
    assert config["env"]["AI_MEMORY_INSTALL_DIR"] == str(install_dir)


# ---------------------------------------------------------------------------
# _normalize_session_start_matcher: stripping 'clear' (Fix 4)
# ---------------------------------------------------------------------------


def _session_start_settings(matcher: str) -> dict:
    """Build minimal settings dict with a SessionStart hook containing session_start.py."""
    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": matcher,
                    "hooks": [
                        {
                            "type": "command",
                            "command": '"$AI_MEMORY_INSTALL_DIR/.venv/bin/python" '
                            '"$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/session_start.py"',
                        }
                    ],
                }
            ]
        }
    }


class TestNormalizeSessionStartMatcher:
    """Test _normalize_session_start_matcher() strips stale triggers."""

    def test_strips_startup_and_clear_both_stale(self):
        """'startup|clear' — both stale → fallback to 'resume|compact'."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("startup|clear")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_strips_clear_from_mixed_matcher(self):
        """'resume|compact|clear' — clear is stale, resume|compact remain."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("resume|compact|clear")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_strips_clear_alone(self):
        """'clear' alone — stale, fallback to 'resume|compact'."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("clear")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_clean_matcher_unchanged(self):
        """'resume|compact' — already clean, must not be modified."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("resume|compact")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_strips_startup_alone(self):
        """'startup' alone — stale, fallback to 'resume|compact'."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("startup")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_strips_startup_from_mixed_matcher(self):
        """'startup|resume|compact' — startup is stale, resume|compact remain."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("startup|resume|compact")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_strips_full_old_pattern(self):
        """startup|resume|compact|clear — the original v2.1.x pattern → resume|compact."""
        from merge_settings import _normalize_session_start_matcher

        settings = _session_start_settings("startup|resume|compact|clear")
        result = _normalize_session_start_matcher(settings)
        assert result["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"


# ---------------------------------------------------------------------------
# TD-334: isabs guard for relative hooks_dir (Fix 5b)
# ---------------------------------------------------------------------------


def test_merge_settings_install_dir_relative_hooks_dir(tmp_path):
    """TD-334 isabs guard: relative hooks_dir is resolved to absolute before computing install_dir."""
    import os

    from merge_settings import merge_settings

    settings_path = tmp_path / "settings.json"
    existing: dict = {"env": {}, "hooks": {}}
    settings_path.write_text(json.dumps(existing))

    # Use a relative path — the isabs guard must call os.path.abspath()
    # so Path(...).parent.parent.parent resolves correctly.
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        relative_hooks_dir = ".claude/hooks/scripts"
        merge_settings(str(settings_path), relative_hooks_dir)
    finally:
        os.chdir(original_cwd)

    with open(settings_path) as f:
        config = json.load(f)

    expected_install_dir = str(tmp_path)
    assert config["env"]["AI_MEMORY_INSTALL_DIR"] == expected_install_dir
