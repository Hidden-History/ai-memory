#!/usr/bin/env python3
"""What is unavailable without BMAD, and where to get it (FR-2, FR-4, AD-33).

Run by the installer when its BMAD detection reports anything other than "the
BMM Module is present". Prints one tab-separated record per line on stdout and
formats no operator message -- rendering is the installer's.

    capability <TAB> <identifier> <TAB> unsatisfied | indeterminate
    enumeration <TAB> listed | empty | did-not-run | failed [<TAB> <reason>]
    upstream-source <TAB> <dependency> <TAB> <where it comes from>
    upstream-source-missing <TAB> <scope member>
    pin <TAB> present <TAB> <version scope> <TAB> <covered Modules, comma-joined>
    pin <TAB> missing | empty | unreadable <TAB> <the file that was looked for>
    outside-pin <TAB> <scope member>
    report-complete

``report-complete`` is always the last line. A consumer that does not see it
has a truncated report and must not render it as a complete one (N-1).

NOTHING HERE IS A LIST OF CAPABILITIES OR A VERSION. The capabilities are
discovered from each capability's own degraded declaration on every run (AD-33:
"never written down as a list"), and nothing is cached, so installing BMAD
afterwards needs no reinstall. The version scope is read from the pin
declaration and from nowhere else (AD-1, AD-2).

TRANSPORT, stated because this must work in the MOST degraded install: the
system ``python3`` and the standard library only. It does not use the product's
virtualenv, which may not exist yet when the installer reports, and it loads
``degraded.py`` by file path instead of importing the ``memory`` package, whose
``__init__`` needs third-party packages. If ``python3`` itself cannot run this
file the installer reports that as its own state; it never reads as "nothing is
unavailable".
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

_DEGRADED_PY = Path(__file__).resolve().parent.parent / "src" / "memory" / "degraded.py"

PIN_BEGIN = "ai-memory:pin-declaration"
PIN_END = "ai-memory:end-pin-declaration"

# The pin reader's four returns. "missing", "empty" and "unreadable" are three
# conditions, not one (AD-6): the file is not there; it is there and declares no
# version scope; it is there and could not be read or parsed. None of them is
# ever replaced by a default value (AD-33).
#
# AD-24 CLASSIFICATION of a pin that is not "present": FAIL OPEN -- reported,
# zero exit. AD-33 requires the install to exit zero in every absent case, and a
# report that could not name a version scope is still a report.
PIN_PRESENT = "present"
PIN_MISSING = "missing"
PIN_EMPTY = "empty"
PIN_UNREADABLE = "unreadable"
PIN_STATES = (PIN_PRESENT, PIN_MISSING, PIN_EMPTY, PIN_UNREADABLE)

SATISFIED = "satisfied"
UNSATISFIED = "unsatisfied"
INDETERMINATE = "indeterminate"

# The two scope members the installer's detector examines: the product root and
# the one Module it checks beneath it. Its four states are statements about
# these two and about nothing else.
DETECTOR_ROOT = "bmad"
DETECTOR_MODULE = "bmad.bmm"
ABSENCE_STATES = ("bmad-absent", "bmm-absent", "bmad-indeterminate")


@dataclass(frozen=True)
class Pin:
    state: str
    subject: str
    dependency: str | None = None
    version_scope: str | None = None
    covers: tuple[str, ...] = ()

    def scope(self) -> set[str]:
        """Every member this pin covers: its root, and the Modules it names."""
        return {self.dependency, *self.covers}


def _load_degraded():
    spec = importlib.util.spec_from_file_location("_bmad_degraded", _DEGRADED_PY)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves a class's module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_pin(product_root: Path) -> Pin:
    """Read the pin declaration. Returns data; never a default."""
    degraded = _load_degraded()
    site = Path(product_root) / degraded.POV_TREE / "BMAD-PIN.md"
    subject = str(site)
    if not site.exists() and not site.is_symlink():
        return Pin(PIN_MISSING, subject)
    try:
        blocks = degraded.parse_blocks(
            site.read_text(encoding="utf-8"), PIN_BEGIN, PIN_END, subject
        )
    except (OSError, ValueError):
        return Pin(PIN_UNREADABLE, subject)
    if not blocks:
        return Pin(PIN_EMPTY, subject)
    if len(blocks) > 1 or not blocks[0].get("dependency"):
        return Pin(PIN_UNREADABLE, subject)
    fields = blocks[0]
    if not fields.get("version_scope"):
        return Pin(PIN_EMPTY, subject)
    covers = tuple(m.strip() for m in fields.get("covers", "").split(",") if m.strip())
    return Pin(
        PIN_PRESENT, subject, fields["dependency"], fields["version_scope"], covers
    )


def member_verdict(state: str, member: str) -> str:
    """Resolve one dotted scope member against the detector's state.

    Containment over the two levels the detector examined: a member is
    unsatisfied when the root, or the Module on its path, is known to be
    absent; satisfied when it is one of the two examined members and nothing on
    its path is absent; and indeterminate otherwise -- which covers both "the
    evidence could not be checked" and a Module the detector never looked at.
    An unknown is never reported as present or as absent.
    """
    if state == "bmad-indeterminate":
        return INDETERMINATE
    root_present = state != "bmad-absent"
    module_present = state == "bmm-present"
    on_root = member == DETECTOR_ROOT or member.startswith(DETECTOR_ROOT + ".")
    on_module = member == DETECTOR_MODULE or member.startswith(DETECTOR_MODULE + ".")
    if on_root and not root_present:
        return UNSATISFIED
    if on_module and not module_present:
        return UNSATISFIED
    if member in (DETECTOR_ROOT, DETECTOR_MODULE):
        return SATISFIED
    return INDETERMINATE


def _one_line(text: object) -> str:
    return " ".join(str(text).split())


def build_report(state: str, product_root: Path) -> list[tuple[str, ...]]:
    """Every record for one absence state. Reads; writes nothing."""
    degraded = _load_degraded()
    records: list[tuple[str, ...]] = []

    # The members that need a route out: the one the detector itself found
    # wanting, then whatever the unavailable capabilities declare.
    members = [DETECTOR_ROOT if state == "bmad-absent" else DETECTOR_MODULE]
    result = None
    try:
        # One explicit root, supplied by the caller: discover() pins nothing
        # itself, and a searched-for root would find a sibling worktree (AD-19).
        result = degraded.discover(Path(product_root))
    except (OSError, ValueError) as exc:
        # A malformed or unreadable site raises. That is not an empty result.
        records.append(("enumeration", "failed", _one_line(exc)))
    else:
        if not result.ran:
            records.append(("enumeration", "did-not-run", _one_line(result.reason)))
        else:
            # THE GATE: a capability is listed only when the scope member it
            # depends on resolves to something other than satisfied.
            for declaration in result.declarations:
                verdict = member_verdict(state, declaration.depends_on)
                if verdict == SATISFIED:
                    continue
                records.append(("capability", declaration.capability, verdict))
                if declaration.depends_on not in members:
                    members.append(declaration.depends_on)
            listed = any(r[0] == "capability" for r in records)
            records.append(("enumeration", "listed" if listed else "empty"))

    sources: list[tuple[str, ...]] = []
    for member in members:
        remedy = None
        if result is not None and result.ran:
            # remedy_for() is the one A -> B lookup; it reads only depends_on.
            remedy = degraded.remedy_for(result, SimpleNamespace(depends_on=member))
        if remedy is None:
            sources.append(("upstream-source-missing", member))
        else:
            record = ("upstream-source", remedy.dependency, remedy.upstream_source)
            if record not in sources:
                sources.append(record)
    records.extend(sources)

    pin = read_pin(Path(product_root))
    if pin.state == PIN_PRESENT:
        records.append(("pin", PIN_PRESENT, pin.version_scope, ", ".join(pin.covers)))
        # A member outside the pin's declared coverage is not described as
        # pinned (FR-4). Reported, and nothing else about the report changes.
        records.extend(("outside-pin", m) for m in members if m not in pin.scope())
    else:
        records.append(("pin", pin.state, pin.subject))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", required=True)
    parser.add_argument("--product-root", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.state not in ABSENCE_STATES:
        print(f"not an absence state: {args.state!r}", file=sys.stderr)
        return 2
    records = build_report(args.state, args.product_root)
    lines = ["\t".join(_one_line(field) for field in record) for record in records]
    print("\n".join([*lines, "report-complete"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
