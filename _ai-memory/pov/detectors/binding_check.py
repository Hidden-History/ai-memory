#!/usr/bin/env python3
"""Prove each Detector against its fixture pair, and refuse one that cannot fail.

A Detector, for this check, is a program directly in one directory: a ``.py``
file with a top-level ``if __name__ == "__main__":`` block. Its fixture pair
is the directory ``fixtures/<name>/`` beside it, declared by the manifest
``fixture-pair.json``. The check runs the Detector on each fixture the
manifest names and gives the Detector exactly one verdict:

  unbound                   no pair, or half of one
  refused:<key>             the manifest, or the named key in it, is not valid
  unchecked:<name>          the Detector could not be parsed or could not be run
  non-functional            its positive fixture did not make it fail
  false-positive:<fixture>  its negative or a declared exemption made it fail
  functional                positive fails, negative and every exemption pass

Exit status: 0 when every Detector is functional (including a directory that
holds none), 1 when at least one is unbound, refused, non-functional or a
false positive, 2 when the directory or a Detector could not be checked or
the command line is wrong.

The check does not read the Constraint registry and does not inspect fixture
content. It does not check the files named in SKIPPED_FILES in its own
directory.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NamedTuple

#: The directory read when --root is not given: the one this file is in.
DEFAULT_ROOT = Path(__file__).resolve().parent

#: Files in this check's own directory that it does not check, by file name.
SKIPPED_FILES = ("binding_check.py",)

FIXTURES_DIR = "fixtures"
MANIFEST = "fixture-pair.json"
FIXTURE_MARKER = "synthetic-fixture"
PLACEHOLDER = "{fixture}"

#: A limit on one Detector run, in seconds.
RUN_TIMEOUT_SECONDS = 60

SUBJECT = "fixture-binding"

# Outcomes of a run. FINDINGS is never printed as a token: a run with
# findings prints its finding lines and a "checked" line.
CLEAN = "clean"
EMPTY = "empty"
UNCHECKED = "unchecked"
FINDINGS = "findings"

# Verdicts for one Detector.
UNBOUND = "unbound"
REFUSED = "refused"
NON_FUNCTIONAL = "non-functional"
FALSE_POSITIVE = "false-positive"
FUNCTIONAL = "functional"

_FINDING_VERDICTS = (UNBOUND, REFUSED, NON_FUNCTIONAL, FALSE_POSITIVE)

# What one run of a Detector on one fixture showed.
_PASS = "pass"
_FAIL = "fail"

#: What the interpreter writes to stderr when a program ends on an exception.
_TRACEBACK = b"Traceback (most recent call last):"

_KEY_MANIFEST = "manifest"
_KEY_MARKER = "fixture_marker"
_KEY_ARGS = "args"
_KEY_POSITIVE = "positive"
_KEY_NEGATIVE = "negative"
_KEY_EXEMPTIONS = "exemptions"


class DetectorBinding(NamedTuple):
    """What the check decided about one Detector."""

    name: str
    """The Detector's file name without ``.py``; also its pair directory."""

    file_name: str
    """The Detector's file name, ``<name>.py``."""

    verdict: str
    """One of the six verdicts, without the part after the colon."""

    named: str
    """The key a ``refused`` names or the fixture a ``false-positive`` names."""

    reason: str

    @property
    def token(self) -> str:
        """The verdict as printed, such as ``refused:args``."""
        if self.verdict == UNCHECKED:
            return f"{UNCHECKED}:{self.name}"
        return f"{self.verdict}:{self.named}" if self.named else self.verdict

    @property
    def is_finding(self) -> bool:
        """True when this Detector counts toward exit status 1."""
        return self.verdict in _FINDING_VERDICTS


class BindingResult(NamedTuple):
    """One run of the check over one directory."""

    outcome: str
    """``clean``, ``empty``, ``unchecked`` or ``findings``."""

    root: Path
    detectors: tuple[DetectorBinding, ...]
    detail: str
    """Why the directory could not be read, when it could not."""


def _printable(text: object) -> str:
    """*text* as one line, so a file name or an id cannot forge a line."""
    return "".join(
        ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii")
        for ch in str(text)
    )


def _skipped_paths() -> set[Path]:
    return {DEFAULT_ROOT / name for name in SKIPPED_FILES}


def _main_block(path: Path) -> bool:
    """Whether *path* has a top-level ``if __name__ == "__main__":`` block.

    Raises OSError, SyntaxError or ValueError when the file cannot be read
    or parsed.
    """
    for node in ast.parse(path.read_bytes()).body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            continue
        sides = (test.left, test.comparators[0])
        names = [s.id for s in sides if isinstance(s, ast.Name)]
        values = [s.value for s in sides if isinstance(s, ast.Constant)]
        if names == ["__name__"] and values == ["__main__"]:
            return True
    return False


