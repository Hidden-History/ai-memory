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
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import yaml

# ---------------------------------------------------------------------------
# Sibling import — the shadow-git / tree-digest / doc-drift / findings
# substrate (TD-675).  Loaded by path so the engine works whether invoked as a
# standalone script (hooks) or imported in tests.  Degrades gracefully: if the
# module is absent, the directory-tree / shadow / doc-drift paths are skipped
# and file-SOT drift detection (the pre-TD-675 behavior) is unchanged.
# ---------------------------------------------------------------------------
try:
    _SHADOW_SCRIPT = Path(__file__).resolve().parent / "aim_sot_shadow.py"
    _shadow_spec = importlib.util.spec_from_file_location(
        "aim_sot_shadow", _SHADOW_SCRIPT
    )
    shadow = importlib.util.module_from_spec(_shadow_spec)
    _shadow_spec.loader.exec_module(shadow)
except Exception:
    shadow = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CANDIDATE_LIMIT = 20

# Hard wall-time cap for the advisory git subprocesses (registry walk + owner
# hints).  These are best-effort hints; on a wedged/slow git they degrade
# silently rather than hang the hook (TimeoutExpired → skip/not-available).
_GIT_SUBPROCESS_TIMEOUT = 10.0


def _env_float(name: str, default: float) -> float:
    """Read a positive float from the environment, else ``default`` (F-SOT-3)."""
    raw = os.environ.get(name, "")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    return val if val > 0 else default


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, else ``default`` (F-SOT-3)."""
    raw = os.environ.get(name, "")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    return val if val > 0 else default


# Upper bound on directories visited during auto-discovery (throttle, F-A2-5),
# complemented by a wall-time budget (F-SOT-3) — on a slow filesystem the
# per-directory IO dominates, so a dir-count cap alone still lets the scan blow
# the [CL] hook's ~20s subprocess cap.  Both are env-overridable.
_MAX_DISCOVERY_DIRS = _env_int("AI_MEMORY_SOT_DISCOVERY_MAX_DIRS", 5000)
_DISCOVERY_MAX_SECONDS = _env_float("AI_MEMORY_SOT_DISCOVERY_MAX_SECONDS", 6.0)
# Wall-time cap for the per-entry reindex loop (F-RT5-GAP-1 / F-SOT-2); mirrors
# _DISCOVERY_MAX_SECONDS.  0 → treated as default per _env_float convention.
_SOT_REINDEX_MAX_SECONDS = _env_float("AI_MEMORY_SOT_REINDEX_MAX_SECONDS", 30.0)
# Stale-lock threshold: always >= 2x the reindex cap so a live holder (which
# releases within _SOT_REINDEX_MAX_SECONDS) can never own a lock older than this
# window.  The 300s floor preserves safe behaviour for the default cap (30s).
_LOCK_STALE_SECONDS = max(300.0, 2 * _SOT_REINDEX_MAX_SECONDS)

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

# Recognized source-container directory names.  When one is found NESTED
# (depth >= 2) with no co-located manifest it is a weak structural signal → the
# `low` confidence tier (TD-744 Q5).
_SOURCE_DIR_NAMES: frozenset[str] = frozenset(
    {
        "src",
        "lib",
        "libs",
        "app",
        "apps",
        "pkg",
        "packages",
        "cmd",
        "internal",
        "modules",
        "services",
        "components",
    }
)

# Ordinal confidence tiers, strongest → weakest (TD-744 Q5).  The label is a
# human-review triage priority paired with the mandatory ``inferred_from`` source;
# it is NEVER an auto-approve gate and never licenses auto-filling semantics.
_CONFIDENCE_TIERS: tuple[str, ...] = ("high", "medium", "low")

# Non-committed staging-proposal filename written by ``--write-proposal``
# (TD-744 Q4).  The committed registry is ``registry.yaml`` and is NEVER written
# by this engine (BP-030); the only writable artifact is this draft.
_PROPOSED_FILENAME = "registry.proposed.yaml"

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
            timeout=_GIT_SUBPROCESS_TIMEOUT,
        )
        return Path(result.stdout.strip()) / ".sot" / "registry.yaml"
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
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
    """sha256(file_bytes)[:8].  Returns None on read error or a directory.

    This is the ``content-digest`` strategy for FILE sot_locations.  Directory
    sot_locations are covered by the ``tree-digest`` strategy (BP-039) dispatched
    via ``_compute_entry_digest`` → the shadow module; see ``select_strategy``.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()[:8]


def _compute_entry_digest(
    strategy: str, full_path: Path | None, excludes=None
) -> str | None:
    """Drift digest for an entry, dispatched by enum strategy (no shell exec).

    - ``content-digest`` → ``sha256(file)[:8]`` (file SOT; behavior-preserving).
    - ``tree-digest`` / ``git-tree-hash`` → BP-039 ``vN:`` tree digest (dir SOT).
    - ``temporal`` / ``git-ahead-behind`` → None (those boundaries rely on the
      temporal / ref checks, not a content digest).

    ``excludes`` (the registry's committed exclude config) is applied to the
    directory tree digest.  Returns None when the path is absent or the shadow
    module is unavailable for a tree strategy (graceful degrade to the file-only
    pre-TD-675 behavior).
    """
    if full_path is None or not full_path.exists():
        return None
    if strategy == "content-digest":
        return _sha256_short(full_path)
    if strategy in ("tree-digest", "git-tree-hash"):
        if shadow is None:
            return None
        try:
            if excludes is None:
                return shadow.tree_digest(full_path).digest
            return shadow.tree_digest(full_path, excludes).digest
        except Exception:
            return None
    return None  # temporal / git-ahead-behind: no content digest


