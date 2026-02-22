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

    hooks_dir = "/home/user/.ai-memory/.claude/hooks/scripts"
    config = generate_hook_config(hooks_dir, "test-project")

    assert "hooks" in config, "Config must have 'hooks' top-level key"
    assert isinstance(config["hooks"], dict), "hooks value must be dict"


def test_generate_hook_config_session_start(monkeypatch):
    """Test SessionStart hook generation with correct Claude Code structure."""
    from generate_settings import generate_hook_config

    # Ensure non-Parzival path (BUG-078: resume|compact only)
    monkeypatch.delenv("PARZIVAL_ENABLED", raising=False)

    hooks_dir = "/test/path/hooks"
    config = generate_hook_config(hooks_dir, "test-project")

    assert "SessionStart" in config["hooks"]
    session_start = config["hooks"]["SessionStart"]
    assert isinstance(session_start, list), "SessionStart must be list"
    assert len(session_start) == 1, "SessionStart must have exactly 1 wrapper"

    # Correct structure: wrapper with 'matcher' + 'hooks' array
    wrapper = session_start[0]
    assert "matcher" in wrapper, "SessionStart must have 'matcher' field"
    assert wrapper["matcher"] == "resume|compact"
    assert "hooks" in wrapper, "SessionStart must have 'hooks' array"
    assert isinstance(wrapper["hooks"], list)
    assert len(wrapper["hooks"]) == 1

    hook = wrapper["hooks"][0]
    assert hook["type"] == "command"
    # V2.0 uses $AI_MEMORY_INSTALL_DIR env var for portability
    assert "$AI_MEMORY_INSTALL_DIR" in hook["command"]
    assert "session_start.py" in hook["command"]


def test_generate_hook_config_session_start_parzival(monkeypatch):
    """BUG-118: Parzival requires startup|resume|compact|clear for Tier 1 Bootstrap."""
    from generate_settings import generate_hook_config

    monkeypatch.setenv("PARZIVAL_ENABLED", "true")

    config = generate_hook_config("/test/path/hooks", "test-project")
    wrapper = config["hooks"]["SessionStart"][0]
    assert wrapper["matcher"] == "startup|resume|compact|clear"


def test_generate_hook_config_post_tool_use():
    """Test PostToolUse hook generation with matcher filtering (correct Claude Code format)."""
    from generate_settings import generate_hook_config

    hooks_dir = "/test/hooks"
    config = generate_hook_config(hooks_dir, "test-project")

    assert "PostToolUse" in config["hooks"]
    post_tool = config["hooks"]["PostToolUse"]
    assert isinstance(post_tool, list)
    # V2.0 has 2 wrappers: Bash (error detection) + Edit/Write/NotebookEdit (capture)
    assert len(post_tool) == 2

    # First wrapper: Bash error detection
    bash_wrapper = post_tool[0]
    assert "matcher" in bash_wrapper
    assert bash_wrapper["matcher"] == "Bash"
    assert "hooks" in bash_wrapper
    assert len(bash_wrapper["hooks"]) == 2  # error_detection + error_pattern_capture

    # Second wrapper: Edit/Write/NotebookEdit capture
    edit_wrapper = post_tool[1]
    assert "matcher" in edit_wrapper, "PostToolUse must have 'matcher' field"
    assert edit_wrapper["matcher"] == "Edit|Write|NotebookEdit"
    assert "hooks" in edit_wrapper, "PostToolUse must have 'hooks' array"
    assert isinstance(edit_wrapper["hooks"], list)
    assert len(edit_wrapper["hooks"]) == 1

    hook = edit_wrapper["hooks"][0]
    assert hook["type"] == "command"
    assert "post_tool_capture.py" in hook["command"]


