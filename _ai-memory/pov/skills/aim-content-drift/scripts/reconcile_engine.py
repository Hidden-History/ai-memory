#!/usr/bin/env python3
"""Template-drift reconciliation engine (PLAN-033 P3, grounded in BP-187).

Consumes the frozen ``pending-updates.json`` manifest the installer emits (PLAN-033
P1 producer, ``install.sh::_write_pending_updates``) and reconciles each drifted
oversight file **without ever clobbering the operator's data**. This is the
data-safety-critical core: a bad merge corrupts an operator's accumulated oversight
data (decision-log entries, task tables, TD records), so every decision is grounded
in BP-187 and every write is crash-atomic.

Design (W-07 skills-with-scripts, mirrors sibling ``content_drift.py``): this is the
deterministic, standalone, import-testable engine invoked BY PATH — it has NO
dependency on ``install.sh`` or the Parzival session-start surface (those are P1 /
P2). SKILL orchestration decides *when* to run and *how to present*; this module
does the exact decision, migration, and write mechanics.

Three responsibilities, straight from BP-187:

1. **The 4-outcome decision** (BP-187 §2.2). Two comparisons against the pristine
   base ``B`` — ``user_edited = D != B`` and ``template_changed = S != B`` — yield
   ``no-op`` / ``refresh`` / ``preserve`` / ``conflict``. The pristine base is
   non-negotiable (BP-187 §2.1): when ``B`` is unknown ("" — a legacy pre-manifest
   file per the P1 producer) we CANNOT prove the file is unedited, so we fail safe to
   CONFLICT and never blind-refresh.

2. **Structural migration** (BP-187 §3, the Alembic model). Data-bearing oversight
   files carry user data in an evolving *structure* (frontmatter, INDEX format,
   headers). A text merge would corrupt them; overwrite would destroy the data. So
   STRUCTURE evolves via a stamped (``format_version`` in frontmatter), ordered,
   idempotent migration chain that transforms the operator's on-disk file FORWARD —
   never ship-new-empty. The operator's DATA (body) rides through untouched.

3. **Write-safety invariants** (BP-187 §4). Every write: backup-before-write, then
   write-temp (same directory) -> fsync -> atomic rename. A crash leaves either the
   whole old file or the whole new file, never a truncated hybrid — matters given the
   documented WSL2 single-file bind-mount corruption risk. A level-triggered
   staleness re-check runs BEFORE any apply: if the source or deployed file moved
   since the manifest was generated, we refuse to apply stale (regenerate instead).

Migration ``0001`` establishes the ``format_version`` baseline stamp; the registry is
the extension point for concrete structural transforms (``0002+``) added as real
old-vs-new scaffold deltas are identified downstream. The engine itself ships the
proven machinery + the zero-data-loss guarantee.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# The manifest schema this engine understands. Mirrors the P1 producer's
# reject-unknown-MAJOR guard (install.sh): a higher MINOR is
# backward-compatible (additive), a higher MAJOR is not and is refused fail-loud.
SUPPORTED_SCHEMA_MAJOR = 1

# The current structural format all managed oversight files migrate toward.
CURRENT_FORMAT_VERSION = 1


class ReconcileError(Exception):
    """Base class for reconciliation failures."""


class UnsupportedSchemaError(ReconcileError):
    """The manifest's schema_version MAJOR is newer than this engine supports."""


class StaleManifestError(ReconcileError):
    """The deployed file or new template moved since the manifest was generated.

    Level-triggered (BP-187 / BP-188): the manifest describes a point-in-time drift
    state; if the underlying files have since changed, applying it would act on stale
    inputs. The caller must regenerate the manifest rather than apply this entry.
    """


class MigrationChainError(ReconcileError):
    """No migration is registered to advance a file from its stamped version."""


class CannotStampError(ReconcileError):
    """The file has no frontmatter block to carry a ``format_version`` stamp."""


