#!/usr/bin/env python3
"""Version-marker consistency check (BUG-307, BUG-313).

The repository declares its version in four places that must always agree:

- ``version.txt``                       -- plain-text marker
- ``pyproject.toml`` ``[project] version`` -- packaging marker
- ``src/memory/__version__.py`` ``__version__`` -- Python single source of truth
- ``scripts/install.sh`` ``INSTALLER_VERSION`` -- installer stamp (AIM_INSTALLED_VERSION)

Nothing previously kept them in sync, so v2.4.0 shipped all three stale and
v2.4.1 bumped only two -- the drift was invisible until release tag-cut. This
script asserts the four markers agree and is wired into the Test Suite
workflow so drift fails a pull request instead of a release.

On a tag/release build (``--tag`` supplied) it additionally asserts the
markers equal the release tag (``v`` prefix stripped) and the latest
non-``[Unreleased]`` ``CHANGELOG.md`` heading.

Exit codes:
    0 - all markers agree (and match the tag/CHANGELOG when ``--tag`` given)
    1 - a mismatch was found; disagreeing markers and values are printed
    2 - a marker could not be read (missing file or unparseable value)

Usage:
    python scripts/check_version_consistency.py
    python scripts/check_version_consistency.py --tag v2.4.2
    python scripts/check_version_consistency.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Marker location relative to the repository root.
VERSION_TXT = "version.txt"
PYPROJECT = "pyproject.toml"
VERSION_PY = "src/memory/__version__.py"
INSTALL_SH = "scripts/install.sh"
CHANGELOG = "CHANGELOG.md"


class MarkerError(Exception):
    """A version marker could not be located or parsed."""


def _repo_root(explicit: str | None) -> Path:
    """Resolve the repository root.

    Defaults to the parent of this script's directory (``scripts/``).
    """
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[1]


def read_version_txt(root: Path) -> str:
    """Return the version string from ``version.txt``."""
    path = root / VERSION_TXT
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise MarkerError(f"cannot read {VERSION_TXT}: {exc}") from exc
    if not value:
        raise MarkerError(f"{VERSION_TXT} is empty")
    return value


def read_pyproject_version(root: Path) -> str:
    """Return the ``[project] version`` value from ``pyproject.toml``.

    Parsed with a scoped regex rather than a TOML library so the check runs
    identically on Python 3.10 (no stdlib ``tomllib``).
    """
    path = root / PYPROJECT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarkerError(f"cannot read {PYPROJECT}: {exc}") from exc

    # Isolate the [project] table: from its header to the next table header.
    section = re.search(
        r"^\[project\]\s*$(.*?)(?=^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not section:
        raise MarkerError(f"{PYPROJECT} has no [project] table")

    match = re.search(
        r'^version\s*=\s*["\']([^"\']+)["\']',
        section.group(1),
        re.MULTILINE,
    )
    if not match:
        raise MarkerError(f"{PYPROJECT} [project] table has no version key")
    return match.group(1).strip()


def read_version_py(root: Path) -> str:
    """Return the ``__version__`` value from ``src/memory/__version__.py``."""
    path = root / VERSION_PY
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarkerError(f"cannot read {VERSION_PY}: {exc}") from exc

    match = re.search(
        r'^__version__\s*=\s*["\']([^"\']+)["\']',
        text,
        re.MULTILINE,
    )
    if not match:
        raise MarkerError(f"{VERSION_PY} has no __version__ assignment")
    return match.group(1).strip()


def read_installer_version(root: Path) -> str:
    """Return the ``INSTALLER_VERSION`` value from ``scripts/install.sh``."""
    path = root / INSTALL_SH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarkerError(f"cannot read {INSTALL_SH}: {exc}") from exc

    match = re.search(
        r'^INSTALLER_VERSION\s*=\s*["\']([^"\']+)["\']',
        text,
        re.MULTILINE,
    )
    if not match:
        raise MarkerError(f"{INSTALL_SH} has no INSTALLER_VERSION assignment")
    return match.group(1).strip()


def read_changelog_release_version(root: Path) -> str:
    """Return the latest non-``[Unreleased]`` release heading in the CHANGELOG."""
    path = root / CHANGELOG
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarkerError(f"cannot read {CHANGELOG}: {exc}") from exc

    match = re.search(
        r"^##\s*\[(\d+\.\d+\.\d+)\]",
        text,
        re.MULTILINE,
    )
    if not match:
        raise MarkerError(f"{CHANGELOG} has no '## [x.y.z]' release heading")
    return match.group(1).strip()


def collect_markers(root: Path) -> dict[str, str]:
    """Read the four required version markers.

    Returns a mapping of human-readable marker name to its value.
    """
    return {
        VERSION_TXT: read_version_txt(root),
        f"{PYPROJECT} [project] version": read_pyproject_version(root),
        f"{VERSION_PY} __version__": read_version_py(root),
        f"{INSTALL_SH} INSTALLER_VERSION": read_installer_version(root),
    }


def check_consistency(
    markers: dict[str, str],
    tag: str | None = None,
    changelog_version: str | None = None,
) -> list[str]:
    """Return a list of mismatch messages; empty list means all agree.

    ``markers`` maps marker name to value. When ``tag`` is given, every marker
    must also equal the ``v``-stripped tag and ``changelog_version``.
    """
    errors: list[str] = []

    distinct = set(markers.values())
    if len(distinct) > 1:
        detail = ", ".join(f"{name}={value!r}" for name, value in markers.items())
        errors.append(f"version markers disagree: {detail}")

    if tag is not None:
        expected = tag[1:] if tag.startswith("v") else tag
        for name, value in markers.items():
            if value != expected:
                errors.append(
                    f"{name}={value!r} does not match release tag "
                    f"{tag!r} (expected {expected!r})"
                )
        if changelog_version is not None and changelog_version != expected:
            errors.append(
                f"latest CHANGELOG release heading {changelog_version!r} "
                f"does not match release tag {tag!r} (expected {expected!r})"
            )

    return errors


def _emit_actions_error(message: str) -> None:
    """Emit a GitHub Actions error annotation when running in CI."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Newlines are not permitted inside a workflow command.
        print(f"::error title=Version consistency::{message.replace(chr(10), ' ')}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. See module docstring for exit codes."""
    parser = argparse.ArgumentParser(
        description="Assert the four repository version markers agree."
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root (defaults to the parent of scripts/).",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Release tag to additionally assert against (e.g. v2.4.2).",
    )
    args = parser.parse_args(argv)

    root = _repo_root(args.root)

    try:
        markers = collect_markers(root)
        changelog_version = read_changelog_release_version(root) if args.tag else None
    except MarkerError as exc:
        message = f"cannot read a version marker: {exc}"
        print(f"ERROR: {message}", file=sys.stderr)
        _emit_actions_error(message)
        return 2

    print("Version markers:")
    for name, value in markers.items():
        print(f"  {name} = {value}")
    if args.tag:
        print(f"  release tag = {args.tag}")
        print(f"  {CHANGELOG} latest release heading = {changelog_version}")

    errors = check_consistency(
        markers, tag=args.tag, changelog_version=changelog_version
    )
    if errors:
        print("\nVersion consistency check FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
            _emit_actions_error(error)
        return 1

    print("\nVersion consistency check passed: all markers agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