def _scan(root: Path) -> tuple[dict[str, str] | None, str]:
    """The Detector files directly in *root*, each with its parse error.

    Returns ``(None, why)`` when *root* is not a directory or cannot be
    listed. A file that cannot be parsed is kept, with the error as its
    value: whether it is a Detector is not known, and it must not vanish.
    """
    if not root.is_dir():
        return None, f"no directory at {_printable(root)}"
    try:
        children = sorted(root.iterdir())
    except OSError as exc:
        return None, f"{_printable(root)} could not be listed: {_printable(exc)}"

    skipped = _skipped_paths()
    found: dict[str, str] = {}
    for child in children:
        if child.suffix != ".py" or not child.is_file():
            continue
        if child.resolve() in skipped:
            continue
        try:
            if _main_block(child):
                found[child.name] = ""
        except (OSError, SyntaxError, ValueError) as exc:
            found[child.name] = f"{type(exc).__name__}: {exc}"
    return found, ""


def detector_files(root: Path) -> tuple[str, ...] | None:
    """The sorted file names of the Detectors directly in *root*.

    A Detector is a ``.py`` file with a top-level ``__main__`` block. A
    ``.py`` file that cannot be read or parsed is included, because it
    cannot be shown not to be one. The files named in SKIPPED_FILES in this
    check's own directory are left out. Nothing in a sub-directory is listed.

    Returns ``None`` when *root* is not a directory or cannot be listed,
    which is a different answer from an empty tuple.
    """
    found, _ = _scan(Path(root))
    return None if found is None else tuple(found)


def _contained(pair: Path, value: object) -> Path | None:
    """The fixture *value* names inside *pair*, or None when it is not valid."""
    if not isinstance(value, str) or not value:
        return None
    for flavour in (PurePosixPath, PureWindowsPath):
        pure = flavour(value)
        if pure.is_absolute() or pure.drive or ".." in pure.parts:
            return None
    base = pair.resolve()
    target = (pair / value).resolve()
    if target == base or not target.is_relative_to(base):
        return None
    return target


