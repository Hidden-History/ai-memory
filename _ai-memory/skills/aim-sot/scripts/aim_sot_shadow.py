#!/usr/bin/env python3
"""
aim-sot shadow — SOT-owned shadow-git substrate, tree-digest gate, doc-drift,
and the structured findings pipe (TD-675 / TASK-079).

This module is the detection substrate shared by all four CLIs.  It holds NO
CLI-specific logic: the per-CLI Stop/SessionStart hooks call the engine
(``aim_sot_detect_propose.py``), which imports the primitives here.  Nothing in
this module writes the committed ``.sot/registry.yaml`` or any oversight register.

Layers (design §1):
    SETUP GATE  — BP-041 idempotent run-once sentinel
    LAYER 1     — BP-039 sorted-per-file-SHA-256 tree-digest ("did anything change?")
    LAYER 2     — BP-040 bare two-pointer shadow git ("what / where / how")
    LAYER 3     — BP-042 git-diff doc-drift ("which docs are now stale")
    FINDINGS    — one structured emitter for drift + doc-staleness + ERROR + FRICTION

Machine-local state (never committed) lives under
``${AI_MEMORY_INSTALL_DIR:-~/.ai-memory}/``:
    sot-git/<project_id>/      bare shadow repo (BP-040)
    sot-setup/sot_setup_<id>.json   setup sentinel (BP-041)
    drift-state/sot_drift_<id>.json the 5a drift cache (BP-027; owned by the engine)

Of-record state (committed, team-visible) lives under the user repo's
``.sot/``: ``registry.yaml`` (BP-030) and ``DOCOWNERS`` (BP-042 Pattern A).

Safety rails (non-negotiable, design §8):
    - No arbitrary code execution — strategies are enum-selected built-ins.
    - Non-invasive — zero writes into the user's project tree (bare repo +
      explicit two-pointer; ``--separate-git-dir`` is rejected).
    - git is a required tool; the project itself need NOT be a git repo.
"""

import contextlib
import fcntl
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Machine-local roots (honor AI_MEMORY_INSTALL_DIR; tests patch these attrs)
# ---------------------------------------------------------------------------

_INSTALL_DIR = Path(
    os.environ.get("AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory"))
)
_SHADOW_GIT_ROOT = _INSTALL_DIR / "sot-git"
_SETUP_DIR = _INSTALL_DIR / "sot-setup"
# Per-file hash cache lives beside the engine's 5a drift-state (BP-027 / BP-048).
_DRIFT_STATE_DIR = _INSTALL_DIR / "drift-state"

# Versions — bump SETUP_VERSION when setup does something new; bump
# SCHEMA_VERSION when the sentinel JSON shape changes (BP-041 Q3).
SETUP_SCHEMA_VERSION = "1"
SETUP_VERSION = "2.9.0"

# Tree-digest algorithm version.  A v1:→v2: bump is a RE-BASELINE, not drift
# (R-1): the engine compares the stored digest_version before treating a digest
# mismatch as drift.
DIGEST_VERSION = "v1"


def _env_float(name: str, default: float) -> float:
    """Read a positive float from the environment, falling back to ``default``.

    A blank, non-numeric, or non-positive value yields the default so a typo
    never silently disables the budget.  ``0`` is treated as "use default" for
    this reason (an explicit disable is intentionally not offered here — the
    digest budget is a safety guard, not an opt-out).
    """
    raw = os.environ.get(name, "")
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return default
    return val if val > 0 else default


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back to ``default``."""
    raw = os.environ.get(name, "")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    return val if val > 0 else default


# Wall-time + file-count budget for the whole-project tree-digest (F-SOT-3).
# The [CL] Stop hook caps the engine subprocess at ~20s; an unbounded digest of
# a large/slow-fs project (measured 80.7s / 9,846 files on /mnt/e) blows that
# cap and the hook silently times out, so the drift channel produces zero
# findings forever.  These defaults keep a typical project well under the hook
# cap while bounding the pathological case to a *signaled* truncation rather
# than a hang.  The 18s wall-time sits just under the hook cap: with the BP-048
# warm cache + scandir stat-fold a large-dir warm run now completes (measured
# well below 18s) instead of truncating, while the cap still guards a cold or
# pathological run.  Override per-project via the environment.
_DIGEST_MAX_SECONDS = _env_float("AI_MEMORY_SOT_DIGEST_MAX_SECONDS", 18.0)
_DIGEST_MAX_FILES = _env_int("AI_MEMORY_SOT_DIGEST_MAX_FILES", 20000)


def _safe_id(project_id: str) -> str:
    """Filesystem-safe form of a project_id (mirrors the 5a cache convention)."""
    return project_id.replace("/", "__")


# ---------------------------------------------------------------------------
# BP-039 — sorted-per-file-SHA-256 tree-digest + exclude semantics
# ---------------------------------------------------------------------------

# Default exclude globs applied to the POSIX relpath BEFORE the file set is
# frozen (BP-039 §ignore-semantics).  Committed alongside the SOT intent rather
# than read from an ambient .gitignore, so the identical file set is compared on
# every machine.  Shared with the shadow git's info/exclude (BP-040 Q2).
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "node_modules/",
    ".npm/",
    "dist/",
    "build/",
    "*.egg-info/",
    ".eggs/",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    ".sot/",
    ".DS_Store",
    ".idea/",
    ".vscode/",
    "Thumbs.db",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.log",
)


def path_excluded(rel: str, patterns) -> bool:
    """gitignore-style match of a POSIX relpath against ``patterns``.

    Supports the subset the default exclude set needs: a trailing-slash dir
    prefix (``build/`` → any path under ``build/`` or the dir itself), a bare
    name (matched against any path segment, e.g. ``__pycache__``), and an
    ``fnmatch`` glob applied to both the full relpath and the basename
    (``*.pyc``, ``.env.*``).  Matching is on the relpath, never the absolute
    path, so it is cross-machine deterministic.
    """
    rel = rel.replace(os.sep, "/")
    if rel.startswith("./"):
        rel = rel[2:]
    if not rel:
        return False
    segments = rel.split("/")
    base = segments[-1]
    for pat in patterns:
        p = pat.replace(os.sep, "/").strip()
        if not p:
            continue
        if p.endswith("/"):
            d = p.rstrip("/")
            has_glob = any(c in d for c in "*?[")
            if has_glob:
                # fnmatch each non-final segment (directory component) and the
                # whole relpath for a bare top-level dir name (e.g. "foo.egg-info").
                if any(
                    fnmatch.fnmatch(seg, d) for seg in segments[:-1]
                ) or fnmatch.fnmatch(rel, d):
                    return True
            elif d in segments[:-1] or rel == d or rel.startswith(d + "/"):
                return True
            continue
        if "/" in p:
            if fnmatch.fnmatch(rel, p):
                return True
            continue
        # bare name or basename glob: match any path segment or the basename
        if p in segments or fnmatch.fnmatch(base, p):
            return True
    return False


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    """Stream sha256 of a file's bytes (never loads the whole file)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# BP-048 — incremental per-file hash cache (accelerator ONLY, never authority)
# ---------------------------------------------------------------------------

# Per-entry hash-algorithm version.  Bump when the content hash changes (e.g.
# SHA-256 → BLAKE3) so every stale entry is silently treated as a miss.
FILE_HASH_CACHE_VERSION = "1"

