#!/usr/bin/env python3
"""Report every Constraint whose declared Detector does not exist, and refuse.

Reads the rows of one Constraint registry and the Detector files directly in
one directory, and gives each row that declares a Detector one token:

  resolved           the ``detector`` value is exactly the file name of a
                     Detector in that directory
  resolution-error   the value is not empty and names no Detector there
  excluded:detector  the ``detector`` field failed validation, so the row
                     could not be resolved

A row whose ``detector`` value is empty declares no Detector and gets none.

Exit status: 0 when no row is a resolution-error, 1 when at least one is, 2
when the registry or the directory could not be read, a row names a ``.py``
file that could not be read or parsed, the output could not be written, or
the command line is wrong.

The runner does not run any Detector, does not check fixture pairs, and does
not compare the registry with the constraint files on disk.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import binding_check
import constraint_registry as registry

#: The registry read when --registry is not given: the file beside this one.
DEFAULT_REGISTRY = Path(__file__).resolve().parent / "constraint-registry.csv"

#: The directory read when --detectors is not given: the one this file is in.
DEFAULT_DETECTORS = Path(__file__).resolve().parent

SUBJECT = "detector-resolution"

# Statuses of a run. CHECKED is printed as "clean" or, with findings, as the
# finding lines and a "checked" line.
CHECKED = "checked"
EMPTY = "empty"
UNCHECKED = "unchecked"
CLEAN = "clean"

# Tokens for one row.
RESOLVED = "resolved"
RESOLUTION_ERROR = "resolution-error"
EXCLUDED = f"excluded:{registry.COLUMN_DETECTOR}"

_SCOPE = (
    "The runner reads the rows of that one file and the Detector files "
    "directly in that one directory. It does not run any Detector, does not "
    "check fixture pairs, and does not compare the registry with the "
    "constraint files on disk, so a Constraint with no row is not seen."
)


@dataclass(frozen=True)
class RowResolution:
    """What the runner decided about one row."""

    line: int
    """The registry line the row ends on."""

    id: str | None
    """The row's ``id``, or None when that field failed validation."""

    value: str | None
    """The row's ``detector`` value, or None for an ``excluded:detector`` row."""

    token: str
    """``resolved``, ``resolution-error`` or ``excluded:detector``."""

    file_name: str | None = None
    """For a ``resolved`` row, the file name of the Detector it names."""


@dataclass(frozen=True)
class Enumeration:
    """One run of the runner over one registry and one directory."""

    status: str
    """``checked``, ``empty`` or ``unchecked``."""

    registry: str
    detectors_dir: str

    entries: tuple[RowResolution, ...] = ()
    """One entry per row that declares a Detector or was excluded."""

    rows_read: int = 0

    detail: str = ""
    """Why the run is ``unchecked``, when it is."""


def resolve_detector(value: str, detector_names: tuple[str, ...]) -> str | None:
    """The Detector file name *value* names among *detector_names*, or None.

    This is the one place the rule is decided: after trimming spaces, the
    value must equal a Detector's file name exactly.
    """
    value = value.strip()
    return value if value and value in detector_names else None


