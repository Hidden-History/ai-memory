"""Tests for v2.0.7 Langfuse config fields (SPEC-019 §5.2).

Tests Langfuse configuration fields, defaults, validation, and validator
behaviour (missing keys when enabled = error).

Uses _env_file=None to avoid loading .env during tests.
Uses monkeypatch for env var management.
"""

import logging

import pytest
from pydantic import SecretStr, ValidationError

from src.memory.config import MemoryConfig, get_config, reset_config


class TestLangfuseDefaults:
    """Test that all Langfuse fields have correct defaults when disabled."""

    def test_langfuse_defaults_disabled(self):
        """Verify default state: enabled=False, all fields have defaults."""
        config = MemoryConfig(_env_file=None)
        assert config.langfuse_enabled is False
        assert config.langfuse_public_key == ""
        assert config.langfuse_secret_key.get_secret_value() == ""
        assert config.langfuse_base_url == "http://localhost:23100"
        assert config.langfuse_flush_interval == 5
        assert config.langfuse_trace_hooks is True
        assert config.langfuse_trace_sessions is True
        assert config.langfuse_retention_days == 90

    def test_langfuse_base_url_default(self):
        """Default URL is http://localhost:23100."""
        config = MemoryConfig(_env_file=None)
        assert config.langfuse_base_url == "http://localhost:23100"

    def test_langfuse_trace_flags_default_true(self):
        """Both trace flags default to True."""
        config = MemoryConfig(_env_file=None)
        assert config.langfuse_trace_hooks is True
        assert config.langfuse_trace_sessions is True


class TestLangfuseValidation:
    """Test validator logic for Langfuse configuration."""

    def test_langfuse_enabled_missing_keys_warns(self, caplog):
        """When LANGFUSE_ENABLED=true but keys empty, config loads with warning (BUG-132)."""
        with caplog.at_level(logging.WARNING):
            config = MemoryConfig(
                _env_file=None,
                langfuse_enabled=True,
                langfuse_public_key="",
                langfuse_secret_key=SecretStr(""),
            )
        assert config.langfuse_enabled is True
        assert "API keys not configured" in caplog.text

    def test_langfuse_enabled_missing_public_key_warns(self, caplog):
        """When enabled=true and only secret key provided, warning logged (BUG-132)."""
        with caplog.at_level(logging.WARNING):
            config = MemoryConfig(
                _env_file=None,
                langfuse_enabled=True,
                langfuse_public_key="",
                langfuse_secret_key=SecretStr("sk-lf-test"),
            )
        assert config.langfuse_enabled is True
        assert "API keys not configured" in caplog.text

    def test_langfuse_enabled_missing_secret_key_warns(self, caplog):
        """When enabled=true and only public key provided, warning logged (BUG-132)."""
        with caplog.at_level(logging.WARNING):
            config = MemoryConfig(
                _env_file=None,
                langfuse_enabled=True,
                langfuse_public_key="pk-lf-test",
                langfuse_secret_key=SecretStr(""),
            )
        assert config.langfuse_enabled is True
        assert "API keys not configured" in caplog.text

    def test_langfuse_enabled_with_keys(self):
        """When enabled=true and both keys provided, config loads successfully."""
        config = MemoryConfig(
            _env_file=None,
            langfuse_enabled=True,
            langfuse_public_key="pk-lf-abc123",
            langfuse_secret_key=SecretStr("sk-lf-xyz789"),
        )
        assert config.langfuse_enabled is True
        assert config.langfuse_public_key == "pk-lf-abc123"
        assert config.langfuse_secret_key.get_secret_value() == "sk-lf-xyz789"

    def test_langfuse_disabled_ignores_keys(self):
        """When disabled, missing keys don't cause errors."""
        config = MemoryConfig(
            _env_file=None,
            langfuse_enabled=False,
            langfuse_public_key="",
            langfuse_secret_key=SecretStr(""),
        )
        assert config.langfuse_enabled is False


class TestLangfuseBounds:
    """Test ge/le bounds on Langfuse numeric fields."""

    def test_langfuse_retention_days_bounds(self):
        """Test ge=7, le=365 validation on retention_days."""
        # Valid boundaries
        assert (
            MemoryConfig(
                _env_file=None, langfuse_retention_days=7
            ).langfuse_retention_days
            == 7
        )
        assert (
            MemoryConfig(
                _env_file=None, langfuse_retention_days=365
            ).langfuse_retention_days
            == 365
        )
        assert (
            MemoryConfig(
                _env_file=None, langfuse_retention_days=90
            ).langfuse_retention_days
            == 90
        )

        # Below minimum
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, langfuse_retention_days=6)

        # Above maximum
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, langfuse_retention_days=366)

    def test_langfuse_flush_interval_bounds(self):
        """Test ge=1, le=300 validation on flush_interval."""
        # Valid boundaries
        assert (
            MemoryConfig(
                _env_file=None, langfuse_flush_interval=1
            ).langfuse_flush_interval
            == 1
        )
        assert (
            MemoryConfig(
                _env_file=None, langfuse_flush_interval=300
            ).langfuse_flush_interval
            == 300
        )
        assert (
            MemoryConfig(
                _env_file=None, langfuse_flush_interval=5
            ).langfuse_flush_interval
            == 5
        )

        # Below minimum
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, langfuse_flush_interval=0)

        # Above maximum
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, langfuse_flush_interval=301)


