#!/usr/bin/env python3
"""Report every Constraint in a registry that enforces nothing, and refuse.

Reads one Constraint registry and gives each row exactly one disposition:

  orphan             no Detector and no Enforcement state declared
  refused:<column>   a field this check reads failed validation, or the row
                     claims a working Detector and declares none
  marked:<state>     no Detector, and one of the four Enforcement states
  bound              a Detector is declared

Exit status: 0 when no row is an orphan or refused (including a registry
that holds no rows), 1 when at least one is, 2 when the registry could not
be checked or the command line is wrong.

The check reads the rows of that one file only. It does not compare the
registry against the constraint files on disk, and it does not check that a
declared Detector exists.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import constraint_registry as registry

#: The registry read when --registry is not given: the file beside this one.
DEFAULT_REGISTRY = Path(__file__).resolve().parent / "constraint-registry.csv"

ORPHAN = "orphan"
BOUND = "bound"
REFUSED = "refused"
MARKED = "marked"

#: States that say a working Detector exists.
_STATES_NEEDING_A_DETECTOR = registry.ENFORCEMENT_STATES[2:]

_SCOPE = (
    "This check reads the rows of that one file only; it does not compare "
    "the registry against the constraint files on disk."
)


@dataclass(frozen=True)
class Disposition:
    """What the check decided about one row."""

    token: str
    """``orphan``, ``refused:<column>``, ``marked:<state>`` or ``bound``."""

    is_finding: bool
    """True when the row counts toward exit status 1."""

    reason: str = ""


def row_disposition(row: registry.RegistryRow) -> Disposition:
    """Give one registry row its single disposition."""
    for column in registry.REQUIRED_COLUMNS:
        failure = row.failed(column)
        if failure is not None:
            return Disposition(
                f"{REFUSED}:{column}", True, f"column {column}: {failure.reason}"
            )

    detector = row.values[registry.COLUMN_DETECTOR]
    state = row.values[registry.COLUMN_STATE]
    if detector:
        return Disposition(BOUND, False)
    if not state:
        return Disposition(
            ORPHAN, True, "no Detector and no Enforcement state is declared"
        )
    if state in _STATES_NEEDING_A_DETECTOR:
        column = registry.COLUMN_STATE
        return Disposition(
            f"{REFUSED}:{column}",
            True,
            f"column {column}: {state!r} claims a working Detector "
            "and no Detector is declared",
        )
    return Disposition(f"{MARKED}:{state}", False)


def _label(row: registry.RegistryRow) -> str:
    """The row's id as one printable token, so an id cannot forge a line."""
    label = row.values.get(registry.COLUMN_ID, "(no usable id)")
    return "".join(
        ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii")
        for ch in label
    )


def find(read: registry.RegistryRead) -> list[str]:
    """The finding lines for *read*: one per orphan or refused row."""
    findings = []
    for row in read.rows:
        disposition = row_disposition(row)
        if disposition.is_finding:
            findings.append(
                f"finding: line {row.line}: {_label(row)}: "
                f"{disposition.token} - {disposition.reason}"
            )
    return findings


def exit_status(read: registry.RegistryRead, findings: list[str]) -> int:
    """The one place the exit status is decided."""
    if read.status == registry.UNCHECKED:
        return 2
    return 1 if findings else 0


def render(read: registry.RegistryRead, findings: list[str]) -> list[str]:
    """Every line the check prints for *read*, findings first."""
    subject = registry.SUBJECT
    if read.status == registry.UNCHECKED:
        return [f"{registry.UNCHECKED}:{subject} - {read.detail}"]
    if read.status == registry.EMPTY:
        return [
            f"{registry.EMPTY}:{subject} - {read.path} was read and holds no "
            f"Constraint rows, so nothing was checked against it. {_SCOPE}"
        ]

    lines = list(findings)
    by_line = {row.line: row for row in read.rows}
    for item in read.excluded:
        lines.append(
            f"exclusion: line {item.line}: {_label(by_line[item.line])}: "
            f"column {item.column}: {item.reason}"
        )
    counts = (
        f"{len(read.rows)} row(s) of {read.path}, {len(findings)} finding(s), "
        f"{len(read.excluded)} excluded field(s)"
    )
    if findings:
        lines.append(f"checked {counts}. {_SCOPE}")
    else:
        lines.append(f"clean:{subject} - {counts}. {_SCOPE}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orphan-check",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="registry file to check (default: constraint-registry.csv "
        "beside this script)",
    )
    args = parser.parse_args(argv)

    read = registry.read_registry(args.registry)
    findings = find(read)
    # No try around the printing: a failed write must end the run non-zero.
    for line in render(read, findings):
        print(line)
    return exit_status(read, findings)


if __name__ == "__main__":
    sys.exit(main())
