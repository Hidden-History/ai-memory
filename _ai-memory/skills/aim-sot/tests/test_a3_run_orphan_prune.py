"""A3: detect-propose run prunes 5a drift-cache orphans.

``run`` seeds the 5a cache from the prior record and adds the current registry's
components, but previously left records for ids no longer in the registry in
place (F-ENG-3). That diverges from the 5b reindex (which prunes) and lets a
stale baseline resurface if an id is later re-added. ``run`` now prunes the 5a
cache to exactly the committed registry's component ids.

Run targeted only:
    pytest tests/test_a3_run_orphan_prune.py
"""

import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
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


def _write_registry(root: Path, ids) -> Path:
    entries = [
        {
            "id": cid,
            "kind": "module",
            "owner": "team-platform",
            "sot_location": f"src/{cid}.py",
            "status": "active",
        }
        for cid in ids
    ]
    sot_dir = root / ".sot"
    sot_dir.mkdir(parents=True, exist_ok=True)
    path = sot_dir / "registry.yaml"
    path.write_text(yaml.safe_dump({"entries": entries}), encoding="utf-8")
    return path


def _seed_cache(cache_dir: Path, project_id: str, registry_sha: str, comp_ids) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_id = project_id.replace("/", "__")
    path = cache_dir / f"sot_drift_{safe_id}.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "project_id": project_id,
                "generated_at": "",
                "registry_sha": registry_sha,
                "components": {
                    cid: {
                        "last_verified_sha": "",
                        "last_verified_at": "",
                        "drift_status": "unverified",
                        "sot_location": f"src/{cid}.py",
                    }
                    for cid in comp_ids
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_run_prunes_orphan_components(monkeypatch, tmp_path):
    project_id = "lane-a-a3"
    registry = _write_registry(tmp_path, ids=["C1", "C2"])

    cache_dir = tmp_path / "drift-state"
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", cache_dir)

    # Seed registry_sha == current so reg_changed is False (no 5b reindex attempt,
    # which would need the memory stack). Cache holds an ORPHAN absent from the
    # committed registry.
    current_sha = dp._registry_sha(registry)
    cache_path = _seed_cache(
        cache_dir, project_id, current_sha, comp_ids=["C1", "C2", "ORPHAN"]
    )

    # Fake the memory stack so project_id resolves without a real install.
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)

    args = SimpleNamespace(registry=str(registry), as_json=True, limit=20, all=False)
    rc = dp.cmd_run(args)
    assert rc == 0

    written = json.loads(cache_path.read_text(encoding="utf-8"))
    comp_ids = set(written["components"].keys())

    assert comp_ids == {"C1", "C2"}, f"orphan not pruned: {comp_ids}"
    assert "ORPHAN" not in comp_ids


def test_run_keeps_throttle_skipped_components(monkeypatch, tmp_path):
    """A-FIX-2: the 5a prune keeps components that ARE in the committed registry but
    were throttle-skipped this run (clean + recent + unchanged) — only true orphans
    are dropped. Exercises seed-from-prior → loop-skips → prune-keeps."""
    project_id = "lane-a-a3-keep"
    registry = _write_registry(tmp_path, ids=["KEEP"])

    # Create KEEP's artifact so the DD-A stat pre-check in _should_skip_component
    # passes — mtime/size must match the cached baseline for the throttle to hold.
    artifact = tmp_path / "src" / "KEEP.py"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("# KEEP\n", encoding="utf-8")
    mtime, size = dp._stat_mtime_size(artifact)

    cache_dir = tmp_path / "drift-state"
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", cache_dir)

    # registry_sha == current → reg_changed False (force_recheck stays off so the
    # throttle skip can engage; no 5b reindex attempt that would need the stack).
    current_sha = dp._registry_sha(registry)
    recent = datetime.now(timezone.utc).isoformat()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"sot_drift_{project_id}.json"
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "project_id": project_id,
                "generated_at": "",
                "registry_sha": current_sha,
                "components": {
                    # In-registry, clean, recent, artifact unchanged → throttle SKIP.
                    "KEEP": {
                        "last_verified_sha": "",
                        "last_verified_at": recent,
                        "last_verified_mtime": mtime,
                        "last_verified_size": size,
                        "drift_status": "clean",
                        "sot_location": "src/KEEP.py",
                    },
                    # Absent from the committed registry → ORPHAN, must be pruned.
                    "ORPHAN": {
                        "last_verified_sha": "",
                        "last_verified_at": recent,
                        "drift_status": "clean",
                        "sot_location": "src/ORPHAN.py",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    # Fake the memory stack so project_id resolves without a real install.
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)

    args = SimpleNamespace(registry=str(registry), as_json=True, limit=20, all=False)
    rc = dp.cmd_run(args)
    assert rc == 0

    written = json.loads(cache_path.read_text(encoding="utf-8"))
    comp_ids = set(written["components"].keys())

    assert (
        "KEEP" in comp_ids
    ), f"throttle-skipped in-registry component dropped: {comp_ids}"
    assert "ORPHAN" not in comp_ids, f"orphan not pruned: {comp_ids}"
    assert comp_ids == {"KEEP"}
