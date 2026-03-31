#!/usr/bin/env python3
"""
Unit tests for scripts/recover_hook_guards.py

Covers the P3a-modified behaviour:
  - BUG-078: Stale trigger stripping via normalize_matcher (hook_utils import)
  - BUG-066: Old-style unguarded commands upgraded to guard pattern
"""


def _make_session_start_wrapper(matcher: str, script: str = "session_start.py") -> dict:
    """Build a minimal SessionStart wrapper dict for test input."""
    from hook_utils import _hook_cmd

    return {
        "matcher": matcher,
        "hooks": [{"type": "command", "command": _hook_cmd(script)}],
    }


def _make_unguarded_wrapper(script: str = "session_start.py") -> dict:
    """Build a wrapper with an old-style unguarded command."""
    return {
        "matcher": "resume|compact",
        "hooks": [
            {
                "type": "command",
                "command": f'python3 "$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/{script}"',
            }
        ],
    }


class TestProcessSettingsMatcherStripping:
    """BUG-078: stale trigger stripping via normalize_matcher (hook_utils)."""

    def test_strips_startup_and_clear_leaves_resume_compact(self):
        """'startup|resume|compact|clear' → 'resume|compact'."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {
                "SessionStart": [
                    _make_session_start_wrapper("startup|resume|compact|clear")
                ]
            }
        }
        modified, _guarded, matchers_fixed = process_settings(settings)
        assert matchers_fixed == 1
        assert modified["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_strips_startup_and_clear_only(self):
        """'startup|clear' → 'resume|compact' (fallback when all parts stale)."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {"SessionStart": [_make_session_start_wrapper("startup|clear")]}
        }
        modified, _guarded, matchers_fixed = process_settings(settings)
        assert matchers_fixed == 1
        assert modified["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_already_clean_matcher_unchanged(self):
        """'resume|compact' has no stale triggers → unchanged, matchers_fixed=0."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {"SessionStart": [_make_session_start_wrapper("resume|compact")]}
        }
        modified, _guarded, matchers_fixed = process_settings(settings)
        assert matchers_fixed == 0
        assert modified["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"

    def test_non_session_start_hooks_untouched(self):
        """Hooks under other event types are not matcher-modified."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "startup|clear",
                        "hooks": [{"type": "command", "command": "echo hi || true"}],
                    }
                ]
            }
        }
        modified, _guarded, matchers_fixed = process_settings(settings)
        assert matchers_fixed == 0
        # matcher untouched for non-SessionStart
        assert modified["hooks"]["PostToolUse"][0]["matcher"] == "startup|clear"

    def test_strips_only_startup_leaves_resume_compact(self):
        """'startup|resume|compact' → 'resume|compact'."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {
                "SessionStart": [_make_session_start_wrapper("startup|resume|compact")]
            }
        }
        modified, _guarded, matchers_fixed = process_settings(settings)
        assert matchers_fixed == 1
        assert modified["hooks"]["SessionStart"][0]["matcher"] == "resume|compact"


class TestProcessSettingsCommandGuarding:
    """BUG-066: old unguarded commands are upgraded to guard pattern."""

    def test_unguarded_command_gets_guard(self):
        """Old python3 command without '|| true' is replaced with guarded form."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {"SessionStart": [_make_unguarded_wrapper("session_start.py")]}
        }
        modified, commands_guarded, _fixed = process_settings(settings)
        assert commands_guarded == 1
        cmd = modified["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        assert "|| true" in cmd
        assert "session_start.py" in cmd

    def test_already_guarded_command_unchanged(self):
        """Command already containing '|| true' is not counted or changed."""
        from hook_utils import _hook_cmd
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "resume|compact",
                        "hooks": [
                            {
                                "type": "command",
                                "command": _hook_cmd("session_start.py"),
                            }
                        ],
                    }
                ]
            }
        }
        _modified, commands_guarded, _fixed = process_settings(settings)
        assert commands_guarded == 0

    def test_original_not_mutated(self):
        """process_settings deep-copies — original dict is never mutated."""
        from recover_hook_guards import process_settings

        original = {
            "hooks": {
                "SessionStart": [
                    _make_session_start_wrapper("startup|resume|compact|clear")
                ]
            }
        }
        import copy

        snapshot = copy.deepcopy(original)
        process_settings(original)
        assert original == snapshot

    def test_non_ai_memory_session_start_matcher_unchanged(self):
        """SessionStart hooks without session_start.py should not have matchers modified."""
        from recover_hook_guards import process_settings

        settings = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup|resume",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "some_other_hook.py",
                            }
                        ],
                    }
                ]
            }
        }
        modified, _guarded, matchers_fixed = process_settings(settings)
        assert matchers_fixed == 0
        assert modified["hooks"]["SessionStart"][0]["matcher"] == "startup|resume"
