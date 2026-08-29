"""Per-capability degraded declarations and their discovery (FR-5, AD-26).

Two surfaces, deliberately split so a per-dependency fact is not duplicated
across every capability that depends on it (N-5):

* **Surface A** -- one *degraded declaration* per BMAD-dependent capability,
  co-located with the capability it describes. Never a central list: the
  enumeration Story 1.6 renders is *derived* from these sites, so a written
  roster would defeat it at the root (AD-33, AD-2).
* **Surface B** -- one *dependency declaration* per dependency, at a single
  definition site, carrying where the dependency comes from.

Both surfaces use one block format, so a single reader serves every transport
(markdown workflow files, shell scripts, Python modules). Building a second
mechanism for a second transport would leave nothing holding the two
equivalent.

Discovery enumerates *declared declaration sites* at bounded depth. It never
uses a recursive glob: sibling ``ai-memory-<branch>/`` worktrees carry
duplicate trees, and a ``**/`` walk would enumerate every capability once per
worktree (AD-19).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# AD-65 resolves the pov tree once, for the whole product. This module is the
# single place this package spells it; consumers import from here rather than
# writing the path a second time (SO-17).
POV_TREE = "_ai-memory/pov"

# The one Surface B definition site.
DEPENDENCY_DECLARATION_SITE = f"{POV_TREE}/DEPENDENCIES.md"

DECLARATION_BEGIN = "ai-memory:degraded-declaration"
DECLARATION_END = "ai-memory:end-degraded-declaration"
DEPENDENCY_BEGIN = "ai-memory:dependency-declaration"
DEPENDENCY_END = "ai-memory:end-dependency-declaration"

DECLARATION_FIELDS = (
    "capability",
    "depends_on",
    "degraded_behaviour",
    "degraded_test",
)
DEPENDENCY_FIELDS = ("dependency", "upstream_source")

# The version scope belongs to FR-4's pin declaration and is read from it by
# Story 1.6. Restating it in a shipped artifact is a claim about current
# reality that does not carry its pin (AD-1, AD-2).
FORBIDDEN_DEPENDENCY_FIELDS = ("version_scope",)

# A degraded_test value is either a test reference or one of FR-13's four
# enforcement states. A bare boolean is not a valid marking (AD-20).
ENFORCEMENT_STATES = (
    "unenforceable",
    "not-yet-enforced",
    "enforced-but-non-blocking",
    "enforced-and-blocking",
)


class DeclarationError(ValueError):
    """A declaration block is malformed, incomplete, or duplicated."""


@dataclass(frozen=True)
class Declaration:
    """Surface A -- what one capability does when its dependency is absent."""

    capability: str
    depends_on: str
    degraded_behaviour: str
    degraded_test: str
    source: str


@dataclass(frozen=True)
class Dependency:
    """Surface B -- what one dependency is, and what would provide it."""

    dependency: str
    upstream_source: str
    source: str


@dataclass(frozen=True)
class DiscoveryResult:
    """The outcome of a discovery run.

    ``ran`` separates "discovery did not run" from "discovery ran and found
    nothing". An empty resolution is a result, not a silence (AD-6): a
    consumer must be able to tell "none declared" from "not looked for".
    """

    ran: bool
    declarations: tuple[Declaration, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    sites_scanned: int = 0
    reason: str | None = None


def _strip_comment(line: str) -> str:
    """Reduce one line of any supported transport to its bare payload."""
    text = line.strip()
    for opener in ("<!--", "//", "#"):
        if text.startswith(opener):
            text = text[len(opener) :].strip()
            break
    if text.endswith("-->"):
        text = text[:-3].strip()
    return text


def parse_blocks(text: str, begin: str, end: str, source: str) -> list[dict[str, str]]:
    """Extract every ``begin``..``end`` block from *text* as a field mapping.

    Raises DeclarationError on an unterminated block -- a truncated
    declaration must not read as a valid short one.
    """
    blocks: list[dict[str, str]] = []
    fields: dict[str, str] | None = None
    for raw in text.splitlines():
        payload = _strip_comment(raw)
        if fields is None:
            if begin in payload:
                fields = {}
            continue
        if end in payload:
            blocks.append(fields)
            fields = None
            continue
        if begin in payload:
            # A second begin marker inside an open block means the first was
            # never terminated. Parsed as a field it would be absorbed and the
            # blocks merged, so the earlier capability would leave the
            # enumeration with nothing raised (AC-5).
            raise DeclarationError(
                f"{source}: a nested {begin!r} marker means the preceding block "
                f"(capability {fields.get('capability', '<unnamed>')!r}) is not "
                f"terminated by {end!r}"
            )
        if not payload:
            continue
        key, sep, value = payload.partition(":")
        if not sep:
            raise DeclarationError(
                f"{source}: line inside a declaration block is not 'key: value': {payload!r}"
            )
        fields[key.strip()] = value.strip()
    if fields is not None:
        raise DeclarationError(
            f"{source}: declaration block is not terminated by {end!r}"
        )
    return blocks


def _require(fields: dict[str, str], names: tuple[str, ...], source: str) -> None:
    missing = [n for n in names if not fields.get(n)]
    if missing:
        raise DeclarationError(f"{source}: declaration is missing {', '.join(missing)}")


def declaration_sites(product_root: Path) -> list[Path] | None:
    """Every declared Surface A site under the pov tree, or None if absent.

    Sites are enumerated at explicitly bounded depth -- skills one level deep,
    workflows one or two levels deep -- never by a recursive glob (AD-19).
    """
    pov = Path(product_root) / POV_TREE
    if not pov.is_dir():
        return None

    sites: list[Path] = []

    skills = pov / "skills"
    if skills.is_dir():
        for entry in sorted(skills.iterdir()):
            site = entry / "SKILL.md"
            if entry.is_dir() and site.is_file():
                sites.append(site)

    workflows = pov / "workflows"
    if workflows.is_dir():
        for first in sorted(workflows.iterdir()):
            if not first.is_dir():
                continue
            site = first / "workflow.md"
            if site.is_file():
                sites.append(site)
            for second in sorted(first.iterdir()):
                if not second.is_dir():
                    continue
                site = second / "workflow.md"
                if site.is_file():
                    sites.append(site)

    return sites


def discover(product_root: Path) -> DiscoveryResult:
    """Derive the declared degraded set from its sites.

    Returns both surfaces so a consumer can traverse A -> B on the join key.
    Rendering the set for an operator is Story 1.6's; this function only
    produces it.
    """
    root = Path(product_root)
    sites = declaration_sites(root)
    if sites is None:
        return DiscoveryResult(
            ran=False,
            reason=f"pov tree not found at {root / POV_TREE}",
        )

    declarations: list[Declaration] = []
    seen: dict[str, str] = {}
    for site in sites:
        relative = str(site.relative_to(root))
        # Symmetric with the registry reader: these are bytes this product did
        # not necessarily write, and one undecodable byte must not take the
        # whole enumeration down with an unhandled error (AC-1).
        for fields in parse_blocks(
            site.read_text(encoding="utf-8", errors="replace"),
            DECLARATION_BEGIN,
            DECLARATION_END,
            relative,
        ):
            _require(fields, DECLARATION_FIELDS, relative)
            capability = fields["capability"]
            if capability in seen:
                raise DeclarationError(
                    f"{relative}: capability {capability!r} is already declared at {seen[capability]}"
                )
            seen[capability] = relative
            declarations.append(
                Declaration(
                    capability=capability,
                    depends_on=fields["depends_on"],
                    degraded_behaviour=fields["degraded_behaviour"],
                    degraded_test=fields["degraded_test"],
                    source=relative,
                )
            )

    dependencies: list[Dependency] = []
    declared: set[str] = set()
    site = root / DEPENDENCY_DECLARATION_SITE
    if site.is_file():
        for fields in parse_blocks(
            site.read_text(encoding="utf-8", errors="replace"),
            DEPENDENCY_BEGIN,
            DEPENDENCY_END,
            DEPENDENCY_DECLARATION_SITE,
        ):
            _require(fields, DEPENDENCY_FIELDS, DEPENDENCY_DECLARATION_SITE)
            present = [f for f in FORBIDDEN_DEPENDENCY_FIELDS if f in fields]
            if present:
                raise DeclarationError(
                    f"{DEPENDENCY_DECLARATION_SITE}: {', '.join(present)} is forbidden here -- "
                    "the version scope is read from FR-4's pin declaration"
                )
            if fields["dependency"] in declared:
                raise DeclarationError(
                    f"{DEPENDENCY_DECLARATION_SITE}: dependency "
                    f"{fields['dependency']!r} is already declared -- two entries "
                    "make the remedy join order-dependent"
                )
            declared.add(fields["dependency"])
            dependencies.append(
                Dependency(
                    dependency=fields["dependency"],
                    upstream_source=fields["upstream_source"],
                    source=DEPENDENCY_DECLARATION_SITE,
                )
            )

    return DiscoveryResult(
        ran=True,
        declarations=tuple(declarations),
        dependencies=tuple(dependencies),
        sites_scanned=len(sites),
    )


def remedy_for(result: DiscoveryResult, declaration: Declaration) -> Dependency | None:
    """Join one declaration to its remedy by containment over the dotted scope.

    ``bmad.bmm`` is served by a ``bmad.bmm`` entry if one exists, otherwise by
    ``bmad``. There is no mapping table: both sides draw their values from the
    same pin-declared scope.
    """
    parts = declaration.depends_on.split(".")
    for depth in range(len(parts), 0, -1):
        prefix = ".".join(parts[:depth])
        for dependency in result.dependencies:
            if dependency.dependency == prefix:
                return dependency
    return None
