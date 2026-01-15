#!/usr/bin/env python3
"""
Unit tests for scripts/generate_settings.py

Tests hook configuration generation for Claude Code settings.json.
Follows red-green-refactor cycle - these tests MUST fail initially.

2026 Best Practice: pytest for Python 3.10+ testing
"""

import json
import sys
from pathlib import Path

import pytest


# Import the module we're testing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_generate_hook_config_basic():
    """Test basic hook configuration structure."""
    from generate_settings import generate_hook_config

    hooks_dir = "/home/user/.bmad-memory/.claude/hooks/scripts"
    config = generate_hook_config(hooks_dir)

    assert "hooks" in config, "Config must have 'hooks' top-level key"
    assert isinstance(config["hooks"], dict), "hooks value must be dict"


def test_generate_hook_config_session_start():
    """Test SessionStart hook generation with correct Claude Code structure."""
    from generate_settings import generate_hook_config

    hooks_dir = "/test/path/hooks"
    config = generate_hook_config(hooks_dir)

    assert "SessionStart" in config["hooks"]
    session_start = config["hooks"]["SessionStart"]
    assert isinstance(session_start, list), "SessionStart must be list"
    assert len(session_start) == 1, "SessionStart must have exactly 1 wrapper"

    # Correct structure: wrapper with 'hooks' array
    wrapper = session_start[0]
    assert "hooks" in wrapper, "SessionStart must have 'hooks' array"
    assert isinstance(wrapper["hooks"], list)
    assert len(wrapper["hooks"]) == 1

    hook = wrapper["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == f"python3 {hooks_dir}/session_start.py"


def test_generate_hook_config_post_tool_use():
    """Test PostToolUse hook generation with matcher filtering (correct Claude Code format)."""
    from generate_settings import generate_hook_config

    hooks_dir = "/test/hooks"
    config = generate_hook_config(hooks_dir)

    assert "PostToolUse" in config["hooks"]
    post_tool = config["hooks"]["PostToolUse"]
    assert isinstance(post_tool, list)
    assert len(post_tool) == 1

    # Correct structure: wrapper with 'matcher' + 'hooks' array
    wrapper = post_tool[0]
    assert "matcher" in wrapper, "PostToolUse must have 'matcher' field"
    assert wrapper["matcher"] == "Edit|Write|NotebookEdit"
    assert "hooks" in wrapper, "PostToolUse must have 'hooks' array"
    assert isinstance(wrapper["hooks"], list)
    assert len(wrapper["hooks"]) == 1

    hook = wrapper["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == f"python3 {hooks_dir}/post_tool_capture.py"


def test_generate_hook_config_stop():
    """Test Stop hook generation with correct Claude Code structure."""
    from generate_settings import generate_hook_config

    hooks_dir = "/test/hooks"
    config = generate_hook_config(hooks_dir)

    assert "Stop" in config["hooks"]
    stop_hook = config["hooks"]["Stop"]
    assert isinstance(stop_hook, list)
    assert len(stop_hook) == 1

    # Correct structure: wrapper with 'hooks' array
    wrapper = stop_hook[0]
    assert "hooks" in wrapper, "Stop must have 'hooks' array"
    assert isinstance(wrapper["hooks"], list)
    assert len(wrapper["hooks"]) == 1

    hook = wrapper["hooks"][0]
    assert hook["type"] == "command"
    assert hook["command"] == f"python3 {hooks_dir}/session_stop.py"


def test_generate_hook_config_absolute_paths():
    """Test that absolute paths are used correctly in nested hook structure."""
    from generate_settings import generate_hook_config

    hooks_dir = "/absolute/path/to/hooks"
    config = generate_hook_config(hooks_dir)

    # Check all commands use provided absolute path (in nested 'hooks' arrays)
    for hook_type, wrappers in config["hooks"].items():
        for wrapper in wrappers:
            assert "hooks" in wrapper, f"{hook_type} must have 'hooks' array"
            for hook in wrapper["hooks"]:
                assert hook["command"].startswith("python3 /absolute/path")


def test_main_creates_file(tmp_path):
    """Test main() function creates settings.json file."""
    from generate_settings import main

    output_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    # Override sys.argv
    sys.argv = ["generate_settings.py", str(output_file), hooks_dir]

    main()

    assert output_file.exists(), "settings.json must be created"


def test_main_creates_parent_directories(tmp_path):
    """Test main() creates parent directories if needed."""
    from generate_settings import main

    output_file = tmp_path / "nested" / "dir" / "settings.json"
    hooks_dir = "/test/hooks"

    sys.argv = ["generate_settings.py", str(output_file), hooks_dir]
    main()

    assert output_file.exists()
    assert output_file.parent.exists()


def test_main_writes_valid_json(tmp_path):
    """Test main() writes valid JSON with correct structure."""
    from generate_settings import main

    output_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    sys.argv = ["generate_settings.py", str(output_file), hooks_dir]
    main()

    # Parse JSON to verify it's valid
    with open(output_file) as f:
        config = json.load(f)

    assert "hooks" in config
    assert len(config["hooks"]) == 3  # SessionStart, PostToolUse, Stop


def test_main_requires_arguments():
    """Test main() exits with error if arguments missing."""
    from generate_settings import main

    sys.argv = ["generate_settings.py"]  # Missing args

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_main_json_formatting(tmp_path):
    """Test JSON is written with proper indentation."""
    from generate_settings import main

    output_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    sys.argv = ["generate_settings.py", str(output_file), hooks_dir]
    main()

    # Read raw content
    content = output_file.read_text()

    # Check for indentation (indent=2)
    assert '  "hooks"' in content, "JSON must be indented"
    assert '    "SessionStart"' in content
    # Verify correct structure with nested 'hooks' arrays
    assert '"matcher"' in content, "PostToolUse must have matcher field"
