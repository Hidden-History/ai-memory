#!/usr/bin/env python3
"""Report the Constraints of one registry as four counts, one per Enforcement state.

Reads one Constraint registry and counts each row at most once, in the state
it is shown to be in. The four counts are printed on four lines, always the
same four in the same order, and are never added together.

A row that names a Detector is counted in an enforced state only when the
row declares that state and the binding check finds the Detector functional.
A Detector's verdict only ever lowers a count; it never raises one.

Four conditions are counted on a line of their own instead of failing the run:

  uncounted         a row in none of the four states
  lowered           a row counted as not yet enforced because the Detector it
                    names is not shown to work
  undeclared-state  a row with a working Detector and no declared state,
                    counted as not yet enforced
  field-exclusion   a field the registry reader dropped

Exit status: 0 whenever the report was produced, 2 when the registry or the
detectors directory could not be read, the report itself failed, or the
command line is wrong. The report is not a gate and never exits 1.

It counts the rows of that one file only. It does not count Detector files,
fixture pairs or the markings in capability declarations, and it does not
compare the registry against the constraint files on disk.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import binding_check
import constraint_registry as registry
import orphan_check

#: The registry read when --registry is not given: the file beside this one.
DEFAULT_REGISTRY = Path(__file__).resolve().parent / "constraint-registry.csv"

#: The directory read when --detectors is not given: the one this file is in.
DEFAULT_DETECTORS = Path(__file__).resolve().parent

SUBJECT = "enforcement-report"

# Outcomes of a run. REPORTED is never printed as a token.
REPORTED = "reported"
EMPTY = registry.EMPTY
UNCHECKED = registry.UNCHECKED

# The four states, by position in the one tuple that defines them.
(
    _UNENFORCEABLE,
    _NOT_YET_ENFORCED,
    _NON_BLOCKING,
    _BLOCKING,
) = registry.ENFORCEMENT_STATES

# Counted lines: conditions the report states and counts, and still exits 0.
UNCOUNTED = "uncounted"
LOWERED = "lowered"
UNDECLARED_STATE = "undeclared-state"
FIELD_EXCLUSION = "field-exclusion"

#: The counted-line tokens, in the order their lines are printed.
COUNTED_LINES = (UNCOUNTED, LOWERED, UNDECLARED_STATE, FIELD_EXCLUSION)

#: The reason a row is lowered when its ``detector`` value names no Detector.
NOT_FOUND = "not-found"

#: A marked row's disposition, mapped to the state it is counted in.
_MARKED = MappingProxyType(
    {
        f"{orphan_check.MARKED}:{state}": state
        for state in (_UNENFORCEABLE, _NOT_YET_ENFORCED)
    }
)

_SCOPE = (
    "Each count is a number of rows of that one registry file, and a row is "
    "counted once. Detector files, fixture pairs and the markings in "
    "capability declarations are not counted, the registry is not compared "
    "with the constraint files on disk, and nothing here shows that anything "
    "runs a Detector."
)


@dataclass(frozen=True)
class ReportRow:
    """What the report decided about one registry row."""

    line: int
    """The file line the row's record ends on."""

    id: str
    """The row's id, or an empty string when the id could not be read."""

    disposition: str
    """The orphan check's disposition for the row."""

    state: str | None
    """The state the row is counted in, or None when it is in none."""

    counted_line: str
    """``uncounted``, ``lowered``, ``undeclared-state``, or an empty string."""

    reason: str
    """For a ``lowered`` row, the binding check's verdict or ``not-found``."""

    excluded: tuple[str, ...]
    """The columns of this row that the registry reader dropped."""


@dataclass(frozen=True)
class EnforcementReport:
    """One run of the report over one registry."""

    status: str
    """``reported``, ``empty`` or ``unchecked``."""

    counts: Mapping[str, int]
    """Rows per state, keyed by the four state tokens, in their order."""

    rows: tuple[ReportRow, ...]

    counted_lines: Mapping[str, int]
    """The count each counted line carries, keyed by its token."""

    detail: str
    """Why the run is ``unchecked``; otherwise the registry path that was read."""