# Racy-clean guard (BP-048): a cache hit is trusted only when the file was last
# modified at least this long ago, so a same-second overwrite (WSL2/9p has 1s
# mtime resolution) can never be mistaken for "unchanged".  2s is safe for 1s
# granularity — ccache's proven horizon.
_FRESHNESS_HORIZON_NS = 2_000_000_000  # 2 seconds in nanoseconds

# Reserved scope for the whole-project digest (``run_shadow_pass``).  The
# double-underscore sentinel is deliberately a token no SOT ``entry_id`` can be,
# so a per-entry cache — even for an entry literally named ``tree`` — never
# collides with the whole-project cache and prunes it (LOW-1).
_WHOLE_TREE_SCOPE = "__whole_tree__"


def file_hash_cache_path(project_id: str, scope: str = _WHOLE_TREE_SCOPE) -> Path:
    """Return the per-file hash cache path for ``(project_id, scope)``.

    The cache is machine-local and co-located with the engine's 5a drift-state
    (BP-027 layout):
    ``~/.ai-memory/drift-state/sot_file_hash_<id>__<scope>__<tag>.json``.  Its
    ``.lock`` sibling guards the read-modify-write.

    ``scope`` isolates independent digest roots into separate cache files.  This
    is REQUIRED for correctness: :func:`tree_digest` prunes its cache to the
    file set of the root it walked, so two different roots (e.g. the whole
    project vs. a single directory SOT entry) sharing one cache would each prune
    away the other's entries.  ``run_shadow_pass`` uses the reserved
    :data:`_WHOLE_TREE_SCOPE`; the per-entry drift path passes the entry id.

    The ``<id>``/``<scope>`` stem is human-readable only: both are flattened with
    ``/`` → ``__``, so ``("a/b", "c")`` and ``("a", "b/c")`` would share the stem
    ``a__b__c``.  A NUL-delimited ``<tag>`` digest of the *raw*
    ``(project_id, scope)`` pair disambiguates them, so distinct pairs never
    collide on one file.

    Args:
        project_id: The active project id.
        scope: A token identifying the digest root (default
            :data:`_WHOLE_TREE_SCOPE` for the whole-project digest; use the entry
            id for a per-entry digest).

    Returns:
        The absolute path to this project+scope per-file hash cache JSON file.
    """
    stem = f"{_safe_id(project_id)}__{_safe_id(scope)}"
    tag = hashlib.sha256(f"{project_id}\x00{scope}".encode()).hexdigest()[:8]
    return _DRIFT_STATE_DIR / f"sot_file_hash_{stem}__{tag}.json"


