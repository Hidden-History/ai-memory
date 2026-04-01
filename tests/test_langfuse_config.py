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