def named_detector(
    value: str, bindings: tuple[binding_check.DetectorBinding, ...]
) -> binding_check.DetectorBinding | None:
    """The Detector a row's ``detector`` value names, or None.

    A value names a Detector when it equals the file name of one the binding
    check found in the directory it read. A path, a bare name, and a name no
    Detector file has, name none. This is the one place that decides it.
    """
    for binding in bindings:
        if binding.file_name == value:
            return binding
    return None


def _place(
    row: registry.RegistryRow,
    disposition: str,
    bindings: tuple[binding_check.DetectorBinding, ...],
) -> tuple[str | None, str, str]:
    """Where one row is counted: ``(state or None, counted line, reason)``."""
    if disposition in _MARKED:
        return _MARKED[disposition], "", ""
    if disposition != orphan_check.BOUND:
        # An orphan, a refused row, or a disposition this table does not
        # name: never guessed into a state.
        return None, UNCOUNTED, ""

    declared = row.values[registry.COLUMN_STATE]
    if declared in (_UNENFORCEABLE, _NOT_YET_ENFORCED):
        # Counted as declared. A Detector's verdict never raises a count.
        return declared, "", ""
    binding = named_detector(row.values[registry.COLUMN_DETECTOR], bindings)
    if binding is None:
        return _NOT_YET_ENFORCED, LOWERED, NOT_FOUND
    if binding.verdict != binding_check.FUNCTIONAL:
        return _NOT_YET_ENFORCED, LOWERED, binding.token
    if declared == _BLOCKING:
        return _BLOCKING, "", ""
    if declared == _NON_BLOCKING:
        return _NON_BLOCKING, "", ""
    # A working Detector and no declared state: not counted as enforced,
    # because the row does not say so, and named on a line of its own.
    return _NOT_YET_ENFORCED, UNDECLARED_STATE, ""


def _result(
    status: str,
    detail: str,
    rows: tuple[ReportRow, ...] = (),
    field_exclusions: int = 0,
) -> EnforcementReport:
    counts = dict.fromkeys(registry.ENFORCEMENT_STATES, 0)
    counted = dict.fromkeys(COUNTED_LINES, 0)
    for row in rows:
        if row.state is not None:
            counts[row.state] += 1
        if row.counted_line:
            counted[row.counted_line] += 1
    counted[FIELD_EXCLUSION] = field_exclusions
    return EnforcementReport(
        status=status,
        counts=MappingProxyType(counts),
        rows=rows,
        counted_lines=MappingProxyType(counted),
        detail=detail,
    )


def build_report(
    registry_path: Path | str, detectors_dir: Path | str
) -> EnforcementReport:
    """Count the rows of the registry at *registry_path* in the four states.

    The detectors directory is read, through the binding check, only when at
    least one row names a Detector. When the registry cannot be checked, or a
    row names a Detector and the directory cannot be read, the result is
    ``unchecked`` and carries no rows and no counts above zero.
    """
    read = registry.read_registry(registry_path)
    if read.status == registry.UNCHECKED:
        return _result(UNCHECKED, read.detail)

    dispositions = [orphan_check.row_disposition(row).token for row in read.rows]

    bindings: tuple[binding_check.DetectorBinding, ...] = ()
    if orphan_check.BOUND in dispositions:
        checked = binding_check.check_bindings(Path(detectors_dir))
        if checked.outcome == binding_check.UNCHECKED and not checked.detectors:
            return _result(
                UNCHECKED,
                "a row names a Detector and the detectors directory could "
                f"not be read: {checked.detail}",
            )
        bindings = checked.detectors

    rows = []
    for row, disposition in zip(read.rows, dispositions, strict=True):
        state, counted_line, reason = _place(row, disposition, bindings)
        rows.append(
            ReportRow(
                line=row.line,
                id=row.values.get(registry.COLUMN_ID, ""),
                disposition=disposition,
                state=state,
                counted_line=counted_line,
                reason=reason,
                excluded=tuple(item.column for item in row.excluded),
            )
        )
    return _result(
        REPORTED if rows else EMPTY, read.path, tuple(rows), len(read.excluded)
    )


