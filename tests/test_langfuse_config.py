"""Unit tests for memory.langfuse_config — SPEC-020 §9.1 client factory tests."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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

    @patch("memory.langfuse_config.Langfuse", create=True)
    def test_enabled_with_keys_returns_client(self, mock_langfuse_cls, monkeypatch):
        """Valid config → returns Langfuse instance."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test123")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test456")
        mock_instance = MagicMock()
        mock_langfuse_cls.return_value = mock_instance

        with patch.dict("sys.modules", {"langfuse": MagicMock(Langfuse=mock_langfuse_cls)}):
            reset_langfuse_client()
            client = get_langfuse_client()

        assert client is not None

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

        mock_langfuse = MagicMock()
        with patch("memory.langfuse_config.Langfuse", return_value=mock_langfuse, create=True), \
             patch.dict("sys.modules", {"langfuse": MagicMock(Langfuse=MagicMock(return_value=mock_langfuse))}):
            reset_langfuse_client()
            client1 = get_langfuse_client()
            client2 = get_langfuse_client()

        assert client1 is client2


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
