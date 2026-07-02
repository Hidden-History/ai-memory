"""R1 + R3 + R4: hot/cold discovery split, exclude-walk consistency, and the
BP-051 boundary/size-guard proposals in ``aim_sot_detect_propose.py``.

R1 (BP-047) — drift runs every session (hot); the discovery walk (cold) runs
only when the internal cadence gate is due (TTL 24 h OR 20 sessions) or forced
via ``--discover``; ``--drift-only`` forces a skip.  The gate is internal so the
Stop hooks need no change.

R3 (BP-049) — the committed registry ``exclude:`` set prunes the discovery walk,
not just the tree-digest; one config drives both passes.

R4 (BP-033 / BP-051) — a structureless project gets a single whole-tree
leaf-fallback entry; a large, coarsely-covered tree (no component boundary) is
flagged with a narrowing recommendation.  The drift mechanism is never touched.

Run targeted only:
    pytest tests/test_r1r3r4_perf_split.py
"""

import importlib.util
import io
import json
import sys
import types
from contextlib import redirect_stdout
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


def _fake_memory_stack(monkeypatch, project_id):
    """Stub memory.project.resolve_project_id so no real install is needed."""
    fake_memory = types.ModuleType("memory")
    fake_project = types.ModuleType("memory.project")
    fake_project.resolve_project_id = lambda cwd=None, warn=True: project_id
    fake_memory.project = fake_project
    monkeypatch.setitem(sys.modules, "memory", fake_memory)
    monkeypatch.setitem(sys.modules, "memory.project", fake_project)


def _redirect_state(monkeypatch, tmp_path):
    """Point the drift cache, the discovery sentinel (derived from it), AND the
    shadow file-hash cache into tmp so tests never touch the real ~/.ai-memory.

    The per-entry hash cache (FIX-D1) lives under ``shadow._DRIFT_STATE_DIR`` — a
    separate module constant from ``dp._DRIFT_CACHE_DIR`` — so redirect it too."""
    monkeypatch.setattr(dp, "_DRIFT_CACHE_DIR", tmp_path / "drift-state")
    if dp.shadow is not None:
        monkeypatch.setattr(dp.shadow, "_DRIFT_STATE_DIR", tmp_path / "shadow-drift")


def _fixed_time(monkeypatch, now):
    """Freeze ``dp.time`` so the TTL branch of the cadence gate is deterministic."""
    monkeypatch.setattr(
        dp, "time", SimpleNamespace(time=lambda: now, monotonic=lambda: now)
    )


# ---------------------------------------------------------------------------
# R3 — one exclude config, both passes (BP-049)
# ---------------------------------------------------------------------------


def test_discovery_walk_skips_registry_excluded_path(tmp_path):
    """A manifest under a registry ``exclude:`` entry is NOT descended into by the
    discovery walk — the same config that prunes the tree-digest prunes discovery
    (R3/BP-049)."""
    (tmp_path / "pkg_a").mkdir()
    (tmp_path / "pkg_a" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "vendor" / "pkg_b").mkdir(parents=True)
    (tmp_path / "vendor" / "pkg_b" / "pyproject.toml").write_text(
        "[project]\n", encoding="utf-8"
    )

    excluded = dp._discover_candidates(tmp_path, None, ("vendor/",))
    locs = {c["sot_location"] for c in excluded}
    assert "pkg_a/" in locs
    assert "vendor/pkg_b/" not in locs  # pruned by the registry exclude
    assert "vendor/" not in locs  # the excluded top dir is not proposed either

    # Without the exclude, the vendored component IS discovered (control).
    included = {c["sot_location"] for c in dp._discover_candidates(tmp_path)}
    assert "vendor/pkg_b/" in included


def test_pruned_walk_prunes_excluded_dirname(tmp_path):
    """`_pruned_walk` never yields an excluded subtree's contents."""
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "build").mkdir()  # in _SKIP_DIRS already
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "f.txt").write_text("x", encoding="utf-8")

    walked = {p.name for p, _d, _f in dp._pruned_walk(tmp_path, None, ("secret/",))}
    assert "keep" in walked
    assert "secret" not in walked
    assert "build" not in walked


