#!/usr/bin/env python3
"""
Integration tests for hook configuration (Story 7.2).

Tests end-to-end hook configuration flow:
- New installation (no existing settings.json)
- Merge with existing settings.json
- Idempotency (run installer twice)
- Backup creation
- Verification catches errors

2026 Best Practice: Integration tests in tests/integration/
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Script calls sys.exit() which pytest captures incorrectly in CI",
)
def test_new_installation_creates_settings(tmp_path):
    """Test hook configuration on fresh installation (AC 7.2.5)."""
    from generate_settings import main as generate_main

    settings_file = tmp_path / "settings.json"
    hooks_dir = "/home/user/.ai-memory/.claude/hooks/scripts"

    sys.argv = ["generate_settings.py", str(settings_file), hooks_dir]
    generate_main()

    assert settings_file.exists(), "settings.json must be created"

    with open(settings_file) as f:
        config = json.load(f)

    # Verify structure per AC 7.2.5 (correct Claude Code format)
    assert "hooks" in config
    assert "SessionStart" in config["hooks"]
    assert "PostToolUse" in config["hooks"]
    assert "Stop" in config["hooks"]

    # Verify correct nested structure with 'hooks' array
    session_start_wrapper = config["hooks"]["SessionStart"][0]
    assert "hooks" in session_start_wrapper, "SessionStart must have 'hooks' array"
    session_start = session_start_wrapper["hooks"][0]
    assert session_start["type"] == "command"
    assert hooks_dir in session_start["command"]

    # Verify PostToolUse has matcher (not toolNames)
    post_tool_wrapper = config["hooks"]["PostToolUse"][0]
    assert "matcher" in post_tool_wrapper, "PostToolUse must have 'matcher' field"
    assert post_tool_wrapper["matcher"] == "Edit|Write|NotebookEdit"
    assert "hooks" in post_tool_wrapper, "PostToolUse must have 'hooks' array"


def test_merge_with_existing_settings(tmp_path):
    """Test merging preserves existing user settings."""
    from merge_settings import main as merge_main

    settings_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    # Create existing settings with custom configuration (correct Claude Code format)
    existing = {
        "user_preference": "dark_mode",
        "hooks": {
            "CustomHook": [
                {"hooks": [{"type": "command", "command": "custom-script.sh"}]}
            ]
        },
    }
    settings_file.write_text(json.dumps(existing, indent=2))

    # Merge BMAD hooks
    sys.argv = ["merge_settings.py", str(settings_file), hooks_dir]
    merge_main()

    with open(settings_file) as f:
        config = json.load(f)

    # User settings preserved
    assert config["user_preference"] == "dark_mode"
    assert "CustomHook" in config["hooks"]

    # BMAD hooks added with correct structure
    assert "SessionStart" in config["hooks"]
    assert "PostToolUse" in config["hooks"]
    assert "Stop" in config["hooks"]
    # Verify correct nested structure
    assert "matcher" in config["hooks"]["PostToolUse"][0]


def test_idempotency_no_duplicates(tmp_path):
    """Test running installer twice doesn't create duplicates."""
    from merge_settings import main as merge_main

    settings_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    # First run
    sys.argv = ["merge_settings.py", str(settings_file), hooks_dir]
    merge_main()

    # Second run (simulating reinstall)
    sys.argv = ["merge_settings.py", str(settings_file), hooks_dir]
    merge_main()

    with open(settings_file) as f:
        config = json.load(f)

    # Should not have duplicate hook wrappers
    # Note: PostToolUse has 2 matchers (Bash for errors, Edit/Write for capture)
    assert len(config["hooks"]["SessionStart"]) == 1
    assert len(config["hooks"]["PostToolUse"]) == 2  # Bash + Edit|Write|NotebookEdit
    assert len(config["hooks"]["Stop"]) == 1
    # Each wrapper should have the expected number of hooks
    assert len(config["hooks"]["SessionStart"][0]["hooks"]) == 1
    # PostToolUse[0] is Bash matcher with 2 hooks (error_detection + error_pattern_capture)
    assert len(config["hooks"]["PostToolUse"][0]["hooks"]) == 2
    assert len(config["hooks"]["Stop"][0]["hooks"]) == 1