def exclude_epoch(excludes) -> str:
    """Return the invalidation epoch for an exclude set (BP-048).

    A change to the exclude patterns changes which files are in the tree, so
    every cached hash must be discarded.  Hashing the sorted patterns yields a
    stable epoch that flips the whole cache stale on any exclude-config change.

    Args:
        excludes: The exclude globs the tree digest is computed with.

    Returns:
        The SHA-256 hex digest of the newline-joined, sorted patterns.
    """
    joined = "\n".join(sorted(str(p) for p in excludes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def load_file_hash_cache(
    project_id: str, excludes=DEFAULT_EXCLUDES, scope: str = _WHOLE_TREE_SCOPE
) -> dict:
    """Load the per-file hash cache for a project+scope, failing open (BP-048).

    Callable standalone (not only inside :func:`run_shadow_pass`) so the
    per-entry drift path can accelerate a directory digest.  The cache is always
    safe to discard: a missing, corrupt, version-mismatched, or
    epoch-mismatched file yields a fresh empty cache, so a cold start simply
    re-hashes everything.  The epoch is derived from ``excludes``, which MUST
    match the ``excludes`` later passed to :func:`tree_digest`.

    Args:
        project_id: The active project id.
        excludes: The exclude set the digest will use (drives the epoch).
        scope: The digest-root scope (see :func:`file_hash_cache_path`).

    Returns:
        A cache dict ``{"v", "epoch", "files": {rel: entry}}`` — freshly empty
        when the on-disk cache is absent, unreadable, or stale.
    """
    epoch = exclude_epoch(excludes)
    empty = {"v": FILE_HASH_CACHE_VERSION, "epoch": epoch, "files": {}}
    cache_path = file_hash_cache_path(project_id, scope)
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if (
        not isinstance(data, dict)
        or data.get("v") != FILE_HASH_CACHE_VERSION
        or data.get("epoch") != epoch
        or not isinstance(data.get("files"), dict)
    ):
        return empty
    return data


def save_file_hash_cache(
    project_id: str, cache: dict, scope: str = _WHOLE_TREE_SCOPE
) -> None:
    """Persist the per-file hash cache atomically under a ``flock`` (BP-048).

    Follows the BP-027 atomic-write pattern (temp file → ``flush`` → ``fsync`` →
    ``os.replace``) so an interrupted write never leaves corrupt JSON.  The
    read-modify-write is serialized with a stdlib :func:`fcntl.flock` advisory
    lock — the exact mechanism the 5a drift cache uses, so no third-party
    dependency is required (the cache is rebuildable, so a lock that cannot be
    acquired fails open rather than blocking the hot path).

    Args:
        project_id: The active project id.
        cache: The cache dict to persist.
        scope: The digest-root scope (see :func:`file_hash_cache_path`).
    """
    cache_path = file_hash_cache_path(project_id, scope)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = None
    try:
        lock_fd = open(  # noqa: SIM115 — held across the write, closed in finally
            str(cache_path) + ".lock", "w", encoding="utf-8"
        )
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError:
        if lock_fd is not None:
            lock_fd.close()
            lock_fd = None
    try:
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=cache_path.parent,
                delete=False,
                suffix=".tmp",
            ) as tmp:
                tmp_path = Path(tmp.name)
                json.dump(cache, tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_path, cache_path)
        except Exception:
            if tmp_path is not None:
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
            raise
    finally:
        if lock_fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


def get_file_hash(rel: str, full: Path, cache: dict, st=None) -> str:
    """Return the SHA-256 of ``full``, reusing a cached hash when unchanged.

    The ``(mtime_ns, size)`` pre-filter (BP-048) skips the file read when a
    cached entry matches and the file is older than the freshness horizon;
    otherwise the content is re-hashed and the entry refreshed.  Inode/device are
    deliberately omitted — unreliable on the WSL2/9p mount.  The returned hash is
    identical to a bare :func:`file_sha256`, so the cache never alters the digest.

    Args:
        rel: POSIX relpath key for the file within the tree.
        full: Absolute path to the file to hash.
        cache: The cache dict; its ``"files"`` map is updated in place on a miss.
        st: A pre-fetched ``stat_result`` (e.g. the ``os.scandir`` entry's stat)
            to avoid a redundant syscall on the WSL2/9p hot path; ``None`` stats
            ``full`` here.  For a regular file ``lstat`` and ``stat`` agree, so a
            ``follow_symlinks=False`` entry stat is a valid key source.

    Returns:
        The hex SHA-256 of the file's current content.
    """
    if st is None:
        st = os.stat(full)
    mtime_ns = st.st_mtime_ns
    size = st.st_size
    aged = (time.time_ns() - mtime_ns) >= _FRESHNESS_HORIZON_NS
    entry = cache["files"].get(rel)
    if (
        entry is not None
        and entry.get("v") == FILE_HASH_CACHE_VERSION
        and aged  # racy-clean retrieval guard
        and entry.get("mtime") == mtime_ns
        and entry.get("size") == size
    ):
        return entry["sha256"]
    sha256 = file_sha256(full)
    # STORE guard (FIX-S1): persist an entry ONLY when the file is already older
    # than the freshness horizon, so a NATURAL forward write (which advances the
    # mtime to ~now) can never reproduce a stored, already-aged mtime — a
    # same-second overwrite therefore cannot surface a stale hash.  Caveat: a
    # timestamp-*preserving* restore (``tar -x``, ``rsync -a``, an ``os.utime``
    # rewind) can stamp an old mtime onto new content and produce a stale hit;
    # that is the inherent limit of the ccache-style (mtime, size) horizon,
    # accepted here.  Too-fresh files (age < horizon) — including any with a
    # future or perpetually-"now" mtime — stay uncached and are re-hashed every
    # run (a perf residual only; the returned hash is always the true content
    # hash, so the digest stays exact).
    if aged:
        cache["files"][rel] = {
            "v": FILE_HASH_CACHE_VERSION,
            "mtime": mtime_ns,
            "size": size,
            "sha256": sha256,
        }
    return sha256


@dataclass
class TreeDigest:
    """Result of :func:`tree_digest`: the versioned digest plus the symlinks
    skipped (recorded per BP-039 — symlink policy is *skip*, made explicit).

    ``truncated`` is True when the walk hit the wall-time or file-count budget
    (F-SOT-3); the ``digest`` is then a partial sentinel that callers must NOT
    treat as drift or store as a baseline.

    ``changed_rels`` / ``deleted_rels`` (TD-730) are populated ONLY when a
    ``cache`` was supplied: the POSIX relpaths whose content hash differs from
    the cache's prior entry (new or modified), and the cached relpaths no longer
    present (deleted).  They let the caller stage a scoped ``git add`` instead of
    a whole-tree ``-A`` walk.  Empty on a cache-free run (the caller then falls
    back to the full ``add -A``).  Purely additive — existing callers/tests that
    construct or read a ``TreeDigest`` are unaffected."""

    digest: str
    skipped_symlinks: list[str]
    file_count: int
    truncated: bool = False
    changed_rels: list[str] = field(default_factory=list)
    deleted_rels: list[str] = field(default_factory=list)


def tree_digest(
    root: Path,
    excludes=DEFAULT_EXCLUDES,
    *,
    max_files: int | None = None,
    max_seconds: float | None = None,
    cache: dict | None = None,
) -> TreeDigest:
    """BP-039 sorted-per-file-SHA-256 hash-of-hashes over ``root``.

    Deterministic across walk-order, machine, and clone/restore:
      - regular files only; directories are not entries; symlinks are skipped
        and recorded (cycle-safe, platform-stable).
      - per-file summary line ``<hex>  <posix-relpath>\\n``; relpath is relative
        to ``root`` and POSIX-normalized (never absolute).
      - lines byte-sorted by the relpath-keyed line, then SHA-256'd.
      - ``DIGEST_VERSION`` prefix so the algorithm can evolve (R-1 re-baseline).

    Excludes are applied to the relpath before the file set is frozen.

    The walk is bounded by ``max_files`` and ``max_seconds`` (F-SOT-3); ``None``
    uses the module defaults (env-overridable).  On budget exceed the walk stops
    early and the result carries ``truncated=True`` with a partial digest the
    caller must discard (never compared as drift, never stored as a baseline).

    When ``cache`` is provided (a dict from :func:`load_file_hash_cache`), each
    file's hash is resolved through :func:`get_file_hash` so unchanged files skip
    the read (BP-048).  The cache is a pure accelerator: the resulting digest is
    byte-identical to a cache-free run.  Entries for files no longer present are
    pruned after a complete (non-truncated) walk.

    The traversal uses :func:`os.scandir` (not :func:`os.walk`) so the single
    per-entry syscall it already makes serves double duty: ``is_symlink`` is read
    from the cached ``d_type`` and the entry's own ``stat`` feeds the cache key —
    folding away the redundant ``lstat`` + ``stat`` the ``os.walk`` form incurred
    on every file (the dominant cost on the WSL2/9p hot path).
    """
    if max_files is None:
        max_files = _DIGEST_MAX_FILES
    if max_seconds is None:
        max_seconds = _DIGEST_MAX_SECONDS
    deadline = time.monotonic() + max_seconds if max_seconds > 0 else None

    lines: list[str] = []
    skipped: list[str] = []
    seen_rels: set[str] = set()
    changed_rels: list[str] = []
    # Snapshot the prior per-file hashes so the walk can report which rels changed
    # (TD-730 scoped-add source).  get_file_hash reassigns a cache entry to a fresh
    # dict on a miss, so a shallow copy of the mapping preserves the prior values.
    prior_hashes = dict(cache["files"]) if cache is not None else {}
    truncated = False
    # Explicit LIFO stack over os.scandir; symlinked directories are never
    # descended (mirrors os.walk followlinks=False) and excluded dirs are pruned
    # before descent so their subtrees are never read.
    stack: list[str] = [str(root)]
    while stack and not truncated:
        current = stack.pop()
        try:
            scan = os.scandir(current)
        except OSError:
            continue  # unreadable dir: skip (deterministic, same on every machine)
        subdirs: list[str] = []
        with scan:
            for entry in scan:
                rel = os.path.relpath(entry.path, root).replace(os.sep, "/")
                try:
                    is_dir = entry.is_dir(follow_symlinks=True)
                except OSError:
                    is_dir = False
                if is_dir:
                    # Directory or symlink-to-directory: never a digest entry.
                    try:
                        if entry.is_symlink():
                            continue  # do not follow (followlinks=False parity)
                    except OSError:
                        continue
                    if path_excluded(rel + "/", excludes):
                        continue  # pruned — do not descend
                    subdirs.append(entry.path)
                    continue
                # Regular file, symlink-to-file, or broken symlink.
                # Budget gate BEFORE the per-file IO (sha256 dominates wall-time).
                if (max_files > 0 and len(lines) >= max_files) or (
                    deadline is not None and time.monotonic() > deadline
                ):
                    truncated = True
                    break
                if path_excluded(rel, excludes):
                    continue
                try:
                    if entry.is_symlink():
                        skipped.append(rel)
                        continue
                except OSError:
                    continue
                full = Path(entry.path)
                try:
                    if cache is not None:
                        # Reuse the entry's stat as the cache key — no extra
                        # syscall (lstat == stat for a non-symlink regular file).
                        digest = get_file_hash(
                            rel, full, cache, entry.stat(follow_symlinks=False)
                        )
                    else:
                        digest = file_sha256(full)
                except OSError:
                    # Unreadable regular file: skip but do not abort the whole
                    # digest — record nothing for it (deterministic: same skip on
                    # every machine where it is unreadable).
                    continue
                lines.append(f"{digest}  {rel}\n")
                if cache is not None:
                    seen_rels.add(rel)
                    prior = prior_hashes.get(rel)
                    if prior is None or prior.get("sha256") != digest:
                        changed_rels.append(rel)
        stack.extend(subdirs)
    # Prune deleted-file entries only after a complete walk; a truncated walk has
    # an incomplete file set and must not drop live entries (BP-048).
    if cache is not None and not truncated:
        cache["files"] = {k: v for k, v in cache["files"].items() if k in seen_rels}
    # Deleted rels (TD-730): cached paths absent from a COMPLETE walk.  A truncated
    # walk has an incomplete file set, so nothing is reported deleted (and the caller
    # early-returns on truncation before staging anyway).
    deleted_rels: list[str] = (
        [k for k in prior_hashes if k not in seen_rels]
        if cache is not None and not truncated
        else []
    )
    summary = "".join(sorted(lines))
    full_digest = (
        DIGEST_VERSION + ":" + hashlib.sha256(summary.encode("utf-8")).hexdigest()
    )
    return TreeDigest(
        digest=full_digest,
        skipped_symlinks=sorted(skipped),
        file_count=len(lines),
        truncated=truncated,
        changed_rels=changed_rels,
        deleted_rels=deleted_rels,
    )


# ---------------------------------------------------------------------------
# Drift strategy registry — enum-selected built-ins (NO arbitrary exec)
# ---------------------------------------------------------------------------

# The full safe strategy set (design §4).  ``drift_strategy`` in the registry is
# validated against this enum by verify S4 (schema-driven); a non-enum value is
# REJECTED, never executed.  Only ``content-digest`` and ``tree-digest`` are
# wired as default selectors today; the others are reserved, schema-valid
# opt-ins (``git-tree-hash`` needs the shadow git, ``git-ahead-behind`` needs a
# ref boundary, ``temporal`` is the date-only fallback).
STRATEGIES: tuple[str, ...] = (
    "content-digest",
    "tree-digest",
    "git-tree-hash",
    "git-ahead-behind",
    "temporal",
)

# Strategies that are schema-valid enum members but produce no content digest.
# Selecting one emits a FRICTION finding so it is never silently dropped.
_UNIMPLEMENTED_STRATEGIES: frozenset[str] = frozenset({"git-ahead-behind"})


def select_strategy(
    entry: dict, full_path: Path | None, findings: list | None = None
) -> str:
    """Pick the drift strategy for an entry.

    A schema-validated ``drift_strategy`` override wins (verify S4 guarantees it
    is one of :data:`STRATEGIES`).  Otherwise the default is by artifact shape:
    a directory ``sot_location`` → ``tree-digest`` (BP-039); a file → the
    existing ``content-digest`` (sha256(file)[:8], behavior-preserving).

    When ``findings`` is provided and the override is in
    :data:`_UNIMPLEMENTED_STRATEGIES`, a FRICTION finding is appended so the
    caller knows no content digest was computed for this entry.
    """
    override = entry.get("drift_strategy")
    if override in STRATEGIES:
        if override in _UNIMPLEMENTED_STRATEGIES and findings is not None:
            findings.append(
                friction_finding(
                    f"strategy '{override}' is reserved and not yet implemented "
                    "— no content digest will be computed for this entry; "
                    "use 'content-digest' or 'tree-digest' instead.",
                    where=entry.get("entry_id", "unknown"),
                    severity="LOW",
                )
            )
        return override
    if full_path is not None and full_path.is_dir():
        return "tree-digest"
    return "content-digest"


# ---------------------------------------------------------------------------
# BP-040 — bare two-pointer shadow git
# ---------------------------------------------------------------------------

# Written to <shadow>/info/exclude at setup.  The user never sees or edits this;
# it guarantees the same file set is snapshotted on every machine (no ambient
# .gitignore drift).  Mirrors DEFAULT_EXCLUDES with the .git internals first.
_SHADOW_EXCLUDE_LINES: tuple[str, ...] = (
    "# Written by aim-sot at setup (BP-040). The user never sees or edits this.",
    ".git",
    ".git/**",
    "__pycache__/",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    "node_modules/",
    ".npm/",
    "dist/",
    "build/",
    "*.egg-info/",
    ".eggs/",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    ".sot/",
    ".sot/**",
    ".DS_Store",
    ".idea/",
    ".vscode/",
    "Thumbs.db",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.log",
)

# Cap-and-rotate thresholds (BP-040 Q4).
_MAX_COMMITS = 500
_MAX_PACK_MB = 100

# S3-F1: inner `git add -A` cap, scoped to that one call (not run_git's general
# 30s default — gc/rev-list/etc. are unaffected).  Must stay below the hook
# layer's inner-subprocess cap so a timeout surfaces cleanly instead of a
# SIGKILL orphaning an in-flight add (coordinated cross-lane: inner-add 15s <
# hook inner-subprocess 20s < hook outer SIGALRM 25s).
_SHADOW_ADD_TIMEOUT_SECONDS = 15

# S3-F2: stale `index.lock` threshold.  `run_git` bounds every git call with
# `subprocess.run(timeout=...)`, which SIGKILLs the child on expiry, so no
# legitimate holder of a lock we created can outlive its own timeout.  Mirrors
# the `max(300, 2*cap)` convention in aim_sot_detect_propose.py's
# `_LOCK_STALE_SECONDS` (product-wide stale-lock invariant): the 2x multiplier
# absorbs mtime/clock-skew slop, the 300s floor guards against sweeping a
# genuinely live lock on a slow/laggy filesystem.
_SHADOW_LOCK_STALE_SECONDS = max(300.0, 2 * _SHADOW_ADD_TIMEOUT_SECONDS)

# TD-730: cap on how many paths a scoped `git add -A -- <paths>` will carry on the
# command line.  Above it the caller falls back to a full `add -A` — both to dodge
# ARG_MAX and because staging that many paths is no cheaper than the whole-tree add.
_SCOPED_ADD_MAX_PATHS = 1000


def _project_gitignore_lines(project_dir: Path) -> tuple[str, ...]:
    """Lines from the project's own on-disk ``.gitignore``, if present (S3-F1).

    Folded into the shadow's ``info/exclude`` after the mandatory list so a
    project's own nested-clone/backup conventions (unpredictable in general —
    e.g. this workspace's ``pov-work*/`` or ``_ai-memory_backup_*/``) are
    picked up automatically instead of hardcoded here.  A *tracked*
    ``.gitignore`` is identical on every machine that clones the project, so
    this preserves the module's reproducibility rationale (deliberately NOT
    reading the ambient/untracked excludesfile) while generalizing beyond any
    one project's naming choices.  Absent file, or one that isn't valid UTF-8
    (e.g. a stray byte from a Windows-authored repo), → no lines, no error.
    """
    try:
        text = (project_dir / ".gitignore").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    return tuple(text.splitlines())


def shadow_git_dir(project_id: str) -> Path:
    """``~/.ai-memory/sot-git/<project_id>`` — the bare shadow repo."""
    return _SHADOW_GIT_ROOT / _safe_id(project_id)


def _git_env(project_id: str, project_dir: Path) -> dict:
    """Subprocess env pinning the two pointers (BP-040 Q1): GIT_DIR = the bare
    shadow repo, GIT_WORK_TREE = the user's project.  Equivalent to
    ``--git-dir``/``--work-tree`` but keeps command lines clean."""
    env = dict(os.environ)
    env["GIT_DIR"] = str(shadow_git_dir(project_id))
    env["GIT_WORK_TREE"] = str(project_dir)
    return env


def run_git(project_id: str, project_dir: Path, *args: str, timeout: int = 30):
    """Run a git command against the shadow repo with the two-pointer env."""
    return subprocess.run(
        ["git", *args],
        env=_git_env(project_id, project_dir),
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def git_available() -> bool:
    """True iff the ``git`` binary is callable (git is a required tool)."""
    try:
        return (
            subprocess.run(
                ["git", "--version"], capture_output=True, text=True
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_shadow_git(project_id: str, project_dir: Path) -> None:
    """Idempotently create + configure the bare shadow repo (BP-040, BP-041 Q4).

    Every action is check-then-create: ``git init --bare`` is re-run-safe, config
    is set each call (cheap, declarative), and ``info/exclude`` is rewritten to
    the mandatory list.  ``--separate-git-dir`` is never used — it would write a
    ``.git`` pointer file into the user's tree.
    """
    shadow = shadow_git_dir(project_id)
    shadow.parent.mkdir(parents=True, exist_ok=True)
    if not (shadow / "HEAD").exists():
        subprocess.run(
            ["git", "init", "--bare", str(shadow)],
            capture_output=True,
            text=True,
            check=True,
        )
    # Config (idempotent set). core.worktree pins the work-tree so plain commands
    # need no --work-tree; the noise/perf/safety knobs are BP-040 Q1/Q4.
    for key, val in (
        ("core.worktree", str(project_dir)),
        ("status.showUntrackedFiles", "no"),
        ("gc.auto", "256"),
        ("gc.pruneExpire", "30.days.ago"),
        ("gc.autoPackLimit", "10"),
        ("core.symlinks", "false"),
        # Commits are machine-local snapshots; pin an identity so commit never
        # fails on a host without a configured git user.
        ("user.name", "aim-sot"),
        ("user.email", "aim-sot@localhost"),
    ):
        subprocess.run(
            ["git", f"--git-dir={shadow}", "config", key, val],
            capture_output=True,
            text=True,
        )
    info_dir = shadow / "info"
    info_dir.mkdir(parents=True, exist_ok=True)
    exclude_lines = _SHADOW_EXCLUDE_LINES
    gitignore_lines = _project_gitignore_lines(project_dir)
    if gitignore_lines:
        exclude_lines = (
            *_SHADOW_EXCLUDE_LINES,
            "",
            "# Folded in from the project's own tracked .gitignore (S3-F1) —",
            "# picks up this project's nested-clone/backup conventions.",
            *gitignore_lines,
        )
    (info_dir / "exclude").write_text("\n".join(exclude_lines) + "\n", encoding="utf-8")


def shadow_head(project_id: str, project_dir: Path) -> str | None:
    """Current shadow HEAD sha, or None when there are no commits yet."""
    res = run_git(project_id, project_dir, "rev-parse", "HEAD")
    sha = res.stdout.strip()
    return sha if res.returncode == 0 and sha else None


class ShadowGitError(Exception):
    """Raised by shadow_commit when a git operation (add/commit) returns non-zero."""


def _clear_stale_index_lock(project_id: str) -> None:
    """Clear an orphaned ``index.lock`` left by a killed ``git add`` (S3-F2).

    A timed-out (SIGKILLed) ``git add -A`` leaves ``index.lock`` behind with no
    process left to release it — every later add then fails with "Unable to
    create '.../index.lock': File exists", permanently wedging the shadow-git.
    Since ``run_git`` bounds every call with ``subprocess.run(timeout=...)``,
    no legitimate holder of a lock we created can outlive its own timeout, so a
    lock older than :data:`_SHADOW_LOCK_STALE_SECONDS` is provably orphaned —
    clear it before staging.  Best-effort: an ``OSError`` (e.g. lost the race
    to another process, or unwritable) is not fatal — ``git add`` below will
    simply fail with its usual error if the lock is still genuinely held.
    """
    lock_path = shadow_git_dir(project_id) / "index.lock"
    try:
        if (
            lock_path.exists()
            and (time.time() - lock_path.stat().st_mtime) > _SHADOW_LOCK_STALE_SECONDS
        ):
            lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def shadow_commit(
    project_id: str,
    project_dir: Path,
    message: str,
    pathspec: list[str] | None = None,
) -> str | None:
    """``add`` + commit against the shadow repo; return the new HEAD sha.

    ``pathspec`` (TD-730) scopes the stage: ``None`` → whole-tree ``git add -A``
    (the behavior-preserving default and fallback); a non-empty list → the scoped
    ``git add -A -- <paths>`` that stages only those relpaths (add/modify/delete),
    skipping the expensive whole-tree lstat/readdir walk on a slow mount.  Both
    forms still honor ``info/exclude`` (#258 scoped-exclude) and the stale-lock
    clear + inner-add cap below (#258 recovery net).  An empty list means "nothing
    changed since the last digest" → the ``add`` is skipped entirely; the index is
    left as-is so a prior run's staged-but-uncommitted change still commits here.

    Returns None (and does not commit) when the index is clean.  Raises
    :exc:`ShadowGitError` on a git error so the caller can surface an ERROR
    finding without aborting the session.
    """
    # Stage, then test the index: ``git diff --cached --quiet`` exits 0 when
    # nothing is staged (clean → skip, no empty snapshot) and 1 when there are
    # staged changes.  This is correct even on the first commit, where every file
    # is untracked (a plain ``status`` would hide them under the repo's
    # status.showUntrackedFiles=no).
    _clear_stale_index_lock(project_id)
    if pathspec is None:
        add = run_git(
            project_id, project_dir, "add", "-A", timeout=_SHADOW_ADD_TIMEOUT_SECONDS
        )
        if add.returncode != 0:
            raise ShadowGitError(
                f"git add failed (rc={add.returncode}): {add.stderr.strip()}"
            )
    elif pathspec:
        # Scoped stage.  Deleted paths in the pathspec are always tracked (every
        # file that enters the digest cache is reported changed and committed that
        # same run), so a deletion stages cleanly.  The one abort case is a
        # never-tracked path hashed by the digest then removed before this add (a
        # sub-ms TOCTOU): git returns "pathspec did not match" (rc=128) → the
        # ShadowGitError below trips the caller's dirty flag → a full `add -A`
        # resync next run (#258 recovery net), so nothing is lost.
        add = run_git(
            project_id,
            project_dir,
            "add",
            "-A",
            "--",
            *pathspec,
            timeout=_SHADOW_ADD_TIMEOUT_SECONDS,
        )
        if add.returncode != 0:
            raise ShadowGitError(
                f"git add failed (rc={add.returncode}): {add.stderr.strip()}"
            )
    # else: empty pathspec → nothing changed → skip add (index untouched).
    staged = run_git(project_id, project_dir, "diff", "--cached", "--quiet")
    if staged.returncode == 0:
        return None  # nothing staged → clean → skip
    commit = run_git(project_id, project_dir, "commit", "-m", message, "--quiet")
    if commit.returncode != 0:
        raise ShadowGitError(
            f"git commit failed (rc={commit.returncode}): {commit.stderr.strip()}"
        )
    return shadow_head(project_id, project_dir)


def shadow_gc(project_id: str, project_dir: Path) -> None:
    """Bounded ``git gc`` after the Stop commit (BP-040 Q4 layer 1).  Never
    ``--aggressive`` on the hot path."""
    run_git(project_id, project_dir, "gc", "--prune=30.days.ago", "--quiet", timeout=60)


def cap_and_rotate(project_id: str, project_dir: Path) -> bool:
    """Cap-and-rotate when the shadow repo exceeds the commit/size bounds.

    At ≥500 commits or ≥100 MB packed, run a one-shot aggressive gc (BP-040 Q4
    layer 3).  Returns True when a rotation ran.  History squashing beyond gc is
    intentionally NOT done here (out of scope; gc reclaims the bulk).
    """
    res = run_git(project_id, project_dir, "rev-list", "--count", "HEAD")
    try:
        count = int(res.stdout.strip() or "0")
    except ValueError:
        count = 0
    pack = shadow_git_dir(project_id) / "objects" / "pack"
    pack_mb = 0
    if pack.exists():
        pack_mb = sum(f.stat().st_size for f in pack.glob("*")) // (1024 * 1024)
    if count >= _MAX_COMMITS or pack_mb >= _MAX_PACK_MB:
        run_git(
            project_id,
            project_dir,
            "gc",
            "--aggressive",
            "--prune=now",
            "--quiet",
            timeout=120,
        )
        return True
    return False


def teardown(project_id: str) -> None:
    """Remove the shadow repo entirely — zero user-project residue (BP-040 Q6)."""
    shadow = shadow_git_dir(project_id)
    if shadow.exists():
        import shutil

        shutil.rmtree(shadow, ignore_errors=True)


# ---------------------------------------------------------------------------
# BP-041 — idempotent run-once setup sentinel
# ---------------------------------------------------------------------------


def sentinel_path(project_id: str) -> Path:
    """``~/.ai-memory/sot-setup/sot_setup_<project_id>.json`` (never committed)."""
    return _SETUP_DIR / f"sot_setup_{_safe_id(project_id)}.json"


def is_setup_valid(project_id: str) -> bool:
    """Fast-exit gate (~0.35 ms): True iff setup is done AND current.

    Invalidation, cheapest-first (BP-041 Q3): sentinel absent → corrupt →
    schema_version mismatch → setup_version mismatch → explicit reconfigure
    (``AIM_SOT_RECONFIGURE=1``).  The shadow ``.git`` presence is NOT checked
    here — that is an on-demand ``--verify`` diagnostic, not a per-session stat.
    """
    if os.environ.get("AIM_SOT_RECONFIGURE") == "1":
        return False
    path = sentinel_path(project_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False  # corrupt → treat as absent
    if data.get("schema_version") != SETUP_SCHEMA_VERSION:
        return False
    return data.get("setup_version") == SETUP_VERSION


def _write_sentinel(project_id: str, project_dir: Path) -> None:
    """Write the sentinel LAST (atomic temp→replace), proof-of-completion."""
    path = sentinel_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "project_id": project_id,
        "setup_version": SETUP_VERSION,
        "setup_at": datetime.now(timezone.utc).isoformat(),
        "setup_by": "aim-sot/setup-workflow",
        "artifacts": {
            "shadow_git": {
                "path": str(shadow_git_dir(project_id)),
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    }
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(data, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
        raise


def run_setup(project_id: str, project_dir: Path) -> bool:
    """Full setup.  Sentinel is written ONLY after all artifacts verify (BP-041
    Q4): partial failure ⇒ sentinel absent ⇒ retry next session.  Returns True
    on success."""
    ensure_shadow_git(project_id, project_dir)
    # Verify the artifact exists before recording completion.
    if not (shadow_git_dir(project_id) / "HEAD").exists():
        return False
    _write_sentinel(project_id, project_dir)
    return True


def ensure_setup(project_id: str, project_dir: Path) -> bool:
    """Skip-fast when valid, else run setup.  Returns True iff setup is usable
    after the call (valid sentinel + shadow repo present)."""
    if is_setup_valid(project_id):
        return True
    return run_setup(project_id, project_dir)


# ---------------------------------------------------------------------------
# BP-042 — git-history change detection + doc-drift correlation
# ---------------------------------------------------------------------------


@dataclass
class FileChange:
    """One ``git diff --name-status`` row (BP-042 Q1)."""

    status: str  # 'A' | 'M' | 'D' | 'R' | 'C'
    similarity: int | None  # rename/copy score 0-100, else None
    old_path: str
    new_path: str | None  # destination for R/C, else None

    @property
    def path(self) -> str:
        """The change's effective current path (new_path for R/C, else old)."""
        return self.new_path or self.old_path


def parse_name_status(text: str) -> list[FileChange]:
    """Parse ``git diff --name-status`` output into typed FileChange rows."""
    changes: list[FileChange] = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        parts = line.split("\t")
        raw = parts[0]
        code = raw[0]
        if code in ("R", "C") and len(parts) == 3:
            similarity = int(raw[1:]) if len(raw) > 1 and raw[1:].isdigit() else None
            changes.append(FileChange(code, similarity, parts[1], parts[2]))
        elif len(parts) >= 2:
            changes.append(FileChange(code, None, parts[1], None))
    return changes


def get_change_set(
    project_id: str, project_dir: Path, since_sha: str, until_sha: str = "HEAD"
) -> list[FileChange]:
    """``git diff --name-status <since>..<until>`` over the shadow history."""
    res = run_git(
        project_id, project_dir, "diff", "--name-status", since_sha, until_sha
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "git diff failed")
    return parse_name_status(res.stdout)


def load_docowners(
    project_dir: Path, rel_path: str = ".sot/DOCOWNERS"
) -> list[tuple[str, list[str]]]:
    """Parse the DOCOWNERS file (BP-042 Pattern A): ``<doc-glob>  <code-glob...>``.

    Defaults to ``.sot/DOCOWNERS`` (the single committed SOT home), NOT repo root
    — it is of-record class (committed, team-visible) and consumed only by this
    engine.  ``rel_path`` honors a registry ``docowners:`` pointer override.
    Blank lines and ``#`` comments are ignored.  Returns a list of
    ``(doc_glob, [code_globs])`` rules in file order.
    """
    path = project_dir / rel_path
    rules: list[tuple[str, list[str]]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rules
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        rules.append((parts[0], parts[1:]))
    return rules


def _glob_match(path: str, glob: str) -> bool:
    """Match a POSIX path against a DOCOWNERS glob.

    A trailing ``/**`` (or bare ``dir/``) matches anything under the dir; other
    globs use ``fnmatch`` with ``*`` allowed to span ``/`` so ``src/api/**`` and
    ``docs/api/*.md`` behave as authors expect.
    """
    path = path.replace(os.sep, "/")
    glob = glob.replace(os.sep, "/")
    if glob.endswith("/**"):
        prefix = glob[:-3]
        return path == prefix or path.startswith(prefix + "/")
    if glob.endswith("/"):
        return path.startswith(glob)
    # Translate '**' → '*' so a single fnmatch '*' (which already spans '/') covers it.
    return fnmatch.fnmatch(path, glob.replace("**", "*"))


# Path-class predicates for the false-positive guards (BP-042 Q3).
def _is_test_path(p: str) -> bool:
    p = p.replace(os.sep, "/")
    base = p.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{p}"
        or "/__tests__/" in f"/{p}"
        or base.startswith("test_")
        or base.endswith(("_test.py", "_test.go", ".test.ts", ".test.js", ".spec.ts"))
        or base in ("conftest.py",)
    )


def _is_doc_path(p: str) -> bool:
    p = p.replace(os.sep, "/")
    return p.startswith("docs/") or p.endswith((".md", ".mdx", ".rst"))


def _is_internal_path(p: str) -> bool:
    p = p.replace(os.sep, "/")
    return "/internal/" in f"/{p}" or "/_internal/" in f"/{p}"


def correlate_doc_drift(
    changes: list[FileChange],
    docowners: list[tuple[str, list[str]]],
    project_dir: Path,
    trigger_commit: dict | None = None,
) -> list[dict]:
    """Correlate a change set against DOCOWNERS → DOC_DRIFT findings (BP-042).

    For each changed code path, find the DOCOWNERS rules whose code-globs cover
    it and emit a finding for each owned doc-glob.  False-positive guards
    (BP-042 Q3) are applied to the *whole* change set first: if every changed
    path is test-only, doc-only, or internal-only, no findings are emitted.
    Severity: a deleted/renamed code path → HIGH; otherwise MEDIUM (area-level
    correlation, Pattern A precision).
    """
    if not changes or not docowners:
        return []

    # Guard: skip when the commit is entirely test-only / doc-only / internal-only.
    # Note: a reformat-only guard is deferred — ``--name-status`` cannot see line
    # content, so all-M is indistinguishable from a normal modify commit; findings
    # are advisory/propose-only and a reviewer can dismiss a formatter false-positive.
    paths = [c.path for c in changes]
    if all(_is_test_path(p) for p in paths):
        return []
    if all(_is_doc_path(p) for p in paths):
        return []
    if all(_is_internal_path(p) for p in paths):
        return []

    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for change in changes:
        cpath = change.path
        # Per-path guards: never let a test/doc/internal path trigger a doc.
        if _is_test_path(cpath) or _is_doc_path(cpath) or _is_internal_path(cpath):
            continue
        # For renames/copies, also match old_path so a rename-away from a watched
        # area is still correlated to its doc (F-L2).
        match_paths = {cpath}
        if change.status in ("R", "C") and change.old_path:
            match_paths.add(change.old_path)
        for doc_glob, code_globs in docowners:
            if not any(_glob_match(p, g) for p in match_paths for g in code_globs):
                continue
            # Resolve the doc-glob to concrete doc files when it is a literal or
            # a simple glob under the project; fall back to the glob itself.
            doc_targets = _resolve_doc_glob(project_dir, doc_glob)
            for doc in doc_targets:
                key = (doc, cpath)
                if key in seen:
                    continue
                seen.add(key)
                status_word = {
                    "A": "Added",
                    "M": "Modified",
                    "D": "Deleted",
                    "R": "Renamed",
                    "C": "Copied",
                }.get(change.status, change.status)
                severity = "HIGH" if change.status in ("D", "R") else "MEDIUM"
                findings.append(
                    emit_finding(
                        finding_type="DOC_DRIFT",
                        severity=severity,
                        doc_file=doc,
                        trigger_path=f"{cpath} ({status_word})",
                        trigger_commit=trigger_commit or {},
                        anchor_type="DOCOWNERS_MAP",
                        recommended_action=(
                            f"Review {doc} against the change to {cpath}."
                        ),
                    )
                )
    return findings


def _resolve_doc_glob(project_dir: Path, doc_glob: str) -> list[str]:
    """Expand a DOCOWNERS doc-glob to existing doc files, else return the glob.

    Keeps findings concrete when possible (``docs/api/*.md`` → the real files)
    while never failing if the doc dir is absent (returns ``[doc_glob]``)."""
    g = doc_glob.replace(os.sep, "/")
    if any(ch in g for ch in "*?["):
        try:
            matched = sorted(
                str(p.relative_to(project_dir)).replace(os.sep, "/")
                for p in project_dir.glob(g)
                if p.is_file()
            )
        except (OSError, ValueError):
            matched = []
        return matched or [doc_glob]
    return [doc_glob]


# ---------------------------------------------------------------------------
# Findings pipe — one structured emitter for ALL findings (design §6)
# ---------------------------------------------------------------------------


def emit_finding(
    finding_type: str,  # DOC_DRIFT | SOT_ANOMALY | ERROR | FRICTION
    severity: str,  # HIGH | MEDIUM | LOW | INFO
    doc_file: str,
    trigger_path: str,
    trigger_commit: dict,
    anchor_type: str,
    recommended_action: str,
    bp_id: str = "BP-042",
) -> dict:
    """Build one structured finding dict (design §6 / BP-042 Q4).

    The engine EMITS these (in its ``--json`` output); only Parzival writes the
    oversight register.  ALL finding classes — drift, doc-staleness, anomalies,
    and tool ERROR/FRICTION — flow through this single pipe so nothing is
    silently dropped.
    """
    return {
        "bp_id": bp_id,
        "finding_type": finding_type,
        "severity": severity,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "doc_file": doc_file,
        "trigger_path": trigger_path,
        "trigger_commit": trigger_commit,
        "anchor_type": anchor_type,
        "recommended_action": recommended_action,
    }


def error_finding(message: str, where: str, severity: str = "HIGH") -> dict:
    """Convenience emitter for a tool ERROR (git failure, parse error)."""
    return emit_finding(
        finding_type="ERROR",
        severity=severity,
        doc_file="",
        trigger_path=where,
        trigger_commit={},
        anchor_type="NONE",
        recommended_action=message,
        bp_id="BP-042",
    )


def friction_finding(message: str, where: str, severity: str = "MEDIUM") -> dict:
    """Convenience emitter for a FRICTION (ambiguity resolved, workaround applied)."""
    return emit_finding(
        finding_type="FRICTION",
        severity=severity,
        doc_file="",
        trigger_path=where,
        trigger_commit={},
        anchor_type="NONE",
        recommended_action=message,
        bp_id="BP-042",
    )


# ---------------------------------------------------------------------------
# Stop-path orchestration — ONE digest → commit → diff → doc-drift → findings
# ---------------------------------------------------------------------------


def run_shadow_pass(
    project_id: str,
    project_dir: Path,
    drift_state: dict,
    excludes=DEFAULT_EXCLUDES,
    docowners_rel: str = ".sot/DOCOWNERS",
) -> dict:
    """The [CL] detect pass (settled decision #3): ONE BP-039 digest at Stop →
    if changed, drive (1) shadow-git commit, (2) git diff → doc-drift, (3)
    findings emit.  No double tree-walk, no double emit.

    ``drift_state`` is the 5a cache dict (mutated in place: stores
    ``project_digest``, ``last_verified_sha``, ``drift_rollup``).  ``excludes``
    and ``docowners_rel`` carry the registry's committed config (BP-039 exclude
    set / BP-042 DOCOWNERS pointer).  Returns a summary
    ``{committed, digest_changed, findings, docs_stale}`` for the caller to fold
    into its JSON output.  Never raises — git/parse failures become ERROR
    findings.
    """
    findings: list[dict] = []
    summary = {
        "committed": False,
        "digest_changed": False,
        "findings": findings,
        "docs_stale": 0,
        "digest_truncated": False,
    }

    if not git_available():
        findings.append(
            error_finding("git binary not available; shadow pass skipped", "shadow")
        )
        return summary

    try:
        if not ensure_setup(project_id, project_dir):
            findings.append(error_finding("shadow-git setup did not complete", "setup"))
            return summary
    except Exception as exc:  # pragma: no cover - defensive
        findings.append(error_finding(f"setup error: {exc}", "setup"))
        return summary

    # LAYER 1 — one BP-039 digest of the project tree, accelerated by the BP-048
    # per-file hash cache.  The cache is a pure accelerator: load failures degrade
    # to a cache-free (cold) digest with identical output.
    cache = None
    try:
        cache = load_file_hash_cache(project_id, excludes)
    except Exception:  # pragma: no cover - defensive; cache is optional
        cache = None
    # TD-730: was the cache warm (had prior entries) BEFORE the digest walk mutates
    # it?  A cold/empty cache can't source a trustworthy changed-set, so the scoped
    # `git add` is used only when the cache was already warm this run.
    cache_warm = bool(cache and cache.get("files"))
    try:
        td = tree_digest(project_dir, excludes, cache=cache)
    except Exception as exc:  # pragma: no cover - defensive
        findings.append(error_finding(f"tree-digest error: {exc}", "tree-digest"))
        return summary
    # Persist the cache even on a truncated walk (FIX-S3): a truncated run still
    # computed real, correct per-file hashes for the files it reached — those are
    # valid entries, so persisting them lets repeated truncated runs incrementally
    # warm the cache until one completes (the bootstrap path for large/slow trees).
    # tree_digest itself gates the deleted-entry PRUNE on a complete walk, and the
    # partial *digest* is never stored as a baseline (guarded below).  Never fatal.
    if cache is not None:
        with contextlib.suppress(Exception):
            save_file_hash_cache(project_id, cache)

    # Budget-truncated digest is a partial sentinel (F-SOT-3): it must never be
    # compared as drift or stored as a baseline (a later complete run would read
    # it as a false re-baseline).  Emit a visible non-fatal signal and leave the
    # stored baseline untouched for the next session.
    if td.truncated:
        findings.append(
            friction_finding(
                "tree-digest exceeded its budget (large/slow project) — drift "
                "scan incomplete this session; baseline left unchanged. Tune "
                "AI_MEMORY_SOT_DIGEST_MAX_SECONDS / AI_MEMORY_SOT_DIGEST_MAX_FILES "
                "or narrow the registry exclude set.",
                where="tree-digest",
                severity="LOW",
            )
        )
        summary["digest_truncated"] = True
        return summary

    prior_digest = drift_state.get("project_digest", "")
    prior_version = drift_state.get("project_digest_version", "")
    # R-1: a digest-version bump is a re-baseline, not drift.
    version_changed = bool(prior_version) and prior_version != DIGEST_VERSION
    summary["digest_changed"] = (
        bool(prior_digest) and td.digest != prior_digest and not version_changed
    )

    last_sha = drift_state.get("last_verified_sha", "")
    # TD-730: pick the scoped-add pathspec.  Fall back to the whole-tree `add -A`
    # (pathspec=None) whenever the changed-set is not trustworthy — a cold/empty
    # cache this run, a prior commit that raised (may have left a file unstaged), or
    # a changed-set larger than the scoped-add cap.  Otherwise stage exactly the rels
    # the digest saw change (new/modified) or disappear (deleted).
    prior_commit_dirty = bool(drift_state.get("shadow_commit_dirty"))
    if not cache_warm or prior_commit_dirty:
        add_pathspec: list[str] | None = None
    else:
        changed = [*td.changed_rels, *td.deleted_rels]
        add_pathspec = None if len(changed) > _SCOPED_ADD_MAX_PATHS else changed
    new_head = None
    # Pessimistically mark dirty; cleared only after shadow_commit returns cleanly,
    # so any add/commit failure forces a full `add -A` resync on the next run.
    drift_state["shadow_commit_dirty"] = True
    try:
        # Always (idempotently) snapshot at Stop so the next session has a
        # baseline; commit is skipped internally when the tree is clean.
        new_head = shadow_commit(
            project_id,
            project_dir,
            f"sot-snapshot: session-end {project_id} "
            f"{datetime.now(timezone.utc).isoformat()}",
            pathspec=add_pathspec,
        )
        drift_state["shadow_commit_dirty"] = False
    except ShadowGitError as exc:
        findings.append(error_finding(str(exc), "commit"))
    except Exception as exc:  # pragma: no cover - defensive
        findings.append(error_finding(f"shadow commit error: {exc}", "commit"))

    if new_head:
        summary["committed"] = True
        # LAYER 3 — doc-drift over exactly the delta since the last verified sha.
        if last_sha:
            try:
                changes = get_change_set(project_id, project_dir, last_sha, new_head)
                docowners = load_docowners(project_dir, docowners_rel)
                doc_findings = correlate_doc_drift(changes, docowners, project_dir)
                findings.extend(doc_findings)
                summary["docs_stale"] = len(doc_findings)
            except Exception as exc:
                findings.append(error_finding(f"doc-drift error: {exc}", "doc-drift"))
        # Bound storage after the commit.
        with contextlib.suppress(Exception):
            shadow_gc(project_id, project_dir)
            cap_and_rotate(project_id, project_dir)
        drift_state["last_verified_sha"] = new_head
    elif last_sha:
        # Clean tree this session — keep the prior verified sha as the baseline.
        drift_state["last_verified_sha"] = last_sha
    else:
        # First-ever run with a clean tree: nothing committed yet. Establish the
        # baseline sha if a HEAD now exists (e.g. an earlier session committed).
        head = shadow_head(project_id, project_dir)
        if head:
            drift_state["last_verified_sha"] = head

    drift_state["project_digest"] = td.digest
    drift_state["project_digest_version"] = DIGEST_VERSION
    return summary


# ---------------------------------------------------------------------------
# CLI — explicit setup / teardown / status (the "separate setup workflow")
# ---------------------------------------------------------------------------


def _resolve_project_id(project_dir: Path) -> str | None:
    try:
        _install = os.environ.get(
            "AI_MEMORY_INSTALL_DIR", os.path.expanduser("~/.ai-memory")
        )
        _src = os.path.join(_install, "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from memory.project import resolve_project_id

        return resolve_project_id(cwd=str(project_dir), warn=False)
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="aim_sot_shadow",
        description="SOT-owned shadow-git setup / teardown / status (machine-local).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("setup", "teardown", "status"):
        p = sub.add_parser(name)
        p.add_argument("--project-dir", default=os.getcwd())
        p.add_argument("--reconfigure", action="store_true")

    args = parser.parse_args(argv)
    project_dir = Path(args.project_dir).resolve()
    project_id = _resolve_project_id(project_dir)
    if not project_id:
        print("Error: could not resolve project_id.", file=sys.stderr)
        return 1

    if args.cmd == "setup":
        if getattr(args, "reconfigure", False):
            os.environ["AIM_SOT_RECONFIGURE"] = "1"
        ok = ensure_setup(project_id, project_dir)
        print(
            f"aim-sot shadow setup: {'ready' if ok else 'FAILED'} for '{project_id}' "
            f"(shadow: {shadow_git_dir(project_id)})"
        )
        return 0 if ok else 1
    if args.cmd == "teardown":
        teardown(project_id)
        with contextlib.suppress(OSError):
            sentinel_path(project_id).unlink(missing_ok=True)
        print(f"aim-sot shadow teardown: removed shadow git for '{project_id}'.")
        return 0
    if args.cmd == "status":
        valid = is_setup_valid(project_id)
        head = shadow_head(project_id, project_dir) if valid else None
        print(
            f"aim-sot shadow status: setup={'valid' if valid else 'absent'} "
            f"head={head or '(none)'} shadow={shadow_git_dir(project_id)}"
        )
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
