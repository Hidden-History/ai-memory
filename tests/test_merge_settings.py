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
from pathlib import Path

import pytest

# Import the module we're testing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


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
                    "matcher": "startup|resume|compact|clear",
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
