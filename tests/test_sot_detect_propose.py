"""
Tests for aim_sot_detect_propose — detect-propose engine (Item 3).

Coverage:
  T-DP01 — Location drift: missing path detected
  T-DP02 — Location drift: existing path → no drift
  T-DP03 — Temporal staleness: exceeds medium threshold (90d)
  T-DP04 — Temporal staleness: within threshold → None
  T-DP05 — Temporal staleness: high-volatility threshold (30d)
  T-DP06 — Temporal staleness: missing last_verified → None
  T-DP06b — Temporal staleness: YAML-native datetime.date — no crash
  T-DP07 — Content-hash drift: hash changed
  T-DP08 — Content-hash drift: hash matches → None
  T-DP09 — Content-hash drift: no baseline yet → None (cold-start)
  T-DP10 — Declaration-vs-reality (K1 trigger): hash changed → k1_trigger=True
  T-DP11 — Declaration-vs-reality: no hash change → None
  T-DP12 — Never-writes-the-registry invariant: static source scan (write-mode open,
           .write_text, .write_bytes) + behavioral bytes+mtime check
  T-DP13 — First-run bootstrap: stateless cap applied
  T-DP14 — First-run bootstrap: --all disables cap (limit=0)
  T-DP15 — First-run bootstrap: already-registered candidates filtered out
  T-DP16 — 5a cache: cold-start returns empty skeleton
  T-DP17 — 5a cache: atomic write + read round-trip
  T-DP18 — 5a cache: TTL throttle — clean + recent → skip
  T-DP18b — 5a cache: drifted component always re-checked
  T-DP18c — 5a cache: TTL expired → re-check
  T-DP19 — 5b reindex: graceful no-op when store is unreachable
  T-DP20 — 5b reindex: determinism — deletes existing records then re-stores
  T-DP20b — 5b reindex: machine-state fields excluded from stored content
  T-DP21 — cmd_run: JSON output shape (no-drift case) with project-id injected
  T-DP21b — cmd_run: drift fires (staleness_hash) — drift_proposals non-empty
  T-DP22 — sha change forces full re-check: clean+recent component IS re-checked
  T-DP23 — K1 fires on registry-edit run: hash baselines preserved

  H3 cycle-1 fixes (DD-A / DD-B / M1 / M5 / M6 + LOWs):
  T-DP24 — DD-A: cheap stat pre-check busts the TTL skip on artifact edit
  T-DP25 — DD-B: baseline held on drift + proposal re-fires; human reconfirm re-baselines
  T-DP26 — DD-B record rules (cold-start unverified/missing, hold, reconfirm, missing-wins)
  T-DP27 — M1: reindex failure does NOT advance registry_sha
  T-DP28 — M1: prepare-before-delete — no destroy on parse error / transiently-empty
  T-DP29 — M6/F-A2-9: reindex twice is idempotent through a stateful store schema
  T-DP30 — LOW: write releases the lock + cleans the temp file on error
  T-DP31 — M5: flat --registry path cannot trigger an unbounded discovery scan

All tests are hermetic (no network, tmp dirs, store mocked via injection points).
"""

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Module import (importlib pattern — no package install required)
# ---------------------------------------------------------------------------

_ENGINE_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "_ai-memory"
    / "skills"
    / "aim-sot"
    / "scripts"
    / "aim_sot_detect_propose.py"
)
_spec = importlib.util.spec_from_file_location("aim_sot_detect_propose", _ENGINE_SCRIPT)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_registry(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump({"schema_version": "1.0", "entries": entries}), encoding="utf-8"
    )


def _past_iso(days: int) -> str:
    """ISO 8601 date string N days in the past."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inject_project_id(project_id: str):
    """Context manager that injects a mock memory.project into sys.modules."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        mock_mod = MagicMock()
        mock_mod.resolve_project_id.return_value = project_id
        old = sys.modules.get("memory.project")
        sys.modules["memory.project"] = mock_mod
        try:
            yield mock_mod
        finally:
            if old is None:
                sys.modules.pop("memory.project", None)
            else:
                sys.modules["memory.project"] = old

    return _ctx()


# ---------------------------------------------------------------------------
# T-DP01 — Location drift: missing path detected
# ---------------------------------------------------------------------------