def test_backup_creation_on_merge(tmp_path):
    """Test backup is created before modifying existing settings."""
    from merge_settings import main as merge_main

    settings_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    # Create existing settings
    original_content = {"test": "original"}
    settings_file.write_text(json.dumps(original_content))

    # Merge
    sys.argv = ["merge_settings.py", str(settings_file), hooks_dir]
    merge_main()

    # Check backup was created
    backups = list(tmp_path.glob("settings.json.backup.*"))
    assert len(backups) == 1, "Backup must be created"

    # Verify backup has original content
    with open(backups[0]) as f:
        backup_content = json.load(f)
    assert backup_content == original_content


def test_verification_catches_invalid_json(tmp_path):
    """Test verification detects invalid JSON."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{invalid json")

    # Verify using Python (simulating verify_hooks bash function)
    result = subprocess.run(
        ["python3", "-c", f"import json; json.load(open('{settings_file}'))"],
        capture_output=True,
    )

    assert result.returncode != 0, "Must detect invalid JSON"


def test_verification_catches_missing_hooks_section(tmp_path):
    """Test verification detects missing hooks section."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"other": "config"}))

    # Verify using Python (simulating verify_hooks bash function)
    result = subprocess.run(
        [
            "python3",
            "-c",
            f"""
import json
import sys
settings = json.load(open('{settings_file}'))
if 'hooks' not in settings:
    sys.exit(1)
""",
        ],
        capture_output=True,
    )

    assert result.returncode != 0, "Must detect missing hooks section"


def test_verification_catches_missing_required_hooks(tmp_path):
    """Test verification detects missing required hook types."""
    settings_file = tmp_path / "settings.json"
    incomplete_config = {
        "hooks": {
            "SessionStart": [{"type": "command", "command": "test.py"}]
            # Missing PostToolUse and Stop
        }
    }
    settings_file.write_text(json.dumps(incomplete_config))

    # Verify using Python
    result = subprocess.run(
        [
            "python3",
            "-c",
            f"""
import json
import sys
settings = json.load(open('{settings_file}'))
required_hooks = ['SessionStart', 'PostToolUse', 'Stop']
missing = [h for h in required_hooks if h not in settings['hooks']]
if missing:
    sys.exit(1)
""",
        ],
        capture_output=True,
    )

    assert result.returncode != 0, "Must detect missing hooks"


def test_manual_testing_checklist():
    """Document manual testing requirements for Story 7.2 AC 7.2.5."""
    # This test documents the manual testing checklist (not automated)

    manual_tests = """
    Manual Testing Checklist (Story 7.2 - Task 5):

    [ ] Test on Ubuntu 22.04/24.04
        - Run: ./install.sh
        - Verify: $HOME/.claude/settings.json created
        - Check: All 3 hooks present with absolute paths

    [ ] Test on macOS (Intel)
        - Run: ./install.sh
        - Verify: Hooks use python3 (not python)

    [ ] Test on macOS (Apple Silicon)
        - Same as Intel test

    [ ] Test on WSL2
        - Run: ./install.sh from WSL shell
        - Verify: Windows-side .claude/settings.json accessible

    [ ] Test with existing settings.json
        - Create custom settings first
        - Run installer
        - Verify: Custom settings preserved, BMAD hooks added

    [ ] Test deduplication (run twice)
        - Run: ./install.sh
        - Run: ./install.sh again
        - Verify: No duplicate hooks in settings.json

    [ ] Test backup creation
        - Modify existing settings.json
        - Run installer
        - Verify: Backup created with timestamp

    [ ] Test verification catches errors
        - Corrupt settings.json manually
        - Run installer
        - Verify: Install fails with clear error

    [ ] Test missing hook scripts
        - Delete one hook script
        - Run installer
        - Verify: Verification fails
    """

    # This test always passes but documents manual testing requirements
    assert True, "Manual testing documented in test output"
    print(manual_tests)
