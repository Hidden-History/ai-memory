"""
Tests for aim_sot_consult 5b cache read-through (Item 3 seam).

F2 refactor: _load_entries reads via _scroll_sot_payloads/_parse_cached_entries
directly, bypassing _try_memory_cache. _try_memory_cache was therefore
production-orphaned and removed. These tests are rewired to the
_scroll_sot_payloads seam via monkeypatch (mirrors
_ai-memory/skills/aim-sot/tests/test_a1_consult_freshness.py).

Covers:
  T-CR1 — store unreachable (_scroll_sot_payloads returns None) → file fallback
  T-CR2 — empty cache (_scroll_sot_payloads returns []) → file fallback
  T-CR3 — full fresh cache served (stamped SHA + cardinality match)
  T-CR4 — _load_entries falls back to file when _scroll_sot_payloads returns None
  T-CR5 — partial cache (subset stamped committed SHA) → cardinality guard → file fallback [C4-1]

All tests are hermetic (no network; _scroll_sot_payloads mocked via monkeypatch).
"""

import importlib.util
import json
from pathlib import Path

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


def _stamped_payloads(entries: list[dict], registry_sha: str) -> list[dict]:
    """Build 5b Qdrant payloads as the reindex writes them: entry JSON in
    ``content`` plus the stamped ``registry_sha`` top-level field."""
    return [{"content": json.dumps(e), "registry_sha": registry_sha} for e in entries]


_FILE_ENTRIES = [
    {"id": "alpha", "sot_location": "src/alpha/", "owner": "@alpha-team"},
    {"id": "beta", "sot_location": "src/beta/", "owner": "@beta-team"},
    {"id": "gamma", "sot_location": "src/gamma/", "owner": "@gamma-team"},
]


# ---------------------------------------------------------------------------
# T-CR1 — store unreachable → file fallback
# ---------------------------------------------------------------------------


def test_scroll_store_unreachable_falls_back_to_file(monkeypatch, tmp_path):
    """_scroll_sot_payloads returns None (store down) → _load_entries serves file."""
    registry = _make_registry(tmp_path, _FILE_ENTRIES)
    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: "proj", raising=False
    )
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: None, raising=False
    )

    result = consult._load_entries(registry)
    assert [e["id"] for e in result] == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# T-CR2 — empty cache → file fallback
# ---------------------------------------------------------------------------


def test_scroll_empty_falls_back_to_file(monkeypatch, tmp_path):
    """_scroll_sot_payloads returns [] → no payloads → file fallback."""
    registry = _make_registry(tmp_path, _FILE_ENTRIES)
    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: "proj", raising=False
    )
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: [], raising=False
    )

    result = consult._load_entries(registry)
    assert [e["id"] for e in result] == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# T-CR3 — full fresh cache served (cardinality + SHA match)
# ---------------------------------------------------------------------------


def test_full_fresh_cache_served(monkeypatch, tmp_path):
    """All rows stamped with committed SHA, count matches file → cache served."""
    registry = _make_registry(tmp_path, _FILE_ENTRIES)
    committed_sha = consult._registry_sha(registry)
    payloads = _stamped_payloads(_FILE_ENTRIES, committed_sha)

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: "proj", raising=False
    )
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: payloads, raising=False
    )

    result = consult._load_entries(registry)
    assert {e["id"] for e in result} == {"alpha", "beta", "gamma"}


# ---------------------------------------------------------------------------
# T-CR4 — _load_entries falls back to file when scroll returns None
# ---------------------------------------------------------------------------


def test_load_entries_file_fallback_when_scroll_none(monkeypatch, tmp_path):
    """Explicit fallback seam: None payloads → file entries returned."""
    file_entries = [{"id": "core", "sot_location": "src/core/", "owner": "@core-team"}]
    registry = _make_registry(tmp_path, file_entries)
    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: "proj", raising=False
    )
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: None, raising=False
    )

    result = consult._load_entries(registry)
    assert len(result) == 1
    assert result[0]["id"] == "core"


# ---------------------------------------------------------------------------
# T-CR5 — partial cache (C4-1 cardinality guard): subset stamped → file fallback
# ---------------------------------------------------------------------------


def test_partial_cache_falls_back_to_file(monkeypatch, tmp_path):
    """C4-1 cardinality guard: 2 of 3 rows stamped committed_sha → file-fallback,
    returning ALL 3 committed entries (not the 2-row partial cache).

    Fails pre-fix (SHA-only check trusts 2-row subset as fresh since all stamps
    match the committed SHA). Passes post-fix (cardinality guard:
    len(payloads)==2 != len(file_entries)==3 → fallback to committed file).
    """
    registry = _make_registry(tmp_path, _FILE_ENTRIES)  # 3 entries in committed file
    committed_sha = consult._registry_sha(registry)

    # Only 2 of 3 entries in cache — both stamped with the committed SHA.
    partial_cache = _stamped_payloads(_FILE_ENTRIES[:2], committed_sha)
    assert len(partial_cache) == 2

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: "proj", raising=False
    )
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: partial_cache, raising=False
    )

    result = consult._load_entries(registry)

    # Must serve the COMMITTED FILE (all 3), not the partial cache (2).
    assert (
        len(result) == 3
    ), f"Expected 3 committed entries, got {len(result)} — cardinality guard failed"
    assert {e["id"] for e in result} == {"alpha", "beta", "gamma"}
