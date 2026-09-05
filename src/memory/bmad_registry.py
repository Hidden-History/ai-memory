"""The absent-registry arm of BMAD skill resolution (AC-4, AD-26, AD-6).

BMAD ships its own skill registry. AI-Memory reads it and never writes,
patches, or vendors it. When it is absent -- which is the state of every
install without BMAD -- resolution returns the bare token ``unavailable``,
which a consumer must be able to tell apart from a registry that is present
and carries no rows.

Only the absence arm is built here. The present-case semantics, roster
membership, and the Skill resolution test belong to the epic that owns the
resolver surface; this module is written so that work extends it rather than
replacing it.

Presence is detected at call time. Nothing about the degraded state is cached
into a durable artifact or into module state, which is what lets a BMAD
install taken *after* AI-Memory take effect with no reinstall.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

# The registry is BMAD's, at BMAD's path. Resolved here, once.
REGISTRY_RELATIVE_PATH = "_bmad/_config/bmad-help.csv"

#: No registry to resolve against. AC-4's token, bare and unqualified.
UNAVAILABLE = "unavailable"
#: A registry was read. ``rows`` may legitimately be empty.
RESOLVED = "resolved"
#: Present but unreadable, or readable and headerless. Distinct from absent:
#: "declared and not found" is not "none declared" (AD-6), and an unresolved
#: upstream state fails open and is counted (AD-24).
INDETERMINATE = "indeterminate"

_OVERFLOW_KEY = "__unmapped__"


@dataclass(frozen=True)
class ExcludedField:
    """One field dropped by validation. The row it came from is kept."""

    row: int
    """The file line the field's record ends on, not its ordinal among records."""

    column: str
    reason: str


@dataclass(frozen=True)
class RegistryResolution:
    """The result of one resolution attempt."""

    status: str
    rows: tuple[dict[str, str], ...] = ()
    columns: tuple[str, ...] = ()
    excluded: tuple[ExcludedField, ...] = field(default=())
    detail: str | None = None

    @property
    def is_empty_roster(self) -> bool:
        """True only for a registry that was read and carries no rows."""
        return self.status == RESOLVED and not self.rows


def registry_path(workspace_root: Path | str) -> Path:
    """The registry's location under *workspace_root*."""
    return Path(workspace_root) / REGISTRY_RELATIVE_PATH


def resolve_registry(path: Path | str) -> RegistryResolution:
    """Resolve against the registry at *path*, tolerating a malformed row.

    Validation is per column, never per row length: a row with one bad column
    loses that field and keeps the rest. Dropping a whole row on one bad
    column is a defect (AD-6), and this registry is known to carry a
    field-shifted row that parses cleanly on field count.
    """
    target = Path(path)

    # Probe with lstat, not exists(): exists() re-raises EACCES rather than
    # swallowing it, so a non-traversable parent would escape as an unhandled
    # PermissionError (AC-1), and it follows symlinks, so a dangling link
    # would read as "none declared" rather than "declared and not found"
    # (AD-6). lstat separates the three: nothing here, something unreadable,
    # or something to read.
    try:
        target.lstat()
    except FileNotFoundError:
        return RegistryResolution(
            status=UNAVAILABLE,
            detail=f"no registry at {target}",
        )
    except OSError as exc:
        return RegistryResolution(
            status=INDETERMINATE,
            detail=f"registry at {target} could not be examined: {exc}",
        )

    # Something is declared at the path. Anything that stops us reading it now
    # is an unresolved upstream state -- a broken symlink, a directory, a
    # refused permission -- which fails open and is counted (AD-24), never
    # folded into absent.
    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return RegistryResolution(
            status=INDETERMINATE,
            detail=f"registry at {target} could not be read: {exc}",
        )

    reader = csv.DictReader(io.StringIO(text), restkey=_OVERFLOW_KEY, restval=None)
    rows: list[dict[str, str]] = []
    excluded: list[ExcludedField] = []
    try:
        columns = reader.fieldnames
        if not columns:
            return RegistryResolution(
                status=INDETERMINATE,
                detail=f"registry at {target} has no header row",
            )

        # A repeated header name costs a field: the later column overwrites the
        # earlier one in the mapping. Silent loss is the defect AD-6 names, so
        # it is excluded explicitly rather than absorbed.
        seen: set[str] = set()
        duplicates = [c for c in columns if c in seen or seen.add(c)]
        for column in dict.fromkeys(duplicates):
            excluded.append(
                ExcludedField(
                    row=1,
                    column=column,
                    reason="duplicate header column: only the last is readable",
                )
            )

        for raw in reader:
            # line_num is the file line the record ends on. A data ordinal
            # cannot locate a row a reader has to go and look at, and it
            # diverges from the file the moment a quoted field spans lines.
            line = reader.line_num
            kept: dict[str, str] = {}
            for column in columns:
                value = raw.get(column)
                if value is None:
                    excluded.append(
                        ExcludedField(
                            row=line, column=column, reason="column absent from row"
                        )
                    )
                    continue
                kept[column] = value
            if raw.get(_OVERFLOW_KEY):
                excluded.append(
                    ExcludedField(
                        row=line,
                        column=_OVERFLOW_KEY,
                        reason="row carries more fields than the header declares",
                    )
                )
            rows.append(kept)
    except csv.Error as exc:
        # Parsing raises from the iterator, which is not covered by the read.
        return RegistryResolution(
            status=INDETERMINATE,
            detail=f"registry at {target} could not be parsed: {exc}",
        )

    return RegistryResolution(
        status=RESOLVED,
        rows=tuple(rows),
        columns=tuple(columns),
        excluded=tuple(excluded),
    )


def resolve(workspace_root: Path | str) -> RegistryResolution:
    """Resolve against the registry belonging to *workspace_root*."""
    return resolve_registry(registry_path(workspace_root))