class Decision(Enum):
    """The four canonical reconciliation outcomes (BP-187 §2.2)."""

    NO_OP = "no-op"
    REFRESH = "refresh"
    PRESERVE = "preserve"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ReconcileEntry:
    """One drifted file from the manifest — the three-state digest triple + metadata.

    Field names mirror the P1 producer's emitted JSON exactly
    (install.sh::_write_pending_updates).
    """

    id: str
    path: str
    classification: str
    old_shipped_hash: str  # base B — may be "" for a legacy pre-manifest file
    deployed_hash: str  # D — the operator's on-disk copy
    new_template_hash: str  # S — the new shipped template
    suggested_action: str
    rationale: str
    severity: str
    order: int


@dataclass(frozen=True)
class Manifest:
    """The whole ``pending-updates.json`` manifest."""

    schema_version: str
    generated_at: str
    generated_by: str
    source_version: str
    manifest_id: str
    entries: tuple[ReconcileEntry, ...]


@dataclass(frozen=True)
class Migration:
    """One structural migration step in the ordered chain (BP-187 §3).

    ``transform`` changes only STRUCTURE and must be zero-data-loss for the operator's
    body content. The version stamp itself is written by :func:`apply_migrations`
    after a successful transform, so a transform never has to manage the stamp.
    """

    from_version: int
    to_version: int
    transform: Callable[[str], str]
    name: str


@dataclass(frozen=True)
class ReconcileResult:
    """The outcome of reconciling one entry."""

    entry_id: str
    decision: Decision
    action_taken: str  # no-op | refreshed | preserved | migrated
    backup_path: str | None


# --------------------------------------------------------------------------- #
# Hashing — matches the installer's ``_sha256_file`` (sha256sum of raw bytes,
# lowercase hex), so a staleness re-check compares like-for-like.
# --------------------------------------------------------------------------- #
def compute_hash(path: str | os.PathLike[str]) -> str:
    """Return the sha256 hex digest of a file's raw bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# The 4-outcome decision (BP-187 §2.2).
# --------------------------------------------------------------------------- #
def decide(*, user_edited: bool, template_changed: bool) -> Decision:
    """Map the two comparisons to a reconciliation outcome (the RPM table)."""
    if not user_edited and not template_changed:
        return Decision.NO_OP
    if not user_edited and template_changed:
        return Decision.REFRESH
    if user_edited and not template_changed:
        return Decision.PRESERVE
    return Decision.CONFLICT


def classify(entry: ReconcileEntry) -> Decision:
    """Classify an entry from its digest triple, failing safe when base is unknown.

    BP-187 §2.1: without a pristine base ``B`` you cannot distinguish "user edited it"
    from "a new default arrived" — so an empty base forces CONFLICT (never a blind
    refresh that could clobber operator edits).
    """
    base = entry.old_shipped_hash
    if not base:
        return Decision.CONFLICT
    user_edited = entry.deployed_hash != base
    template_changed = entry.new_template_hash != base
    return decide(user_edited=user_edited, template_changed=template_changed)


# --------------------------------------------------------------------------- #
# Manifest loading — reject an unknown MAJOR (mirrors the P1 producer guard).
# --------------------------------------------------------------------------- #
def load_manifest(path: str | os.PathLike[str]) -> Manifest:
    """Parse and validate ``pending-updates.json``."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    raw_version = str(data.get("schema_version", ""))
    try:
        major = int(raw_version.split(".")[0])
    except (ValueError, IndexError) as exc:
        raise UnsupportedSchemaError(
            f"invalid schema_version: {raw_version!r}"
        ) from exc
    if major > SUPPORTED_SCHEMA_MAJOR:
        raise UnsupportedSchemaError(
            f"unsupported schema_version major {major} "
            f"(engine supports <= {SUPPORTED_SCHEMA_MAJOR})"
        )

    entries = tuple(
        ReconcileEntry(
            id=e["id"],
            path=e["path"],
            classification=e.get("classification", ""),
            old_shipped_hash=e.get("old_shipped_hash", ""),
            deployed_hash=e.get("deployed_hash", ""),
            new_template_hash=e.get("new_template_hash", ""),
            suggested_action=e.get("suggested_action", ""),
            rationale=e.get("rationale", ""),
            severity=e.get("severity", ""),
            order=int(e.get("order", 0)),
        )
        for e in data.get("entries", [])
    )
    return Manifest(
        schema_version=raw_version,
        generated_at=data.get("generated_at", ""),
        generated_by=data.get("generated_by", ""),
        source_version=data.get("source_version", ""),
        manifest_id=data.get("manifest_id", ""),
        entries=entries,
    )


