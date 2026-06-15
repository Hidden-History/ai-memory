"""A1: consult must never return entries that don't match the committed registry.

Regression guard for the cache-first staleness defect (DEC-PM336-C): consult read
the 5b derived memory cache first and returned it whenever non-empty, with no
binding to the committed registry's SHA — so after any registry edit (or when
another project's rows shared the group_id) it shadowed the file with stale rows.

The freshness gate binds the 5b read to the 5a drift cache's ``registry_sha``
(which advances only on a successful reindex): cache is used only when that SHA
matches the committed file's SHA, else consult falls back to the committed file.

Run targeted only:
    pytest tests/test_a1_consult_freshness.py
"""

import importlib.util
import json
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


consult = _load("aim_sot_consult")


def _realistic_registry(root: Path, n: int = 12) -> Path:
    """Write a realistic <root>/.sot/registry.yaml with n entries; return its path."""
    entries = [
        {
            "id": f"COMP-{i:02d}",
            "kind": "module",
            "owner": "team-platform",
            "sot_location": f"src/pkg{i:02d}/__init__.py",
            "status": "active",
            "drift_status": "clean",
        }
        for i in range(n)
    ]
    sot_dir = root / ".sot"
    sot_dir.mkdir(parents=True, exist_ok=True)
    path = sot_dir / "registry.yaml"
    path.write_text(yaml.safe_dump({"entries": entries}), encoding="utf-8")
    return path


def _seed_drift_cache(tmp_cache_dir: Path, project_id: str, registry_sha: str) -> None:
    tmp_cache_dir.mkdir(parents=True, exist_ok=True)
    safe_id = project_id.replace("/", "__")
    (tmp_cache_dir / f"sot_drift_{safe_id}.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "project_id": project_id,
                "generated_at": "",
                "registry_sha": registry_sha,
                "components": {},
            }
        ),
        encoding="utf-8",
    )


def test_stale_cache_bypassed_returns_committed_entries(monkeypatch, tmp_path):
    """PRE-FIX FAILING: a populated 5b cache from a different registry state (5a
    registry_sha mismatched) must be bypassed; consult returns the committed file."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"

    cache_dir = tmp_path / "drift-state"
    monkeypatch.setattr(consult._dp, "_DRIFT_CACHE_DIR", cache_dir)
    # 5a cache built from a DIFFERENT registry state → SHA cannot match committed.
    _seed_drift_cache(cache_dir, project_id, registry_sha="00000000")

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    # Simulate a populated 5b cache holding stale/cross-state rows.
    stale_rows = [{"id": "STALE-ONLY", "kind": "x", "sot_location": "gone.py"}]
    monkeypatch.setattr(
        consult, "_try_memory_cache", lambda *a, **k: stale_rows, raising=False
    )

    entries = consult._load_entries(registry)
    ids = {e.get("id") for e in entries}

    assert "STALE-ONLY" not in ids, "stale cache row leaked into consult output"
    assert len(entries) == 12, "committed registry entries not returned on cache miss"
    assert ids == {f"COMP-{i:02d}" for i in range(12)}


def test_fresh_cache_used_preserves_drift_status(monkeypatch, tmp_path):
    """When the 5a registry_sha matches the committed file, the enriched 5b cache
    is used so digest still surfaces drift_status (no regression of that path)."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"
    committed_sha = consult._registry_sha(registry)

    cache_dir = tmp_path / "drift-state"
    monkeypatch.setattr(consult._dp, "_DRIFT_CACHE_DIR", cache_dir)
    _seed_drift_cache(cache_dir, project_id, registry_sha=committed_sha)  # MATCH

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    enriched = [
        {"id": "COMP-00", "drift_status": "drifted", "sot_location": "a.py"},
        {"id": "COMP-01", "drift_status": "clean", "sot_location": "b.py"},
    ]
    monkeypatch.setattr(
        consult, "_try_memory_cache", lambda *a, **k: enriched, raising=False
    )

    entries = consult._load_entries(registry)
    assert entries == enriched, "fresh cache should be used (enriched rows)"
    assert any(e.get("drift_status") == "drifted" for e in entries)


def test_consult_is_read_only(monkeypatch, tmp_path):
    """consult never mutates the registry file (SHA unchanged across calls)."""
    registry = _realistic_registry(tmp_path, n=12)
    before = consult._registry_sha(registry)

    # No memory stack in the test env → file fallback; exercise the real path.
    for argv in (["list"], ["digest"], ["get", "COMP-00"]):
        rc = consult.main([*argv, "--registry", str(registry)])
        assert rc == 0

    after = consult._registry_sha(registry)
    assert before == after, "consult mutated the committed registry"