# ---------------------------------------------------------------------------
# FIX-D1 — per-entry drift digest accelerated by the BP-048 hash cache
# ---------------------------------------------------------------------------


def test_entry_digest_cache_is_byte_identical(tmp_path, monkeypatch):
    """FIX-D1: the cache is accelerator-only — a warm cached digest is
    byte-identical to the cold (cache-free) digest."""
    _redirect_state(monkeypatch, tmp_path)
    root = tmp_path / "oversight"
    root.mkdir()
    for i in range(3):
        (root / f"n{i}.md").write_text(f"content {i}\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "d.md").write_text("deep\n", encoding="utf-8")
    ex = dp.shadow.DEFAULT_EXCLUDES

    cold = dp.shadow.tree_digest(root, ex).digest
    warm1, _ = dp._compute_entry_digest(
        "tree-digest", root, ex, project_id="p", entry_id="OV"
    )
    warm2, _ = dp._compute_entry_digest(  # second run reads the populated cache
        "tree-digest", root, ex, project_id="p", entry_id="OV"
    )
    assert warm1 == cold
    assert warm2 == cold


def test_entry_digest_cache_scope_is_per_entry(tmp_path, monkeypatch):
    """FIX-D1 (load-bearing): distinct scope=entry_id per root, so tree_digest's
    cache-pruning never lets two roots evict each other."""
    _redirect_state(monkeypatch, tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text("x", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "y.py").write_text("y", encoding="utf-8")
    ex = dp.shadow.DEFAULT_EXCLUDES

    da, _ = dp._compute_entry_digest(
        "tree-digest", tmp_path / "a", ex, project_id="p", entry_id="A"
    )
    dp._compute_entry_digest(
        "tree-digest", tmp_path / "b", ex, project_id="p", entry_id="B"
    )
    # Re-hash A after B: if scopes collided, B's walk would have pruned A's cache.
    da2, _ = dp._compute_entry_digest(
        "tree-digest", tmp_path / "a", ex, project_id="p", entry_id="A"
    )
    assert da == da2 == dp.shadow.tree_digest(tmp_path / "a", ex).digest

    ca = dp.shadow.file_hash_cache_path("p", "A")
    cb = dp.shadow.file_hash_cache_path("p", "B")
    assert ca.exists() and cb.exists() and ca != cb  # separate cache files


def test_entry_digest_uncached_without_ids_no_tree_scope(tmp_path, monkeypatch):
    """FIX-D1: without project_id/entry_id no cache is touched — the dangerous
    scope='tree' (run_shadow_pass's cache) is NEVER written by the drift path."""
    _redirect_state(monkeypatch, tmp_path)
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f.py").write_text("x", encoding="utf-8")
    ex = dp.shadow.DEFAULT_EXCLUDES
    digest, _ = dp._compute_entry_digest("tree-digest", tmp_path / "d", ex)
    assert digest == dp.shadow.tree_digest(tmp_path / "d", ex).digest
    shadow_dir = tmp_path / "shadow-drift"
    written = list(shadow_dir.glob("sot_file_hash_*")) if shadow_dir.exists() else []
    assert written == []  # no cache write at all → no 'tree' scope collision


# ---------------------------------------------------------------------------
# R4 — whole-tree leaf fallback + size guard (BP-033 / BP-051)
# ---------------------------------------------------------------------------


def test_whole_tree_leaf_fallback_when_no_structure(tmp_path):
    """A directory with no manifests / sub-areas (a leaf) yields ONE whole-tree
    fallback entry so the project is still trackable (BP-051 Policy 1 step 4)."""
    (tmp_path / "README.md").write_text("hi", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path)
    assert len(cands) == 1
    only = cands[0]
    assert only["sot_location"] == "./"
    assert only["boundary_type"] == "path"
    assert only["inferred_from"] == "whole_tree_fallback"
    assert only["confidence"] == "low"


def test_no_whole_tree_fallback_for_structured_repo(tmp_path):
    """A repo with a manifest gets component boundaries, never the low-value
    monolithic whole-tree entry."""
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "go.mod").write_text("module svc\n", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path)
    locs = {c["sot_location"] for c in cands}
    assert "svc/" in locs
    assert "./" not in locs
    assert all(c["inferred_from"] != "whole_tree_fallback" for c in cands)


def test_size_guard_flags_large_no_component_tree(tmp_path, monkeypatch):
    """A large, coarsely-covered tree (no component boundary) is flagged with a
    narrowing recommendation (BP-051 Policy 3)."""
    monkeypatch.setattr(dp, "_WHOLE_TREE_FILE_THRESHOLD", 3)
    for d in ("docs", "data"):
        (tmp_path / d).mkdir()
        for i in range(2):
            (tmp_path / d / f"f{i}.txt").write_text("x", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path)
    assert all(c["boundary_type"] != "component" for c in cands)

    finding = dp._size_guard_finding(tmp_path, cands, dp._ScanBudget())
    assert finding is not None
    assert finding["finding_type"] == "SOT_ANOMALY"
    assert finding["bp_id"] == "BP-051"
    assert "narrow" in finding["recommended_action"].lower()
    # Names the discovered top-level dirs as candidate sub-boundaries.
    assert "docs/" in finding["recommended_action"]


def test_size_guard_silent_when_component_present(tmp_path, monkeypatch):
    """A structured repo is already narrow — no size-guard finding even if large."""
    monkeypatch.setattr(dp, "_WHOLE_TREE_FILE_THRESHOLD", 1)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "package.json").write_text("{}", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path)
    assert dp._size_guard_finding(tmp_path, cands, dp._ScanBudget()) is None


