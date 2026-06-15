"""
Tests for aim_sot_consult 5b cache read-through (Item 3 seam).

Covers:
  T-CR1 — _try_memory_cache returns None when store raises (graceful)
  T-CR2 — _try_memory_cache returns None when cache is empty
  T-CR3 — _try_memory_cache returns list[dict] when cache has valid entries
  T-CR4 — _load_entries falls back to file when _try_memory_cache returns None

All tests are hermetic (no network; store mocked via sys.modules injection).
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

# ---------------------------------------------------------------------------
# Module import (importlib pattern)
# ---------------------------------------------------------------------------

_CONSULT_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-sot"
    / "scripts"
    / "aim_sot_consult.py"
)
_spec = importlib.util.spec_from_file_location("aim_sot_consult", _CONSULT_SCRIPT)
consult = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(consult)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path, entries: list[dict]) -> Path:
    reg_dir = tmp_path / ".sot"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg_file = reg_dir / "registry.yaml"
    reg_file.write_text(
        yaml.dump({"schema_version": "1.0", "entries": entries}), encoding="utf-8"
    )
    return reg_file


def _fake_qdrant_modules(entries: list[dict]):
    """Build minimal mocks for the qdrant + memory.* import chain.

    Returns a dict suitable for patching into sys.modules.
    """
    # Build mock scroll points
    points = []
    for e in entries:
        pt = MagicMock()
        pt.payload = {"content": json.dumps(e)}
        points.append(pt)

    mock_client_instance = MagicMock()
    mock_client_instance.scroll.return_value = (points, None)

    # qdrant_client.models
    mock_models = MagicMock()
    mock_models.Filter = MagicMock(return_value=MagicMock())
    mock_models.FieldCondition = MagicMock(return_value=MagicMock())
    mock_models.MatchValue = MagicMock(return_value=MagicMock())
    mock_qdrant_pkg = MagicMock()
    mock_qdrant_pkg.models = mock_models

    # memory.*
    mock_config = MagicMock()
    mock_config.COLLECTION_CONVENTIONS = "conventions"
    mock_config.get_config.return_value = {}

    mock_project = MagicMock()
    mock_project.resolve_project_id.return_value = "test-project"

    mock_qdrant_client_mod = MagicMock()
    mock_qdrant_client_mod.get_qdrant_client.return_value = mock_client_instance

    return {
        "qdrant_client": mock_qdrant_pkg,
        "qdrant_client.models": mock_models,
        "memory.config": mock_config,
        "memory.project": mock_project,
        "memory.qdrant_client": mock_qdrant_client_mod,
    }


# ---------------------------------------------------------------------------
# T-CR1 — _try_memory_cache: store raises → graceful None
# ---------------------------------------------------------------------------


def test_try_memory_cache_store_unreachable(tmp_path):
    registry_path = _make_registry(tmp_path, [])
    mods = _fake_qdrant_modules([])
    client_instance = mods["memory.qdrant_client"].get_qdrant_client.return_value
    client_instance.scroll.side_effect = Exception("Connection refused")

    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v
    try:
        result = consult._try_memory_cache(registry_path, "test-project")
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    assert result is None


# ---------------------------------------------------------------------------
# T-CR2 — _try_memory_cache: empty cache → None (triggers file fallback)
# ---------------------------------------------------------------------------


def test_try_memory_cache_empty_returns_none(tmp_path):
    registry_path = _make_registry(tmp_path, [])
    mods = _fake_qdrant_modules([])  # scroll returns empty list

    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v
    try:
        result = consult._try_memory_cache(registry_path, "test-project")
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    assert result is None


# ---------------------------------------------------------------------------
# T-CR3 — _try_memory_cache: valid cache entries returned as list[dict]
# ---------------------------------------------------------------------------


def test_try_memory_cache_returns_entries(tmp_path):
    cached_entries = [
        {"id": "frontend", "sot_location": "frontend/", "owner": "@ui-team"},
        {"id": "backend", "sot_location": "backend/", "owner": "@api-team"},
    ]
    registry_path = _make_registry(tmp_path, [])
    mods = _fake_qdrant_modules(cached_entries)

    old = {}
    for k, v in mods.items():
        old[k] = sys.modules.get(k)
        sys.modules[k] = v
    try:
        result = consult._try_memory_cache(registry_path, "test-project")
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 2
    ids = {e["id"] for e in result}
    assert ids == {"frontend", "backend"}


# ---------------------------------------------------------------------------
# T-CR4 — _load_entries: falls back to file when _try_memory_cache returns None
# ---------------------------------------------------------------------------


def test_load_entries_file_fallback_when_cache_none(tmp_path):
    file_entries = [
        {"id": "core", "sot_location": "src/core/", "owner": "@core-team"},
    ]
    registry_path = _make_registry(tmp_path, file_entries)

    with patch.object(consult, "_try_memory_cache", return_value=None):
        result = consult._load_entries(registry_path)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "core"
