"""Tests for v2.0.6 Foundation config fields (SPEC-002).

Tests decay scoring fields, audit_dir, auto_update_enabled,
decay_type_overrides validator, and get_decay_type_overrides() helper.

Uses monkeypatch for env var management (review item M-7).
Uses _env_file=None to avoid loading .env during tests (review item L-4).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.memory.config import MemoryConfig, get_config, reset_config


class TestDecayFieldDefaults:
    """Test decay field defaults match SPEC-001 Section 4.3."""

    def test_decay_fields_defaults(self):
        """All decay fields have correct defaults from Section 11."""
        config = MemoryConfig(_env_file=None)
        assert config.decay_enabled is True
        assert config.decay_semantic_weight == 0.7
        assert config.decay_half_life_code_patterns == 14
        assert config.decay_half_life_discussions == 21
        assert config.decay_half_life_conventions == 60
        assert config.decay_half_life_jira_data == 30
        assert config.decay_min_score == 0.1

    def test_decay_enabled_default_true(self):
        """Decay is enabled by default."""
        config = MemoryConfig(_env_file=None)
        assert config.decay_enabled is True

    def test_decay_type_overrides_default(self):
        """Type overrides have the full default string."""
        config = MemoryConfig(_env_file=None)
        overrides = config.get_decay_type_overrides()
        assert len(overrides) == 13
        assert overrides["github_ci_result"] == 7
        assert overrides["github_code_blob"] == 14
        assert overrides["github_commit"] == 14
        assert overrides["conversation"] == 21
        assert overrides["session_summary"] == 21
        assert overrides["github_issue"] == 30
        assert overrides["github_pr"] == 30
        assert overrides["jira_issue"] == 30
        assert overrides["agent_memory"] == 30
        assert overrides["agent_handoff"] == 30
        assert overrides["guideline"] == 60
        assert overrides["rule"] == 60
        assert overrides["architecture_decision"] == 90


class TestDecayFieldValidation:
    """Test decay field bounds and validation."""

    def test_decay_semantic_weight_bounds(self):
        """Semantic weight must be between 0.0 and 1.0."""
        # Valid boundaries
        assert MemoryConfig(_env_file=None, decay_semantic_weight=0.0).decay_semantic_weight == 0.0
        assert MemoryConfig(_env_file=None, decay_semantic_weight=1.0).decay_semantic_weight == 1.0

        # Out of range
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_semantic_weight=1.5)
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_semantic_weight=-0.1)

    def test_decay_half_life_positive(self):
        """Half-life must be >= 1 day."""
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_half_life_code_patterns=0)
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_half_life_discussions=0)
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_half_life_conventions=0)
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_half_life_jira_data=0)

    def test_decay_half_life_minimum(self):
        """Half-life of 1 day is valid."""
        config = MemoryConfig(
            _env_file=None,
            decay_half_life_code_patterns=1,
            decay_half_life_discussions=1,
            decay_half_life_conventions=1,
            decay_half_life_jira_data=1,
        )
        assert config.decay_half_life_code_patterns == 1
        assert config.decay_half_life_discussions == 1
        assert config.decay_half_life_conventions == 1
        assert config.decay_half_life_jira_data == 1

    def test_decay_min_score_bounds(self):
        """Min score must be between 0.0 and 1.0."""
        assert MemoryConfig(_env_file=None, decay_min_score=0.0).decay_min_score == 0.0
        assert MemoryConfig(_env_file=None, decay_min_score=1.0).decay_min_score == 1.0
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_min_score=1.1)
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_min_score=-0.1)


class TestDecayTypeOverrides:
    """Test decay_type_overrides parsing and validation."""

    def test_type_overrides_valid_format(self):
        """Valid type override format parses correctly."""
        config = MemoryConfig(_env_file=None, decay_type_overrides="foo:7,bar:14")
        overrides = config.get_decay_type_overrides()
        assert overrides == {"foo": 7, "bar": 14}

    def test_type_overrides_invalid_format(self):
        """Invalid type override format raises ValidationError."""
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_type_overrides="not_valid")

    def test_type_overrides_invalid_non_numeric_days(self):
        """Non-numeric days value raises ValidationError."""
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_type_overrides="foo:abc")

    def test_type_overrides_invalid_zero_days(self):
        """Zero days raises ValidationError (L-3: days must be >= 1)."""
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_type_overrides="foo:0")

    def test_type_overrides_empty_string(self):
        """Empty string returns empty dict."""
        config = MemoryConfig(_env_file=None, decay_type_overrides="")
        assert config.get_decay_type_overrides() == {}

    def test_type_overrides_single_entry(self):
        """Single entry parses correctly."""
        config = MemoryConfig(_env_file=None, decay_type_overrides="test:42")
        assert config.get_decay_type_overrides() == {"test": 42}

    def test_type_overrides_whitespace_handling(self):
        """Whitespace around entries is handled correctly."""
        config = MemoryConfig(_env_file=None, decay_type_overrides=" foo : 7 , bar : 14 ")
        overrides = config.get_decay_type_overrides()
        assert overrides == {"foo": 7, "bar": 14}

    def test_type_overrides_empty_type_name(self):
        """Empty type name is rejected."""
        with pytest.raises(ValidationError):
            MemoryConfig(_env_file=None, decay_type_overrides=":7")

    def test_type_overrides_trailing_comma(self):
        """Trailing comma is tolerated."""
        config = MemoryConfig(_env_file=None, decay_type_overrides="foo:7,bar:14,")
        overrides = config.get_decay_type_overrides()
        assert overrides == {"foo": 7, "bar": 14}


class TestAuditDir:
    """Test audit_dir field."""

    def test_audit_dir_default(self):
        """Audit dir defaults to .audit relative path."""
        config = MemoryConfig(_env_file=None)
        assert config.audit_dir == Path(".audit")

    def test_audit_dir_expand_user(self, monkeypatch):
        """Audit dir expands ~ in path."""
        monkeypatch.setenv("AUDIT_DIR", "~/custom-audit")
        reset_config()
        config = get_config()
        assert str(config.audit_dir).startswith("/")  # Expanded
        assert "~" not in str(config.audit_dir)

    def test_audit_dir_custom_path(self):
        """Audit dir accepts custom path."""
        config = MemoryConfig(_env_file=None, audit_dir=Path("/tmp/test-audit"))
        assert config.audit_dir == Path("/tmp/test-audit")


class TestAutoUpdateEnabled:
    """Test auto_update_enabled field."""

    def test_auto_update_default(self):
        """Auto-update kill switch defaults to enabled."""
        config = MemoryConfig(_env_file=None)
        assert config.auto_update_enabled is True

    def test_auto_update_env_override(self, monkeypatch):
        """Auto-update can be disabled via env var."""
        monkeypatch.setenv("AUTO_UPDATE_ENABLED", "false")
        reset_config()
        config = get_config()
        assert config.auto_update_enabled is False

    def test_auto_update_explicit_false(self):
        """Auto-update can be set to False explicitly."""
        config = MemoryConfig(_env_file=None, auto_update_enabled=False)
        assert config.auto_update_enabled is False


class TestDecayEnvOverrides:
    """Test decay fields can be overridden via environment variables."""

    def test_decay_enabled_env_override(self, monkeypatch):
        """Decay can be disabled via env var."""
        monkeypatch.setenv("DECAY_ENABLED", "false")
        reset_config()
        config = get_config()
        assert config.decay_enabled is False

    def test_decay_semantic_weight_env_override(self, monkeypatch):
        """Semantic weight overridden via env var."""
        monkeypatch.setenv("DECAY_SEMANTIC_WEIGHT", "0.5")
        reset_config()
        config = get_config()
        assert config.decay_semantic_weight == 0.5

    def test_decay_half_life_env_override(self, monkeypatch):
        """Half-life overridden via env var."""
        monkeypatch.setenv("DECAY_HALF_LIFE_CODE_PATTERNS", "7")
        reset_config()
        config = get_config()
        assert config.decay_half_life_code_patterns == 7

    def test_decay_type_overrides_env_override(self, monkeypatch):
        """Type overrides can be set via env var."""
        monkeypatch.setenv("DECAY_TYPE_OVERRIDES", "custom:5,other:10")
        reset_config()
        config = get_config()
        overrides = config.get_decay_type_overrides()
        assert overrides == {"custom": 5, "other": 10}


class TestFrozenAndSingleton:
    """Test frozen model and singleton behavior with new fields."""

    def test_frozen_config(self):
        """Config is immutable after creation."""
        config = MemoryConfig(_env_file=None)
        with pytest.raises(ValidationError):
            config.decay_enabled = False  # type: ignore

    def test_frozen_auto_update(self):
        """Auto-update field is immutable."""
        config = MemoryConfig(_env_file=None)
        with pytest.raises(ValidationError):
            config.auto_update_enabled = False  # type: ignore

    def test_singleton_with_new_fields(self, monkeypatch):
        """get_config() singleton includes new fields."""
        monkeypatch.setenv("DECAY_ENABLED", "true")
        reset_config()
        config = get_config()
        assert hasattr(config, "decay_enabled")
        assert hasattr(config, "audit_dir")
        assert hasattr(config, "auto_update_enabled")

    def test_reset_config_clears_new_fields(self, monkeypatch):
        """reset_config() clears cache for new fields."""
        monkeypatch.setenv("DECAY_HALF_LIFE_CODE_PATTERNS", "7")
        reset_config()
        config1 = get_config()
        assert config1.decay_half_life_code_patterns == 7

        monkeypatch.setenv("DECAY_HALF_LIFE_CODE_PATTERNS", "28")
        reset_config()
        config2 = get_config()
        assert config2.decay_half_life_code_patterns == 28
        assert config1 is not config2


class TestExistingFieldsUnchanged:
    """Verify existing v2.0.5 fields retain their defaults (non-regression)."""

    def test_existing_fields_unchanged(self):
        """All existing v2.0.5 fields are still accessible and correctly typed.

        Note: We check types and accessibility rather than exact defaults because
        environment variables (from the host .env) may override defaults at test time.
        Exact default values are verified in test_config.py.
        """
        config = MemoryConfig(_env_file=None)
        assert isinstance(config.similarity_threshold, float)
        assert isinstance(config.qdrant_port, int)
        assert isinstance(config.embedding_port, int)
        assert isinstance(config.token_budget, int)
        assert isinstance(config.jira_sync_enabled, bool)
        assert isinstance(config.dedup_threshold, float)
        assert isinstance(config.max_retrievals, int)
        assert isinstance(config.log_level, str)
        assert isinstance(config.log_format, str)

    def test_helper_methods_still_work(self):
        """Existing helper methods still return correct URLs."""
        config = MemoryConfig(_env_file=None)
        assert config.get_qdrant_url() == "http://localhost:26350"
        assert config.get_embedding_url() == "http://localhost:28080"
        assert config.get_monitoring_url() == "http://localhost:28000"


class TestFieldDescriptions:
    """Verify all new fields have description parameter."""

    def test_all_new_fields_have_descriptions(self):
        """All v2.0.6 fields have description in their Field definition."""
        new_fields = [
            "decay_enabled",
            "decay_semantic_weight",
            "decay_half_life_code_patterns",
            "decay_half_life_discussions",
            "decay_half_life_conventions",
            "decay_half_life_jira_data",
            "decay_min_score",
            "decay_type_overrides",
            "audit_dir",
            "auto_update_enabled",
        ]
        for field_name in new_fields:
            field_info = MemoryConfig.model_fields[field_name]
            assert field_info.description is not None, (
                f"Field '{field_name}' missing description"
            )
            assert len(field_info.description) > 0, (
                f"Field '{field_name}' has empty description"
            )
