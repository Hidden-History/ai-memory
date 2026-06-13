#!/usr/bin/env python3
"""
aim-sot detect-propose — hybrid auto-discovery + drift detection engine.

Invoked via run-with-env.sh (Pattern B, BP-013): pyyaml + memory.* are venv deps.

Subcommands:
    run      Discover candidate components + compute drift against the committed
             registry.  Emits proposed patches only — NEVER writes the registry.
    reindex  Rebuild the derived memory cache (5b) from the committed registry.

Flags (run):
    --registry PATH    Override registry path (skip git-root walk)
    --json             Machine-readable JSON output
    --limit N          Cap new-candidate proposals per run (default 20)
    --all              Disable candidate cap (surface all new candidates)

Flags (reindex):
    --registry PATH    Override registry path

Exit codes: 0 = success; 1 = system error (YAML parse failure, etc.).

Hard invariant: this script never opens .sot/registry.yaml in write mode.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CANDIDATE_LIMIT = 20

# Upper bound on directories visited during auto-discovery (throttle, F-A2-5).
_MAX_DISCOVERY_DIRS = 5000

_DRIFT_CACHE_DIR = (
    Path(os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")))
    / "drift-state"
)

# Staleness thresholds keyed by volatility tier (days).
_STALENESS_THRESHOLDS: dict[str, int] = {"high": 30, "medium": 90, "low": 180}
_DEFAULT_STALENESS_TIER = "medium"

# Per-component re-check TTL: 7 days in seconds.
_CACHE_TTL_SECONDS = 7 * 24 * 3600

# 5a cache schema version.
_CACHE_SCHEMA_VERSION = "1"

# Manifest filenames that signal a component boundary (BP-029).
_MANIFEST_FILENAMES: frozenset[str] = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Gemfile",
        "composer.json",
    }
)

# Top-level directory names to skip during discovery.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".github",
        ".claude",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
    }
)

# ADR/decision directory names → concern boundary.
_ADR_DIR_NAMES: frozenset[str] = frozenset(
    {"adr", "decisions", "adrs", "decision-records"}
)

# Registry fields that must NOT be stored in the 5b cache (machine state only).
_MACHINE_STATE_FIELDS: frozenset[str] = frozenset(
    {"last_verified_at", "last_verified_sha", "drift_status", "drift_detail"}
)


# ---------------------------------------------------------------------------
# Registry resolution
# ---------------------------------------------------------------------------


def _find_registry(override: str | None = None) -> Path | None:
    """Locate .sot/registry.yaml.

    Resolution order:
    1. --registry PATH override.
    2. git root + '.sot/registry.yaml'.
    3. Parent-directory walk from cwd upward.
    """
    if override is not None:
        return Path(override)

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip()) / ".sot" / "registry.yaml"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / ".sot" / "registry.yaml"
        if candidate.exists():
            return candidate

    return None


def _project_root_from_registry(registry_path: Path) -> Path | None:
    """Return <project_root> for a conforming <project_root>/.sot/registry.yaml.

    Returns None when the path does not conform (e.g. a flat ``--registry``
    override pointing at a loose file).  Deriving a root via ``parent.parent``
    from a non-conforming path can land on ``/`` or a home directory and trigger
    an unbounded auto-discovery scan (DEFECT-FV-1).  Callers must skip discovery
    when the root is None.
    """
    if registry_path.parent.name == ".sot":
        return registry_path.parent.parent
    return None


# ---------------------------------------------------------------------------
# SHA helpers
# ---------------------------------------------------------------------------


def _sha256_short(path: Path) -> str | None:
    """sha256(file_bytes)[:8].  Returns None on read error."""
    # TODO(aim-sot): content-hash drift (Type 2b/3/K1) covers FILE sot_locations only;
    # directory sot_locations get location + temporal drift but no content-hash drift
    # (sha256(file) no-ops on a dir). Future enhancement: a directory-tree digest
    # (sorted per-file sha256) to extend hash/K1 coverage to directory components.
    # Deferred per owner (Session 88); file-only is spec-§5-literal for now.
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()[:8]


def _stat_mtime_size(path: Path) -> tuple[float | None, int | None]:
    """(mtime, size) of ``path``, or (None, None) on stat error.

    Cheap pre-check input for the TTL bust (DD-A): a changed mtime/size means
    the artifact moved since the last clean check and must be re-evaluated.
    """
    try:
        st = path.stat()
        return st.st_mtime, st.st_size
    except OSError:
        return None, None


def _parse_human_date(raw) -> datetime | None:
    """Parse a human ``last_verified`` value (str / YAML date / datetime) to a
    tz-aware datetime, or None when absent or unparseable."""
    if not raw:
        return None
    try:
        raw_str = str(raw).strip()
        dt = datetime.fromisoformat(
            (raw_str + "T00:00:00+00:00")
            if len(raw_str) == 10
            else raw_str.replace("Z", "+00:00")
        )
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError, TypeError):
        return None


def _registry_sha(registry_path: Path) -> str:
    """sha256(registry_file_bytes)[:8] used to detect human edits to the file."""
    return _sha256_short(registry_path) or ""


# ---------------------------------------------------------------------------
# 5a per-install drift cache
# ---------------------------------------------------------------------------


def _drift_cache_path(project_id: str) -> Path:
    """~/.ai-memory/drift-state/sot_drift_{project_id}.json"""
    safe_id = project_id.replace("/", "__")
    return _DRIFT_CACHE_DIR / f"sot_drift_{safe_id}.json"


def _read_drift_cache(project_id: str) -> dict:
    """Read the per-install drift cache.  Returns empty skeleton on any error."""
    path = _drift_cache_path(project_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "project_id": project_id,
        "generated_at": "",
        "registry_sha": "",
        "components": {},
    }


def _write_drift_cache(project_id: str, data: dict) -> None:
    """Write the drift cache atomically (temp-file → os.replace) with advisory lock."""
    path = _drift_cache_path(project_id)
    lock_path = path.with_suffix(".json.lock")
    path.parent.mkdir(parents=True, exist_ok=True)

    # Last-writer-wins: the read (in cmd_run) and this write are not held under a
    # single lock, so concurrent runs can clobber each other's record.  This is
    # intentional — 5a is a per-machine, deterministically-rebuildable cache
    # (spec §5a), so a lost write self-heals on the next run (F-A2-11).
    with open(lock_path, "w", encoding="utf-8") as lock_fd:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            tmp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=path.parent,
                    delete=False,
                    suffix=".tmp",
                ) as tmp:
                    tmp_path = Path(tmp.name)
                    json.dump(data, tmp, indent=2)
                    tmp.flush()
                    os.fsync(tmp.fileno())  # durable before replace (F-C-S-8)
                os.replace(tmp_path, path)
            except Exception:
                # Clean up the partial temp file on any failure (json.dump,
                # fsync, or replace) so no orphan .tmp is left behind (F-A2-7).
                if tmp_path is not None:
                    with contextlib.suppress(OSError):
                        tmp_path.unlink(missing_ok=True)
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _should_skip_component(
    entry_id: str,
    cache: dict,
    project_root: Path | None = None,
    *,
    force_recheck: bool = False,
) -> bool:
    """True if this component was checked recently, was clean, AND is unchanged.

    Throttle: skip only when drift_status=='clean' AND last_verified_at < 7d ago
    AND the artifact's mtime/size match the last clean check (DD-A).  A cheap
    stat (not a full read) busts the TTL skip when the artifact changed, closing
    the hash-blind window where an artifact-only edit was invisible for up to
    7 days.  Unverified / drifted / missing / stale entries always re-run.
    force_recheck=True bypasses the throttle (registry sha changed → re-check
    everything, while preserving hash baselines).
    """
    if force_recheck:
        return False  # registry edited this run — re-check everything
    comp = cache.get("components", {}).get(entry_id)
    if not comp:
        return False  # cold-start → always check
    if comp.get("drift_status") != "clean":
        return False  # non-clean → always re-check
    last_at = comp.get("last_verified_at", "")
    if not last_at:
        return False
    try:
        last_dt = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if (datetime.now(timezone.utc) - last_dt).total_seconds() >= _CACHE_TTL_SECONDS:
        return False  # TTL expired → re-check

    # DD-A — cheap stat pre-check: bust the TTL skip if the artifact changed.
    if project_root is not None:
        loc = comp.get("sot_location", "")
        if loc:
            mtime, size = _stat_mtime_size(project_root / loc)
            if mtime is None:
                return False  # cannot stat (e.g. now-missing) → re-check
            if mtime != comp.get("last_verified_mtime") or size != comp.get(
                "last_verified_size"
            ):
                return False  # artifact edited within the TTL → re-check

    return True  # clean + recent + unchanged → skip


def _human_reconfirmed(entry: dict, prior_at: str) -> bool:
    """True when the registry's human ``last_verified`` date is newer than the
    cache's ``last_verified_at`` — a fresh human re-confirmation (spec §3, DD-B).

    This is the only machine-observable signal that ties a baseline advance to
    the human HITL act; without it the baseline is held on detected drift.
    """
    if not prior_at:
        return False
    lv_dt = _parse_human_date(entry.get("last_verified", ""))
    if lv_dt is None:
        return False
    try:
        prior_dt = datetime.fromisoformat(prior_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    if prior_dt.tzinfo is None:
        prior_dt = prior_dt.replace(tzinfo=timezone.utc)
    return lv_dt > prior_dt


def _compute_component_record(
    *,
    prior: dict | None,
    drifts: list[dict],
    current_sha: str | None,
    mtime: float | None,
    size: int | None,
    loc: str,
    now_iso: str,
    human_reconfirmed: bool,
) -> dict:
    """Build the next 5a component record per DD-B baseline rules.

    - cold-start (no prior baseline)      → record sha, drift_status=unverified
      (or missing when the location is gone); the verify gate (DD-C) surfaces
      this as CONDITIONAL until a human confirms.
    - human re-confirmation               → re-baseline to current, clean.
    - drift detected                      → HOLD the prior baseline (sha + at +
      mtime/size unchanged) so the proposal re-fires until resolved.
    - clean                               → advance baseline to current.
    """
    loc_missing = any(d.get("drift_type") == "location" for d in drifts)
    detail = [d["drift_type"] for d in drifts] if drifts else None
    prior_sha = (prior or {}).get("last_verified_sha", "")
    cold_start = not prior or not prior_sha

    if cold_start:
        return {
            "sot_location": loc,
            "last_verified_at": now_iso,
            "last_verified_sha": current_sha or "",
            "last_verified_mtime": mtime,
            "last_verified_size": size,
            "drift_status": "missing" if loc_missing else "unverified",
            "drift_detail": detail,
        }

    def _hold(status: str) -> dict:
        # Keep the prior baseline (sha + at + mtime/size) so the proposal
        # re-fires until resolved — do NOT advance to drifted content.
        return {
            "sot_location": loc,
            "last_verified_at": prior.get("last_verified_at", now_iso),
            "last_verified_sha": prior_sha,
            "last_verified_mtime": prior.get("last_verified_mtime"),
            "last_verified_size": prior.get("last_verified_size"),
            "drift_status": status,
            "drift_detail": detail,
        }

    def _advance() -> dict:
        return {
            "sot_location": loc,
            "last_verified_at": now_iso,
            "last_verified_sha": current_sha or "",
            "last_verified_mtime": mtime,
            "last_verified_size": size,
            "drift_status": "clean",
            "drift_detail": None,
        }

    if loc_missing:
        # A missing artifact can never be 'clean' — hold, even if a human just
        # bumped last_verified (they cannot re-confirm a file that is gone).
        return _hold("missing")
    if human_reconfirmed:
        return _advance()
    if drifts:
        return _hold("drifted")
    return _advance()


# ---------------------------------------------------------------------------
# Auto-discovery (BP-029 hybrid model)
# ---------------------------------------------------------------------------


def _pruned_walk(root: Path, *, max_dirs: int = _MAX_DISCOVERY_DIRS):
    """``os.walk`` that prunes ``_SKIP_DIRS`` in-place (so skipped trees are
    never descended into) and caps the directory count (F-A2-5).

    Pruning during traversal — rather than ``rglob`` + post-hoc filtering —
    avoids walking node_modules / .venv / build trees on every run; the cap
    bounds the worst case on pathological repos.
    """
    for visited, (dirpath, dirnames, filenames) in enumerate(os.walk(root)):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if visited >= max_dirs:
            return
        yield Path(dirpath), dirnames, filenames


def _discover_manifests(project_root: Path) -> list[dict]:
    """Manifest files → boundary_type=component candidates."""
    manifest_order = sorted(_MANIFEST_FILENAMES)
    candidates: list[dict] = []
    for dirpath, _dirnames, filenames in _pruned_walk(project_root):
        fileset = set(filenames)
        name = next((n for n in manifest_order if n in fileset), None)
        if name is None:
            continue
        rel = dirpath.relative_to(project_root)
        rel_str = str(rel)
        loc = (rel_str + "/") if rel_str != "." else "./"
        cid = rel_str.replace(os.sep, "-") or "root"
        candidates.append(
            {
                "id": cid,
                "boundary_type": "component",
                "sot_location": loc,
                "confidence": "high",
                "inferred_from": name,
            }
        )
    return sorted(candidates, key=lambda c: c["sot_location"])


def _discover_top_dirs(project_root: Path) -> list[dict]:
    """Top-level directories → boundary_type=path candidates."""
    candidates: list[dict] = []
    try:
        for entry in sorted(project_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            name = entry.name
            if name in _SKIP_DIRS or name.startswith("."):
                continue
            candidates.append(
                {
                    "id": name,
                    "boundary_type": "path",
                    "sot_location": name + "/",
                    "confidence": "medium",
                    "inferred_from": "top_level_directory",
                }
            )
    except OSError:
        pass
    return candidates


def _discover_adr_dirs(project_root: Path) -> list[dict]:
    """ADR/decision directories → boundary_type=concern candidates."""
    candidates: list[dict] = []
    for dirpath, _dirnames, _filenames in _pruned_walk(project_root):
        if dirpath == project_root or dirpath.name not in _ADR_DIR_NAMES:
            continue
        rel = dirpath.relative_to(project_root)
        loc = str(rel) + "/"
        cid = str(rel).replace(os.sep, "-")
        candidates.append(
            {
                "id": cid,
                "boundary_type": "concern",
                "sot_location": loc,
                "confidence": "high",
                "inferred_from": "adr_directory",
            }
        )
    return sorted(candidates, key=lambda c: c["sot_location"])


def _discover_candidates(project_root: Path) -> list[dict]:
    """Orchestrate all three scanners, deduplicated and sorted by sot_location."""
    seen: set[str] = set()
    all_candidates: list[dict] = []
    for c in (
        _discover_manifests(project_root)
        + _discover_adr_dirs(project_root)
        + _discover_top_dirs(project_root)
    ):
        loc = c["sot_location"]
        if loc not in seen:
            seen.add(loc)
            all_candidates.append(c)
    return sorted(all_candidates, key=lambda c: c["sot_location"])


# ---------------------------------------------------------------------------
# Bootstrap filtering
# ---------------------------------------------------------------------------


def _filter_new_candidates(
    candidates: list[dict], existing_entries: list[dict]
) -> list[dict]:
    """Remove candidates whose sot_location already appears in the registry."""
    registered = {e.get("sot_location", "") for e in existing_entries}
    return [c for c in candidates if c["sot_location"] not in registered]


def _apply_cap(candidates: list[dict], limit: int) -> tuple[list[dict], int]:
    """Cap the candidate list.  limit≤0 means no cap.

    Returns (capped_list, deferred_count).
    """
    if limit <= 0 or len(candidates) <= limit:
        return list(candidates), 0
    return candidates[:limit], len(candidates) - limit


# ---------------------------------------------------------------------------
# Drift detection — 4 types (spec §5, BP-031)
# ---------------------------------------------------------------------------


def _check_location_drift(entry: dict, project_root: Path) -> dict | None:
    """Type 1 — sot_location path no longer resolves."""
    loc = entry.get("sot_location", "")
    if not loc:
        return None
    if not (project_root / loc).exists():
        return {
            "drift_type": "location",
            "entry_id": entry.get("id", "?"),
            "sot_location": loc,
            "root_cause": f"Path '{loc}' does not exist relative to project root.",
            "impact": "The declared SOT location cannot be verified or consulted.",
            "recommended_action": (
                "Update sot_location to the new path, or set status=superseded "
                "if the component has been removed."
            ),
        }
    return None


def _check_temporal_staleness(
    entry: dict,
    thresholds: dict[str, int] | None = None,
) -> dict | None:
    """Type 2a — last_verified older than a volatility-tiered threshold.

    Handles both string dates ("2026-06-01") and YAML-native datetime.date
    objects (produced by unquoted ``last_verified: 2026-06-01`` in YAML).
    """
    thresholds = thresholds or _STALENESS_THRESHOLDS
    # Handles str / YAML-native datetime.date / datetime; tz-aware result.
    lv_dt = _parse_human_date(entry.get("last_verified", ""))
    if lv_dt is None:
        return None

    drift_check = str(entry.get("drift_check", "")).lower()
    if "high" in drift_check:
        tier, days = "high", thresholds.get("high", 30)
    elif "low" in drift_check:
        tier, days = "low", thresholds.get("low", 180)
    else:
        tier, days = _DEFAULT_STALENESS_TIER, thresholds.get(
            _DEFAULT_STALENESS_TIER, 90
        )

    age_days = (datetime.now(timezone.utc) - lv_dt).days
    if age_days > days:
        return {
            "drift_type": "staleness_temporal",
            "entry_id": entry.get("id", "?"),
            "sot_location": entry.get("sot_location", "?"),
            "root_cause": (
                f"last_verified is {age_days}d ago "
                f"(threshold for {tier} volatility: {days}d)."
            ),
            "impact": "Registry entry may not reflect the current state of the component.",
            "recommended_action": (
                "Re-verify the component and update last_verified to today's date."
            ),
        }
    return None


def _check_content_hash_drift(
    entry: dict,
    project_root: Path,
    cache: dict,
    *,
    current_sha: str | None = None,
) -> dict | None:
    """Type 2b — sha256(file)[:8] != cached last_verified_sha.

    ``current_sha`` may be pre-computed by the caller (avoids a duplicate
    file read when both 2b and Type 3 are checked in the same loop iteration).
    Only applies to file ``sot_location``s; directory paths are no-ops by
    design (spec §5 "sha256(file)").
    """
    loc = entry.get("sot_location", "")
    if not loc:
        return None
    full = project_root / loc
    if not full.exists():
        return None  # location drift (Type 1) takes precedence

    comp = cache.get("components", {}).get(entry.get("id", ""), {})
    cached_sha = comp.get("last_verified_sha", "")
    if not cached_sha:
        return None  # no baseline yet; will be established on this run

    if current_sha is None:
        current_sha = _sha256_short(full)
    if current_sha is None or current_sha == cached_sha:
        return None
    return {
        "drift_type": "staleness_hash",
        "entry_id": entry.get("id", "?"),
        "sot_location": loc,
        "root_cause": f"Content hash changed: was {cached_sha}, now {current_sha}.",
        "impact": "The SOT artifact has been modified since last verification.",
        "recommended_action": (
            "Review the change. If still accurate, update last_verified and "
            "re-run detect-propose to clear this drift."
        ),
    }


def _check_declaration_reality_drift(
    entry: dict,
    project_root: Path,
    cache: dict,
    *,
    current_sha: str | None = None,
) -> dict | None:
    """Type 3 — file exists + hash changed = K1 trigger (mandatory human re-confirm).

    Fires only when a content-hash change is present.  Complements (not
    replaces) Type 2b — both fire intentionally on the same hash change:
    ``staleness_hash`` signals "re-verify", ``declaration_reality`` (K1) signals
    "mandatory human re-confirm of description/tags" (spec §5).  Consumers may
    act on ``k1_trigger`` independently of the staleness signal.

    ``current_sha`` may be pre-computed by the caller (avoids a duplicate file
    read when both 2b and Type 3 are checked in the same loop iteration).
    Only applies to file ``sot_location``s; directory paths are no-ops by design.
    """
    loc = entry.get("sot_location", "")
    if not loc:
        return None
    full = project_root / loc
    if not full.exists():
        return None

    comp = cache.get("components", {}).get(entry.get("id", ""), {})
    cached_sha = comp.get("last_verified_sha", "")
    if not cached_sha:
        return None

    if current_sha is None:
        current_sha = _sha256_short(full)
    if current_sha is None or current_sha == cached_sha:
        return None

    return {
        "drift_type": "declaration_reality",
        "entry_id": entry.get("id", "?"),
        "sot_location": loc,
        "k1_trigger": True,
        "root_cause": (
            f"Content hash changed ({cached_sha} → {current_sha}) but the registry "
            "description has not been re-confirmed since then."
        ),
        "impact": (
            "The declared description/tags may no longer match the artifact. "
            "K1: mandatory human re-confirmation required (spec §5)."
        ),
        "recommended_action": (
            "Review the artifact change vs. the registry description. "
            "If the description is still accurate, update last_verified. "
            "Otherwise update the description in the registry."
        ),
    }


# ---------------------------------------------------------------------------
# 5b reindex — derived memory cache (spec §5 Q5)
# ---------------------------------------------------------------------------


class ReindexResult(NamedTuple):
    """Outcome of a 5b reindex.  ``ok`` distinguishes a real success (including
    a legitimately-empty registry) from a failure / store-unreachable — so the
    caller never advances ``registry_sha`` on a failed rebuild (M1)."""

    ok: bool
    stored: int


@contextlib.contextmanager
def _reindex_lock(project_id: str):
    """Serialize the reindex per project_id so concurrent registry-change runs
    cannot interleave delete/re-store into the 5b cache (M6).

    Best-effort: if the lock cannot be acquired (e.g. the drift-state dir is
    unwritable), proceed without it — the 5b cache is rebuildable, so failing
    open here is safe.
    """
    lock_fd = None
    try:
        _DRIFT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = project_id.replace("/", "__")
        lock_fd = open(  # noqa: SIM115 — held across the yield; closed in finally
            _DRIFT_CACHE_DIR / f"sot_reindex_{safe_id}.lock", "w", encoding="utf-8"
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError:
        if lock_fd is not None:
            lock_fd.close()
            lock_fd = None
    try:
        yield
    finally:
        if lock_fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


def _reindex_sot_entries(
    registry_path: Path,
    project_id: str,
    *,
    _qdrant_client=None,  # injectable for tests
    _storage=None,  # injectable for tests
) -> ReindexResult:
    """Rebuild the 5b derived memory cache from the committed registry.

    Prepare-then-replace: load the registry, construct ``MemoryStorage``, and
    build the replacement payloads BEFORE deleting any existing points (M1).  A
    failure during preparation (YAML parse error, store-unreachable) therefore
    leaves the existing 5b cache intact rather than emptied-not-restored.  A
    transiently-empty registry is treated as a no-op (existing points are kept)
    for the same reason.

    Returns ``ReindexResult(ok, stored)``.  ``ok`` is False only on a genuine
    failure; an empty registry is ``ReindexResult(True, 0)``.  The
    ``_qdrant_client`` / ``_storage`` kwargs are test injection points.
    """
    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)

        from qdrant_client.models import FieldCondition, Filter, MatchValue

        from memory.config import COLLECTION_CONVENTIONS, get_config
        from memory.models import MemoryType
        from memory.qdrant_client import get_qdrant_client
        from memory.storage import MemoryStorage

        # --- Prepare (no destructive op yet) ---------------------------------
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        entries: list[dict] = (
            [e for e in raw.get("entries", []) if isinstance(e, dict)]
            if isinstance(raw, dict)
            else []
        )
        if not entries:
            # Keep existing points rather than wiping on a transiently-empty
            # or unparseable registry (M1 prepare-then-replace).
            return ReindexResult(True, 0)

        if _qdrant_client is None:
            config = get_config()
            qdrant_client = get_qdrant_client(config)
        else:
            qdrant_client = _qdrant_client
            config = None  # type: ignore[assignment]

        storage = MemoryStorage(config=config) if _storage is None else _storage

        # Replacement payload set (content = non-machine-state fields).
        prepared: list[str] = [
            json.dumps(
                {k: v for k, v in entry.items() if k not in _MACHINE_STATE_FIELDS},
                ensure_ascii=False,
            )
            for entry in entries
        ]

        with _reindex_lock(project_id):
            # --- Scroll existing ids (still pre-delete; a scroll failure here
            #     raises out before any delete) ---------------------------------
            existing_ids: list = []
            offset = None
            while True:
                points, next_offset = qdrant_client.scroll(
                    collection_name=COLLECTION_CONVENTIONS,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="group_id", match=MatchValue(value=project_id)
                            ),
                            FieldCondition(
                                key="type", match=MatchValue(value="sot_entry")
                            ),
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=False,
                )
                for pt in points:
                    existing_ids.append(pt.id)
                if next_offset is None:
                    break
                offset = next_offset

            # --- Replace: delete existing, then re-store the prepared set ----
            if existing_ids:
                for i in range(0, len(existing_ids), 100):
                    qdrant_client.delete(
                        collection_name=COLLECTION_CONVENTIONS,
                        points_selector=existing_ids[i : i + 100],
                    )

            stored = 0
            for content in prepared:
                try:
                    result = storage.store_memory(
                        content=content,
                        cwd=str(registry_path.parent),
                        memory_type=MemoryType.SOT_ENTRY,
                        source_hook="aim_sot_detect_propose",
                        session_id=f"aim_sot_reindex_{project_id}",
                        group_id=project_id,
                        collection=COLLECTION_CONVENTIONS,
                    )
                    if result.get("status") in ("stored", "duplicate"):
                        stored += 1
                except Exception:
                    pass  # per-entry failure is non-fatal
        return ReindexResult(True, stored)

    except Exception:
        # Graceful no-op when the store is unreachable — existing 5b points are
        # untouched because no delete runs until after preparation succeeds.
        return ReindexResult(False, 0)


# ---------------------------------------------------------------------------
# Proposal builders
# ---------------------------------------------------------------------------


def _make_drift_proposal(entry: dict, drifts: list[dict]) -> dict:
    return {
        "kind": "drift",
        "entry_id": entry.get("id", "?"),
        "sot_location": entry.get("sot_location", "?"),
        "drifts": drifts,
    }


def _make_candidate_proposal(candidate: dict) -> dict:
    return {
        "kind": "new_candidate",
        "boundary_type": candidate["boundary_type"],
        "suggested_id": candidate["id"],
        "sot_location": candidate["sot_location"],
        "confidence": candidate["confidence"],
        "inferred_from": candidate["inferred_from"],
        "note": (
            "Semantic fields (owner, description, provenance_note) must be "
            "authored by a human — never auto-filled (BP-029)."
        ),
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _format_human(
    drift_proposals: list[dict],
    candidate_proposals: list[dict],
    deferred_count: int,
) -> str:
    lines: list[str] = []
    if not drift_proposals and not candidate_proposals:
        return "aim-sot detect-propose: no drift detected, no new candidates."

    if drift_proposals:
        lines.append(f"## Drift detected ({len(drift_proposals)} entries)\n")
        for p in drift_proposals:
            lines.append(f"### [{p['entry_id']}]  {p['sot_location']}")
            for d in p["drifts"]:
                lines.append(f"  drift_type: {d['drift_type']}")
                if d.get("k1_trigger"):
                    lines.append(
                        "  ⚠ K1 trigger: mandatory human re-confirmation required"
                    )
                lines.append(f"  root_cause: {d['root_cause']}")
                lines.append(f"  impact: {d['impact']}")
                lines.append(f"  recommended_action: {d['recommended_action']}")
            lines.append("")

    if candidate_proposals:
        lines.append(f"## New candidates ({len(candidate_proposals)} proposals)\n")
        for p in candidate_proposals:
            lines.append(
                f"  [{p['boundary_type']}] {p['sot_location']}  "
                f"(id: {p['suggested_id']}, confidence: {p['confidence']})"
            )
        lines.append("")
        lines.append(
            "  Semantic fields (owner, description, provenance_note) must be "
            "authored by a human — never auto-filled (BP-029)."
        )
        lines.append("")

    if deferred_count > 0:
        lines.append(
            f"  {deferred_count} more candidate(s) not shown. "
            "Run with --all to see all, or re-run after applying these."
        )
        lines.append("")

    lines.append(
        "Apply by editing .sot/registry.yaml. "
        "Run 'detect-propose run' again to verify drift is resolved "
        "and refresh the memory cache."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


def _load_registry_entries(registry_path: Path) -> tuple[list[dict], int]:
    """Parse the registry file.  Returns (entries, exit_code); ec=1 on error."""
    try:
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return [], 1
        entries = raw.get("entries", [])
        if not isinstance(entries, list):
            return [], 1
        return [e for e in entries if isinstance(e, dict)], 0
    except (yaml.YAMLError, OSError):
        return [], 1


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Main detect-propose run."""
    # --- Resolve registry ---
    registry_path = _find_registry(getattr(args, "registry", None))
    if registry_path is None or not registry_path.exists():
        loc = f" at {registry_path}" if registry_path else ""
        print(f"No registry found{loc}. Run aim-sot detect-propose to create one.")
        return 0

    # --- Derive project_id ---
    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from memory.project import resolve_project_id

        project_id = resolve_project_id(cwd=str(registry_path.parent.parent))
    except Exception as exc:
        print(f"Error: could not resolve project_id: {exc}", file=sys.stderr)
        return 1

    # --- Load registry ---
    entries, ec = _load_registry_entries(registry_path)
    if ec != 0:
        print("Registry is not valid YAML.", file=sys.stderr)
        return 1

    # --- 5a cache: opportunistic reindex when registry sha changed ---
    cache = _read_drift_cache(project_id)
    current_reg_sha = _registry_sha(registry_path)
    reg_changed = bool(current_reg_sha) and current_reg_sha != cache.get(
        "registry_sha", ""
    )
    if reg_changed:
        reindex_result = _reindex_sot_entries(registry_path, project_id)
        # Advance registry_sha only on a successful rebuild — a failed reindex
        # is retried next run rather than masked (M1).  Preserve
        # cache["components"] either way so last_verified_sha baselines survive
        # for hash/K1 drift; force_recheck=True bypasses the TTL skip below.
        if reindex_result.ok:
            cache["registry_sha"] = current_reg_sha

    # --- Project root ---
    # A conforming registry (<root>/.sot/registry.yaml) yields a project root we
    # can safely scan; a flat --registry override yields None — resolve declared
    # locations relative to the registry's directory and skip the unbounded
    # auto-discovery scan (M5).
    project_root = _project_root_from_registry(registry_path)
    resolve_root = project_root if project_root is not None else registry_path.parent
    now_iso = datetime.now(timezone.utc).isoformat()
    updated_components: dict = dict(cache.get("components", {}))

    # --- Drift detection across registry entries ---
    drift_proposals: list[dict] = []
    for entry in entries:
        eid = entry.get("id", "")
        if not eid:
            continue
        if _should_skip_component(eid, cache, resolve_root, force_recheck=reg_changed):
            continue

        prior = cache.get("components", {}).get(eid)

        # Compute file sha + stat once per entry — reused for hash/decl drift
        # checks and the 5a component record (avoids a duplicate file read).
        loc = entry.get("sot_location", "")
        full_path = (resolve_root / loc) if loc else None
        exists = bool(full_path and full_path.exists())
        current_sha = _sha256_short(full_path) if exists else None
        mtime, size = _stat_mtime_size(full_path) if exists else (None, None)

        drifts: list[dict] = []
        loc_drift = _check_location_drift(entry, resolve_root)
        if loc_drift:
            drifts.append(loc_drift)
        temp_drift = _check_temporal_staleness(entry)
        if temp_drift:
            drifts.append(temp_drift)
        hash_drift = _check_content_hash_drift(
            entry, resolve_root, cache, current_sha=current_sha
        )
        if hash_drift:
            drifts.append(hash_drift)
        decl_drift = _check_declaration_reality_drift(
            entry, resolve_root, cache, current_sha=current_sha
        )
        if decl_drift:
            drifts.append(decl_drift)

        if drifts:
            drift_proposals.append(_make_drift_proposal(entry, drifts))

        # Update 5a component record per DD-B baseline rules (hold on drift,
        # advance on clean / human re-confirm, cold-start → unverified).
        updated_components[eid] = _compute_component_record(
            prior=prior,
            drifts=drifts,
            current_sha=current_sha,
            mtime=mtime,
            size=size,
            loc=loc,
            now_iso=now_iso,
            human_reconfirmed=_human_reconfirmed(
                entry, (prior or {}).get("last_verified_at", "")
            ),
        )

    # --- Auto-discovery: new candidates (skipped for non-conforming roots) ---
    if project_root is not None:
        candidates = _discover_candidates(project_root)
        new_candidates = _filter_new_candidates(candidates, entries)
        limit = (
            0
            if getattr(args, "all", False)
            else getattr(args, "limit", _DEFAULT_CANDIDATE_LIMIT)
        )
        capped, deferred_count = _apply_cap(new_candidates, limit)
        candidate_proposals = [_make_candidate_proposal(c) for c in capped]
    else:
        capped, deferred_count, candidate_proposals = [], 0, []

    # --- Persist 5a cache ---
    cache["components"] = updated_components
    cache["generated_at"] = now_iso
    with contextlib.suppress(OSError):
        _write_drift_cache(project_id, cache)

    # --- Emit output ---
    as_json = getattr(args, "as_json", False)
    if as_json:
        print(
            json.dumps(
                {
                    "drift_proposals": drift_proposals,
                    "candidate_proposals": candidate_proposals,
                    "deferred_count": deferred_count,
                    "project_id": project_id,
                }
            )
        )
    else:
        print(_format_human(drift_proposals, candidate_proposals, deferred_count))

    return 0