def test_size_guard_suppressed_on_truncation(tmp_path, monkeypatch):
    """FIX-D5: a truncated discovery yields a PARTIAL candidate set, so 'no
    component' can't be proven → the guard is suppressed (no false 'narrow me')."""
    monkeypatch.setattr(dp, "_WHOLE_TREE_FILE_THRESHOLD", 1)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("x", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path)
    budget = dp._ScanBudget()
    budget.truncated = True
    assert dp._size_guard_finding(tmp_path, cands, budget) is None


# ---------------------------------------------------------------------------
# R1 — hot/cold discovery cadence gate (BP-047)
# ---------------------------------------------------------------------------


def test_gate_due_on_cold_sentinel(tmp_path, monkeypatch):
    """First ever run (no sentinel) → discovery due, no nudge.  The gate only
    TICKS the counter (→1); the reset/stamp is deferred to completion (FIX-D3)."""
    _redirect_state(monkeypatch, tmp_path)
    run, nudge = dp._discovery_gate("proj", force_discover=False, drift_only=False)
    assert run is True
    assert nudge is None
    state = dp._read_discovery_state()
    assert state["proj"]["sessions_since_discovery"] == 1  # ticked, not yet reset
    assert state["proj"]["last_discovery_ts"] == 0  # not stamped until walk done


def test_record_discovery_complete_resets(tmp_path, monkeypatch):
    """FIX-D3: only _record_discovery_complete stamps last_discovery_ts + resets
    the counter — called ONLY after a clean (non-truncated) walk."""
    _redirect_state(monkeypatch, tmp_path)
    _fixed_time(monkeypatch, 5_000.0)
    dp._write_discovery_state(
        {"proj": {"last_discovery_ts": 0, "sessions_since_discovery": 7}}
    )
    dp._record_discovery_complete("proj")
    state = dp._read_discovery_state()
    assert state["proj"]["sessions_since_discovery"] == 0
    assert state["proj"]["last_discovery_ts"] == 5_000.0


def test_gate_not_due_within_ttl_and_count(tmp_path, monkeypatch):
    """A recent discovery + few sessions → not due; the counter ticks."""
    _redirect_state(monkeypatch, tmp_path)
    _fixed_time(monkeypatch, 1_000_000.0)
    dp._write_discovery_state(
        {"proj": {"last_discovery_ts": 1_000_000.0, "sessions_since_discovery": 0}}
    )
    run, nudge = dp._discovery_gate("proj", force_discover=False, drift_only=False)
    assert run is False
    assert nudge is None
    assert dp._read_discovery_state()["proj"]["sessions_since_discovery"] == 1