def _run_fixture(detector: Path, args: list[str], fixture: Path) -> tuple[str, str]:
    """Run *detector* on one fixture: ``(pass | fail | "", why it did not run)``."""
    command = [sys.executable, "-B", str(detector)]
    command += [arg.replace(PLACEHOLDER, str(fixture)) for arg in args]
    try:
        done = subprocess.run(
            command, capture_output=True, timeout=RUN_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        return "", f"did not finish within {RUN_TIMEOUT_SECONDS} seconds"
    except OSError as exc:
        return "", f"could not be started: {exc}"
    if done.returncode == 0:
        return _PASS, ""
    if done.returncode == 1:
        # An uncaught exception also exits 1. A crash is not a finding.
        if _TRACEBACK in done.stderr:
            return "", "raised an exception instead of reporting a result"
        return _FAIL, ""
    return "", f"exited {done.returncode}, which is neither pass (0) nor fail (1)"


def _bind(root: Path, file_name: str, parse_error: str) -> DetectorBinding:
    """Give one Detector its single verdict, in the order the table reads."""
    name = file_name[: -len(".py")]

    def verdict(token: str, reason: str, named: str = "") -> DetectorBinding:
        return DetectorBinding(name, file_name, token, named, reason)

    pair = root / FIXTURES_DIR / name
    manifest_path = pair / MANIFEST
    if not pair.is_dir():
        return verdict(UNBOUND, f"no fixture pair directory {FIXTURES_DIR}/{name}/")
    if not manifest_path.exists():
        return verdict(UNBOUND, f"no {MANIFEST} in {FIXTURES_DIR}/{name}/")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return verdict(
            REFUSED, f"{MANIFEST} could not be read as JSON: {exc}", _KEY_MANIFEST
        )
    if not isinstance(manifest, dict):
        return verdict(REFUSED, f"{MANIFEST} is not a JSON object", _KEY_MANIFEST)

    # unbound: half a pair is not a pair.
    fixtures: dict[str, Path | None] = {}
    for key in (_KEY_POSITIVE, _KEY_NEGATIVE):
        if key not in manifest:
            return verdict(UNBOUND, f"{MANIFEST} names no {key} fixture")
        fixtures[key] = _contained(pair, manifest[key])
        if fixtures[key] is not None and not fixtures[key].exists():
            return verdict(
                UNBOUND, f"the {key} fixture {manifest[key]!r} does not exist"
            )

    # refused: a key is missing or not valid.
    if manifest.get(_KEY_MARKER) != FIXTURE_MARKER:
        return verdict(REFUSED, f"{_KEY_MARKER} is not {FIXTURE_MARKER!r}", _KEY_MARKER)
    args = manifest.get(_KEY_ARGS)
    if (
        not isinstance(args, list)
        or not all(isinstance(arg, str) for arg in args)
        or not any(PLACEHOLDER in arg for arg in args)
    ):
        return verdict(
            REFUSED,
            f"{_KEY_ARGS} is not a list of strings holding {PLACEHOLDER}",
            _KEY_ARGS,
        )
    for key in (_KEY_POSITIVE, _KEY_NEGATIVE):
        if fixtures[key] is None:
            return verdict(
                REFUSED,
                f"{manifest[key]!r} is not a path inside the pair directory",
                key,
            )
    exemptions = manifest.get(_KEY_EXEMPTIONS)
    if not isinstance(exemptions, dict):
        return verdict(
            REFUSED,
            f"{_KEY_EXEMPTIONS} is not an object mapping an id to a fixture",
            _KEY_EXEMPTIONS,
        )
    for exemption in sorted(exemptions):
        target = _contained(pair, exemptions[exemption])
        if target is None or not target.exists():
            return verdict(
                REFUSED,
                f"the fixture for exemption {exemption!r} is not an existing "
                "path inside the pair directory",
                _KEY_EXEMPTIONS,
            )
        fixtures[exemption] = target

    # unchecked: the Detector could not be parsed, or could not be run.
    if parse_error:
        return verdict(UNCHECKED, f"{file_name} could not be parsed: {parse_error}")
    results: dict[str, str] = {}
    for fixture_name, fixture in fixtures.items():
        results[fixture_name], why = _run_fixture(root / file_name, args, fixture)
        if why:
            return verdict(UNCHECKED, f"on the {fixture_name!r} fixture it {why}")

    if results.pop(_KEY_POSITIVE) != _FAIL:
        return verdict(
            NON_FUNCTIONAL, "the positive fixture did not make the Detector fail"
        )
    for fixture_name, result in results.items():
        if result == _FAIL:
            return verdict(
                FALSE_POSITIVE,
                f"the {fixture_name!r} fixture made the Detector fail",
                fixture_name,
            )
    return verdict(FUNCTIONAL, "")


def check_bindings(root: Path) -> BindingResult:
    """Check every Detector directly in *root* against its fixture pair.

    When *root* is not a directory, or cannot be listed, the result is the
    ``unchecked`` outcome with no Detector entries. Each entry otherwise
    carries the Detector's name, its file name and its verdict.
    """
    root = Path(root)
    found, detail = _scan(root)
    if found is None:
        return BindingResult(UNCHECKED, root, (), detail)

    detectors = tuple(_bind(root, name, error) for name, error in found.items())
    if not detectors:
        outcome = EMPTY
    elif any(d.is_finding for d in detectors):
        outcome = FINDINGS
    elif any(d.verdict == UNCHECKED for d in detectors):
        outcome = UNCHECKED
    else:
        outcome = CLEAN
    return BindingResult(outcome, root, detectors, "")


def exit_status(result: BindingResult) -> int:
    """The one place the exit status is decided."""
    if result.outcome == UNCHECKED:
        return 2
    return 1 if result.outcome == FINDINGS else 0


def _scope() -> str:
    """What a total leaves out, built from SKIPPED_FILES."""
    skipped = " and ".join(SKIPPED_FILES)
    return (
        "This check counts the Detector files present in that one directory. "
        f"In its own directory {skipped} was not checked and is not counted. "
        "It does not read the Constraint registry, does not check that any "
        "Constraint names a Detector, and does not inspect fixture content."
    )


def render(result: BindingResult) -> list[str]:
    """Every line the check prints for *result*, the outcome last."""
    root = _printable(result.root)
    if result.detail:
        return [f"{UNCHECKED}:{SUBJECT} - {result.detail}"]
    if result.outcome == EMPTY:
        return [
            f"{EMPTY}:{SUBJECT} - {root} was read and holds no Detector files, "
            f"so nothing was checked. {_scope()}"
        ]

    lines = []
    for detector in result.detectors:
        prefix = "finding" if detector.is_finding else "detector"
        line = f"{prefix}: {detector.file_name}: {detector.token}"
        if detector.reason:
            line += f" - {detector.reason}"
        lines.append(_printable(line))

    findings = sum(d.is_finding for d in result.detectors)
    unchecked = sum(d.verdict == UNCHECKED for d in result.detectors)
    counts = (
        f"{len(result.detectors)} Detector file(s) in {root}, "
        f"{findings} finding(s), {unchecked} that could not be checked"
    )
    if result.outcome == FINDINGS:
        lines.append(f"checked {counts}. {_scope()}")
    else:
        lines.append(f"{result.outcome}:{SUBJECT} - {counts}. {_scope()}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="binding-check",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="detectors directory to check (default: the directory this "
        "script is in)",
    )
    args = parser.parse_args(argv)

    # A failure of the check itself is "could not check", never a finding.
    try:
        result = check_bindings(args.root)
        for line in render(result):
            print(line)
        return exit_status(result)
    except Exception as exc:
        # The write that failed may be this one; the exit status still says 2.
        with contextlib.suppress(OSError):
            print(
                f"{UNCHECKED}:{SUBJECT} - the check itself failed: "
                f"{_printable(f'{type(exc).__name__}: {exc}')}"
            )
        return 2


if __name__ == "__main__":
    sys.exit(main())
