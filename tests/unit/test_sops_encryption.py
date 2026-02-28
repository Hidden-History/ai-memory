"""Unit tests for SPEC-011 encryption configuration.

Tests config field validation, backend detection, and security patterns.
"""

import os
from pathlib import Path

import pytest

from memory.config import MemoryConfig, get_config, reset_config


class TestEncryptionConfig:
    """Test SPEC-011 secrets_backend configuration field."""

    def teardown_method(self):
        """Reset config singleton after each test."""
        reset_config()
        # Clean up any test env vars
        for key in ["AI_MEMORY_SECRETS_BACKEND", "SECRETS_BACKEND"]:
            os.environ.pop(key, None)

    def test_secrets_backend_default_value(self):
        """Test secrets_backend defaults to 'env-file'."""
        config = get_config()
        assert config.secrets_backend == "env-file"

    def test_secrets_backend_sops_age(self):
        """Test secrets_backend accepts 'sops-age' value."""
        os.environ["SECRETS_BACKEND"] = "sops-age"
        reset_config()
        config = get_config()
        assert config.secrets_backend == "sops-age"

    def test_secrets_backend_keyring(self):
        """Test secrets_backend accepts 'keyring' value."""
        os.environ["SECRETS_BACKEND"] = "keyring"
        reset_config()
        config = get_config()
        assert config.secrets_backend == "keyring"

    def test_secrets_backend_env_file(self):
        """Test secrets_backend accepts 'env-file' value."""
        os.environ["SECRETS_BACKEND"] = "env-file"
        reset_config()
        config = get_config()
        assert config.secrets_backend == "env-file"

    def test_secrets_backend_invalid_value_rejected(self):
        """Test secrets_backend rejects invalid values."""
        os.environ["SECRETS_BACKEND"] = "invalid-backend"
        reset_config()
        with pytest.raises(Exception) as exc_info:
            get_config()
        # Pydantic ValidationError should mention pattern mismatch
        assert (
            "secrets_backend" in str(exc_info.value).lower()
            or "pattern" in str(exc_info.value).lower()
        )

    def test_secrets_backend_uppercase_rejected(self):
        """Test secrets_backend pattern requires lowercase values.

        Note: case_sensitive=False in model_config only affects field name matching,
        not field value validation. The pattern requires exact lowercase matches.
        """
        os.environ["SECRETS_BACKEND"] = "SOPS-AGE"
        reset_config()
        with pytest.raises(Exception) as exc_info:
            get_config()
        # Pydantic ValidationError should mention pattern mismatch
        assert (
            "secrets_backend" in str(exc_info.value).lower()
            or "pattern" in str(exc_info.value).lower()
        )

    def test_secrets_backend_in_env_file(self, tmp_path):
        """Test secrets_backend can be read from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("SECRETS_BACKEND=keyring\n")

        # Change working directory to tmp_path so pydantic finds .env
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            reset_config()
            config = get_config()
            assert config.secrets_backend == "keyring"
        finally:
            os.chdir(original_cwd)

    def test_config_description_mentions_informational(self):
        """Test secrets_backend description clarifies it's informational only."""
        field_info = MemoryConfig.model_fields["secrets_backend"]
        description = field_info.description or ""
        assert (
            "informational" in description.lower()
            or "diagnostic" in description.lower()
        )
        assert "start.sh" in description or "wrapper" in description.lower()


class TestSecurityValidation:
    """Test security-related validation and patterns."""

    def test_gitignore_contains_env_exclusion(self):
        """Test .gitignore excludes docker/.env (plaintext secrets).

        TD-175: Note this test checks the repo root .gitignore, not the install dir.
        The install dir (~/.ai-memory) is NOT a git repo and has no .gitignore.
        """
        gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
        if not gitignore_path.exists():
            pytest.skip(".gitignore not found in expected location")

        gitignore_content = gitignore_path.read_text()
        # Check for .env exclusion (already present, not just added by SPEC-011)
        assert ".env" in gitignore_content or "docker/.env" in gitignore_content

    def test_gitignore_contains_age_key_exclusion(self):
        """Test .gitignore excludes age private keys."""
        gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
        if not gitignore_path.exists():
            pytest.skip(".gitignore not found in expected location")

        gitignore_content = gitignore_path.read_text()
        # SPEC-011 adds age key exclusion pattern
        assert "keys.txt" in gitignore_content or "sops/age" in gitignore_content

    def test_secrets_template_exists(self):
        """Test docker/secrets.template.yaml exists."""
        template_path = (
            Path(__file__).parent.parent.parent / "docker" / "secrets.template.yaml"
        )
        assert template_path.exists(), "secrets.template.yaml should exist"

    def test_secrets_template_has_required_fields(self):
        """Test secrets.template.yaml contains required secret placeholders."""
        template_path = (
            Path(__file__).parent.parent.parent / "docker" / "secrets.template.yaml"
        )
        if not template_path.exists():
            pytest.skip("secrets.template.yaml not found")

        import yaml

        with open(template_path) as f:
            data = yaml.safe_load(f)

        # Required field per spec
        assert "QDRANT_API_KEY" in data
        # Optional fields per spec
        assert "GITHUB_TOKEN" in data
        assert "JIRA_API_TOKEN" in data


class TestFallbackBehavior:
    """Test graceful fallback when encryption tools are unavailable."""

    def test_start_script_exists_and_executable(self):
        """Test start.sh exists and is executable."""
        start_script = Path(__file__).parent.parent.parent / "start.sh"
        assert start_script.exists(), "start.sh should exist"
        # Check if executable bit is set
        assert os.access(start_script, os.X_OK), "start.sh should be executable"

    def test_setup_secrets_script_exists_and_executable(self):
        """Test setup-secrets.sh exists and is executable."""
        setup_script = (
            Path(__file__).parent.parent.parent / "scripts" / "setup-secrets.sh"
        )
        assert setup_script.exists(), "setup-secrets.sh should exist"
        assert os.access(setup_script, os.X_OK), "setup-secrets.sh should be executable"
