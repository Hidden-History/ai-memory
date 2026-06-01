"""Unit tests for memory.langfuse_config — SPEC-020 §9.1 client factory tests."""

from unittest.mock import MagicMock, patch

from memory.langfuse_config import (
    get_langfuse_client,
    is_hook_tracing_enabled,
    is_langfuse_enabled,
    reset_langfuse_client,
)


class TestGetLangfuseClient:
    """Tests for get_langfuse_client() factory function."""

    def setup_method(self):
        reset_langfuse_client()

    def teardown_method(self):
        reset_langfuse_client()

    def test_disabled_returns_none(self, monkeypatch):
        """LANGFUSE_ENABLED=false → returns None."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        assert get_langfuse_client() is None

    def test_disabled_by_default(self, monkeypatch):
        """When LANGFUSE_ENABLED not set, returns None."""
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        assert get_langfuse_client() is None

    def test_enabled_with_keys_returns_client(self, monkeypatch):
        """Valid config → returns Langfuse client via Langfuse() constructor (TD-372)."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test123")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test456")
        mock_client = MagicMock()
        mock_langfuse_cls = MagicMock(return_value=mock_client)
        mock_span_filter = MagicMock()
        mock_span_filter.is_default_export_span = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "langfuse": MagicMock(Langfuse=mock_langfuse_cls),
                "langfuse.span_filter": mock_span_filter,
            },
        ):
            reset_langfuse_client()
            client = get_langfuse_client()

        assert client is mock_client
        mock_langfuse_cls.assert_called_once()

    def test_enabled_without_keys_returns_none(self, monkeypatch):
        """Enabled but no keys → returns None (defensive, not raise)."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
        result = get_langfuse_client()
        assert result is None

    def test_singleton_returns_same_instance(self, monkeypatch):
        """Multiple calls return same cached instance."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

        mock_client = MagicMock()
        mock_langfuse_cls = MagicMock(return_value=mock_client)
        mock_span_filter = MagicMock()
        mock_span_filter.is_default_export_span = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "langfuse": MagicMock(Langfuse=mock_langfuse_cls),
                "langfuse.span_filter": mock_span_filter,
            },
        ):
            reset_langfuse_client()
            client1 = get_langfuse_client()
            client2 = get_langfuse_client()

        assert client1 is mock_client
        assert client1 is client2
        mock_langfuse_cls.assert_called_once()

    def test_import_error_returns_none(self, monkeypatch):
        """When langfuse package is not installed, returns None gracefully."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

        with patch.dict("sys.modules", {"langfuse": None}):
            reset_langfuse_client()
            client = get_langfuse_client()

        assert client is None


class TestKillSwitchHelpers:
    """Tests for is_langfuse_enabled() and is_hook_tracing_enabled()."""

    def test_is_langfuse_enabled_true(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        assert is_langfuse_enabled() is True

    def test_is_langfuse_enabled_false(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        assert is_langfuse_enabled() is False

    def test_is_langfuse_enabled_default(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        assert is_langfuse_enabled() is False

    def test_is_hook_tracing_enabled_both_true(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_TRACE_HOOKS", "true")
        assert is_hook_tracing_enabled() is True

    def test_is_hook_tracing_enabled_hooks_false(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_TRACE_HOOKS", "false")
        assert is_hook_tracing_enabled() is False

    def test_is_hook_tracing_enabled_langfuse_disabled(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        monkeypatch.setenv("LANGFUSE_TRACE_HOOKS", "true")
        assert is_hook_tracing_enabled() is False


class TestTracingEnvironmentValidation:
    """G4 (BP-169): LANGFUSE_TRACING_ENVIRONMENT validation + wiring."""

    def setup_method(self):
        reset_langfuse_client()

    def teardown_method(self):
        reset_langfuse_client()

    def test_validate_accepts_valid_values(self):
        from memory.langfuse_config import validate_tracing_environment as v

        assert v("testv2") == "testv2"
        assert v("prod-install_1") == "prod-install_1"
        assert v("a" * 40) == "a" * 40

    def test_validate_rejects_invalid_values(self):
        from memory.langfuse_config import validate_tracing_environment as v

        assert v("langfuse-reserved") is None  # negative lookahead on "langfuse"
        assert v("UPPER") is None
        assert v("has space") is None
        assert v("a" * 41) is None  # >40 chars
        assert v("") is None
        assert v(None) is None

    def _enabled_env(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    def _mock_langfuse(self):
        mock_span_filter = MagicMock()
        mock_span_filter.is_default_export_span = MagicMock()
        return patch.dict(
            "sys.modules",
            {
                "langfuse": MagicMock(Langfuse=MagicMock(return_value=MagicMock())),
                "langfuse.span_filter": mock_span_filter,
            },
        )

    def test_invalid_environment_is_dropped(self, monkeypatch):
        """An invalid LANGFUSE_TRACING_ENVIRONMENT is removed so the SDK ignores it."""
        import os

        self._enabled_env(monkeypatch)
        monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "Invalid Env!")
        with self._mock_langfuse():
            reset_langfuse_client()
            get_langfuse_client()
        assert "LANGFUSE_TRACING_ENVIRONMENT" not in os.environ

    def test_valid_environment_is_preserved(self, monkeypatch):
        """A valid LANGFUSE_TRACING_ENVIRONMENT is left in env for the SDK to read."""
        import os

        self._enabled_env(monkeypatch)
        monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "testv2")
        with self._mock_langfuse():
            reset_langfuse_client()
            get_langfuse_client()
        assert os.environ.get("LANGFUSE_TRACING_ENVIRONMENT") == "testv2"

    def test_no_hardcoded_environment_when_unset(self, monkeypatch):
        """When unset, the config does NOT inject any environment value."""
        import os

        self._enabled_env(monkeypatch)
        monkeypatch.delenv("LANGFUSE_TRACING_ENVIRONMENT", raising=False)
        with self._mock_langfuse():
            reset_langfuse_client()
            get_langfuse_client()
        assert "LANGFUSE_TRACING_ENVIRONMENT" not in os.environ