def _load_registry_config(registry_path: Path) -> tuple[tuple[str, ...], str]:
    """Read the registry's committed drift config (BP-039 exclude set + BP-042
    DOCOWNERS pointer).  Returns ``(effective_excludes, docowners_rel)``.

    ``effective_excludes`` = the shadow module's defaults extended by the
    registry's optional top-level ``exclude:`` list; ``docowners_rel`` is the
    optional ``docowners:`` pointer (default ``.sot/DOCOWNERS``).  Degrades to
    sane defaults on any parse error (the drift loop already reported a bad
    registry as a fatal error upstream).
    """
    default_excludes = shadow.DEFAULT_EXCLUDES if shadow is not None else ()
    docowners_rel = ".sot/DOCOWNERS"
    try:
        raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return tuple(default_excludes), docowners_rel
    if not isinstance(raw, dict):
        return tuple(default_excludes), docowners_rel
    extra = raw.get("exclude", [])
    excludes = tuple(default_excludes) + tuple(
        e for e in extra if isinstance(e, str) and e
    )
    docs = raw.get("docowners")
    if isinstance(docs, str) and docs:
        docowners_rel = docs
    return excludes, docowners_rel


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
    """True when the registry's human ``last_verified`` date is STRICTLY newer
    than the cache's ``last_verified_at`` — a fresh human re-confirmation
    (spec §3, DD-B).

    This is the only machine-observable signal that ties a baseline advance to
    the human HITL act; without it the baseline is held on detected drift.

    Heal condition (deviation-(a), F-ENG-2): the registry ``last_verified`` is
    day-granular (a human date) while the held ``last_verified_at`` is a sub-day
    machine timestamp.  The comparison is strict ``>``: a human re-confirm
    registers only when the registry date is strictly later than the held
    timestamp's date — a same-day fix+reconfirm is NOT recognized until a
    strictly-later human date.  Strict ``>`` is deliberate; a day-granular ``>=``
    would re-open H3-b (a same-day machine check could spuriously re-bless drift).
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
    strategy: str = "content-digest",
    digest_version: str = "",
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
        # ``unverified`` is an intentionally-transient, in-session marker (DEC-
        # PM332-D2, Option B): on the next no-drift run this entry promotes to
        # ``clean`` via _advance() below even without an explicit human re-confirm.
        # This is accepted behavior, not a defect — the residual cross-run risk is
        # narrow and self-limiting; the durability tradeoff is documented in
        # UNIFIED-FIX-SPEC §DD-B and docs/AIM-SOT.md.  The DD-C verify gate still
        # surfaces the in-session cold-start as CONDITIONAL.
        return {
            "sot_location": loc,
            "last_verified_at": now_iso,
            "last_verified_sha": current_sha or "",
            "last_verified_mtime": mtime,
            "last_verified_size": size,
            "drift_status": "missing" if loc_missing else "unverified",
            "drift_detail": detail,
            "drift_strategy": strategy,
            "digest_version": digest_version,
        }

    def _hold(status: str) -> dict:
        # Keep the prior baseline (sha + at + mtime/size + strategy) so the
        # proposal re-fires until resolved — do NOT advance to drifted content.
        return {
            "sot_location": loc,
            "last_verified_at": prior.get("last_verified_at", now_iso),
            "last_verified_sha": prior_sha,
            "last_verified_mtime": prior.get("last_verified_mtime"),
            "last_verified_size": prior.get("last_verified_size"),
            "drift_status": status,
            "drift_detail": detail,
            "drift_strategy": prior.get("drift_strategy", strategy),
            "digest_version": prior.get("digest_version", digest_version),
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
            "drift_strategy": strategy,
            "digest_version": digest_version,
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


class _ScanBudget:
    """Shared dir-count + wall-time budget for one auto-discovery scan (F-SOT-3).

    A single instance is threaded through every ``_pruned_walk`` of a scan so
    the wall-time clock spans the whole discovery (manifests + ADR dirs), not
    each walk in isolation.  ``truncated`` / ``reason`` are set when a budget is
    hit so the caller can surface a signal instead of silently under-reporting.
    """

    def __init__(
        self,
        max_dirs: int = _MAX_DISCOVERY_DIRS,
        max_seconds: float = _DISCOVERY_MAX_SECONDS,
    ) -> None:
        self.max_dirs = max_dirs
        self._deadline = time.monotonic() + max_seconds if max_seconds > 0 else None
        self.truncated = False
        self.reason: str | None = None

    def exceeded(self, visited: int) -> bool:
        """True once this walk has visited ``visited`` dirs past either budget."""
        if self.max_dirs > 0 and visited >= self.max_dirs:
            self.truncated = True
            self.reason = "max_dirs"
            return True
        if self._deadline is not None and time.monotonic() > self._deadline:
            self.truncated = True
            self.reason = "wall_time"
            return True
        return False


def _pruned_walk(root: Path, budget: "_ScanBudget | None" = None):
    """``os.walk`` that prunes ``_SKIP_DIRS`` in-place (so skipped trees are
    never descended into) and stops on the shared dir-count / wall-time budget
    (F-A2-5 + F-SOT-3).

    Pruning during traversal — rather than ``rglob`` + post-hoc filtering —
    avoids walking node_modules / .venv / build trees on every run; the budget
    bounds the worst case on pathological or slow-filesystem repos.
    """
    if budget is None:
        budget = _ScanBudget()
    for visited, (dirpath, dirnames, filenames) in enumerate(os.walk(root)):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        if budget.exceeded(visited):
            # Surface the truncation rather than silently capping discovery
            # ("no silent caps") — components below the budget are not scanned.
            detail = (
                f"{budget.max_dirs} directories"
                if budget.reason == "max_dirs"
                else "the wall-time budget"
            )
            print(
                f"aim-sot: discovery scan truncated at {detail}; "
                "components beyond the budget were not scanned.",
                file=sys.stderr,
            )
            return
        yield Path(dirpath), dirnames, filenames


def _discover_manifests(
    project_root: Path, budget: "_ScanBudget | None" = None
) -> list[dict]:
    """Manifest files → boundary_type=component candidates."""
    manifest_order = sorted(_MANIFEST_FILENAMES)
    candidates: list[dict] = []
    for dirpath, _dirnames, filenames in _pruned_walk(project_root, budget):
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


def _discover_adr_dirs(
    project_root: Path, budget: "_ScanBudget | None" = None
) -> list[dict]:
    """ADR/decision directories → boundary_type=concern candidates."""
    candidates: list[dict] = []
    for dirpath, _dirnames, _filenames in _pruned_walk(project_root, budget):
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


def _discover_nested_source_dirs(
    project_root: Path, budget: "_ScanBudget | None" = None
) -> list[dict]:
    """Nested source-container dirs with no manifest → ``low`` candidates (Q5).

    A weak structural signal: a directory whose name matches a recognized
    source-container pattern, sits below the top level (depth >= 2), and carries
    no co-located manifest.  Triage priority only — the human still authors all
    semantics; ``low`` never licenses auto-approval.
    """
    candidates: list[dict] = []
    for dirpath, _dirnames, filenames in _pruned_walk(project_root, budget):
        if dirpath == project_root:
            continue
        rel = dirpath.relative_to(project_root)
        if len(rel.parts) < 2:
            continue  # top-level dirs are covered by _discover_top_dirs (medium)
        if dirpath.name not in _SOURCE_DIR_NAMES:
            continue
        if _MANIFEST_FILENAMES & set(filenames):
            continue  # a co-located manifest makes it a high-confidence component
        loc = str(rel) + "/"
        cid = str(rel).replace(os.sep, "-")
        candidates.append(
            {
                "id": cid,
                "boundary_type": "path",
                "sot_location": loc,
                "confidence": "low",
                "inferred_from": "nested_source_directory",
            }
        )
    return sorted(candidates, key=lambda c: c["sot_location"])


def _discover_candidates(
    project_root: Path, budget: "_ScanBudget | None" = None
) -> list[dict]:
    """Orchestrate all scanners, deduplicated and sorted by sot_location.

    A shared ``_ScanBudget`` (created here if not supplied) bounds the combined
    manifest + ADR + nested-source walks by dir-count and wall-time (F-SOT-3);
    the caller can pass its own to read ``budget.truncated`` afterwards.  Scanners
    are concatenated strongest-first (manifest/ADR high → top-dir medium →
    nested-source low) so dedup-by-location keeps the highest-confidence label.
    """
    if budget is None:
        budget = _ScanBudget()
    seen: set[str] = set()
    all_candidates: list[dict] = []
    for c in (
        _discover_manifests(project_root, budget)
        + _discover_adr_dirs(project_root, budget)
        + _discover_top_dirs(project_root)
        + _discover_nested_source_dirs(project_root, budget)
    ):
        loc = c["sot_location"]
        if loc not in seen:
            seen.add(loc)
            all_candidates.append(c)
    # Invariant: every emitted candidate carries a known confidence tier (Q5).
    # This is the one consumer of _CONFIDENCE_TIERS — it keeps the ordinal-tier
    # vocabulary and the scanners' hard-coded labels from silently diverging.
    for c in all_candidates:
        if c["confidence"] not in _CONFIDENCE_TIERS:
            raise ValueError(
                f"candidate {c['id']!r} has unknown confidence "
                f"{c['confidence']!r} (expected one of {_CONFIDENCE_TIERS})"
            )
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
# Staging proposal (TD-744) — non-committed .sot/registry.proposed.yaml
# ---------------------------------------------------------------------------


def _git_owner_candidates(
    project_root: Path, locations: list[str], top_n: int = 3
) -> dict[str, list[dict]]:
    """Advisory ``git log`` owner candidates per sot_location (TD-744 Q6).

    Returns ``{sot_location: [{"name": str, "commits": int}, ...]}`` with the
    top-N committers by commit count.  This is a FLAGGED HINT only — it is never
    written into the ``owner`` field (BP-029/BP-030); the human remains the
    decider.  Degrades SILENTLY to ``{}`` when the project is not a git repo or
    git is unavailable; never raises.
    """
    try:
        rev = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=_GIT_SUBPROCESS_TIMEOUT,
        )
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    if rev.returncode != 0 or rev.stdout.strip() != "true":
        return {}

    out: dict[str, list[dict]] = {}
    for loc in locations:
        try:
            res = subprocess.run(
                ["git", "-C", str(project_root), "log", "--format=%an", "--", loc],
                capture_output=True,
                text=True,
                timeout=_GIT_SUBPROCESS_TIMEOUT,
            )
        except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
            # Skip this location but keep results already accumulated for earlier
            # locations (matching the non-zero-returncode `continue` below).
            continue
        if res.returncode != 0:
            continue
        counts: dict[str, int] = {}
        for line in res.stdout.splitlines():
            name = line.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
        if not counts:
            continue
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
        out[loc] = [{"name": n, "commits": c} for n, c in ranked]
    return out


def _format_proposal_yaml(
    candidates: list[dict], owner_candidates: dict[str, list[dict]]
) -> str:
    """Render the staging proposal body (TD-744 Q4).

    Structural fields (``id``, ``boundary_type``, ``sot_location``, ``status``,
    ``added_by``) are filled; every human-owned semantic field is an explicit
    ``TODO(human):`` placeholder (BP-029); ``confidence`` + the mandatory
    ``inferred_from`` ride as per-entry advisory comments (they are not registry
    schema fields), as does the advisory ``owner_candidates`` block (Q6).

    The entry mappings are serialized with ``yaml.safe_dump`` rather than
    hand-built ``key: value`` lines so that arbitrary ``id`` / ``sot_location``
    values — which originate from on-disk directory names and may legally contain
    YAML metacharacters (``foo: bar``, ``@weird``, ``[bracket``, ``foo"bar``) —
    are correctly quoted/escaped. Entry bodies are therefore rendered via
    ``yaml.safe_dump`` and always parse; the advisory ``owner_candidates``
    comment lines are control-char-sanitized (so an embedded newline in a
    location or hint can never break a ``#`` line out into uncommented YAML),
    so the full draft round-trips through ``yaml.safe_load``.
    """
    lines: list[str] = [
        "# .sot/registry.proposed.yaml — STAGING PROPOSAL (NOT the committed registry)",
        "#",
        "# Generated by `aim-sot detect-propose run --write-proposal`. This is a",
        "# NON-COMMITTED draft — the engine never writes .sot/registry.yaml (BP-030).",
        "#",
        "# To adopt: fill every TODO(human) field, prune candidates you don't want,",
        "# then RENAME this file to .sot/registry.yaml and run `aim-sot verify`.",
        "# That promotion + commit IS your approval (BP-030 human authority).",
        "#",
        "# Recommend git-ignoring .sot/registry.proposed.yaml (a draft, not the SoT).",
    ]
    if owner_candidates:
        lines.append("#")
        lines.append(
            "# ── owner_candidates (ADVISORY — from `git log`, NEVER an owner value) ──"
        )
        lines.append(
            "# Top committers per location, a hint to help you author `owner` by hand."
        )
        lines.append(
            "# The human decides; these are written into NO field (BP-029/BP-030)."
        )

        # Comment lines are hand-built (not yaml.safe_dump), so a control char
        # (e.g. an embedded newline in a dir-derived loc or a git hint) would
        # split the `#` line and leak uncommented YAML. Replace any non-printable
        # char with a space before interpolating.
        def _comment_safe(s: str) -> str:
            return "".join(c if c.isprintable() else " " for c in s)

        for loc in sorted(owner_candidates):
            hint = ", ".join(
                f"{c['name']} ({c['commits']})" for c in owner_candidates[loc]
            )
            lines.append(f"#   {_comment_safe(loc)}: {_comment_safe(hint)}")
    lines.append("")
    lines.append('schema_version: "1.0"')
    lines.append("")
    if not candidates:
        lines.append("entries: []")
        return "\n".join(lines) + "\n"

    lines.append("entries:")
    for c in candidates:
        lines.append(
            f"  # confidence: {c['confidence']}  ·  inferred_from: {c['inferred_from']}"
        )
        # Structural fields carry REAL values; every semantic field is a
        # TODO(human) STRING (BP-029).  safe_dump quotes/escapes whatever the raw
        # id / sot_location contain, so the draft always yaml.safe_load-parses.
        entry = {
            "id": c["id"],
            "kind": (
                "TODO(human): <service|library|application|api|data"
                "|infrastructure|decision|documentation>"
            ),
            "boundary_type": c["boundary_type"],
            "sot_location": c["sot_location"],
            "owner": "TODO(human): <owning team or person>",
            "description": "TODO(human): <one-line summary of this boundary>",
            "last_verified": "TODO(human): <YYYY-MM-DD a person re-confirmed this>",
            "added_by": "aim-sot bootstrap",
            "provenance_note": "TODO(human): <how/why this entry was added>",
            "status": "proposed",
        }
        entry_yaml = yaml.safe_dump(
            [entry],
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
            width=4096,
        ).rstrip("\n")
        # Nest the dumped list item under the 2-space `entries:` indentation.
        lines.append(textwrap.indent(entry_yaml, "  "))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_proposal_file(
    proposed_path: Path,
    candidates: list[dict],
    owner_candidates: dict[str, list[dict]],
    *,
    scan_root: Path,
    force: bool,
) -> tuple[bool, str]:
    """Write the non-committed staging proposal (TD-744 Q3/Q4).

    Skips (returns ``written=False``) when the file already exists and ``force``
    is False, protecting in-progress human edits (idempotency, Q3).

    BP-030 (defense in depth — the committed ``registry.yaml`` is never written).
    A basename check alone is bypassable (a pre-existing ``registry.proposed.yaml``
    symlinked to ``registry.yaml`` would be followed; a ``../registry.proposed.yaml``
    basename also passes a name check yet writes outside ``.sot/``).  Three
    independent guards close that:
      1. basename guard — reject any name but ``registry.proposed.yaml``;
      2. path confinement — the literal ``<scan_root>/.sot`` must not itself be a
         symlink, and the target's resolved parent must equal that directory.
         Rejecting a symlinked ``.sot`` is load-bearing: were ``.sot`` a symlink to
         an external dir, both sides of the resolved-parent comparison would
         resolve through it and compare equal, letting the draft be written
         outside the project.  With that rejection the guarantee is: the draft is
         only ever written to a real (non-symlinked) ``<scan_root>/.sot``
         directory, never through ``..`` traversal or a symlinked SOT dir;
      3. no-symlink-follow — refuse a pre-existing symlink at the target AND
         open with ``O_NOFOLLOW`` so a symlink planted even at write time (TOCTOU)
         can never be followed through to the committed registry.
    """
    # Guard 1 — basename: never write anything but the staging draft.
    if proposed_path.name != _PROPOSED_FILENAME:
        raise ValueError(f"refusing to write non-proposal path: {proposed_path}")

    # Guard 2 — confinement: the only legal target is
    # <scan_root>/.sot/registry.proposed.yaml.  Reject a symlinked .sot first —
    # otherwise both sides below resolve through it and compare equal, letting the
    # draft land outside the project.  Then resolve the PARENT (the file may not
    # exist yet) and compare against the expected .sot directory.
    sot_dir = scan_root / ".sot"
    if sot_dir.is_symlink():
        raise ValueError(f"refusing to write through a symlinked .sot dir: {sot_dir}")
    expected_dir = sot_dir.resolve()
    actual_dir = proposed_path.parent.resolve()
    if actual_dir != expected_dir:
        raise ValueError(f"refusing to write outside {expected_dir}: {proposed_path}")

    # Guard 3a — refuse a pre-existing symlink at the target (never follow it).
    if proposed_path.is_symlink():
        raise ValueError(f"refusing to write through a symlink: {proposed_path}")
    if proposed_path.exists() and not force:
        return False, (
            f"{proposed_path} already exists — skipping to protect in-progress "
            "edits. Re-run with --force to overwrite."
        )
    proposed_path.parent.mkdir(parents=True, exist_ok=True)
    body = _format_proposal_yaml(candidates, owner_candidates)
    # Guard 3b — O_NOFOLLOW: even if a symlink is planted between the check above
    # and this open, the open refuses to follow it (BP-030) rather than writing
    # through to the link target.
    fd = os.open(
        proposed_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        0o644,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(body)
    return True, f"Wrote staging proposal: {proposed_path}"


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

    ``current_sha`` is normally pre-computed by the caller via the strategy
    registry (file → content-digest, directory → tree-digest; BP-039), avoiding
    a duplicate read.  The comparison is digest-agnostic: it compares the
    pre-computed digest against the cached baseline whatever the strategy.
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

    ``current_sha`` is normally pre-computed by the caller via the strategy
    registry (file → content-digest, directory → tree-digest; BP-039).  The
    comparison is digest-agnostic — it works for file and directory SOT alike.
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
    caller never advances ``registry_sha`` on a failed rebuild (M1).  ``reason``
    classifies a failure so the caller reports it accurately (DEFECT-4): writes
    rejected by core validation vs. the store being unreachable."""

    ok: bool
    stored: int
    reason: str | None = None


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
        lock_path = _DRIFT_CACHE_DIR / f"sot_reindex_{safe_id}.lock"
        # Sweep orphaned lock files (R2 / F-SOT-2): flock self-heals on process
        # death, so a surviving .lock is cosmetic for that crash/exit case.  For
        # a live holder, the max()-derived _LOCK_STALE_SECONDS invariant
        # (= max(300, 2 * _SOT_REINDEX_MAX_SECONDS)) ensures any reindex still
        # running — it releases within _SOT_REINDEX_MAX_SECONDS — can never own
        # a lock older than this threshold, so no LIVE lock is ever swept.
        try:
            if (
                lock_path.exists()
                and (time.time() - lock_path.stat().st_mtime) > _LOCK_STALE_SECONDS
            ):
                lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        lock_fd = open(  # noqa: SIM115 — held across the yield; closed in finally
            lock_path, "w", encoding="utf-8"
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
            # registry (M1 prepare-then-replace).  An unparseable registry never
            # reaches here — yaml.safe_load raises to the outer except below.
            return ReindexResult(True, 0)

        if _qdrant_client is None:
            config = get_config()
            qdrant_client = get_qdrant_client(config)
        else:
            qdrant_client = _qdrant_client
            config = None  # type: ignore[assignment]

        storage = MemoryStorage(config=config) if _storage is None else _storage

        # Stamp every 5b row with the SHA of the registry it was rebuilt from, so
        # consult can prove the cache fresh against the committed file directly
        # (F2): a bare ``reindex`` rebuilds 5b but does not advance the 5a drift
        # cache, so binding consult's freshness gate to 5a left it file-falling-back
        # forever after a reindex.  ``registry_sha`` is not a MemoryPayload field, so
        # it lands as a top-level Qdrant payload field via ``**extra_fields``.
        registry_sha = _registry_sha(registry_path)

        # Replacement payload set (content = non-machine-state fields).
        # default=str serializes YAML-native datetime.date/datetime (an unquoted
        # registry ``last_verified: 2026-06-01`` parses as datetime.date) to its
        # isoformat string instead of raising TypeError and failing the whole
        # reindex (F-ENG2-1).
        prepared: list[str] = [
            json.dumps(
                {k: v for k, v in entry.items() if k not in _MACHINE_STATE_FIELDS},
                ensure_ascii=False,
                default=str,
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
            rejected = 0  # writes refused by core validation (DEFECT-4)
            _cap_fired = False  # R1 wall-time guard (F-RT5-GAP-1 / F-SOT-2)
            _deadline = time.monotonic() + _SOT_REINDEX_MAX_SECONDS
            for content in prepared:
                if time.monotonic() > _deadline:
                    # Never silent: emit a visible warning, then stop.  Remaining
                    # entries stay in the registry and are indexed next run.
                    print(
                        f"[aim-sot] reindex wall-time cap ({_SOT_REINDEX_MAX_SECONDS:.0f}s)"
                        f" reached; {stored}/{len(prepared)} entries stored —"
                        " remainder will be indexed next run.",
                        file=sys.stderr,
                    )
                    _cap_fired = True
                    break
                try:
                    result = storage.store_memory(
                        content=content,
                        cwd=str(registry_path.parent),
                        memory_type=MemoryType.SOT_ENTRY,
                        source_hook="aim_sot_detect_propose",
                        session_id=f"aim_sot_reindex_{project_id}",
                        group_id=project_id,
                        collection=COLLECTION_CONVENTIONS,
                        registry_sha=registry_sha,
                    )
                    if result.get("status") in ("stored", "duplicate"):
                        stored += 1
                except ValueError as exc:
                    # store_memory raises ValueError("Validation failed: ...") when
                    # the payload is refused by core validation (storage.py:375).
                    # Count it so a 0-row reindex is reported as a validation
                    # rejection, not a phantom connectivity issue (DEFECT-4).
                    if "Validation failed" in str(exc):
                        rejected += 1
                    # other ValueErrors (and below) are non-fatal per-entry
                except Exception:
                    pass  # per-entry failure is non-fatal

            # Cap fired mid-loop: sha must NOT advance so the next run completes
            # the reindex (F-SOT-2 / F-RT5-GAP-1).
            if _cap_fired:
                return ReindexResult(False, stored, "reindex_capped")
            # Delete ran but every re-store failed → the 5b cache is
            # emptied-not-restored.  Report failure so the caller does NOT advance
            # registry_sha and the rebuild retries next run rather than masking the
            # loss (F-ENG2-2).  Classify the cause so cmd_reindex reports it
            # accurately: validation rejection vs. store-unreachable (DEFECT-4).
            if prepared and stored == 0:
                reason = "validation_rejected" if rejected else "store_unreachable"
                return ReindexResult(False, 0, reason)
        return ReindexResult(True, stored)

    except Exception:
        # Graceful no-op when the store is unreachable — existing 5b points are
        # untouched because no delete runs until after preparation succeeds.
        return ReindexResult(False, 0, "store_unreachable")


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


def _run_cold_start_discovery(
    registry_path: Path | None, args: argparse.Namespace
) -> int:
    """Cold-start (no .sot/registry.yaml): run discovery and emit candidate
    proposals so a project can be bootstrapped from zero (DEFECT-2, Option A).

    Propose-only: candidates go to stdout with a hint to copy them into
    .sot/registry.yaml — this never creates or writes the registry.  Kept fully
    separate from the registry-present drift path: no drift detection, no 5b
    reindex, no 5a cache.  The scan root is the conforming project root if the
    path conforms, else the current working directory (registry_path is None or a
    flat override) — discovery is bounded by the _pruned_walk cap (M5/F-A2-5).
    """
    scan_root = _project_root_from_registry(registry_path) if registry_path else None
    if scan_root is None:
        scan_root = Path(os.getcwd())

    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from memory.project import resolve_project_id

        project_id = resolve_project_id(cwd=str(scan_root))
    except Exception as exc:
        print(f"Error: could not resolve project_id: {exc}", file=sys.stderr)
        return 1

    scan_budget = _ScanBudget()
    candidates = _discover_candidates(scan_root, scan_budget)
    new_candidates = _filter_new_candidates(candidates, [])
    limit = (
        0
        if getattr(args, "all", False)
        else getattr(args, "limit", _DEFAULT_CANDIDATE_LIMIT)
    )
    capped, deferred_count = _apply_cap(new_candidates, limit)
    candidate_proposals = [_make_candidate_proposal(c) for c in capped]

    # --write-proposal (TD-744 Q4): scaffold a non-committed staging draft from
    # the discovered candidates.  Skips an existing draft unless --force (Q3).
    # The committed registry is never written (BP-030).
    proposal_written = False
    proposal_path: str | None = None
    proposal_message: str | None = None
    owner_candidates: dict[str, list[dict]] = {}
    if getattr(args, "write_proposal", False):
        proposed_path = scan_root / ".sot" / _PROPOSED_FILENAME
        owner_candidates = _git_owner_candidates(
            scan_root, [c["sot_location"] for c in capped]
        )
        try:
            proposal_written, proposal_message = _write_proposal_file(
                proposed_path,
                capped,
                owner_candidates,
                scan_root=scan_root,
                force=getattr(args, "force", False),
            )
        except (ValueError, OSError) as exc:
            # A BP-030 guard tripped (ValueError: symlink / out-of-confinement
            # target) or the O_NOFOLLOW open hit a TOCTOU-planted symlink
            # (OSError: ELOOP): refuse the write, surface it as the same graceful
            # message, leave the committed registry untouched.
            proposal_written = False
            proposal_message = f"aim-sot: refusing to write staging proposal: {exc}"
            print(proposal_message, file=sys.stderr)
        proposal_path = str(proposed_path)

    if getattr(args, "as_json", False):
        print(
            json.dumps(
                {
                    "drift_proposals": [],
                    "candidate_proposals": candidate_proposals,
                    "deferred_count": deferred_count,
                    "project_id": project_id,
                    "budget_truncated": bool(scan_budget.truncated),
                    "proposal_written": proposal_written,
                    "proposal_path": proposal_path,
                    "owner_candidates": owner_candidates,
                }
            )
        )
    else:
        print(
            "No .sot/registry.yaml found — this project is not yet under SOT "
            "tracking. Discovered the candidates below; review them, then copy the "
            "ones you want into .sot/registry.yaml (authoring owner/description/"
            "provenance_note by hand), and run aim-sot verify to approve.\n"
            "Tip: `--write-proposal` scaffolds a ready-to-edit "
            ".sot/registry.proposed.yaml draft for you.\n"
        )
        print(_format_human([], candidate_proposals, deferred_count))
        if proposal_message:
            print("\n" + proposal_message)
        if owner_candidates:
            print("\nowner_candidates (advisory — from git log, never an owner value):")
            for loc in sorted(owner_candidates):
                hint = ", ".join(
                    f"{c['name']} ({c['commits']})" for c in owner_candidates[loc]
                )
                print(f"  {loc}: {hint}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Main detect-propose run."""
    # --- Resolve registry ---
    registry_path = _find_registry(getattr(args, "registry", None))
    if registry_path is None or not registry_path.exists():
        # Cold-start: no registry yet → run discovery + propose (Option A,
        # DEFECT-2).  Propose-only — never writes .sot/registry.yaml.
        return _run_cold_start_discovery(registry_path, args)

    # --write-proposal scaffolds only on the cold-start path; with a committed
    # registry present it is a no-op — tell the human how to surface candidates.
    if getattr(args, "write_proposal", False):
        print(
            "aim-sot: --write-proposal has no effect when a committed registry is "
            "present; use 'detect-propose run' to surface new candidates.",
            file=sys.stderr,
        )

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
    # Committed drift config (BP-039 exclude set + BP-042 DOCOWNERS pointer).
    effective_excludes, docowners_rel = _load_registry_config(registry_path)
    # Seeded from the prior cache so throttle-skipped entries (still in the
    # registry, but TTL-skipped this run) retain their record.  Orphans — records
    # for ids no longer in the committed registry — are pruned after the drift loop
    # below so the 5a cache mirrors exactly the current registry, matching the 5b
    # reindex prune and preventing a stale baseline from resurfacing if an id is
    # later re-added.
    updated_components: dict = dict(cache.get("components", {}))

    # --- Drift detection across registry entries ---
    drift_proposals: list[dict] = []
    strategy_frictions: list[dict] = (
        []
    )  # FRICTION findings for unimplemented strategies
    for entry in entries:
        eid = entry.get("id", "")
        if not eid:
            continue
        if _should_skip_component(eid, cache, resolve_root, force_recheck=reg_changed):
            continue

        prior = cache.get("components", {}).get(eid)

        # Compute the drift digest + stat once per entry — reused for hash/decl
        # checks and the 5a component record (avoids a duplicate read).  The
        # digest is dispatched by the enum strategy registry (no shell exec):
        # file → content-digest, directory → tree-digest (BP-039), overridable
        # by a schema-validated drift_strategy field.
        loc = entry.get("sot_location", "")
        full_path = (resolve_root / loc) if loc else None
        exists = bool(full_path and full_path.exists())
        strategy = (
            shadow.select_strategy(entry, full_path, strategy_frictions)
            if shadow is not None
            else "content-digest"
        )
        digest_version = (
            shadow.DIGEST_VERSION
            if (shadow is not None and strategy in ("tree-digest", "git-tree-hash"))
            else ""
        )
        current_sha = (
            _compute_entry_digest(strategy, full_path, effective_excludes)
            if exists
            else None
        )
        mtime, size = _stat_mtime_size(full_path) if exists else (None, None)

        # R-1 (lead): a drift_strategy switch or a digest-version bump is a
        # RE-BASELINE, not drift.  Default the prior strategy to the historical
        # "content-digest" so existing file baselines are never spuriously
        # re-based on upgrade.
        prior_strategy = (prior or {}).get("drift_strategy", "content-digest")
        prior_version = (prior or {}).get("digest_version", "")
        rebaseline = bool((prior or {}).get("last_verified_sha")) and (
            prior_strategy != strategy or prior_version != digest_version
        )

        drifts: list[dict] = []
        loc_drift = _check_location_drift(entry, resolve_root)
        if loc_drift:
            drifts.append(loc_drift)
        temp_drift = _check_temporal_staleness(entry)
        if temp_drift:
            drifts.append(temp_drift)
        # Skip the content-based checks on a re-baseline run (the digest is not
        # comparable across strategies/versions); the record advances to the new
        # baseline below.
        if not rebaseline:
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
            strategy=strategy,
            digest_version=digest_version,
        )

    # --- Auto-discovery: new candidates (skipped for non-conforming roots) ---
    scan_budget = _ScanBudget()
    if project_root is not None:
        candidates = _discover_candidates(project_root, scan_budget)
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

    # --- Prune 5a orphans: keep only ids present in the committed registry ---
    # Mirrors the 5b reindex prune so the drift cache never retains a baseline for
    # a component removed from (or never in) the current registry.
    registry_ids = {e.get("id", "") for e in entries if e.get("id")}
    updated_components = {
        eid: rec for eid, rec in updated_components.items() if eid in registry_ids
    }

    # --- Persist 5a cache ---
    cache["components"] = updated_components
    cache["generated_at"] = now_iso

    # --- [CL] shadow-git + doc-drift + findings pass (settled decision #3) ---
    # ONE BP-039 digest at Stop → if changed: shadow commit, git diff → doc-drift,
    # findings emit.  Gated behind --shadow (the Stop hooks pass it) so the default
    # `run` path is byte-for-byte unchanged (behavior-preserving).  Skipped for a
    # flat --registry override (no conforming, scannable project root).
    findings: list[dict] = []
    docs_stale = 0
    digest_truncated = False
    if (
        getattr(args, "shadow", False)
        and project_root is not None
        and shadow is not None
    ):
        shadow_summary = shadow.run_shadow_pass(
            project_id,
            project_root,
            cache,
            excludes=effective_excludes,
            docowners_rel=docowners_rel,
        )
        findings = shadow_summary.get("findings", []) + strategy_frictions
        docs_stale = shadow_summary.get("docs_stale", 0)
        digest_truncated = bool(shadow_summary.get("digest_truncated", False))
    elif strategy_frictions:
        findings = strategy_frictions

    # Budget-truncation signal (F-SOT-3): either full-project walk hit its budget
    # → the drift/doc-drift channel is incomplete this session.  Surfaced in the
    # JSON pipe so the [CL] hook can emit a visible, non-fatal warning instead of
    # silently reporting zero findings.
    budget_truncated = bool(scan_budget.truncated or digest_truncated)

    # Live drift rollup for the [ST] ambient surface (consult digest reads this).
    n_changed = len(drift_proposals)
    n_clean = max(0, len(registry_ids) - n_changed)
    cache["drift_rollup"] = {
        "clean": n_clean,
        "changed": n_changed,
        "docs_stale": docs_stale,
        "generated_at": now_iso,
    }

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
                    "findings": findings,
                    "drift_rollup": cache["drift_rollup"],
                    "budget_truncated": budget_truncated,
                }
            )
        )
    else:
        print(_format_human(drift_proposals, candidate_proposals, deferred_count))
        if findings:
            # The [CL] findings surface — the existing sot_drift_stop stderr line
            # is absorbed here (settled decision #3): one unified emit, no double.
            print(
                f"\n[ai-memory] SOT findings: {len(findings)} "
                "(drift / doc-staleness / errors) — see --json for the pipe.",
                file=sys.stderr,
            )
        if budget_truncated:
            print(
                "[ai-memory] SOT: drift scan hit its budget (large/slow project) "
                "— results incomplete this run; tune AI_MEMORY_SOT_* budgets or "
                "narrow the registry exclude set.",
                file=sys.stderr,
            )

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
        if result.reason == "validation_rejected":
            # Writes were refused by core validation (e.g. source_hook not in the
            # allow-list) — a real, actionable failure, not a connectivity issue.
            # Exit non-zero so it is not mistaken for a transient store outage.
            print(
                f"aim-sot reindex: writes rejected by core validation for project "
                f"'{project_id}'; 0 entries indexed (existing cache left intact). "
                "Check src/memory/validation.py allow-lists.",
                file=sys.stderr,
            )
            return 1
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
    run_p.add_argument(
        "--write-proposal",
        action="store_true",
        dest="write_proposal",
        help=(
            "On a registry-less project, scaffold a non-committed "
            ".sot/registry.proposed.yaml staging draft (structural fields filled, "
            "semantic fields as TODO(human)). Never writes the committed registry."
        ),
    )
    run_p.add_argument(
        "--force",
        action="store_true",
        dest="force",
        help=(
            "With --write-proposal, overwrite an existing "
            ".sot/registry.proposed.yaml (default: skip to protect in-progress edits)."
        ),
    )
    run_p.add_argument(
        "--shadow",
        action="store_true",
        dest="shadow",
        help=(
            "Run the [CL] detect pass: BP-039 digest → BP-040 shadow-git commit "
            "→ BP-042 doc-drift → structured findings (the Stop-hook cadence). "
            "Off by default; the per-CLI Stop hooks pass it."
        ),
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