# ---------------------------------------------------------------------------
# Subcommand: reindex
# ---------------------------------------------------------------------------


def cmd_reindex(args: argparse.Namespace) -> int:
    """Explicit 5b reindex subcommand."""
    registry_path = _find_registry(getattr(args, "registry", None))
    if registry_path is None or not registry_path.exists():
        print("No registry found. Nothing to reindex.")
        return 0

    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from memory.project import resolve_project_id

        project_id = resolve_project_id(cwd=str(registry_path.parent.parent))
    except Exception as exc:
        print(f"Error: could not resolve project_id: {exc}", file=sys.stderr)
        return 1

    result = _reindex_sot_entries(registry_path, project_id)
    if not result.ok:
        print(
            f"aim-sot reindex: store unreachable for project '{project_id}'; "
            "existing cache left intact.",
            file=sys.stderr,
        )
        return 0
    print(
        f"aim-sot reindex: {result.stored} entries indexed for project '{project_id}'."
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aim_sot_detect_propose",
        description=(
            "Hybrid auto-discovery + drift detection for .sot/registry.yaml. "
            "Never writes the registry."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Detect drift + propose new candidates")
    run_p.add_argument("--registry", metavar="PATH")
    run_p.add_argument("--json", action="store_true", dest="as_json")
    run_p.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_CANDIDATE_LIMIT,
        metavar="N",
        help=f"Max new-candidate proposals per run (default {_DEFAULT_CANDIDATE_LIMIT})",
    )
    run_p.add_argument(
        "--all",
        action="store_true",
        dest="all",
        help="Disable candidate cap",
    )

    reindex_p = sub.add_parser("reindex", help="Rebuild 5b derived memory cache")
    reindex_p.add_argument("--registry", metavar="PATH")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "reindex":
        return cmd_reindex(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
