"""A1: consult must never return entries that don't match the committed registry.

Regression guard for the cache-first staleness defect (DEC-PM336-C): consult read
the 5b derived memory cache first and returned it whenever non-empty, with no
binding to the committed registry's SHA — so after any registry edit (or when
another project's rows shared the group_id) it shadowed the file with stale rows.

The freshness gate (F2) binds the 5b read to the ``registry_sha`` the reindex
STAMPS onto every 5b row: the cache is used only when every row's stamped SHA
matches the committed file's SHA, else consult falls back to the committed file.
Binding to the rows' own stamp (not the per-install 5a drift cache) is what lets a
bare ``reindex`` — which rebuilds 5b but does not advance 5a — serve the fresh
cache instead of file-falling-back forever.

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


def _stamped_payloads(entries: list[dict], registry_sha) -> list[dict]:
    """Build 5b Qdrant payloads as the reindex writes them: the entry JSON in
    ``content`` plus the stamped ``registry_sha`` top-level field."""
    return [{"content": json.dumps(e), "registry_sha": registry_sha} for e in entries]


def test_stale_cache_bypassed_returns_committed_entries(monkeypatch, tmp_path, capsys):
    """A populated 5b cache stamped with a DIFFERENT registry SHA must be bypassed;
    `consult list` returns the committed file.

    This is the staleness invariant: a stamped SHA that does not equal the
    committed file's SHA proves the rows predate the current registry state, so the
    cache cannot be served."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    # 5b rows stamped from a DIFFERENT registry state → stamp cannot match committed.
    stale_rows = [{"id": "STALE-ONLY", "kind": "x", "sot_location": "gone.py"}]
    monkeypatch.setattr(
        consult,
        "_scroll_sot_payloads",
        lambda *a, **k: _stamped_payloads(stale_rows, "00000000"),
        raising=False,
    )

    # Drive the real CLI path (NIT-1): `consult list --registry <path> --json`.
    rc = consult.main(["list", "--registry", str(registry), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    ids = {e.get("id") for e in payload["entries"]}

    assert "STALE-ONLY" not in ids, "stale cache row leaked into consult output"
    assert (
        payload["count"] == 12
    ), "committed registry entries not returned on cache miss"
    assert ids == {f"COMP-{i:02d}" for i in range(12)}


def test_fresh_cache_used_preserves_drift_status(monkeypatch, tmp_path):
    """When every 5b row's stamped SHA matches the committed file, the enriched 5b
    cache is used so digest still surfaces any ``drift_status`` the rows carry (no
    regression of that path). This is the bare-``reindex`` happy path: rows stamped
    with the committed SHA are served without a following ``run``."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"
    committed_sha = consult._registry_sha(registry)

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    enriched = [
        {"id": "COMP-00", "drift_status": "drifted", "sot_location": "a.py"},
        {"id": "COMP-01", "drift_status": "clean", "sot_location": "b.py"},
    ]
    monkeypatch.setattr(
        consult,
        "_scroll_sot_payloads",
        lambda *a, **k: _stamped_payloads(enriched, committed_sha),  # MATCH
        raising=False,
    )

    entries = consult._load_entries(registry)
    assert entries == enriched, "fresh cache should be used (enriched rows)"
    assert any(e.get("drift_status") == "drifted" for e in entries)


def test_registry_edit_without_reindex_falls_back_to_committed(monkeypatch, tmp_path):
    """Cardinal A1 invariant: after a registry EDIT with no following reindex, the
    5b rows' stamp no longer matches the committed SHA → consult serves the
    committed file, never the now-stale cache."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"
    sha_before_edit = consult._registry_sha(registry)

    # 5b rows were stamped at the pre-edit registry state.
    stale_rows = [{"id": "STALE-ONLY", "kind": "x", "sot_location": "gone.py"}]
    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    monkeypatch.setattr(
        consult,
        "_scroll_sot_payloads",
        lambda *a, **k: _stamped_payloads(stale_rows, sha_before_edit),
        raising=False,
    )

    # Human edits the committed registry → its SHA advances; no reindex follows.
    _realistic_registry(tmp_path, n=11)
    assert consult._registry_sha(registry) != sha_before_edit

    entries = consult._load_entries(registry)
    ids = {e.get("id") for e in entries}
    assert "STALE-ONLY" not in ids, "stale cache served after registry edit"
    assert len(entries) == 11, "edited committed registry not served"


def test_mixed_stamps_bypassed(monkeypatch, tmp_path):
    """Cross-state safety: if the 5b rows carry MIXED stamps (e.g. another
    project's rows shared the group_id, or a partial reindex), the cache cannot be
    proven uniformly fresh → consult serves the committed file."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"
    committed_sha = consult._registry_sha(registry)

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    # One row matches committed, one is stamped from another state → not uniform.
    mixed = [
        {"content": json.dumps({"id": "FRESH"}), "registry_sha": committed_sha},
        {"content": json.dumps({"id": "STALE"}), "registry_sha": "00000000"},
    ]
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: mixed, raising=False
    )

    entries = consult._load_entries(registry)
    ids = {e.get("id") for e in entries}
    assert ids == {f"COMP-{i:02d}" for i in range(12)}, "mixed-stamp cache leaked"


def test_unstamped_rows_bypassed(monkeypatch, tmp_path):
    """Pre-F2 rows (no ``registry_sha`` stamp) cannot be proven fresh → file
    fallback. Guards the upgrade path where a cache predates the stamping fix."""
    registry = _realistic_registry(tmp_path, n=12)
    project_id = "lane-a-test"

    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: project_id, raising=False
    )
    unstamped = [{"content": json.dumps({"id": "OLD-ROW"})}]  # no registry_sha key
    monkeypatch.setattr(
        consult, "_scroll_sot_payloads", lambda *a, **k: unstamped, raising=False
    )

    entries = consult._load_entries(registry)
    ids = {e.get("id") for e in entries}
    assert "OLD-ROW" not in ids, "unstamped pre-F2 cache served"
    assert len(entries) == 12


def test_file_fallback_when_sibling_helper_unavailable(monkeypatch, tmp_path):
    """A-FIX-3: when the detect_propose sibling import fails, ``_registry_sha`` is
    None. ``_cache_is_fresh`` must then treat the cache as NOT fresh so consult
    still serves the committed file — never hard-failing, and never serving a cache
    it cannot prove fresh (the committed SHA is uncomputable)."""
    registry = _realistic_registry(tmp_path, n=12)

    # Simulate the degraded import (helper unavailable).
    monkeypatch.setattr(consult, "_registry_sha", None, raising=False)
    # A project_id resolves and a (stamped) 5b cache is reachable — the missing
    # freshness helper must still force the committed-file fallback.
    monkeypatch.setattr(
        consult, "_resolve_project_id_for_cache", lambda p: "lane-a-test", raising=False
    )
    monkeypatch.setattr(
        consult,
        "_scroll_sot_payloads",
        lambda *a, **k: [
            {"content": json.dumps({"id": "STALE-ONLY"}), "registry_sha": "anything"}
        ],
        raising=False,
    )

    entries = consult._load_entries(registry)
    ids = {e.get("id") for e in entries}

    assert (
        "STALE-ONLY" not in ids
    ), "stale cache served despite missing freshness helper"
    assert len(entries) == 12, "committed registry not served on degraded import"
    assert ids == {f"COMP-{i:02d}" for i in range(12)}


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
