"""G5: strategy registry + R-1 re-baseline (TD-675).

- ``select_strategy`` picks by artifact shape (file → content-digest, directory
  → tree-digest) and honors a schema-validated ``drift_strategy`` override.
- ``_compute_entry_digest`` is enum-dispatched (no shell exec).
- R-1 (lead): a ``drift_strategy`` switch or a digest-version bump produces a
  RE-BASELINE, not a drift finding; a same-strategy content change still drifts.

Run targeted only:
    pytest tests/test_g5_strategy_rebaseline.py
"""

import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import yaml

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("aim_sot_detect_propose")
shadow = _load("aim_sot_shadow")


# --------------------------------------------------------------------------- #
# Pure unit tests — selection + dispatch
# --------------------------------------------------------------------------- #


def test_select_strategy_by_shape(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("x", encoding="utf-8")
    d = tmp_path / "d"
    d.mkdir()
    assert shadow.select_strategy({}, f) == "content-digest"
    assert shadow.select_strategy({}, d) == "tree-digest"


def test_select_strategy_override_wins(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("x", encoding="utf-8")
    assert shadow.select_strategy({"drift_strategy": "tree-digest"}, f) == "tree-digest"
    # A non-enum value is ignored by select_strategy (and rejected upstream by
    # verify S4) — never executed.
    assert shadow.select_strategy({"drift_strategy": "rm -rf /"}, f) == "content-digest"


def test_compute_entry_digest_dispatch(tmp_path):
    f = tmp_path / "f.py"
    f.write_text("hello", encoding="utf-8")
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("a", encoding="utf-8")
    content, _ = dp._compute_entry_digest("content-digest", f)
    tree, _ = dp._compute_entry_digest("tree-digest", d)
    assert content and len(content) == 8  # sha256(file)[:8], behavior-preserving
    assert tree.startswith("v1:")
    # temporal / git-ahead-behind: no content digest
    assert dp._compute_entry_digest("temporal", f)[0] is None


# --------------------------------------------------------------------------- #
# cmd_run harness (mirrors test_a3) — exercises R-1 re-baseline end to end
# --------------------------------------------------------------------------- #


def _fake_memory(monkeypatch, project_id):
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)


def _seed_cache(cache_dir: Path, project_id: str, registry_sha: str, components: dict):
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = project_id.replace("/", "__")
    path = cache_dir / f"sot_drift_{safe}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "project_id": project_id,
                "generated_at": "2020-01-01T00:00:00+00:00",
                "registry_sha": registry_sha,
                "components": components,
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(monkeypatch, tmp_path, registry):
    project_id = "proj-rebaseline"
    cache_dir = tmp_path / "drift-state"
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", cache_dir)
    _fake_memory(monkeypatch, project_id)
    # Avoid the 5b reindex import path (store unreachable in tests).
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    args = SimpleNamespace(
        registry=str(registry), as_json=True, limit=20, all=False, shadow=False
    )
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dp.cmd_run(args)
    assert rc == 0
    out = json.loads(buf.getvalue())
    safe = project_id.replace("/", "__")
    cache = json.loads((cache_dir / f"sot_drift_{safe}.json").read_text())
    return out, cache, project_id


def _write_registry(root: Path, entries) -> Path:
    sot = root / ".sot"
    sot.mkdir(parents=True, exist_ok=True)
    path = sot / "registry.yaml"
    path.write_text(
        yaml.safe_dump({"schema_version": "1", "entries": entries}), encoding="utf-8"
    )
    return path


def test_rebaseline_on_digest_version_bump(monkeypatch, tmp_path):
    """A stored tree-digest under an older digest_version → version bump → the
    entry re-baselines (no drift) and the record advances to the new version."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("a", encoding="utf-8")
    registry = _write_registry(
        tmp_path,
        [
            {
                "id": "PKG",
                "kind": "library",
                "boundary_type": "path",
                "sot_location": "pkg/",
                "owner": "@team",
                "description": "pkg",
            }
        ],
    )
    reg_sha = dp._registry_sha(registry)
    # Prior baseline under a *stale* digest_version → must re-baseline, not drift.
    _seed_cache(
        tmp_path / "drift-state",
        "proj-rebaseline",
        reg_sha,
        {
            "PKG": {
                "sot_location": "pkg/",
                "last_verified_at": "2020-01-01T00:00:00+00:00",
                "last_verified_sha": "v0:deadbeef",
                "last_verified_mtime": 1.0,
                "last_verified_size": 1,
                "drift_status": "clean",
                "drift_detail": None,
                "drift_strategy": "tree-digest",
                "digest_version": "v0",
            }
        },
    )
    out, cache, _ = _run(monkeypatch, tmp_path, registry)
    drift_ids = [p["entry_id"] for p in out["drift_proposals"]]
    assert "PKG" not in drift_ids  # re-baseline, NOT a drift finding
    rec = cache["components"]["PKG"]
    assert rec["digest_version"] == "v1"
    assert rec["drift_strategy"] == "tree-digest"
    assert rec["drift_status"] == "clean"
    assert rec["last_verified_sha"].startswith("v1:")


def test_rebaseline_on_strategy_switch(monkeypatch, tmp_path):
    """A directory previously baselined under content-digest, now defaulting to
    tree-digest → strategy switch → re-baseline, not drift."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("a", encoding="utf-8")
    registry = _write_registry(
        tmp_path,
        [
            {
                "id": "PKG",
                "kind": "library",
                "boundary_type": "path",
                "sot_location": "pkg/",
                "owner": "@team",
                "description": "pkg",
            }
        ],
    )
    reg_sha = dp._registry_sha(registry)
    _seed_cache(
        tmp_path / "drift-state",
        "proj-rebaseline",
        reg_sha,
        {
            "PKG": {
                "sot_location": "pkg/",
                "last_verified_at": "2020-01-01T00:00:00+00:00",
                "last_verified_sha": "abcd1234",
                "last_verified_mtime": 1.0,
                "last_verified_size": 1,
                "drift_status": "clean",
                "drift_detail": None,
                "drift_strategy": "content-digest",
                "digest_version": "",
            }
        },
    )
    out, cache, _ = _run(monkeypatch, tmp_path, registry)
    assert "PKG" not in [p["entry_id"] for p in out["drift_proposals"]]
    assert cache["components"]["PKG"]["drift_strategy"] == "tree-digest"


def test_same_strategy_content_change_still_drifts(monkeypatch, tmp_path):
    """Control: a genuine content change under the SAME strategy fires drift."""
    f = tmp_path / "doc.md"
    f.write_text("new content", encoding="utf-8")
    registry = _write_registry(
        tmp_path,
        [
            {
                "id": "DOC",
                "kind": "documentation",
                "boundary_type": "concern",
                "sot_location": "doc.md",
                "owner": "@team",
                "description": "doc",
            }
        ],
    )
    reg_sha = dp._registry_sha(registry)
    _seed_cache(
        tmp_path / "drift-state",
        "proj-rebaseline",
        reg_sha,
        {
            "DOC": {
                "sot_location": "doc.md",
                "last_verified_at": "2020-01-01T00:00:00+00:00",
                "last_verified_sha": "00000000",  # != current sha → drift
                "last_verified_mtime": 1.0,
                "last_verified_size": 1,
                "drift_status": "clean",
                "drift_detail": None,
                "drift_strategy": "content-digest",
                "digest_version": "",
            }
        },
    )
    out, _, _ = _run(monkeypatch, tmp_path, registry)
    assert "DOC" in [p["entry_id"] for p in out["drift_proposals"]]