def exit_status(report: EnforcementReport) -> int:
    """The one place the exit status is decided."""
    return 2 if report.status == UNCHECKED else 0


def _printable(text: object) -> str:
    """*text* as one line, so a path or a name cannot forge a line."""
    return "".join(
        ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii")
        for ch in str(text)
    )


def _item(line: int, note: str = "") -> str:
    """One row of a counted line: its registry line, and a note in brackets.

    The note is a token read from a file. Anything in it that could end the
    bracket or start another item is escaped, so it cannot forge one.
    """
    if not note:
        return f"line {line}"
    safe = "".join(
        f"\\x{ord(ch):02x}" if ch.isspace() or ch in "[],\\" else ch for ch in note
    )
    return f"line {line} [{safe}]"


def render(report: EnforcementReport) -> list[str]:
    """Every line the report prints for *report*."""
    if report.status == UNCHECKED:
        return [_printable(f"{UNCHECKED}:{SUBJECT} - {report.detail}")]

    lines = [f"{state}: {count}" for state, count in report.counts.items()]
    path = report.detail
    counted = report.counted_lines
    if report.status == EMPTY:
        lines.append(
            f"{EMPTY}:{SUBJECT} - 0 Constraint rows were read from {path}, so "
            "each of the four counts is 0. That says no Constraint has been "
            "entered in this registry. It does not say that nothing is "
            f"unenforced. {_SCOPE}"
        )
    else:
        lines.append(
            f"rows: {len(report.rows)} Constraint row(s) read from {path}, "
            f"{counted[UNCOUNTED]} of them in none of the four states. {_SCOPE}"
        )

    def items(token: str, note: str = "") -> str:
        return ", ".join(
            _item(row.line, getattr(row, note) if note else "")
            for row in report.rows
            if row.counted_line == token
        )

    if counted[UNCOUNTED]:
        lines.append(
            f"{UNCOUNTED}: {counted[UNCOUNTED]} row(s) in none of the four "
            f"states, each with its disposition from the orphan check - "
            f"{items(UNCOUNTED, 'disposition')}"
        )
    if counted[LOWERED]:
        lines.append(
            f"{LOWERED}: {counted[LOWERED]} row(s) counted as "
            f"{_NOT_YET_ENFORCED} because the Detector the row names is not "
            f"shown to work, each with the reason - {items(LOWERED, 'reason')}"
        )
    if counted[UNDECLARED_STATE]:
        lines.append(
            f"{UNDECLARED_STATE}: {counted[UNDECLARED_STATE]} row(s) with a "
            f"working Detector and no declared state, counted as "
            f"{_NOT_YET_ENFORCED} - {items(UNDECLARED_STATE)}"
        )
    if counted[FIELD_EXCLUSION]:
        fields = ", ".join(
            _item(row.line, column) for row in report.rows for column in row.excluded
        )
        lines.append(
            f"{FIELD_EXCLUSION}: {counted[FIELD_EXCLUSION]} field(s) dropped "
            f"by the registry reader, counted in fields and not in rows, each "
            f"with its column - {fields}"
        )
    return [_printable(line) for line in lines]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="enforcement-report",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="registry file to report on (default: constraint-registry.csv "
        "beside this script)",
    )
    parser.add_argument(
        "--detectors",
        type=Path,
        default=DEFAULT_DETECTORS,
        help="directory holding the Detectors the registry names (default: "
        "the directory this script is in)",
    )
    args = parser.parse_args(argv)

    # A failure of the report itself is "could not report", never exit 0 or 1.
    try:
        report = build_report(args.registry, args.detectors)
        for line in render(report):
            print(line)
        return exit_status(report)
    except Exception as exc:
        # The write that failed may be this one; the exit status still says 2.
        with contextlib.suppress(OSError):
            print(
                f"{UNCHECKED}:{SUBJECT} - the report itself failed: "
                f"{_printable(f'{type(exc).__name__}: {exc}')}"
            )
        return 2


if __name__ == "__main__":
    sys.exit(main())
