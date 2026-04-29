"""Regression tests for BUG-275: MemoryConfig reads both docker/.env and docker/.env.secrets.

Exercises Pattern A (MemoryConfig.model_config tuple env_file — R1) and the
Pattern C shared helper load_install_env() (R4 / scripts/_env_loader.py).

Research basis: BP-153 §3 (primary fix), §4 (C1/C2 Verified from pydantic-settings 2.7.1
source), §8 (order-of-precedence).

Each test reloads memory.config after setting AI_MEMORY_INSTALL_DIR so the class-level
_docker_env / _docker_secrets paths are re-evaluated with the temp install dir.
"""

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def _reload_memory_config():
    """Force memory.config re-import so class-level env_file paths are re-evaluated."""
    sys.modules.pop("memory.config", None)
    sys.modules.pop("memory.logging_config", None)
    from memory.config import MemoryConfig, reset_config

    reset_config()
    return MemoryConfig, reset_config


def _write_env(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# Shared fixture — clean env slate
# ---------------------------------------------------------------------------

_KEYS_TO_CLEAR = [
    "AI_MEMORY_INSTALL_DIR",
    "GITHUB_SYNC_ENABLED",
    "GITHUB_TOKEN",
    "GITHUB_REPO",
    "JIRA_API_TOKEN",
    "JIRA_EMAIL",
    "JIRA_INSTANCE_URL",
    "JIRA_SYNC_ENABLED",
    "LANGFUSE_ENABLED",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "QDRANT_API_KEY",
    "QDRANT_HOST",
    "SIMILARITY_THRESHOLD",
]


@pytest.fixture()
def clean_install_env(monkeypatch, tmp_path):
    """Set AI_MEMORY_INSTALL_DIR to a fresh temp dir; clear known keys."""
    for key in _KEYS_TO_CLEAR:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    yield tmp_path
    # Teardown: ensure module is reloaded on next test entry
    sys.modules.pop("memory.config", None)
    sys.modules.pop("memory.logging_config", None)


# ---------------------------------------------------------------------------
# Fixture for Pattern C helper tests — snapshot+restore os.environ
# ---------------------------------------------------------------------------


@pytest.fixture()
def env_loader_test_keys(monkeypatch):
    """Snapshot+restore os.environ keys mutated by load_install_env() during a test.

    monkeypatch only auto-reverts vars it set via setenv/delenv; raw os.environ writes
    by load_install_env() are NOT tracked. This fixture takes a snapshot of the keys
    load_install_env() can write, runs the test, then restores the snapshot.
    """
    keys_to_track = [
        "QDRANT_API_KEY",
        "QDRANT_HOST",
        "QDRANT_PORT",
        "GITHUB_TOKEN",
        "GITHUB_REPO",
        "GITHUB_SYNC_ENABLED",
        "JIRA_API_TOKEN",
        "JIRA_EMAIL",
        "JIRA_INSTANCE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_ENABLED",
    ]
    snapshot = {k: os.environ.get(k) for k in keys_to_track}
    yield
    for k, v in snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# Test 1: Pattern A positive — GITHUB_TOKEN read from .env.secrets
# ---------------------------------------------------------------------------


def test_memoryconfig_reads_secrets_from_split_env(clean_install_env):
    """MemoryConfig loads credentials from .env.secrets when .env has empty placeholders.

    Exercises BP-153 §4 C1 (last-file-wins) + C2 (env_ignore_empty per-file).
    Pre-fix: ValidationError fired because GITHUB_TOKEN= in .env was filtered,
    and .env.secrets was not loaded at all.
    """
    tmp = clean_install_env
    _write_env(
        tmp / "docker" / ".env",
        "GITHUB_SYNC_ENABLED=true\nGITHUB_REPO=acme/test-repo\nGITHUB_TOKEN=\n",
    )
    _write_env(
        tmp / "docker" / ".env.secrets",
        "GITHUB_TOKEN=ghp_test_value\nJIRA_API_TOKEN=jira_test\nQDRANT_API_KEY=qdrant_test\n",
    )

    MemoryConfig, reset_config = _reload_memory_config()
    try:
        config = MemoryConfig()
        assert config.github_token.get_secret_value() == "ghp_test_value"
        assert config.jira_api_token.get_secret_value() == "jira_test"
        assert config.qdrant_api_key is not None
        assert config.qdrant_api_key.get_secret_value() == "qdrant_test"
        assert config.github_sync_enabled is True
        assert config.github_repo == "acme/test-repo"
    finally:
        reset_config()


# ---------------------------------------------------------------------------
# Test 2: Pattern A negative — secrets missing → ValidationError still fires
# ---------------------------------------------------------------------------


def test_memoryconfig_validation_fires_when_secrets_missing(clean_install_env):
    """ValidationError raised when GITHUB_SYNC_ENABLED=true but .env.secrets absent.

    Documents pre-fix behavior and ensures the cross-field validator still fires
    when secrets are genuinely missing (not just when consumer side is broken).
    """
    tmp = clean_install_env
    _write_env(
        tmp / "docker" / ".env",
        "GITHUB_SYNC_ENABLED=true\nGITHUB_REPO=acme/test-repo\nGITHUB_TOKEN=\n",
    )
    # .env.secrets intentionally absent

    MemoryConfig, reset_config = _reload_memory_config()
    try:
        with pytest.raises(ValidationError, match="GITHUB_TOKEN required"):
            MemoryConfig()
    finally:
        reset_config()


# ---------------------------------------------------------------------------
# Test 3: .env.secrets overrides .env for overlapping non-empty keys
# ---------------------------------------------------------------------------


def test_memoryconfig_secrets_overrides_env_for_overlapping_keys(clean_install_env):
    """Last-file-wins: .env.secrets value beats .env value for same key (BP-153 §4 C1)."""
    tmp = clean_install_env
    _write_env(
        tmp / "docker" / ".env",
        "QDRANT_API_KEY=from_env_file\n",
    )
    _write_env(
        tmp / "docker" / ".env.secrets",
        "QDRANT_API_KEY=from_secrets_file\n",
    )

    MemoryConfig, reset_config = _reload_memory_config()
    try:
        config = MemoryConfig()
        assert config.qdrant_api_key is not None
        assert config.qdrant_api_key.get_secret_value() == "from_secrets_file"
    finally:
        reset_config()


# ---------------------------------------------------------------------------
# Test 4: Shell env overrides both files
# ---------------------------------------------------------------------------


def test_memoryconfig_shell_env_overrides_files(clean_install_env, monkeypatch):
    """pydantic-settings env_settings source (shell env) outranks dotenv_settings."""
    tmp = clean_install_env
    _write_env(
        tmp / "docker" / ".env",
        "QDRANT_API_KEY=from_env_file\n",
    )
    _write_env(
        tmp / "docker" / ".env.secrets",
        "QDRANT_API_KEY=from_secrets_file\n",
    )
    monkeypatch.setenv("QDRANT_API_KEY", "from_shell")

    MemoryConfig, reset_config = _reload_memory_config()
    try:
        config = MemoryConfig()
        assert config.qdrant_api_key is not None
        assert config.qdrant_api_key.get_secret_value() == "from_shell"
    finally:
        reset_config()


# ---------------------------------------------------------------------------
# Test 5: Empty .env placeholder does NOT suppress non-empty .env.secrets value
# ---------------------------------------------------------------------------


def test_memoryconfig_empty_env_does_not_suppress_secrets(clean_install_env):
    """BP-153 §4 C2: env_ignore_empty is per-file, not global.

    Empty GITHUB_TOKEN= in .env is filtered per-file BEFORE dict.update() merge.
    Non-empty GITHUB_TOKEN in .env.secrets enters the merge dict cleanly.
    """
    tmp = clean_install_env
    _write_env(
        tmp / "docker" / ".env",
        "GITHUB_SYNC_ENABLED=true\nGITHUB_REPO=acme/test-repo\nGITHUB_TOKEN=\n",
    )
    _write_env(
        tmp / "docker" / ".env.secrets",
        "GITHUB_TOKEN=ghp_real_value\n",
    )

    MemoryConfig, reset_config = _reload_memory_config()
    try:
        config = MemoryConfig()
        assert config.github_token.get_secret_value() == "ghp_real_value"
    finally:
        reset_config()


# ---------------------------------------------------------------------------
# Test 6: Pattern C helper — load_install_env() merges split files correctly
# ---------------------------------------------------------------------------


def test_env_loader_merges_split_files(tmp_path, monkeypatch, env_loader_test_keys):
    """load_install_env() loads .env.secrets first (precedence) then .env.

    Verifies: shell env > .env.secrets > .env > no-file defaults (BP-153 §3).
    """
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from _env_loader import load_install_env

    docker_dir = tmp_path / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env").write_text(
        "QDRANT_API_KEY=from_env_file\nQDRANT_HOST=filehost\n"
    )
    (docker_dir / ".env.secrets").write_text("QDRANT_API_KEY=from_secrets_file\n")

    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    monkeypatch.delenv("QDRANT_HOST", raising=False)

    load_install_env()

    # .env.secrets wins for overlapping non-empty key
    assert os.environ.get("QDRANT_API_KEY") == "from_secrets_file"
    # .env value used for key absent from .env.secrets
    assert os.environ.get("QDRANT_HOST") == "filehost"


def test_env_loader_shell_env_wins(tmp_path, monkeypatch, env_loader_test_keys):
    """Shell env set before load_install_env() is not overwritten."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from _env_loader import load_install_env

    docker_dir = tmp_path / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env.secrets").write_text("QDRANT_API_KEY=from_secrets\n")
    (docker_dir / ".env").write_text("QDRANT_API_KEY=from_env\n")

    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    monkeypatch.setenv("QDRANT_API_KEY", "shell_value")

    load_install_env()

    assert os.environ.get("QDRANT_API_KEY") == "shell_value"


def test_env_loader_missing_secrets_file_silent(
    tmp_path, monkeypatch, env_loader_test_keys
):
    """Missing .env.secrets is silently skipped; .env values still load."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from _env_loader import load_install_env

    docker_dir = tmp_path / "docker"
    docker_dir.mkdir(parents=True)
    (docker_dir / ".env").write_text("QDRANT_HOST=envhost\n")
    # .env.secrets intentionally absent

    monkeypatch.setenv("AI_MEMORY_INSTALL_DIR", str(tmp_path))
    monkeypatch.delenv("QDRANT_HOST", raising=False)

    load_install_env()  # must not raise

    assert os.environ.get("QDRANT_HOST") == "envhost"
