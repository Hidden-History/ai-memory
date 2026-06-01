"""Shared pytest fixtures for aim-model-dispatch skill tests."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def scripts_dir() -> Path:
    """Absolute path to scripts/lib/ inside the aim-model-dispatch skill."""
    skill_root = Path(__file__).resolve().parent.parent
    lib_dir = skill_root / "scripts" / "lib"
    assert lib_dir.is_dir(), f"scripts/lib not found: {lib_dir}"
    return lib_dir