def test_gate_due_on_session_count(tmp_path, monkeypatch):
    """The session-count trigger fires independently of the TTL (bursty machine)."""
    _redirect_state(monkeypatch, tmp_path)
    _fixed_time(monkeypatch, 1_000_000.0)
    dp._write_discovery_state(
        {
            "proj": {
                "last_discovery_ts": 1_000_000.0,
                "sessions_since_discovery": dp._DISCOVERY_SESSION_INTERVAL - 1,
            }
        }
    )
    run, _nudge = dp._discovery_gate("proj", force_discover=False, drift_only=False)
    assert run is True  # tick pushes it to the interval → due


def test_gate_due_on_ttl(tmp_path, monkeypatch):
    """The TTL trigger fires independently of the session count (sparse machine)."""
    _redirect_state(monkeypatch, tmp_path)
    now = 1_000_000.0 + dp._DISCOVERY_TTL_SECONDS + 10
    _fixed_time(monkeypatch, now)
    dp._write_discovery_state(
        {"proj": {"last_discovery_ts": 1_000_000.0, "sessions_since_discovery": 1}}
    )
    run, _nudge = dp._discovery_gate("proj", force_discover=False, drift_only=False)
    assert run is True


def test_gate_drift_only_forces_skip(tmp_path, monkeypatch):
    """--drift-only skips discovery even when the gate is due."""
    _redirect_state(monkeypatch, tmp_path)
    run, _nudge = dp._discovery_gate("proj", force_discover=False, drift_only=True)
    assert run is False


def test_gate_discover_forces_run(tmp_path, monkeypatch):
    """--discover forces a run past a not-due gate; the gate ticks (reset is
    deferred to completion, FIX-D3)."""
    _redirect_state(monkeypatch, tmp_path)
    _fixed_time(monkeypatch, 1_000_000.0)
    dp._write_discovery_state(
        {"proj": {"last_discovery_ts": 1_000_000.0, "sessions_since_discovery": 2}}
    )
    run, _nudge = dp._discovery_gate("proj", force_discover=True, drift_only=False)
    assert run is True
    assert dp._read_discovery_state()["proj"]["sessions_since_discovery"] == 3  # tick


def test_gate_emits_nudge_after_threshold(tmp_path, monkeypatch):
    """After _DISCOVERY_NUDGE_SESSIONS with no discovery, a non-blocking nudge is
    returned (but discovery still does not run)."""
    _redirect_state(monkeypatch, tmp_path)
    _fixed_time(monkeypatch, 1_000_000.0)
    dp._write_discovery_state(
        {
            "proj": {
                "last_discovery_ts": 1_000_000.0,
                "sessions_since_discovery": dp._DISCOVERY_NUDGE_SESSIONS - 1,
            }
        }
    )
    run, nudge = dp._discovery_gate("proj", force_discover=False, drift_only=False)
    assert run is False
    assert nudge is not None
    assert "discovery scan is due" in nudge


def test_gate_state_is_per_project(tmp_path, monkeypatch):
    """Two projects keep independent counters in the one sentinel file — a
    completed discovery for A never resets B's cadence."""
    _redirect_state(monkeypatch, tmp_path)
    dp._discovery_gate("A", force_discover=False, drift_only=False)  # A: tick→1
    dp._record_discovery_complete("A")  # A completes → reset 0
    dp._discovery_gate("B", force_discover=False, drift_only=True)  # B: tick→1
    state = dp._read_discovery_state()
    assert state["A"]["sessions_since_discovery"] == 0
    assert state["B"]["sessions_since_discovery"] == 1


# ---------------------------------------------------------------------------
# R1 — end-to-end through cmd_run
# ---------------------------------------------------------------------------


