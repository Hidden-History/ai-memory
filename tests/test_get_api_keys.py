"""Companion test for scripts/memory/lib/get_api_keys.sh.

Tests the 3 BASELINE scenarios from
_ai-memory_backup_pre_task071/baselines/item-1-get_api_keys/BASELINE.md:
  1. .env present with a real QDRANT_API_KEY= line  → key exported, exit 0
  2. .env present, key only in comment (no uncommented line) → empty, exit 0
  3. .env missing entirely                            → empty, exit 0

All scenarios use an explicit HOME= override so the helper reads from a
controlled tmp directory, never the developer's real ~/.ai-memory/docker/.env.
"""

import os
import subprocess
from pathlib import Path

import pytest

HELPER_PATH = (
    Path(__file__).resolve().parent.parent / "scripts/memory/lib/get_api_keys.sh"
)


@pytest.fixture(scope="module")
def helper_path() -> Path:
    assert HELPER_PATH.exists(), f"Helper not found: {HELPER_PATH}"
    return HELPER_PATH


def _make_env(home_dir: Path) -> dict:
    """Minimal env with HOME pointing at tmp dir; PATH inherited for grep/cut."""
    return {"HOME": str(home_dir), "PATH": os.environ["PATH"]}


def _env_file(home_dir: Path) -> Path:
    p = home_dir / ".ai-memory" / "docker"
    p.mkdir(parents=True, exist_ok=True)
    return p / ".env"


def test_real_key_exported(helper_path, tmp_path):
    """Scenario 1: .env has uncommented QDRANT_API_KEY=<value> → exported, exit 0."""
    _env_file(tmp_path).write_text("QDRANT_API_KEY=abc123\n")
    result = subprocess.run(
        ["bash", "-c", f'source "{helper_path}"; printf "%s" "$QDRANT_API_KEY"'],
        env=_make_env(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == "abc123"


def test_empty_value_yields_empty(helper_path, tmp_path):
    """Scenario 2: .env present but QDRANT_API_KEY has no value (key= with empty RHS).
    Mirrors the actual testV2 install state: grep matches 'QDRANT_API_KEY=',
    cut -d= -f2 returns empty string, export succeeds, exit 0."""
    _env_file(tmp_path).write_text("QDRANT_API_KEY=\n")
    result = subprocess.run(
        ["bash", "-c", f'source "{helper_path}"; printf "%s" "$QDRANT_API_KEY"'],
        env=_make_env(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_missing_env_file_yields_empty(helper_path, tmp_path):
    """Scenario 3: .env missing entirely → empty, exit 0 (silent fallback).
    grep emits 'No such file or directory' to stderr (captured, not checked);
    export still succeeds with empty string."""
    # No .env created — directory may not even exist.
    result = subprocess.run(
        ["bash", "-c", f'source "{helper_path}"; printf "%s" "$QDRANT_API_KEY"'],
        env=_make_env(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout == ""