class TestLangfuseBufferMaxMbBounds:
    """Test ge/le bounds on langfuse_trace_buffer_max_mb field."""

    def test_langfuse_buffer_max_mb_bounds(self):
        """Test ge=10, le=1000 validation on langfuse_trace_buffer_max_mb."""
        # Valid boundaries
        assert (
            MemoryConfig(
                _env_file=None, langfuse_trace_buffer_max_mb=10
            ).langfuse_trace_buffer_max_mb
            == 10
        )
        assert (
            MemoryConfig(
                _env_file=None, langfuse_trace_buffer_max_mb=1000
            ).langfuse_trace_buffer_max_mb
            == 1000
        )
        assert (
            MemoryConfig(
                _env_file=None, langfuse_trace_buffer_max_mb=100
            ).langfuse_trace_buffer_max_mb
            == 100
        )

        # Below minimum
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, langfuse_trace_buffer_max_mb=9)

        # Above maximum
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, langfuse_trace_buffer_max_mb=1001)


class TestLangfuseEnvOverrides:
    """Test Langfuse fields can be overridden via environment variables."""

    def test_langfuse_enabled_env_override(self, monkeypatch):
        """LANGFUSE_ENABLED env var overrides default."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "true")
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-env-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-env-test")
        reset_config()
        config = get_config()
        assert config.langfuse_enabled is True
        assert config.langfuse_public_key == "pk-lf-env-test"
        assert config.langfuse_secret_key.get_secret_value() == "sk-lf-env-test"

    def test_langfuse_base_url_env_override(self, monkeypatch):
        """LANGFUSE_BASE_URL env var overrides default."""
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://langfuse.example.com:23100")
        reset_config()
        config = get_config()
        assert config.langfuse_base_url == "http://langfuse.example.com:23100"

    def test_langfuse_retention_days_env_override(self, monkeypatch):
        """LANGFUSE_RETENTION_DAYS env var overrides default."""
        monkeypatch.setenv("LANGFUSE_RETENTION_DAYS", "30")
        reset_config()
        config = get_config()
        assert config.langfuse_retention_days == 30

    def test_langfuse_flush_interval_env_override(self, monkeypatch):
        """LANGFUSE_FLUSH_INTERVAL env var overrides default."""
        monkeypatch.setenv("LANGFUSE_FLUSH_INTERVAL", "10")
        reset_config()
        config = get_config()
        assert config.langfuse_flush_interval == 10

    def test_langfuse_trace_flags_env_override(self, monkeypatch):
        """LANGFUSE_TRACE_HOOKS and LANGFUSE_TRACE_SESSIONS env vars override defaults."""
        monkeypatch.setenv("LANGFUSE_TRACE_HOOKS", "false")
        monkeypatch.setenv("LANGFUSE_TRACE_SESSIONS", "false")
        reset_config()
        config = get_config()
        assert config.langfuse_trace_hooks is False
        assert config.langfuse_trace_sessions is False

    def teardown_method(self):
        """Clear config cache after each test."""
        reset_config()


class TestLangfuseFieldDescriptions:
    """Verify all Langfuse fields have description parameters."""

    def test_all_langfuse_fields_have_descriptions(self):
        """All v2.0.7 Langfuse fields have description in their Field definition."""
        langfuse_fields = [
            "langfuse_enabled",
            "langfuse_public_key",
            "langfuse_secret_key",
            "langfuse_base_url",
            "langfuse_flush_interval",
            "langfuse_trace_hooks",
            "langfuse_trace_sessions",
            "langfuse_retention_days",
            "langfuse_trace_buffer_max_mb",
        ]
        for field_name in langfuse_fields:
            field_info = MemoryConfig.model_fields[field_name]
            assert (
                field_info.description is not None
            ), f"Field '{field_name}' missing description"
            assert (
                len(field_info.description) > 0
            ), f"Field '{field_name}' has empty description"


class TestLangfuseNonRegression:
    """Verify existing fields are unaffected by Langfuse additions."""

    def test_existing_fields_unchanged(self):
        """All pre-existing fields remain accessible and correctly typed."""
        config = MemoryConfig(_env_file=None)
        assert isinstance(config.similarity_threshold, float)
        assert isinstance(config.qdrant_port, int)
        assert isinstance(config.embedding_port, int)
        assert isinstance(config.parzival_enabled, bool)
        assert isinstance(config.decay_enabled, bool)

    def test_helper_methods_still_work(self):
        """Existing helper methods still return correct URLs."""
        config = MemoryConfig(_env_file=None)
        assert config.get_qdrant_url() == "http://localhost:26350"
        assert config.get_embedding_url() == "http://localhost:28080"
        assert config.get_monitoring_url() == "http://localhost:28000"
