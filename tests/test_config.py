"""Unit tests for memory configuration module with pydantic-settings.

Tests Story 7.4 - Environment Variable Configuration with pydantic-settings v2.6+.
"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.memory.config import MemoryConfig, get_config, reset_config


class TestMemoryConfig:
    """Test MemoryConfig with pydantic-settings BaseSettings."""

    def test_default_config_values(self, monkeypatch):
        """AC 7.4.1: Default configuration values are correct."""
        # Clear any environment variables that might interfere
        for key in list(os.environ.keys()):
            if any(
                k in key.upper()
                for k in [
                    "SIMILARITY",
                    "DEDUP",
                    "RETRIEVAL",
                    "TOKEN",
                    "QDRANT",
                    "EMBEDDING",
                    "MONITORING",
                    "LOG_LEVEL",
                    "LOG_FORMAT",
                    "COLLECTION_SIZE",
                    "INSTALL_DIR",
                    "QUEUE_PATH",
                    "SESSION_LOG",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        reset_config()
        config = get_config()

        # Core thresholds
        assert config.similarity_threshold == 0.7
        assert config.dedup_threshold == 0.95
        assert config.max_retrievals == 5
        assert (
            config.token_budget == 4000
        )  # Updated per BP-039 Section 3 (TECH-DEBT-116)

        # Service endpoints
        assert config.qdrant_host == "localhost"
        assert config.qdrant_port == 26350
        assert config.qdrant_api_key is None
        assert config.embedding_host == "localhost"
        assert config.embedding_port == 28080
        assert config.monitoring_host == "localhost"
        assert config.monitoring_port == 28000

        # Logging
        assert config.log_level == "INFO"
        assert config.log_format == "json"

        # Collection thresholds
        assert config.collection_size_warning == 10000
        assert config.collection_size_critical == 50000

        # Paths
        assert config.install_dir == Path.home() / ".ai-memory"
        assert config.queue_path == Path.home() / ".ai-memory" / "pending_queue.jsonl"
        assert config.session_log_path == Path.home() / ".ai-memory" / "sessions.jsonl"

    def test_environment_variable_override(self, monkeypatch):
        """AC 7.4.1: Environment variables override defaults (pydantic-settings)."""
        reset_config()

        # Set environment variables
        monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.85")
        monkeypatch.setenv("MAX_RETRIEVALS", "10")
        monkeypatch.setenv("QDRANT_PORT", "16360")
        monkeypatch.setenv("EMBEDDING_PORT", "18090")
        monkeypatch.setenv("TOKEN_BUDGET", "3000")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_FORMAT", "text")

        config = get_config()

        # Verify overrides
        assert config.similarity_threshold == 0.85
        assert config.max_retrievals == 10
        assert config.qdrant_port == 16360
        assert config.embedding_port == 18090
        assert config.token_budget == 3000
        assert config.log_level == "DEBUG"
        assert config.log_format == "text"

    def test_config_singleton_with_lru_cache(self):
        """AC 7.4.1: get_config() returns singleton via lru_cache (thread-safe)."""
        reset_config()

        config1 = get_config()
        config2 = get_config()

        # Same instance (lru_cache ensures this)
        assert config1 is config2

        # Verify it's properly initialized
        assert config1.qdrant_port == 26350
        assert config1.embedding_port == 28080

    def test_env_file_loading(self, monkeypatch, tmp_path):
        """AC 7.4.1: .env file loading with pydantic-settings SettingsConfigDict."""
        # Save current directory
        import os

        original_cwd = os.getcwd()

        # Clear environment variables
        for key in list(os.environ.keys()):
            if any(
                k in key.upper()
                for k in [
                    "SIMILARITY",
                    "DEDUP",
                    "RETRIEVAL",
                    "TOKEN",
                    "QDRANT",
                    "EMBEDDING",
                    "MONITORING",
                    "LOG_LEVEL",
                    "LOG_FORMAT",
                ]
            ):
                monkeypatch.delenv(key, raising=False)

        reset_config()

        # Create temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("""