def enumerate_constraints(registry_path: Path, detectors_dir: Path) -> Enumeration:
    """Resolve the Detector each row of *registry_path* declares.

    The directory is listed on every call, so one that cannot be listed is
    ``unchecked`` even when no row declares a Detector. A row that names a
    ``.py`` file which could not be read or parsed makes the run ``unchecked``:
    whether that file is a Detector is not known. A failure inside the run is
    returned as ``unchecked`` as well, never raised.
    """
    target = Path(registry_path)
    root = Path(detectors_dir)

    def result(status: str, **fields: object) -> Enumeration:
        return Enumeration(status, str(target), str(root), **fields)

    try:
        read = registry.read_registry(target)
        if read.status == registry.UNCHECKED:
            return result(UNCHECKED, detail=read.detail)
        names = binding_check.detector_files(root)
        undecided = binding_check.undecided_files(root)
        if names is None or undecided is None:
            return result(
                UNCHECKED,
                detail=f"the detectors directory {root} is not a directory "
                "or could not be listed",
            )

        entries = []
        not_known = []
        for row in read.rows:
            row_id = row.values.get(registry.COLUMN_ID)
            if row.failed(registry.COLUMN_DETECTOR) is not None:
                entries.append(RowResolution(row.line, row_id, None, EXCLUDED))
                continue
            value = row.values[registry.COLUMN_DETECTOR]
            if not value:
                continue
            found = resolve_detector(value, names)
            if found in undecided:
                not_known.append(f"line {row.line}: {found!r}")
                continue
            token = RESOLUTION_ERROR if found is None else RESOLVED
            entries.append(RowResolution(row.line, row_id, value, token, found))
        if not_known:
            return result(
                UNCHECKED,
                detail=f"{len(not_known)} row(s) of {target} name a .py file in "
                f"{root} that could not be read or parsed, so it is not known "
                "whether that file is a Detector, and no row was resolved - "
                + ", ".join(not_known),
            )
    except Exception as exc:
        return result(
            UNCHECKED, detail=f"the run itself failed: {type(exc).__name__}: {exc}"
        )

    declared = any(entry.token != EXCLUDED for entry in entries)
    return result(
        CHECKED if declared else EMPTY,
        entries=tuple(entries),
        rows_read=len(read.rows),
    )


def exit_status(result: Enumeration, written: bool = True) -> int:
    """The one place the exit status is decided.

    *written* says whether every line of the result reached standard output.
    """
    if result.status == UNCHECKED or not written:
        return 2
    return 1 if any(e.token == RESOLUTION_ERROR for e in result.entries) else 0


def _printable(text: object) -> str:
    """*text* as one line, so an id, a value or a path cannot forge a line."""
    return "".join(
        ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii")
        for ch in str(text)
    )


def render(result: Enumeration) -> list[str]:
    """Every line the runner prints for *result*, the outcome last."""
    if result.status == UNCHECKED:
        return [_printable(f"{UNCHECKED}:{SUBJECT} - {result.detail}")]

    errors = [e for e in result.entries if e.token == RESOLUTION_ERROR]
    excluded = [e for e in result.entries if e.token == EXCLUDED]
    lines = [
        f"finding: line {e.line}: {e.id or '(no usable id)'}: {e.token} - the "
        f"detector value {e.value!r} is not the file name of a Detector in "
        f"{result.detectors_dir}"
        for e in errors
    ]
    if excluded:
        lines.append(
            f"{EXCLUDED}: {len(excluded)} row(s) not resolved because the "
            f"{registry.COLUMN_DETECTOR} field failed validation - line(s) "
            + ", ".join(str(e.line) for e in excluded)
        )

    declared = len(result.entries) - len(excluded)
    counts = (
        f"{result.rows_read} row(s) of {result.registry} read, {declared} "
        f"declare a Detector, {len(errors)} resolution error(s), Detectors "
        f"looked for in {result.detectors_dir}"
    )
    if errors:
        lines.append(f"checked {counts}. {_SCOPE}")
    elif result.status == EMPTY:
        lines.append(
            f"{EMPTY}:{SUBJECT} - {counts}. No row declares a Detector, so "
            f"nothing was resolved. {_SCOPE}"
        )
    else:
        lines.append(f"{CLEAN}:{SUBJECT} - {counts}. {_SCOPE}")
    return [_printable(line) for line in lines]


def _write(lines: list[str]) -> bool:
    """Write *lines* to standard output; False when they did not all get there."""
    out = sys.stdout
    if out is None:
        return False
    try:
        out.write("".join(f"{line}\n" for line in lines))
        out.flush()
    except (OSError, ValueError):
        # Leave the interpreter nothing to flush at exit: a second failure
        # there would replace the exit status this run returns.
        with contextlib.suppress(OSError, ValueError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), out.fileno())
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="detector-runner",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help="registry file to read (default: constraint-registry.csv "
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

    result = enumerate_constraints(args.registry, args.detectors)
    return exit_status(result, _write(render(result)))


if __name__ == "__main__":
    sys.exit(main())