def _write_registry(tmp_path, extra=None):
    sot = tmp_path / ".sot"
    sot.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "1",
        "entries": [
            {
                "id": "APP",
                "kind": "application",
                "boundary_type": "path",
                "sot_location": "src/",
                "owner": "@team",
                "description": "the app",
            }
        ],
    }
    if extra:
        doc.update(extra)
    (sot / "registry.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "app.py").write_text("x\n", encoding="utf-8")
    return sot / "registry.yaml"


def _run_json(registry, **flags):
    args = SimpleNamespace(
        registry=str(registry),
        as_json=True,
        limit=20,
        all=False,
        shadow=False,
        **flags,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = dp.cmd_run(args)
    assert rc == 0
    return json.loads(buf.getvalue())


def test_cmd_run_drift_only_skips_discovery(tmp_path, monkeypatch):
    """--drift-only: the drift channel still runs, but no new candidates are
    surfaced (discovery walk skipped)."""
    _redirect_state(monkeypatch, tmp_path)
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    _fake_memory_stack(monkeypatch, "e2e-driftonly")
    registry = _write_registry(tmp_path)
    (tmp_path / "newpkg").mkdir()
    (tmp_path / "newpkg" / "go.mod").write_text("module n\n", encoding="utf-8")

    out = _run_json(registry, drift_only=True, discover=False)
    assert out["candidate_proposals"] == []  # discovery skipped


def test_cmd_run_default_then_skip_then_force(tmp_path, monkeypatch):
    """Default first run discovers (cold sentinel → due); the immediate next run
    is within TTL/count → discovery skipped; --discover forces it again."""
    _redirect_state(monkeypatch, tmp_path)
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    _fake_memory_stack(monkeypatch, "e2e-cadence")
    registry = _write_registry(tmp_path)
    (tmp_path / "newpkg").mkdir()
    (tmp_path / "newpkg" / "go.mod").write_text("module n\n", encoding="utf-8")

    first = _run_json(registry, drift_only=False, discover=False)
    first_locs = {c["sot_location"] for c in first["candidate_proposals"]}
    assert "newpkg/" in first_locs  # cold sentinel → discovery due

    second = _run_json(registry, drift_only=False, discover=False)
    assert second["candidate_proposals"] == []  # within cadence → skipped

    forced = _run_json(registry, drift_only=False, discover=True)
    forced_locs = {c["sot_location"] for c in forced["candidate_proposals"]}
    assert "newpkg/" in forced_locs  # --discover bypasses the gate


def test_cmd_run_registry_exclude_prunes_discovery(tmp_path, monkeypatch):
    """End-to-end R3: a committed ``exclude:`` entry keeps a vendored component out
    of the discovery proposals."""
    _redirect_state(monkeypatch, tmp_path)
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    _fake_memory_stack(monkeypatch, "e2e-exclude")
    registry = _write_registry(tmp_path, extra={"exclude": ["vendor/"]})
    (tmp_path / "vendor" / "pkg").mkdir(parents=True)
    (tmp_path / "vendor" / "pkg" / "go.mod").write_text("module v\n", encoding="utf-8")
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "go.mod").write_text("module k\n", encoding="utf-8")

    out = _run_json(registry, drift_only=False, discover=False)
    locs = {c["sot_location"] for c in out["candidate_proposals"]}
    assert "keep/" in locs
    assert "vendor/pkg/" not in locs


# ---------------------------------------------------------------------------
# FIX-D2 — file-level excludes match the tree-digest's file set
# ---------------------------------------------------------------------------


def test_count_files_matches_tree_digest_file_set(tmp_path):
    """`_count_files_bounded` counts the SAME file set `tree_digest` hashes when a
    file glob (`*.log`) is excluded — no over-count (FIX-D2)."""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "x.log").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub" / "y.log").write_text("x", encoding="utf-8")

    excludes = ("*.log",)
    digest_files = dp.shadow.tree_digest(tmp_path, excludes).file_count
    counted = dp._count_files_bounded(tmp_path, 10_000, excludes)
    assert counted == digest_files == 3  # a, b, sub/c — the .log files excluded


def test_excluded_manifest_not_proposed_as_component(tmp_path):
    """FIX-D2: a file-glob exclude of a manifest (`**/package.json`) keeps that
    component out of discovery — matching the digest's file-level semantics."""
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path, None, ("**/package.json",))
    # The web/ dir may still surface as a top-level `path` candidate, but its
    # manifest-driven `component` proposal must be gone.
    assert all(c.get("inferred_from") != "package.json" for c in cands)
    assert all(c.get("boundary_type") != "component" for c in cands)


