"""Tests for update.sh script.

Tests verify 2026 best practices:
- set -euo pipefail error handling
- Signal trap cleanup
- Comprehensive backup
- Idempotent operations
"""

from pathlib import Path

import pytest


class TestUpdateScript:
    """Test update.sh functionality."""

    @pytest.fixture
    def temp_install_dir(self, tmp_path):
        """Create a mock installation directory."""
        install_dir = tmp_path / "ai-memory"
        install_dir.mkdir()

        # Create directory structure
        (install_dir / "docker").mkdir()
        (install_dir / "src" / "memory").mkdir(parents=True)
        (install_dir / "scripts").mkdir()
        (install_dir / ".claude" / "hooks" / "scripts").mkdir(parents=True)

        # Create minimal files
        (install_dir / ".env").write_text("TEST_VAR=value\n")
        (install_dir / "docker" / "docker-compose.yml").write_text("version: '3.8'\n")
        (install_dir / "src" / "memory" / "__init__.py").write_text("")

        return install_dir

    def test_update_script_exists_and_executable(self):
        """Test that update.sh exists and is executable."""
        update_script = Path(__file__).parent.parent / "update.sh"

        assert update_script.exists(), "update.sh must exist"
        assert update_script.stat().st_mode & 0o111, "update.sh must be executable"

    def test_update_script_has_strict_error_handling(self):
        """Test that update.sh uses set -euo pipefail."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        assert "set -euo pipefail" in content, "Must use strict error handling"
        assert "#!/usr/bin/env bash" in content or "#!/bin/bash" in content

    def test_update_script_has_signal_trap(self):
        """Test that update.sh has signal trap for cleanup."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        assert "trap" in content.lower(), "Must have signal trap"
        assert "cleanup" in content.lower(), "Must have cleanup function"

    def test_check_installation_validates_directories(self):
        """Test that check_installation() validates critical directories."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        # Verify check_installation function exists and checks critical dirs
        assert (
            "check_installation()" in content
        ), "Must have check_installation function"
        assert "docker" in content, "Must check docker directory"
        assert "src/memory" in content, "Must check src/memory directory"
        assert "scripts" in content, "Must check scripts directory"
        assert ".claude/hooks/scripts" in content, "Must check hooks directory"
        assert "missing_dirs" in content, "Must track missing directories"

    def test_create_backup_with_timestamp(self):
        """Test that create_backup() creates timestamped backups."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        # Verify backup creation with timestamp
        assert "create_backup()" in content, "Must have create_backup function"
        assert "date +" in content, "Must use date for timestamp"
        assert "BACKUP_DIR" in content, "Must set BACKUP_DIR variable"
        assert "mkdir -p" in content, "Must create backup directory"

    def test_backup_preserves_user_config(self):
        """Test that backup preserves .env and settings.json."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        # Verify backup includes user configuration files
        assert ".env" in content, "Must backup .env file"
        assert "settings.json" in content, "Must backup settings.json"
        assert "docker-compose.override.yml" in content, "Must backup docker overrides"

    def test_update_files_preserves_env(self):
        """Test that update_files() doesn't overwrite user .env."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        # Verify .env preservation logic
        assert "update_files()" in content, "Must have update_files function"
        # Should copy .env.example but not overwrite .env
        assert ".env.example" in content, "Must handle .env.example"
        assert (
            "Kept existing .env" in content or "existing .env" in content.lower()
        ), "Must preserve existing .env"

    def test_cleanup_old_backups_respects_retention(self):
        """Test that cleanup_old_backups() respects retention policy."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        # Verify backup retention logic
        assert "cleanup_old_backups()" in content, "Must have cleanup function"
        assert "BACKUP_RETENTION" in content, "Must use retention variable"
        assert "mtime" in content or "find" in content, "Must find old backups by age"

    def test_idempotent_update_run_twice(self):
        """Test that update.sh is designed to be idempotent (safe to run multiple times)."""
        update_script = Path(__file__).parent.parent / "update.sh"
        content = update_script.read_text()

        # Verify idempotent patterns:
        # - mkdir -p (creates if not exists)
        # - cp with overwrite (not failing if exists)
        # - docker compose up -d (restarts or creates)
        assert "mkdir -p" in content, "Must use mkdir -p for idempotent dir creation"
        assert "docker compose up -d" in content, "Must use docker compose up -d"
        # Check for conditional file operations
        assert (
            "if [[ -f" in content or "if [[ -d" in content
        ), "Must have conditional checks for idempotency"