def test_location_drift_missing_path(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    result = dp._check_location_drift(
        {"id": "frontend", "sot_location": "frontend/"}, project_root
    )
    assert result is not None
    assert result["drift_type"] == "location"
    assert "frontend/" in result["root_cause"]
    assert "root_cause" in result
    assert "impact" in result
    assert "recommended_action" in result


# ---------------------------------------------------------------------------
# T-DP02 — Location drift: existing path → None
# ---------------------------------------------------------------------------


def test_location_drift_existing_path(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "frontend").mkdir(parents=True)
    result = dp._check_location_drift(
        {"id": "frontend", "sot_location": "frontend/"}, project_root
    )
    assert result is None


# ---------------------------------------------------------------------------
# T-DP03 — Temporal staleness: exceeds medium threshold (90d)
# ---------------------------------------------------------------------------


def test_temporal_staleness_over_threshold():
    entry = {"id": "docs", "sot_location": "docs/", "last_verified": _past_iso(100)}
    result = dp._check_temporal_staleness(entry)
    assert result is not None
    assert result["drift_type"] == "staleness_temporal"
    assert "100d" in result["root_cause"]


# ---------------------------------------------------------------------------
# T-DP04 — Temporal staleness: within threshold → None
# ---------------------------------------------------------------------------


def test_temporal_staleness_within_threshold():
    entry = {"id": "docs", "sot_location": "docs/", "last_verified": _past_iso(10)}
    result = dp._check_temporal_staleness(entry)
    assert result is None


# ---------------------------------------------------------------------------
# T-DP05 — Temporal staleness: high-volatility threshold (30d)
# ---------------------------------------------------------------------------


def test_temporal_staleness_high_volatility():
    entry = {
        "id": "api",
        "sot_location": "api/",
        "last_verified": _past_iso(35),
        "drift_check": "high",
    }
    result = dp._check_temporal_staleness(entry)
    assert result is not None
    assert "high" in result["root_cause"]


# ---------------------------------------------------------------------------
# T-DP06 — Temporal staleness: missing last_verified → None
# ---------------------------------------------------------------------------


def test_temporal_staleness_no_field():
    entry = {"id": "core", "sot_location": "core/"}
    result = dp._check_temporal_staleness(entry)
    assert result is None


# ---------------------------------------------------------------------------
# T-DP06b — Temporal staleness: YAML-native datetime.date — no crash
#
# An unquoted ``last_verified: 2026-06-01`` in YAML parses as datetime.date,
# not a string.  The engine must handle that without raising TypeError.
# ---------------------------------------------------------------------------


def test_temporal_staleness_yaml_native_date():
    """Unquoted YAML date (datetime.date) must not raise TypeError."""
    # Simulate what yaml.safe_load produces for an unquoted date field.
    raw_entry = yaml.safe_load(
        "id: docs\nsot_location: docs/\nlast_verified: 2020-01-01"
    )
    import datetime as _dt

    # Confirm YAML parsed it as a date object (not a string).
    assert isinstance(raw_entry["last_verified"], _dt.date)
    # 2020-01-01 is >1800d ago — staleness MUST fire, not crash.
    result = dp._check_temporal_staleness(raw_entry)
    assert result is not None, "Expected staleness drift, got None (or TypeError)"
    assert result["drift_type"] == "staleness_temporal"


# ---------------------------------------------------------------------------
# T-DP07 — Content-hash drift: hash changed
# ---------------------------------------------------------------------------


def test_content_hash_drift_changed(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    # sot_location is a file (spec §5: "sha256(file)[:8]")
    schema_file = project_root / "openapi.yaml"
    schema_file.write_text("original content", encoding="utf-8")
    entry = {"id": "api-contract", "sot_location": "openapi.yaml"}
    cache = {"components": {"api-contract": {"last_verified_sha": "deadbeef"}}}
    result = dp._check_content_hash_drift(entry, project_root, cache)
    assert result is not None
    assert result["drift_type"] == "staleness_hash"
    assert "deadbeef" in result["root_cause"]


# ---------------------------------------------------------------------------
# T-DP08 — Content-hash drift: hash matches → None
# ---------------------------------------------------------------------------


def test_content_hash_drift_no_change(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    schema_file = project_root / "openapi.yaml"
    schema_file.write_text("content", encoding="utf-8")
    actual_sha = dp._sha256_short(schema_file)
    entry = {"id": "api-contract", "sot_location": "openapi.yaml"}
    cache = {"components": {"api-contract": {"last_verified_sha": actual_sha}}}
    result = dp._check_content_hash_drift(entry, project_root, cache)
    assert result is None


# ---------------------------------------------------------------------------
# T-DP09 — Content-hash drift: no baseline → None (cold-start)
# ---------------------------------------------------------------------------


def test_content_hash_drift_no_baseline(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "openapi.yaml").write_text("content", encoding="utf-8")
    entry = {"id": "api-contract", "sot_location": "openapi.yaml"}
    cache = {"components": {}}
    result = dp._check_content_hash_drift(entry, project_root, cache)
    assert result is None


# ---------------------------------------------------------------------------
# T-DP10 — Declaration-vs-reality (K1 trigger): hash changed → k1_trigger=True
# ---------------------------------------------------------------------------


def test_declaration_reality_drift_k1_trigger(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    # File content has changed since last verification
    schema_file = project_root / "openapi.yaml"
    schema_file.write_text("changed content", encoding="utf-8")
    entry = {"id": "api-contract", "sot_location": "openapi.yaml"}
    cache = {"components": {"api-contract": {"last_verified_sha": "oldsha00"}}}
    result = dp._check_declaration_reality_drift(entry, project_root, cache)
    assert result is not None
    assert result["drift_type"] == "declaration_reality"
    assert result.get("k1_trigger") is True
    assert "oldsha00" in result["root_cause"]


# ---------------------------------------------------------------------------
# T-DP11 — Declaration-vs-reality: no hash change → None
# ---------------------------------------------------------------------------


def test_declaration_reality_no_change(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    schema_file = project_root / "openapi.yaml"
    schema_file.write_text("unchanged", encoding="utf-8")
    actual_sha = dp._sha256_short(schema_file)
    entry = {"id": "api-contract", "sot_location": "openapi.yaml"}
    cache = {"components": {"api-contract": {"last_verified_sha": actual_sha}}}
    result = dp._check_declaration_reality_drift(entry, project_root, cache)
    assert result is None


# ---------------------------------------------------------------------------
# T-DP12 — Never-writes-the-registry invariant
#
# (a) Static source scan: write-mode open() literals, .write_text(, and
#     .write_bytes( involving 'registry'. Drift-cache writes to .json are
#     expected — registry writes are the invariant under test.
# (b) Behavioral test: run cmd_run against a drifted entry; assert the
#     registry file's bytes AND mtime are unchanged afterwards.
# ---------------------------------------------------------------------------


def test_engine_never_writes_registry_static():
    """Static source scan — no write path touches registry."""
    import inspect

    src = inspect.getsource(dp)
    violations = []
    for i, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        has_registry = "registry" in line.lower()
        write_modes = ('"w"', "'w'", '"wb"', "'wb'", '"a"', "'a'", '"x"', "'x'")
        has_write_open = any(m in line for m in write_modes)
        has_write_method = ".write_text(" in line or ".write_bytes(" in line
        if has_registry and (has_write_open or has_write_method):
            violations.append((i, line.rstrip()))
    assert violations == [], "Engine opens registry in write mode:\n" + "\n".join(
        f"  line {lineno}: {code}" for lineno, code in violations
    )


def test_registry_not_written_behavioral(tmp_path, capsys):
    """cmd_run with drift must NOT modify the registry file (bytes + mtime)."""
    registry_path = tmp_path / ".sot" / "registry.yaml"
    entry = {
        "id": "docs",
        "sot_location": "docs/",
        "last_verified": _past_iso(200),  # triggers staleness_temporal drift
    }
    _write_registry(registry_path, [entry])
    (tmp_path / "docs").mkdir()

    before_bytes = registry_path.read_bytes()
    before_mtime = registry_path.stat().st_mtime

    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20

    with (
        _inject_project_id("proj"),
        patch.object(dp, "_find_registry", return_value=registry_path),
        patch.object(dp, "_project_root_from_registry", return_value=tmp_path),
        patch.object(
            dp,
            "_read_drift_cache",
            return_value={
                "schema_version": "1",
                "project_id": "proj",
                "generated_at": "",
                "registry_sha": "",
                "components": {},
            },
        ),
        patch.object(dp, "_write_drift_cache"),
        patch.object(
            dp, "_reindex_sot_entries", return_value=dp.ReindexResult(True, 0)
        ),
    ):
        result = dp.cmd_run(args)

    capsys.readouterr()
    assert result == 0
    assert registry_path.read_bytes() == before_bytes, "registry bytes changed"
    assert registry_path.stat().st_mtime == before_mtime, "registry mtime changed"


# ---------------------------------------------------------------------------
# T-DP13 — First-run bootstrap: stateless cap applied
# ---------------------------------------------------------------------------


def test_bootstrap_cap_applied():
    candidates = [
        {
            "sot_location": f"pkg{i}/",
            "id": f"pkg{i}",
            "boundary_type": "component",
            "confidence": "high",
            "inferred_from": "pyproject.toml",
        }
        for i in range(30)
    ]
    capped, deferred = dp._apply_cap(candidates, limit=20)
    assert len(capped) == 20
    assert deferred == 10


# ---------------------------------------------------------------------------
# T-DP14 — First-run bootstrap: --all disables cap (limit=0)
# ---------------------------------------------------------------------------


def test_bootstrap_no_cap():
    candidates = [
        {
            "sot_location": f"pkg{i}/",
            "id": f"pkg{i}",
            "boundary_type": "component",
            "confidence": "high",
            "inferred_from": "pyproject.toml",
        }
        for i in range(30)
    ]
    capped, deferred = dp._apply_cap(candidates, limit=0)
    assert len(capped) == 30
    assert deferred == 0


# ---------------------------------------------------------------------------
# T-DP15 — First-run bootstrap: already-registered candidates filtered out
# ---------------------------------------------------------------------------


def test_filter_registered_candidates():
    candidates = [
        {
            "sot_location": "frontend/",
            "id": "frontend",
            "boundary_type": "path",
            "confidence": "medium",
            "inferred_from": "top_level_directory",
        },
        {
            "sot_location": "backend/",
            "id": "backend",
            "boundary_type": "component",
            "confidence": "high",
            "inferred_from": "pyproject.toml",
        },
    ]
    existing = [{"id": "frontend", "sot_location": "frontend/"}]
    new_ones = dp._filter_new_candidates(candidates, existing)
    assert len(new_ones) == 1
    assert new_ones[0]["sot_location"] == "backend/"


# ---------------------------------------------------------------------------
# T-DP16 — 5a cache: cold-start returns empty skeleton
# ---------------------------------------------------------------------------


def test_drift_cache_cold_start(tmp_path):
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        cache = dp._read_drift_cache("test-project")
    assert cache["project_id"] == "test-project"
    assert cache["components"] == {}
    assert cache["registry_sha"] == ""
    assert "schema_version" in cache


# ---------------------------------------------------------------------------
# T-DP17 — 5a cache: atomic write + read round-trip
# ---------------------------------------------------------------------------


def test_drift_cache_write_read(tmp_path):
    data = {
        "schema_version": "1",
        "project_id": "myproj",
        "generated_at": _now_iso(),
        "registry_sha": "abc12345",
        "components": {
            "frontend": {
                "sot_location": "frontend/",
                "last_verified_at": _now_iso(),
                "last_verified_sha": "deadbeef",
                "drift_status": "clean",
                "drift_detail": None,
            }
        },
    }
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        dp._write_drift_cache("myproj", data)
        readback = dp._read_drift_cache("myproj")
    assert readback["project_id"] == "myproj"
    assert readback["registry_sha"] == "abc12345"
    assert readback["components"]["frontend"]["drift_status"] == "clean"


# ---------------------------------------------------------------------------
# T-DP18 — 5a cache: TTL throttle — clean + recent → skip
# ---------------------------------------------------------------------------


def test_should_skip_recent_clean():
    cache = {
        "components": {
            "frontend": {
                "last_verified_at": _now_iso(),
                "drift_status": "clean",
            }
        }
    }
    assert dp._should_skip_component("frontend", cache) is True


# ---------------------------------------------------------------------------
# T-DP18b — 5a cache: drifted component always re-checked
# ---------------------------------------------------------------------------


def test_should_not_skip_drifted():
    cache = {
        "components": {
            "frontend": {
                "last_verified_at": _now_iso(),
                "drift_status": "drifted",
            }
        }
    }
    assert dp._should_skip_component("frontend", cache) is False


# ---------------------------------------------------------------------------
# T-DP18c — 5a cache: TTL expired → re-check
# ---------------------------------------------------------------------------


def test_should_not_skip_stale_cache():
    old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    cache = {
        "components": {
            "frontend": {
                "last_verified_at": old_ts,
                "drift_status": "clean",
            }
        }
    }
    assert dp._should_skip_component("frontend", cache) is False


# ---------------------------------------------------------------------------
# T-DP19 — 5b reindex: graceful no-op when store is unreachable
# ---------------------------------------------------------------------------


def test_reindex_graceful_store_unreachable(tmp_path):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    _write_registry(registry_path, [{"id": "core", "sot_location": "src/"}])
    bad_client = MagicMock()
    bad_client.scroll.side_effect = Exception("Connection refused")
    # _storage injected so a real MemoryStorage is never constructed; the scroll
    # failure inside the reindex lock must surface as a failed (not silent-0)
    # result and must NOT have deleted anything.
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        result = dp._reindex_sot_entries(
            registry_path,
            "test-proj",
            _qdrant_client=bad_client,
            _storage=MagicMock(),
        )
    assert result.ok is False
    assert result.stored == 0
    bad_client.delete.assert_not_called()


# ---------------------------------------------------------------------------
# T-DP20 — 5b reindex: determinism — deletes existing records then re-stores
# ---------------------------------------------------------------------------


def test_reindex_deterministic(tmp_path):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    entries = [
        {"id": "frontend", "sot_location": "frontend/", "description": "UI"},
        {"id": "backend", "sot_location": "backend/", "description": "API"},
    ]
    _write_registry(registry_path, entries)

    # Existing point with id 42 in the store
    existing_pt = MagicMock()
    existing_pt.id = 42
    mock_client = MagicMock()
    mock_client.scroll.side_effect = [([existing_pt], None)]

    mock_storage = MagicMock()
    mock_storage.store_memory.return_value = {"status": "stored"}

    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        result = dp._reindex_sot_entries(
            registry_path,
            "test-proj",
            _qdrant_client=mock_client,
            _storage=mock_storage,
        )
    # Old point deleted
    mock_client.delete.assert_called_once()
    assert mock_client.delete.call_args[1]["points_selector"] == [42]
    # Both entries re-stored
    assert mock_storage.store_memory.call_count == 2
    assert result.ok is True
    assert result.stored == 2


# ---------------------------------------------------------------------------
# T-DP20b — 5b reindex: machine-state fields excluded from stored content
# ---------------------------------------------------------------------------


def test_reindex_excludes_machine_state_fields(tmp_path):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    entry = {
        "id": "core",
        "sot_location": "src/",
        "description": "Core lib",
        "last_verified_at": "2026-01-01T00:00:00Z",  # must NOT appear in stored content
        "drift_status": "clean",  # must NOT appear in stored content
        "last_verified_sha": "abc00001",  # must NOT appear
    }
    _write_registry(registry_path, [entry])

    mock_client = MagicMock()
    mock_client.scroll.side_effect = [([], None)]
    mock_storage = MagicMock()
    mock_storage.store_memory.return_value = {"status": "stored"}

    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        dp._reindex_sot_entries(
            registry_path, "proj", _qdrant_client=mock_client, _storage=mock_storage
        )

    call_kwargs = mock_storage.store_memory.call_args[1]
    content = json.loads(call_kwargs["content"])
    assert "last_verified_at" not in content
    assert "drift_status" not in content
    assert "last_verified_sha" not in content
    assert content["id"] == "core"
    assert content["description"] == "Core lib"
    assert call_kwargs["group_id"] == "proj"
    assert "aim_sot_reindex_" in call_kwargs["session_id"]


# ---------------------------------------------------------------------------
# T-DP21 — cmd_run: JSON output shape with project-id injected
# ---------------------------------------------------------------------------


def test_cmd_run_json_output(tmp_path, capsys):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    entries = [
        {
            "id": "frontend",
            "sot_location": "frontend/",
            "last_verified": _past_iso(5),
        }
    ]
    _write_registry(registry_path, entries)
    (tmp_path / "frontend").mkdir()

    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20

    with (
        _inject_project_id("test-project"),
        patch.object(dp, "_find_registry", return_value=registry_path),
        patch.object(dp, "_project_root_from_registry", return_value=tmp_path),
        patch.object(
            dp,
            "_read_drift_cache",
            return_value={
                "schema_version": "1",
                "project_id": "test-project",
                "generated_at": "",
                "registry_sha": "",
                "components": {},
            },
        ),
        patch.object(dp, "_write_drift_cache"),
        patch.object(dp, "_registry_sha", return_value="newsha01"),
        patch.object(
            dp, "_reindex_sot_entries", return_value=dp.ReindexResult(True, 1)
        ),
    ):
        result = dp.cmd_run(args)

    captured = capsys.readouterr()
    assert result == 0
    out = json.loads(captured.out)
    assert "drift_proposals" in out
    assert "candidate_proposals" in out
    assert "deferred_count" in out
    assert out["project_id"] == "test-project"


# ---------------------------------------------------------------------------
# T-DP21b — cmd_run: drift fires (staleness_hash) — drift_proposals non-empty
# ---------------------------------------------------------------------------


def test_cmd_run_json_output_drift_fires(tmp_path, capsys):
    """cmd_run emits a non-empty drift_proposals when staleness_hash is detected."""
    registry_path = tmp_path / ".sot" / "registry.yaml"
    schema_file = tmp_path / "openapi.yaml"
    schema_file.write_text("current content", encoding="utf-8")

    entries = [{"id": "api-contract", "sot_location": "openapi.yaml"}]
    _write_registry(registry_path, entries)

    # Cache has a stale sha for this component → staleness_hash fires.
    # drift_status="drifted" ensures TTL throttle doesn't suppress the re-check.
    # components are NOT cleared on registry sha change (force_recheck approach),
    # so the "deadbeef" baseline is preserved and staleness_hash fires correctly.
    seeded_cache = {
        "schema_version": "1",
        "project_id": "test-project",
        "generated_at": "",
        "registry_sha": "",
        "components": {
            "api-contract": {
                "sot_location": "openapi.yaml",
                "last_verified_at": _now_iso(),
                "last_verified_sha": "deadbeef",  # stale — real sha differs
                "drift_status": "drifted",  # non-clean → always re-check
            }
        },
    }

    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20

    with (
        _inject_project_id("test-project"),
        patch.object(dp, "_find_registry", return_value=registry_path),
        patch.object(dp, "_project_root_from_registry", return_value=tmp_path),
        patch.object(dp, "_read_drift_cache", return_value=seeded_cache),
        patch.object(dp, "_write_drift_cache"),
        patch.object(
            dp, "_reindex_sot_entries", return_value=dp.ReindexResult(True, 0)
        ),
    ):
        result = dp.cmd_run(args)

    captured = capsys.readouterr()
    assert result == 0
    out = json.loads(captured.out)
    assert len(out["drift_proposals"]) > 0, "Expected drift_proposals to be non-empty"
    drift_types = [d["drift_type"] for p in out["drift_proposals"] for d in p["drifts"]]
    assert "staleness_hash" in drift_types


# ---------------------------------------------------------------------------
# T-DP22 — sha change forces full re-check: clean+recent component IS re-checked
# ---------------------------------------------------------------------------


def test_sha_change_forces_full_recheck(tmp_path, capsys):
    """When the registry sha differs from the cached sha, force_recheck=True
    bypasses the TTL so even clean+recent entries are re-checked this run."""
    registry_path = tmp_path / ".sot" / "registry.yaml"
    # Entry points to a nonexistent path → location drift if re-checked.
    entry = {"id": "gone", "sot_location": "gone/"}
    _write_registry(registry_path, [entry])

    # Cache marks "gone" as clean+recent — would normally be skipped.
    stale_cache = {
        "schema_version": "1",
        "project_id": "proj",
        "generated_at": _now_iso(),
        "registry_sha": "oldsha00",  # differs from actual registry file sha
        "components": {
            "gone": {
                "last_verified_at": _now_iso(),
                "drift_status": "clean",
            }
        },
    }

    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20

    with (
        _inject_project_id("proj"),
        patch.object(dp, "_find_registry", return_value=registry_path),
        patch.object(dp, "_project_root_from_registry", return_value=tmp_path),
        patch.object(dp, "_read_drift_cache", return_value=stale_cache),
        patch.object(dp, "_write_drift_cache"),
        patch.object(
            dp, "_reindex_sot_entries", return_value=dp.ReindexResult(True, 0)
        ),
    ):
        result = dp.cmd_run(args)

    assert result == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    # Location drift on "gone" MUST appear — force-rechecked despite being clean+recent.
    drift_entry_ids = [p["entry_id"] for p in out["drift_proposals"]]
    assert "gone" in drift_entry_ids, (
        "Expected 'gone' in drift_proposals (sha-change should force re-check), "
        f"got: {drift_entry_ids}"
    )


# ---------------------------------------------------------------------------
# T-DP23 — K1 fires on registry-edit run: hash baselines preserved (not absorbed)
# ---------------------------------------------------------------------------


def test_k1_fires_on_registry_edit_baseline_preserved(tmp_path, capsys):
    """Registry sha change + stale hash baseline → staleness_hash AND k1_trigger
    BOTH fire on that run.  Verifies the force_recheck approach preserves
    last_verified_sha so K1 is not silently absorbed (spec §5 mandatory re-confirm).

    The component is marked clean+recent (TTL would skip it) to confirm
    force_recheck overrides the throttle.  The stale sha "deadbeef" differs from
    the file's real sha, so both hash-drift types fire.
    """
    registry_path = tmp_path / ".sot" / "registry.yaml"
    schema_file = tmp_path / "openapi.yaml"
    schema_file.write_text("post-edit content", encoding="utf-8")

    entries = [{"id": "api-schema", "sot_location": "openapi.yaml"}]
    _write_registry(registry_path, entries)

    # Component is clean+recent — TTL would skip it without force_recheck.
    # last_verified_sha="deadbeef" is stale relative to the file's real sha.
    seeded_cache = {
        "schema_version": "1",
        "project_id": "test-project",
        "generated_at": "",
        "registry_sha": "oldsha",  # differs from "newsha" → reg_changed=True
        "components": {
            "api-schema": {
                "sot_location": "openapi.yaml",
                "last_verified_at": _now_iso(),
                "last_verified_sha": "deadbeef",  # stale — real sha differs
                "drift_status": "clean",  # would be TTL-skipped without force_recheck
            }
        },
    }

    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20

    with (
        _inject_project_id("test-project"),
        patch.object(dp, "_find_registry", return_value=registry_path),
        patch.object(dp, "_project_root_from_registry", return_value=tmp_path),
        patch.object(dp, "_read_drift_cache", return_value=seeded_cache),
        patch.object(dp, "_write_drift_cache"),
        patch.object(
            dp, "_reindex_sot_entries", return_value=dp.ReindexResult(True, 0)
        ),
        patch.object(dp, "_registry_sha", return_value="newsha"),
    ):
        result = dp.cmd_run(args)

    captured = capsys.readouterr()
    assert result == 0
    out = json.loads(captured.out)
    assert (
        len(out["drift_proposals"]) > 0
    ), "Expected drift_proposals — hash baselines must survive registry-edit"
    all_drifts = [d for p in out["drift_proposals"] for d in p["drifts"]]
    drift_types = [d["drift_type"] for d in all_drifts]
    assert (
        "staleness_hash" in drift_types
    ), f"staleness_hash not raised; got {drift_types}"
    assert (
        "declaration_reality" in drift_types
    ), f"declaration_reality/K1 not raised; got {drift_types}"
    k1_flags = [
        d.get("k1_trigger")
        for d in all_drifts
        if d["drift_type"] == "declaration_reality"
    ]
    assert any(k1_flags), "K1 trigger must be set on declaration_reality drift"


# ===========================================================================
# H3 cycle-1 fixes — DD-A / DD-B / M1 / M5 / M6 + engine LOWs
# ===========================================================================


def _run_cmd_real_cache(
    registry_path, cache_dir, capsys, *, project_id="proj", reindex=None
):
    """Drive cmd_run with a real (persisted) 5a cache under ``cache_dir``.

    Returns (return_code, parsed_json_output).  The reindex is stubbed so no
    real memory store is touched; everything else runs for real.
    """
    if reindex is None:
        reindex = dp.ReindexResult(True, 0)
    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20
    with (
        _inject_project_id(project_id),
        patch.object(dp, "_DRIFT_CACHE_DIR", cache_dir),
        patch.object(dp, "_reindex_sot_entries", return_value=reindex),
    ):
        rc = dp.cmd_run(args)
    return rc, json.loads(capsys.readouterr().out)


def _read_cache(cache_dir, project_id="proj"):
    with patch.object(dp, "_DRIFT_CACHE_DIR", cache_dir):
        return dp._read_drift_cache(project_id)


# ---------------------------------------------------------------------------
# T-DP24 — DD-A: cheap stat pre-check busts the TTL skip on artifact edit
# ---------------------------------------------------------------------------


def test_dd_a_stat_busts_ttl_on_edit(tmp_path):
    artifact = tmp_path / "api.yaml"
    artifact.write_text("v1", encoding="utf-8")
    st = artifact.stat()
    cache = {
        "components": {
            "api": {
                "sot_location": "api.yaml",
                "last_verified_at": _now_iso(),
                "drift_status": "clean",
                "last_verified_mtime": st.st_mtime,
                "last_verified_size": st.st_size,
            }
        }
    }
    # Unchanged clean+recent → skip honoured.
    assert dp._should_skip_component("api", cache, tmp_path) is True
    # Edit within the TTL (size + mtime change) → must NOT skip.
    artifact.write_text("v1 modified longer content", encoding="utf-8")
    assert dp._should_skip_component("api", cache, tmp_path) is False


def test_dd_a_artifact_edit_within_ttl_detected(tmp_path, capsys):
    """A clean+recent entry whose artifact was edited within the 7d TTL must
    still surface drift (the pre-DD-A skip-before-hash would have hidden it)."""
    cache_dir = tmp_path / "driftcache"
    registry_path = tmp_path / ".sot" / "registry.yaml"
    artifact = tmp_path / "openapi.yaml"
    artifact.write_text("v1", encoding="utf-8")
    _write_registry(registry_path, [{"id": "api", "sot_location": "openapi.yaml"}])

    st = artifact.stat()
    # Seed a clean+recent baseline for the *original* content, then edit it.
    seeded = {
        "schema_version": "1",
        "project_id": "proj",
        "generated_at": "",
        "registry_sha": dp._registry_sha(registry_path),  # no reg change this run
        "components": {
            "api": {
                "sot_location": "openapi.yaml",
                "last_verified_at": _now_iso(),
                "last_verified_sha": dp._sha256_short(artifact),
                "last_verified_mtime": st.st_mtime,
                "last_verified_size": st.st_size,
                "drift_status": "clean",
            }
        },
    }
    with patch.object(dp, "_DRIFT_CACHE_DIR", cache_dir):
        dp._write_drift_cache("proj", seeded)

    artifact.write_text("v2 substantially different content", encoding="utf-8")
    _, out = _run_cmd_real_cache(registry_path, cache_dir, capsys)
    types = [d["drift_type"] for p in out["drift_proposals"] for d in p["drifts"]]
    assert (
        "staleness_hash" in types
    ), "clean+recent entry edited within TTL must still be re-checked (DD-A)"


# ---------------------------------------------------------------------------
# T-DP25 — DD-B: baseline held on drift + proposal re-fires; human reconfirm
# ---------------------------------------------------------------------------


def test_dd_b_hold_baseline_and_refire(tmp_path, capsys):
    cache_dir = tmp_path / "driftcache"
    registry_path = tmp_path / ".sot" / "registry.yaml"
    artifact = tmp_path / "openapi.yaml"
    artifact.write_text("v1", encoding="utf-8")
    _write_registry(
        registry_path,
        [{"id": "api", "sot_location": "openapi.yaml", "last_verified": _past_iso(30)}],
    )

    # Run 1 — cold-start establishes a baseline; drift_status=unverified.
    _run_cmd_real_cache(registry_path, cache_dir, capsys)
    rec1 = _read_cache(cache_dir)["components"]["api"]
    assert rec1["drift_status"] == "unverified"
    baseline_sha = rec1["last_verified_sha"]
    assert baseline_sha

    # Edit the artifact only (no registry change) — drift must fire, baseline held.
    artifact.write_text("v2 different content", encoding="utf-8")
    _, out2 = _run_cmd_real_cache(registry_path, cache_dir, capsys)
    types2 = [d["drift_type"] for p in out2["drift_proposals"] for d in p["drifts"]]
    assert "staleness_hash" in types2
    rec2 = _read_cache(cache_dir)["components"]["api"]
    assert rec2["drift_status"] == "drifted"
    assert rec2["last_verified_sha"] == baseline_sha, "baseline must be HELD on drift"

    # Re-run with no change — the proposal must re-fire (baseline still held).
    _, out3 = _run_cmd_real_cache(registry_path, cache_dir, capsys)
    types3 = [d["drift_type"] for p in out3["drift_proposals"] for d in p["drifts"]]
    assert "staleness_hash" in types3, "un-acted proposal must re-fire next run"
    assert _read_cache(cache_dir)["components"]["api"]["last_verified_sha"] == (
        baseline_sha
    )


def test_dd_b_human_reconfirm_rebaselines(tmp_path, capsys):
    cache_dir = tmp_path / "driftcache"
    registry_path = tmp_path / ".sot" / "registry.yaml"
    artifact = tmp_path / "openapi.yaml"
    artifact.write_text("current content", encoding="utf-8")
    # Human bumps last_verified to today — newer than the 30d-old machine check.
    _write_registry(
        registry_path,
        [{"id": "api", "sot_location": "openapi.yaml", "last_verified": _past_iso(0)}],
    )

    old_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    seeded = {
        "schema_version": "1",
        "project_id": "proj",
        "generated_at": "",
        "registry_sha": "stale",  # forces reg_changed → force_recheck
        "components": {
            "api": {
                "sot_location": "openapi.yaml",
                "last_verified_at": old_at,
                "last_verified_sha": "oldbase0",  # differs from current file
                "drift_status": "drifted",
            }
        },
    }
    with patch.object(dp, "_DRIFT_CACHE_DIR", cache_dir):
        dp._write_drift_cache("proj", seeded)

    _run_cmd_real_cache(registry_path, cache_dir, capsys)
    rec = _read_cache(cache_dir)["components"]["api"]
    assert rec["drift_status"] == "clean", "human re-confirm must re-baseline to clean"
    assert rec["last_verified_sha"] == dp._sha256_short(artifact)


# ---------------------------------------------------------------------------
# T-DP26 — DD-B record rules (unit)
# ---------------------------------------------------------------------------


def test_compute_record_cold_start_unverified():
    rec = dp._compute_component_record(
        prior=None,
        drifts=[],
        current_sha="aaaa1111",
        mtime=1.0,
        size=10,
        loc="x.yaml",
        now_iso=_now_iso(),
        human_reconfirmed=False,
    )
    assert rec["drift_status"] == "unverified"
    assert rec["last_verified_sha"] == "aaaa1111"


def test_compute_record_cold_start_missing():
    rec = dp._compute_component_record(
        prior=None,
        drifts=[{"drift_type": "location"}],
        current_sha=None,
        mtime=None,
        size=None,
        loc="gone/",
        now_iso=_now_iso(),
        human_reconfirmed=False,
    )
    assert rec["drift_status"] == "missing"


def test_compute_record_holds_on_drift():
    prior = {
        "last_verified_at": "2026-01-01T00:00:00+00:00",
        "last_verified_sha": "oldbase0",
        "last_verified_mtime": 1.0,
        "last_verified_size": 5,
    }
    rec = dp._compute_component_record(
        prior=prior,
        drifts=[{"drift_type": "staleness_hash"}],
        current_sha="newsha00",
        mtime=2.0,
        size=9,
        loc="x.yaml",
        now_iso=_now_iso(),
        human_reconfirmed=False,
    )
    assert rec["drift_status"] == "drifted"
    assert rec["last_verified_sha"] == "oldbase0"  # held
    assert rec["last_verified_at"] == "2026-01-01T00:00:00+00:00"  # not refreshed


def test_compute_record_reconfirm_advances():
    prior = {"last_verified_at": "2026-01-01T00:00:00+00:00", "last_verified_sha": "o"}
    rec = dp._compute_component_record(
        prior=prior,
        drifts=[{"drift_type": "staleness_hash"}],
        current_sha="newsha00",
        mtime=2.0,
        size=9,
        loc="x.yaml",
        now_iso=_now_iso(),
        human_reconfirmed=True,
    )
    assert rec["drift_status"] == "clean"
    assert rec["last_verified_sha"] == "newsha00"


def test_compute_record_missing_overrides_reconfirm():
    """A human cannot re-confirm a now-missing artifact as clean."""
    prior = {"last_verified_at": "2026-01-01T00:00:00+00:00", "last_verified_sha": "o"}
    rec = dp._compute_component_record(
        prior=prior,
        drifts=[{"drift_type": "location"}],
        current_sha=None,
        mtime=None,
        size=None,
        loc="gone/",
        now_iso=_now_iso(),
        human_reconfirmed=True,
    )
    assert rec["drift_status"] == "missing"


def test_human_reconfirmed_signal():
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    assert dp._human_reconfirmed({"last_verified": _past_iso(0)}, old) is True
    assert dp._human_reconfirmed({"last_verified": _past_iso(20)}, old) is False
    assert dp._human_reconfirmed({}, old) is False
    assert dp._human_reconfirmed({"last_verified": _past_iso(0)}, "") is False


# ---------------------------------------------------------------------------
# T-DP27 — M1: reindex failure does NOT advance registry_sha
# ---------------------------------------------------------------------------


def test_reindex_failure_holds_registry_sha(tmp_path, capsys):
    cache_dir = tmp_path / "driftcache"
    registry_path = tmp_path / ".sot" / "registry.yaml"
    (tmp_path / "x.yaml").write_text("c", encoding="utf-8")
    _write_registry(
        registry_path,
        [{"id": "api", "sot_location": "x.yaml", "last_verified": _past_iso(5)}],
    )

    # Reindex fails → registry_sha must stay empty so the rebuild retries.
    _run_cmd_real_cache(
        registry_path, cache_dir, capsys, reindex=dp.ReindexResult(False, 0)
    )
    assert _read_cache(cache_dir)["registry_sha"] == ""

    # Reindex succeeds → registry_sha advances to the file's sha.
    _run_cmd_real_cache(
        registry_path, cache_dir, capsys, reindex=dp.ReindexResult(True, 1)
    )
    assert _read_cache(cache_dir)["registry_sha"] == dp._registry_sha(registry_path)


# ---------------------------------------------------------------------------
# T-DP28 — M1: prepare-before-delete (no destroy on parse error / empty)
# ---------------------------------------------------------------------------


def test_reindex_no_delete_on_parse_error(tmp_path):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("entries: [unclosed", encoding="utf-8")  # invalid YAML
    mock_client = MagicMock()
    mock_storage = MagicMock()
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        result = dp._reindex_sot_entries(
            registry_path, "proj", _qdrant_client=mock_client, _storage=mock_storage
        )
    assert result.ok is False
    mock_client.scroll.assert_not_called()
    mock_client.delete.assert_not_called()  # existing points preserved


def test_reindex_empty_registry_preserves_existing(tmp_path):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    _write_registry(registry_path, [])  # zero entries
    mock_client = MagicMock()
    mock_storage = MagicMock()
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        result = dp._reindex_sot_entries(
            registry_path, "proj", _qdrant_client=mock_client, _storage=mock_storage
        )
    assert result.ok is True
    assert result.stored == 0
    mock_client.delete.assert_not_called()  # did NOT wipe on transiently-empty


# ---------------------------------------------------------------------------
# T-DP29 — M6/F-A2-9: reindex twice is idempotent through a real store schema
# ---------------------------------------------------------------------------


class _StatefulStore:
    """Stateful fake of the qdrant client + storage that mimics the reindex
    contract: store assigns a fresh id each call (as the real store would),
    delete removes by id, scroll returns current ids.  Running reindex twice
    must converge to exactly N points — no duplicate accumulation (I5/F-A2-9)."""

    def __init__(self):
        self.points: dict = {}
        self._next = 0

    # qdrant client surface
    def scroll(self, **kwargs):
        pts = [type("P", (), {"id": i})() for i in self.points]
        return pts, None

    def delete(self, **kwargs):
        for i in list(kwargs["points_selector"]):
            self.points.pop(i, None)

    # storage surface
    def store_memory(self, **kwargs):
        pid = self._next
        self._next += 1
        self.points[pid] = kwargs["content"]
        return {"status": "stored"}


def test_reindex_twice_idempotent(tmp_path):
    registry_path = tmp_path / ".sot" / "registry.yaml"
    entries = [
        {"id": f"c{i}", "sot_location": f"c{i}/", "description": str(i)}
        for i in range(3)
    ]
    _write_registry(registry_path, entries)
    store = _StatefulStore()
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        r1 = dp._reindex_sot_entries(
            registry_path, "proj", _qdrant_client=store, _storage=store
        )
        r2 = dp._reindex_sot_entries(
            registry_path, "proj", _qdrant_client=store, _storage=store
        )
    assert r1.ok and r2.ok
    assert r1.stored == 3 and r2.stored == 3
    assert len(store.points) == 3, "duplicate sot_entry points accumulated"


# ---------------------------------------------------------------------------
# T-DP30 — LOW: write releases the lock + cleans the temp file on error
# ---------------------------------------------------------------------------


def test_write_drift_cache_releases_lock_and_cleans_tmp_on_error(tmp_path):
    data = {"schema_version": "1", "project_id": "proj", "components": {}}
    with patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path):
        with (
            patch("os.replace", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            dp._write_drift_cache("proj", data)
        # No orphan .tmp left behind (F-A2-7).
        assert list(tmp_path.glob("*.tmp")) == []
        # Lock was released in finally → a subsequent write succeeds (F-A2-10).
        dp._write_drift_cache("proj", data)
        readback = dp._read_drift_cache("proj")
    assert readback["project_id"] == "proj"


# ---------------------------------------------------------------------------
# T-DP31 — M5: flat --registry path cannot trigger an unbounded scan
# ---------------------------------------------------------------------------


def test_project_root_conforming_vs_flat(tmp_path):
    conforming = tmp_path / ".sot" / "registry.yaml"
    assert dp._project_root_from_registry(conforming) == tmp_path
    flat = tmp_path / "registry.yaml"
    assert dp._project_root_from_registry(flat) is None


def test_flat_registry_skips_discovery(tmp_path, capsys):
    registry_path = tmp_path / "registry.yaml"  # no .sot parent
    registry_path.write_text(
        yaml.dump(
            {
                "schema_version": "1.0",
                "entries": [
                    {
                        "id": "api",
                        "sot_location": "x.yaml",
                        "last_verified": _past_iso(5),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "x.yaml").write_text("c", encoding="utf-8")

    args = MagicMock()
    args.registry = str(registry_path)
    args.as_json = True
    args.all = False
    args.limit = 20
    with (
        _inject_project_id("proj"),
        patch.object(dp, "_DRIFT_CACHE_DIR", tmp_path / "dc"),
        patch.object(
            dp, "_reindex_sot_entries", return_value=dp.ReindexResult(True, 0)
        ),
        patch.object(dp, "_discover_candidates") as mock_disc,
    ):
        rc = dp.cmd_run(args)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    mock_disc.assert_not_called()  # no unbounded scan on a flat path
    assert out["candidate_proposals"] == []