# ---------------------------------------------------------------------------
# FIX-D6 — leaf fallback + size guard co-fire on a large flat tree
# ---------------------------------------------------------------------------


def test_leaf_fallback_and_size_guard_cofire(tmp_path, monkeypatch):
    """A large, fully-flat/structureless directory: the whole-tree leaf fallback
    AND the size guard both fire (FIX-D6 — behavior was correct but untested)."""
    monkeypatch.setattr(dp, "_WHOLE_TREE_FILE_THRESHOLD", 3)
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    cands = dp._discover_candidates(tmp_path)
    assert len(cands) == 1
    assert cands[0]["inferred_from"] == "whole_tree_fallback"

    finding = dp._size_guard_finding(tmp_path, cands, dp._ScanBudget())
    assert finding is not None
    assert finding["bp_id"] == "BP-051"
    # No sub-dirs to name (flat leaf) → the advisory degrades gracefully.
    assert "internal manifests" in finding["recommended_action"]


# ---------------------------------------------------------------------------
# FIX-D3 — a truncated walk does NOT advance the cadence
# ---------------------------------------------------------------------------


def test_truncated_walk_does_not_stamp_cadence(tmp_path, monkeypatch):
    """FIX-D3: when the discovery walk truncates, last_discovery_ts is NOT stamped
    and the counter is NOT reset → the next run still re-attempts discovery."""
    _redirect_state(monkeypatch, tmp_path)
    monkeypatch.setattr(
        dp, "_reindex_sot_entries", lambda *a, **k: dp.ReindexResult(True, 0)
    )
    _fake_memory_stack(monkeypatch, "e2e-trunc")

    def _truncating_discover(root, budget=None, excludes=()):
        budget.truncated = True  # simulate a budget-blown walk
        return []

    monkeypatch.setattr(dp, "_discover_candidates", _truncating_discover)
    registry = _write_registry(tmp_path)
    _run_json(registry, drift_only=False, discover=False)

    state = dp._read_discovery_state()["e2e-trunc"]
    assert state["last_discovery_ts"] == 0  # not stamped — walk never completed
    assert state["sessions_since_discovery"] == 1  # ticked only


# ---------------------------------------------------------------------------
# FIX-D7 — --no-reindex offline flag (no Qdrant writes)
# ---------------------------------------------------------------------------


def test_no_reindex_skips_reindex_but_runs_drift_discovery(tmp_path, monkeypatch):
    """FIX-D7: with --no-reindex, `_reindex_sot_entries` is never called, yet drift
    + discovery still run (candidates surfaced)."""
    _redirect_state(monkeypatch, tmp_path)
    calls: list = []
    monkeypatch.setattr(
        dp,
        "_reindex_sot_entries",
        lambda *a, **k: calls.append(a) or dp.ReindexResult(True, 0),
    )
    _fake_memory_stack(monkeypatch, "e2e-noreindex")
    registry = _write_registry(tmp_path)
    (tmp_path / "newpkg").mkdir()
    (tmp_path / "newpkg" / "go.mod").write_text("module n\n", encoding="utf-8")

    out = _run_json(registry, drift_only=False, discover=False, no_reindex=True)
    assert calls == []  # reindex never invoked → zero Qdrant writes
    locs = {c["sot_location"] for c in out["candidate_proposals"]}
    assert "newpkg/" in locs  # discovery still ran


def test_reindex_runs_without_no_reindex_flag(tmp_path, monkeypatch):
    """Control: without --no-reindex the reindex IS invoked (default unchanged)."""
    _redirect_state(monkeypatch, tmp_path)
    calls: list = []
    monkeypatch.setattr(
        dp,
        "_reindex_sot_entries",
        lambda *a, **k: calls.append(a) or dp.ReindexResult(True, 0),
    )
    _fake_memory_stack(monkeypatch, "e2e-reindex-on")
    registry = _write_registry(tmp_path)
    _run_json(registry, drift_only=False, discover=False, no_reindex=False)
    assert len(calls) == 1  # reg_changed → reindex called once
