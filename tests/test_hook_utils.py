#!/usr/bin/env python3
"""
Unit tests for scripts/hook_utils.py

Tests shared utilities extracted in TD-338:
  - _hook_cmd(): guard command generation
  - get_langfuse_env_section(): conditional Langfuse env var block
"""


class TestHookCmd:
    """Test _hook_cmd() output format and script path interpolation."""

    def test_output_format_exact(self):
        """Verify complete output matches expected guard pattern."""
        from hook_utils import _hook_cmd

        result = _hook_cmd("session_start.py")
        expected = (
            '[ -f "$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/session_start.py" ] && '
            '"$AI_MEMORY_INSTALL_DIR/.venv/bin/python" '
            '"$AI_MEMORY_INSTALL_DIR/.claude/hooks/scripts/session_start.py" || true'
        )
        assert result == expected

    def test_guard_pattern_structure(self):
        """Verify command uses [ -f ... ] && ... || true guard pattern."""
        from hook_utils import _hook_cmd

        result = _hook_cmd("my_hook.py")
        assert result.startswith('[ -f "')
        assert "] &&" in result
        assert result.endswith("|| true")

    def test_script_path_interpolation(self):
        """Verify script name is correctly embedded in the hook path."""
        from hook_utils import _hook_cmd

        result = _hook_cmd("error_detection.py")
        assert ".claude/hooks/scripts/error_detection.py" in result

    def test_python_interpreter_uses_venv(self):
        """Verify Python interpreter path references .venv, not system python."""
        from hook_utils import _hook_cmd

        result = _hook_cmd("session_start.py")
        assert "$AI_MEMORY_INSTALL_DIR/.venv/bin/python" in result

    def test_uses_install_dir_env_var(self):
        """Verify paths use $AI_MEMORY_INSTALL_DIR, not hardcoded paths."""
        from hook_utils import _hook_cmd

        result = _hook_cmd("any_script.py")
        assert "$AI_MEMORY_INSTALL_DIR" in result

    def test_script_name_appears_twice(self):
        """Script name appears in both the -f check and the execution path."""
        from hook_utils import _hook_cmd

        result = _hook_cmd("pre_compact_save.py")
        assert result.count("pre_compact_save.py") == 2


class TestGetLangfuseEnvSection:
    """Test get_langfuse_env_section() with LANGFUSE_ENABLED variants."""

    def test_returns_empty_when_unset(self, monkeypatch):
        """Returns empty dict when LANGFUSE_ENABLED is not set."""
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert result == {}

    def test_returns_empty_when_false(self, monkeypatch):
        """Returns empty dict when LANGFUSE_ENABLED=false."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert result == {}

    def test_returns_empty_when_uppercase_false(self, monkeypatch):
        """Returns empty dict when LANGFUSE_ENABLED=FALSE (case-insensitive check)."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "FALSE")
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert result == {}

    def test_returns_six_keys_when_enabled(self, monkeypatch):
        """Returns dict with exactly 6 keys when LANGFUSE_ENABLED=true."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert len(result) == 6
        expected_keys = {
            "LANGFUSE_ENABLED",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_BASE_URL",
            "LANGFUSE_TRACE_HOOKS",
            "LANGFUSE_TRACE_SESSIONS",
        }
        assert set(result.keys()) == expected_keys

    def test_reads_env_vars_when_enabled(self, monkeypatch):
        """Env var values are read from environment when LANGFUSE_ENABLED=true."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-abc123")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-xyz789")
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://custom:23100")
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert result["LANGFUSE_PUBLIC_KEY"] == "pk-abc123"
        assert result["LANGFUSE_SECRET_KEY"] == "sk-xyz789"
        assert result["LANGFUSE_BASE_URL"] == "http://custom:23100"

    def test_default_base_url_when_not_set(self, monkeypatch):
        """LANGFUSE_BASE_URL defaults to localhost:23100 when not set."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert result["LANGFUSE_BASE_URL"] == "http://localhost:23100"

    def test_enabled_value_is_string_true(self, monkeypatch):
        """LANGFUSE_ENABLED in returned dict is the string 'true', not a bool."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        from hook_utils import get_langfuse_env_section

        result = get_langfuse_env_section()
        assert result["LANGFUSE_ENABLED"] == "true"


class TestNormalizeMatcher:
    """Test normalize_matcher() stale trigger stripping."""

    def test_strips_startup(self):
        """'startup|resume|compact' → 'resume|compact'."""
        from hook_utils import normalize_matcher

        assert normalize_matcher("startup|resume|compact") == "resume|compact"

    def test_strips_clear(self):
        """'resume|compact|clear' → 'resume|compact'."""
        from hook_utils import normalize_matcher

        assert normalize_matcher("resume|compact|clear") == "resume|compact"

    def test_strips_both(self):
        """'startup|resume|compact|clear' → 'resume|compact'."""
        from hook_utils import normalize_matcher

        assert normalize_matcher("startup|resume|compact|clear") == "resume|compact"

    def test_fallback_when_all_stale(self):
        """'startup|clear' → 'resume|compact' (all parts stale, use fallback)."""
        from hook_utils import normalize_matcher

        assert normalize_matcher("startup|clear") == "resume|compact"

    def test_already_clean(self):
        """'resume|compact' has no stale triggers → unchanged."""
        from hook_utils import normalize_matcher

        assert normalize_matcher("resume|compact") == "resume|compact"

    def test_custom_stale_and_fallback(self):
        """stale and fallback params override defaults."""
        from hook_utils import normalize_matcher

        result = normalize_matcher(
            "foo|bar|baz",
            stale=frozenset({"foo", "baz"}),
            fallback="default",
        )
        assert result == "bar"

        result_all_stale = normalize_matcher(
            "foo|baz",
            stale=frozenset({"foo", "baz"}),
            fallback="default",
        )
        assert result_all_stale == "default"