# --------------------------------------------------------------------------- #
# Level-triggered staleness re-check (BP-187 §4 / BP-188).
# --------------------------------------------------------------------------- #
def is_stale(
    entry: ReconcileEntry,
    *,
    deployed_path: str | os.PathLike[str],
    new_template_path: str | os.PathLike[str] | None = None,
) -> bool:
    """True if the deployed file (or new template) moved since the manifest.

    A missing deployed file is treated as stale — the manifest no longer describes
    what is on disk.
    """
    dpath = Path(deployed_path)
    if not dpath.exists():
        return True
    if compute_hash(dpath) != entry.deployed_hash:
        return True
    if new_template_path is not None:
        tpath = Path(new_template_path)
        if not tpath.exists() or compute_hash(tpath) != entry.new_template_hash:
            return True
    return False


# --------------------------------------------------------------------------- #
# ``format_version`` stamp — lives in the YAML frontmatter block (BP-187 §3 stamp).
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"\Aformat_version:\s*(\d+)\s*\Z")


def _frontmatter_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Return (open_idx, close_idx) of the frontmatter fences, or None if absent.

    A frontmatter block is a leading ``---`` line and the next ``---`` line.
    """
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return 0, idx
    return None


def read_format_version(text: str) -> int:
    """Return the stamped ``format_version`` (0 if no frontmatter / no stamp)."""
    lines = text.split("\n")
    bounds = _frontmatter_bounds(lines)
    if bounds is None:
        return 0
    open_idx, close_idx = bounds
    for line in lines[open_idx + 1 : close_idx]:
        match = _FRONTMATTER_RE.match(line.strip())
        if match:
            return int(match.group(1))
    return 0


def write_format_version(text: str, version: int) -> str:
    """Upsert ``format_version: <version>`` into the frontmatter block.

    Every non-stamp line is preserved verbatim; only the stamp line is
    inserted/replaced. Raises :class:`CannotStampError` if there is no frontmatter
    block to carry the stamp (the caller decides that file is N/A for stamping —
    never forcing a structural change on a plain-body file).
    """
    lines = text.split("\n")
    bounds = _frontmatter_bounds(lines)
    if bounds is None:
        raise CannotStampError("file has no frontmatter block to stamp")
    open_idx, close_idx = bounds
    stamp = f"format_version: {version}"
    for idx in range(open_idx + 1, close_idx):
        if re.match(r"\Aformat_version:\s*\d+\s*\Z", lines[idx].strip()):
            lines[idx] = stamp
            return "\n".join(lines)
    # No existing stamp: insert just before the closing fence.
    lines.insert(close_idx, stamp)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The ordered, idempotent migration chain (BP-187 §3, Alembic model).
# --------------------------------------------------------------------------- #
def apply_migrations(
    text: str,
    target_version: int,
    migrations: Sequence[Migration],
) -> str:
    """Advance ``text`` from its stamped version up to ``target_version``.

    - Idempotent: already at/above target -> returned unchanged.
    - Ordered: applies exactly the migrations between current and target, following
      each migration's ``from_version`` -> ``to_version`` link.
    - Fail-loud on a gap: a missing migration for the current version raises
      :class:`MigrationChainError` (never "assume fresh").
    - N/A-tolerant: if a file cannot carry a stamp (no frontmatter), the structural
      transform is still applied (zero-data-loss) and the chain stops cleanly — the
      file is validly reconciled without a stamp, not a dead-end.
    """
    current = read_format_version(text)
    if current >= target_version:
        return text

    by_from: dict[int, Migration] = {}
    for mig in migrations:
        by_from[mig.from_version] = mig

    while current < target_version:
        mig = by_from.get(current)
        if mig is None:
            raise MigrationChainError(
                f"no migration registered from format_version {current}"
            )
        transformed = mig.transform(text)
        try:
            text = write_format_version(transformed, mig.to_version)
        except CannotStampError:
            # No frontmatter to stamp: the structural transform (if any) is applied
            # and the file is left un-stamped — a valid terminal, data preserved.
            return transformed
        current = mig.to_version
    return text


def _migration_0001_baseline(text: str) -> str:
    """0001 — establish the ``format_version`` baseline stamp.

    Purely additive: no body change. The stamp itself is written by
    :func:`apply_migrations`; this transform only marks that a file entering the
    chain at v0 needs no structural rewrite to reach v1.
    """
    return text


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        from_version=0,
        to_version=1,
        transform=_migration_0001_baseline,
        name="0001_baseline_format_version_stamp",
    ),
)


# --------------------------------------------------------------------------- #
# Atomic, backup-first write (BP-187 §4.1-§4.3).
# --------------------------------------------------------------------------- #
def atomic_write(
    path: str | os.PathLike[str],
    data: str | bytes,
    *,
    backup: bool = True,
) -> str | None:
    """Write ``data`` to ``path`` crash-atomically, backing up any prior content.

    backup-before-write (``path`` -> ``path.bak``) then write a temp file in the SAME
    directory -> flush -> fsync -> ``os.replace`` (atomic rename on one filesystem) ->
    fsync the directory. A crash never leaves a truncated hybrid. Returns the backup
    path (or None if nothing was backed up).
    """
    target = Path(path)
    payload = data.encode("utf-8") if isinstance(data, str) else data

    backup_path: str | None = None
    if backup and target.exists():
        backup_path = str(target) + ".bak"
        shutil.copy2(target, backup_path)

    directory = target.parent
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=target.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        # Leave the original (and its backup) intact; never a partial target.
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

    # Best-effort: fsync the directory so the rename itself survives a crash.
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass

    return backup_path


# --------------------------------------------------------------------------- #
# Top-level per-entry reconciliation — ties decision + migration + write together.
# --------------------------------------------------------------------------- #
def reconcile_entry(
    entry: ReconcileEntry,
    *,
    project_root: str | os.PathLike[str],
    migrations: Sequence[Migration] = MIGRATIONS,
    target_version: int = CURRENT_FORMAT_VERSION,
    new_template_path: str | os.PathLike[str] | None = None,
) -> ReconcileResult:
    """Reconcile one manifest entry against the operator's on-disk file.

    NO_OP / PRESERVE make no write. REFRESH overwrites with the new template (safe:
    the user never edited it). CONFLICT — the both-changed case — migrates STRUCTURE
    forward on the operator's file while preserving DATA; a file already current (or
    one with no frontmatter to stamp) is a clean "preserved" terminal, never a
    dead-end. Every write path runs the staleness re-check first and is crash-atomic.
    """
    deployed_path = Path(project_root) / entry.path
    decision = classify(entry)

    if decision is Decision.NO_OP:
        return ReconcileResult(entry.id, decision, "no-op", None)
    if decision is Decision.PRESERVE:
        return ReconcileResult(entry.id, decision, "preserved", None)

    # REFRESH and CONFLICT both write — re-check staleness before touching disk.
    check_template = new_template_path if decision is Decision.REFRESH else None
    if is_stale(entry, deployed_path=deployed_path, new_template_path=check_template):
        raise StaleManifestError(
            f"{entry.id}: deployed file or template moved since manifest generation; "
            f"regenerate rather than apply stale"
        )

    if decision is Decision.REFRESH:
        if new_template_path is None:
            raise ReconcileError(
                f"{entry.id}: REFRESH requires new_template_path (source content)"
            )
        content = Path(new_template_path).read_bytes()
        backup_path = atomic_write(deployed_path, content, backup=True)
        return ReconcileResult(entry.id, decision, "refreshed", backup_path)

    # CONFLICT — migrate structure forward, preserve the operator's data.
    original = deployed_path.read_text(encoding="utf-8")
    migrated = apply_migrations(original, target_version, migrations)
    if migrated == original:
        # Already current, or no frontmatter to stamp: data preserved, clean terminal.
        return ReconcileResult(entry.id, decision, "preserved", None)
    backup_path = atomic_write(deployed_path, migrated, backup=True)
    return ReconcileResult(entry.id, decision, "migrated", backup_path)