SIMILARITY_THRESHOLD=0.82
DEDUP_THRESHOLD=0.92
MAX_RETRIEVALS=7
TOKEN_BUDGET=2500
QDRANT_PORT=26351
LOG_LEVEL=WARNING
        """.strip())

        # Point to the .env file (Note: pydantic-settings looks in current dir)
        monkeypatch.chdir(tmp_path)

        config = get_config()

        # Restore directory immediately after getting config
        os.chdir(original_cwd)

        # Verify .env values loaded
        assert config.similarity_threshold == 0.82
        assert config.dedup_threshold == 0.92
        assert config.max_retrievals == 7
        assert config.token_budget == 2500
        assert config.qdrant_port == 26351
        assert config.log_level == "WARNING"

    def test_env_ignore_empty_strings(self, monkeypatch):
        """AC 7.4.1: Empty env vars use defaults (env_ignore_empty=True)."""
        reset_config()

        # Set empty environment variable
        monkeypatch.setenv("SIMILARITY_THRESHOLD", "")
        monkeypatch.setenv("LOG_LEVEL", "")

        config = get_config()

        # Should use default, not empty string
        assert config.similarity_threshold == 0.7
        assert config.log_level == "INFO"

    def test_case_insensitive_env_vars(self, monkeypatch):
        """AC 7.4.1: Case-insensitive env var matching (case_sensitive=False)."""
        reset_config()

        # Set environment variables with different cases
        monkeypatch.setenv("similarity_threshold", "0.88")  # lowercase
        monkeypatch.setenv("MAX_RETRIEVALS", "8")  # uppercase
        monkeypatch.setenv("Qdrant_Port", "26352")  # mixed case

        config = get_config()

        # All should work due to case_sensitive=False
        assert config.similarity_threshold == 0.88
        assert config.max_retrievals == 8
        assert config.qdrant_port == 26352

    def test_validation_similarity_threshold(self):
        """AC 7.4.1: similarity_threshold validation (0.0-1.0) with pydantic Field."""
        reset_config()

        # Valid thresholds at boundaries
        assert MemoryConfig(similarity_threshold=0.0).similarity_threshold == 0.0
        assert MemoryConfig(similarity_threshold=1.0).similarity_threshold == 1.0
        assert MemoryConfig(similarity_threshold=0.5).similarity_threshold == 0.5

        # Out of range should raise ValidationError (pydantic)
        with pytest.raises(ValidationError, match="similarity_threshold"):
            MemoryConfig(similarity_threshold=1.1)

        with pytest.raises(ValidationError, match="similarity_threshold"):
            MemoryConfig(similarity_threshold=-0.1)

    def test_validation_dedup_threshold(self):
        """AC 7.4.1: dedup_threshold validation (0.80-0.99) with pydantic Field."""
        reset_config()

        # Valid thresholds at boundaries (AC 2.2.2 range)
        assert MemoryConfig(dedup_threshold=0.80).dedup_threshold == 0.80
        assert MemoryConfig(dedup_threshold=0.99).dedup_threshold == 0.99
        assert MemoryConfig(dedup_threshold=0.90).dedup_threshold == 0.90

        # Below 0.80 should raise ValidationError
        with pytest.raises(ValidationError, match="dedup_threshold"):
            MemoryConfig(dedup_threshold=0.79)

        # Above 0.99 should raise ValidationError
        with pytest.raises(ValidationError, match="dedup_threshold"):
            MemoryConfig(dedup_threshold=1.0)

    def test_validation_max_retrievals(self):
        """AC 7.4.1: max_retrievals validation (1-50) with pydantic Field."""
        reset_config()

        # Valid range
        assert MemoryConfig(max_retrievals=1).max_retrievals == 1
        assert MemoryConfig(max_retrievals=50).max_retrievals == 50

        # Out of range
        with pytest.raises(ValidationError, match="max_retrievals"):
            MemoryConfig(max_retrievals=0)

        with pytest.raises(ValidationError, match="max_retrievals"):
            MemoryConfig(max_retrievals=51)

    def test_validation_token_budget(self):
        """AC 7.4.1: token_budget validation (100-100000) with pydantic Field."""
        reset_config()

        # Valid range
        assert MemoryConfig(token_budget=100).token_budget == 100
        assert MemoryConfig(token_budget=100000).token_budget == 100000

        # Out of range
        with pytest.raises(ValidationError, match="token_budget"):
            MemoryConfig(token_budget=99)

        with pytest.raises(ValidationError, match="token_budget"):
            MemoryConfig(token_budget=100001)

    def test_validation_ports(self):
        """AC 7.4.1: Port validation (1024-65535) with pydantic Field."""
        reset_config()

        # Valid ports
        assert MemoryConfig(qdrant_port=1024).qdrant_port == 1024
        assert MemoryConfig(qdrant_port=65535).qdrant_port == 65535
        assert MemoryConfig(embedding_port=28080).embedding_port == 28080

        # Out of range
        with pytest.raises(ValidationError, match="qdrant_port"):
            MemoryConfig(qdrant_port=1023)

        with pytest.raises(ValidationError, match="embedding_port"):
            MemoryConfig(embedding_port=65536)

    def test_validation_log_level(self):
        """AC 7.4.1: log_level validation (regex pattern) with pydantic Field."""
        reset_config()

        # Valid log levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = MemoryConfig(log_level=level)
            assert config.log_level == level

        # Invalid log level
        with pytest.raises(ValidationError, match="log_level"):
            MemoryConfig(log_level="INVALID")

    def test_validation_log_format(self):
        """AC 7.4.1: log_format validation (regex pattern) with pydantic Field."""
        reset_config()

        # Valid formats
        assert MemoryConfig(log_format="json").log_format == "json"
        assert MemoryConfig(log_format="text").log_format == "text"

        # Invalid format
        with pytest.raises(ValidationError, match="log_format"):
            MemoryConfig(log_format="invalid")

    def test_path_expansion_tilde(self, monkeypatch):
        """AC 7.4.1: Path expansion for ~ with field_validator."""
        reset_config()
        monkeypatch.setenv("INSTALL_DIR", "~/custom-ai-memory")

        config = get_config()

        # Tilde should be expanded to home directory
        assert "~" not in str(config.install_dir)
        assert config.install_dir == Path.home() / "custom-ai-memory"

    def test_path_expansion_env_vars(self, monkeypatch):
        """AC 7.4.1: Path expansion for $HOME with field_validator."""
        reset_config()
        monkeypatch.setenv("QUEUE_PATH", "$HOME/.custom-queue/queue.jsonl")

        config = get_config()

        # $HOME should be expanded
        assert "$HOME" not in str(config.queue_path)
        assert config.queue_path == Path.home() / ".custom-queue" / "queue.jsonl"

    def test_frozen_config_immutable(self):
        """AC 7.4.1: Frozen config (immutable after creation) with frozen=True."""
        reset_config()
        config = get_config()

        # Attempt to modify should raise ValidationError (frozen)
        with pytest.raises(ValidationError, match="frozen"):
            config.similarity_threshold = 0.9  # type: ignore

    def test_helper_methods(self):
        """AC 7.4.1: Helper methods return proper URLs."""
        reset_config()
        config = get_config()

        # Test URL generation helpers
        assert config.get_qdrant_url() == "http://localhost:26350"
        assert config.get_embedding_url() == "http://localhost:28080"
        assert config.get_monitoring_url() == "http://localhost:28000"

    def test_helper_methods_custom_ports(self, monkeypatch):
        """AC 7.4.1: Helper methods with custom ports."""
        reset_config()
        monkeypatch.setenv("QDRANT_PORT", "16350")
        monkeypatch.setenv("EMBEDDING_PORT", "18080")
        monkeypatch.setenv("MONITORING_PORT", "18000")

        config = get_config()

        assert config.get_qdrant_url() == "http://localhost:16350"
        assert config.get_embedding_url() == "http://localhost:18080"
        assert config.get_monitoring_url() == "http://localhost:18000"

    def test_monitoring_host_separate_from_qdrant(self, monkeypatch):
        """Code Review Fix: monitoring_host is independent of qdrant_host."""
        reset_config()
        monkeypatch.setenv("QDRANT_HOST", "qdrant.example.com")
        monkeypatch.setenv("MONITORING_HOST", "monitoring.example.com")
        monkeypatch.setenv("MONITORING_PORT", "9000")

        config = get_config()

        # Each service has its own host
        assert config.get_qdrant_url() == "http://qdrant.example.com:26350"
        assert config.get_monitoring_url() == "http://monitoring.example.com:9000"
        # They should NOT be the same
        assert "qdrant.example.com" not in config.get_monitoring_url()

    def test_reset_config_clears_cache(self, monkeypatch):
        """AC 7.4.1: reset_config() clears lru_cache for test isolation."""
        reset_config()

        # Get initial config
        config1 = get_config()
        assert config1.qdrant_port == 26350

        # Reset and change env var
        reset_config()
        monkeypatch.setenv("QDRANT_PORT", "26360")

        # New config should have updated port
        config2 = get_config()
        assert config2.qdrant_port == 26360

        # Instances should be different after reset
        assert config1 is not config2

    def test_validate_default_values(self):
        """AC 7.4.1: validate_default=True ensures defaults are validated."""
        # This test verifies that default values pass validation
        # If validate_default=True and defaults are invalid, instantiation would fail

        reset_config()
        config = get_config()

        # All defaults should be valid (no ValidationError raised)
        assert 0.0 <= config.similarity_threshold <= 1.0
        assert 0.80 <= config.dedup_threshold <= 0.99
        assert 1 <= config.max_retrievals <= 50
        assert 100 <= config.token_budget <= 100000
        assert 1024 <= config.qdrant_port <= 65535
        assert config.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        assert config.log_format in ["json", "text"]

    def test_optional_qdrant_api_key(self, monkeypatch):
        """AC 7.4.1: QDRANT_API_KEY is optional (future use)."""
        # Clear any QDRANT_API_KEY that might be set
        monkeypatch.delenv("QDRANT_API_KEY", raising=False)
        reset_config()

        # Default: None
        config = get_config()
        assert config.qdrant_api_key is None

        # Can be set via env var
        reset_config()
        monkeypatch.setenv("QDRANT_API_KEY", "test-key-123")
        config = get_config()
        assert config.qdrant_api_key == "test-key-123"

    def test_collection_size_thresholds(self):
        """AC 7.4.1: Collection size thresholds with validation."""
        reset_config()
        config = get_config()

        # Defaults
        assert config.collection_size_warning == 10000
        assert config.collection_size_critical == 50000

        # Custom values
        custom = MemoryConfig(
            collection_size_warning=5000, collection_size_critical=25000
        )
        assert custom.collection_size_warning == 5000
        assert custom.collection_size_critical == 25000

        # Validation: warning must be >= 100
        with pytest.raises(ValidationError):
            MemoryConfig(collection_size_warning=99)

        # Validation: critical must be >= 1000
        with pytest.raises(ValidationError):
            MemoryConfig(collection_size_critical=999)

    def test_type_safety(self):
        """AC 7.4.1: Pydantic ensures type safety."""
        reset_config()

        # Correct types work
        config = MemoryConfig(
            similarity_threshold=0.8, max_retrievals=10, qdrant_host="example.com"
        )
        assert isinstance(config.similarity_threshold, float)
        assert isinstance(config.max_retrievals, int)
        assert isinstance(config.qdrant_host, str)

        # Wrong types raise ValidationError
        with pytest.raises(ValidationError):
            MemoryConfig(similarity_threshold="not_a_float")  # type: ignore

        with pytest.raises(ValidationError):
            MemoryConfig(max_retrievals="not_an_int")  # type: ignore