def test_session_start_excludes_startup_and_clear(monkeypatch):
    """BUG-078: Without Parzival, startup and clear MUST NOT trigger session_start.py."""
    from generate_settings import generate_hook_config

    monkeypatch.delenv("PARZIVAL_ENABLED", raising=False)

    config = generate_hook_config("/test/hooks", "test")
    matcher = config["hooks"]["SessionStart"][0]["matcher"]
    assert (
        "startup" not in matcher
    ), "startup must NOT trigger session_start without Parzival"
    assert (
        "clear" not in matcher
    ), "clear must NOT trigger session_start without Parzival"


def test_session_start_includes_startup_and_clear_with_parzival(monkeypatch):
    """BUG-118: With Parzival, startup and clear MUST trigger session_start.py for Tier 1 Bootstrap."""
    from generate_settings import generate_hook_config

    monkeypatch.setenv("PARZIVAL_ENABLED", "true")

    config = generate_hook_config("/test/hooks", "test")
    matcher = config["hooks"]["SessionStart"][0]["matcher"]
    assert "startup" in matcher, "startup MUST trigger session_start with Parzival"
    assert "clear" in matcher, "clear MUST trigger session_start with Parzival"


def test_generate_hook_config_stop():
    """Test Stop hook generation with correct Claude Code structure."""
    from generate_settings import generate_hook_config

    hooks_dir = "/test/hooks"
    config = generate_hook_config(hooks_dir, "test-project")

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
    # V2.0 uses agent_response_capture.py (renamed from session_stop.py)
    assert "agent_response_capture.py" in hook["command"]


def test_generate_hook_config_absolute_paths():
    """Test that $AI_MEMORY_INSTALL_DIR env var is used for portability."""
    from generate_settings import generate_hook_config

    hooks_dir = "/absolute/path/to/hooks"
    config = generate_hook_config(hooks_dir, "test-project")

    # V2.0 uses $AI_MEMORY_INSTALL_DIR env var for portability
    # Verify env section contains the install dir
    assert "env" in config
    assert "AI_MEMORY_INSTALL_DIR" in config["env"]

    # Check all commands use $AI_MEMORY_INSTALL_DIR (in nested 'hooks' arrays)
    for hook_type, wrappers in config["hooks"].items():
        for wrapper in wrappers:
            assert "hooks" in wrapper, f"{hook_type} must have 'hooks' array"
            for hook in wrapper["hooks"]:
                assert "$AI_MEMORY_INSTALL_DIR" in hook["command"]


def test_main_creates_file(tmp_path):
    """Test main() function creates settings.json file."""
    from generate_settings import main

    output_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    # Override sys.argv - requires 3 args: output_path, hooks_dir, project_name
    sys.argv = ["generate_settings.py", str(output_file), hooks_dir, "test-project"]

    main()

    assert output_file.exists(), "settings.json must be created"


def test_main_creates_parent_directories(tmp_path):
    """Test main() creates parent directories if needed."""
    from generate_settings import main

    output_file = tmp_path / "nested" / "dir" / "settings.json"
    hooks_dir = "/test/hooks"

    sys.argv = ["generate_settings.py", str(output_file), hooks_dir, "test-project"]
    main()

    assert output_file.exists()
    assert output_file.parent.exists()


def test_main_writes_valid_json(tmp_path):
    """Test main() writes valid JSON with correct structure."""
    from generate_settings import main

    output_file = tmp_path / "settings.json"
    hooks_dir = "/test/hooks"

    sys.argv = ["generate_settings.py", str(output_file), hooks_dir, "test-project"]
    main()

    # Parse JSON to verify it's valid
    with open(output_file) as f:
        config = json.load(f)

    assert "hooks" in config
    # V2.0 has 6 hook types: SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PreCompact, Stop
    assert len(config["hooks"]) == 6


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

    sys.argv = ["generate_settings.py", str(output_file), hooks_dir, "test-project"]
    main()

    # Read raw content
    content = output_file.read_text()

    # Check for indentation (indent=2)
    assert '  "hooks"' in content, "JSON must be indented"
    assert '    "SessionStart"' in content
    # Verify correct structure with nested 'hooks' arrays
    assert '"matcher"' in content, "PostToolUse must have matcher field"
