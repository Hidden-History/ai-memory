"""Reader for the Constraint registry.

The registry is a CSV file with one header row and one row per Constraint.
This module parses it, validates it column by column, and returns one
immutable result. It prints nothing and decides no exit status: the orphan
check and any later consumer import the result instead of parsing text.

Validation is per column, never per row length. A field that fails loses
that field only; its row is kept and stays usable for every operation that
does not read the failed field.

Standard library only, so the module runs wherever the tree is deployed.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

#: The subject every outcome token is qualified with.
SUBJECT = "constraint-registry"

COLUMN_ID = "id"
COLUMN_DETECTOR = "detector"
COLUMN_STATE = "enforcement_state"

#: The columns the header must declare, in the order a check reads them.
REQUIRED_COLUMNS = (COLUMN_ID, COLUMN_DETECTOR, COLUMN_STATE)

#: The four Enforcement states, in order. Only the last two have a working
#: Detector. This is the one definition of the tokens in this tree.
ENFORCEMENT_STATES = (
    "unenforceable",
    "not-yet-enforced",
    "enforced-but-non-blocking",
    "enforced-and-blocking",
)

#: The registry could not be checked: no file, unreadable, unparseable, or a
#: header that does not declare the required columns unambiguously.
UNCHECKED = "unchecked"
#: The registry was read and holds zero Constraint rows.
EMPTY = "empty"
#: The registry was read and holds at least one Constraint row.
READ = "read"

#: The column name an exclusion carries for fields beyond the header's width.
OVERFLOW_COLUMN = "(overflow)"

_OVERFLOW_KEY = "\x00overflow"
_REPLACEMENT = "�"


@dataclass(frozen=True)
class ExcludedField:
    """One field dropped by validation. The row it came from is kept."""

    line: int
    """The file line the field's record ends on."""

    column: str
    reason: str


@dataclass(frozen=True)
class RegistryRow:
    """One Constraint row: the fields that passed, and the ones that did not."""

    line: int
    """The file line the record ends on."""

    values: Mapping[str, str]
    """Fields that passed validation. ``id`` and ``detector`` are trimmed."""

    excluded: tuple[ExcludedField, ...] = ()

    def failed(self, column: str) -> ExcludedField | None:
        """The exclusion recorded for *column* in this row, if there is one."""
        for item in self.excluded:
            if item.column == column:
                return item
        return None


@dataclass(frozen=True)
class RegistryRead:
    """The result of one attempt to read a registry."""

    status: str
    """``UNCHECKED``, ``EMPTY`` or ``READ``."""

    path: str
    rows: tuple[RegistryRow, ...] = ()
    columns: tuple[str, ...] = ()
    excluded: tuple[ExcludedField, ...] = ()
    detail: str = ""


def _unchecked(target: Path, detail: str) -> RegistryRead:
    return RegistryRead(status=UNCHECKED, path=str(target), detail=detail)


def _validate(column: str, value: str | None) -> tuple[str | None, str | None]:
    """Return ``(usable value, None)`` or ``(None, reason the field failed)``."""
    if value is None:
        return None, "column absent from row"
    if _REPLACEMENT in value:
        return None, "field holds a byte that is not valid UTF-8"
    if column == COLUMN_ID:
        value = value.strip()
        if not value:
            return None, "id is empty"
    elif column == COLUMN_DETECTOR:
        value = value.strip()
    elif column == COLUMN_STATE:
        if value and value not in ENFORCEMENT_STATES:
            return None, f"{value!r} is not one of the four Enforcement states"
    return value, None


def read_registry(path: Path | str) -> RegistryRead:
    """Read and validate the registry at *path*.

    A missing file, an unreadable one, a parse error and an unusable header
    all return ``UNCHECKED`` with a detail saying which. None of them is ever
    reported as an empty read.
    """
    target = Path(path)

    # lstat rather than exists(): a dangling link or a refused parent must
    # read as "declared and not checkable", never as "nothing there".
    try:
        target.lstat()
    except FileNotFoundError:
        return _unchecked(target, f"no file at {target}")
    except OSError as exc:
        return _unchecked(target, f"{target} could not be examined: {exc}")

    try:
        text = target.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return _unchecked(target, f"{target} could not be read: {exc}")

    reader = csv.DictReader(io.StringIO(text), restkey=_OVERFLOW_KEY, restval=None)
    parsed: list[tuple[int, dict[str, str | None], dict[str, str]]] = []
    try:
        columns = reader.fieldnames
        if not columns:
            return _unchecked(target, f"{target} has no header row")

        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            return _unchecked(
                target,
                f"{target} header is missing required column(s): " + ", ".join(missing),
            )

        # A repeated name leaves only the last of the two readable. For a
        # column a check reads, that is an ambiguous header, not a row defect.
        repeated = [c for c in REQUIRED_COLUMNS if columns.count(c) > 1]
        if repeated:
            return _unchecked(
                target,
                f"{target} header declares required column(s) more than once: "
                + ", ".join(repeated),
            )

        for raw in reader:
            # line_num is the file line the record ends on: the only thing
            # that locates a row whose id cannot be read.
            line = reader.line_num
            failures: dict[str, str] = {}
            if raw.get(_OVERFLOW_KEY):
                failures[OVERFLOW_COLUMN] = (
                    "row carries more fields than the header declares"
                )
            raw.pop(_OVERFLOW_KEY, None)
            parsed.append((line, raw, failures))
    except csv.Error as exc:
        # Parsing raises from the iterator, which the read above does not cover.
        return _unchecked(target, f"{target} could not be parsed: {exc}")

    # Validate each required column of each row. Other columns are carried
    # through unvalidated so a later consumer may add one without a format
    # break; an absent one is simply not present in the row.
    cleaned: list[tuple[int, dict[str, str], dict[str, str]]] = []
    id_lines: dict[str, list[int]] = {}
    for line, raw, failures in parsed:
        values: dict[str, str] = {}
        for column, value in raw.items():
            if column in REQUIRED_COLUMNS:
                usable, reason = _validate(column, value)
                if reason is not None:
                    failures[column] = reason
                    continue
                values[column] = usable
            elif value is not None:
                values[column] = value
        if COLUMN_ID in values:
            id_lines.setdefault(values[COLUMN_ID], []).append(line)
        cleaned.append((line, values, failures))

    # An id shared by two rows names neither of them. Every row sharing it
    # loses its id; none is silently taken as the first match.
    rows: list[RegistryRow] = []
    excluded: list[ExcludedField] = []
    for line, values, failures in cleaned:
        shared = id_lines.get(values.get(COLUMN_ID, ""), [])
        if len(shared) > 1:
            others = ", ".join(str(n) for n in shared if n != line)
            failures[COLUMN_ID] = (
                f"id {values.pop(COLUMN_ID)!r} is also declared on line(s) {others}"
            )
        ordered = [c for c in (*REQUIRED_COLUMNS, OVERFLOW_COLUMN) if c in failures]
        row_excluded = tuple(
            ExcludedField(line=line, column=c, reason=failures[c]) for c in ordered
        )
        rows.append(
            RegistryRow(
                line=line, values=MappingProxyType(values), excluded=row_excluded
            )
        )
        excluded.extend(row_excluded)

    return RegistryRead(
        status=READ if rows else EMPTY,
        path=str(target),
        rows=tuple(rows),
        columns=tuple(columns),
        excluded=tuple(excluded),
    )
