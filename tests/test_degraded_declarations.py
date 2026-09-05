"""Contract and unit tests for per-capability degraded declarations (Story 1.4).

Covers FR-5's testable consequences as they land on the three transports this
product ships. Most BMAD-dependent capabilities are prose — workflow and skill
markdown that instructs an action requiring a BMAD-shipped artifact — so their
absent-mode test is a structural contract test over the markdown, which is what
the ``process`` marker exists for.

Synthetic identifiers only in fixtures: a fixture using live skill, module or
agent names is an unbound roster wearing a test hat and goes stale just as
fast (AD-20b). The contract tests below read the real tree, but they *derive*
the set they check rather than carrying a list of it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from memory.degraded import (
    DECLARATION_BEGIN,
    DECLARATION_END,
    DEPENDENCY_BEGIN,
    DEPENDENCY_DECLARATION_SITE,
    DEPENDENCY_END,
    ENFORCEMENT_STATES,
    POV_TREE,
    Declaration,
    DeclarationError,
    DiscoveryResult,
    declaration_sites,
    discover,
    parse_blocks,
    remedy_for,
)

PRODUCT_ROOT = Path(__file__).resolve().parent.parent

# A reference to a BMAD-shipped artifact that must exist for the instruction to
# be followable. Mirrors Story 1.4's Task 1 derivation.
#
# Excluded, stated alongside the set it produces: the bare word "BMAD", which
# appears as methodology prose on every workflow file ("This file is a BMAD
# module summary") and names no artifact; and AI-Memory's own identifiers that
# merely contain the string (bmad-dispatch, bmad-hooks, _bmad-output).
_ARTIFACT_REFERENCE = re.compile(
    r"/bmad-[a-z0-9-]+"
    r"|bmad-agent-[a-z-]+"
    r"|skills/bmad-[a-z0-9-]+"
    r"|test -d _bmad"
    r"|_bmad/_config/"
    r"|\$\{skills_dir\}/bmad-\*"
    r"|load bmad-[a-z0-9-]+"
)
_NOT_A_BMAD_ARTIFACT = re.compile(r"bmad-dispatch|bmad-hooks|bmad_hooks|bmad-output")


def _references_bmad_artifact(container: Path) -> bool:
    """True if any file under *container* names a BMAD-shipped artifact."""
    for base, _dirs, names in os.walk(container):
        for name in names:
            path = Path(base) / name
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in _ARTIFACT_REFERENCE.finditer(text):
                if not _NOT_A_BMAD_ARTIFACT.search(match.group(0)):
                    return True
    return False


@pytest.fixture(scope="module")
def real_discovery() -> DiscoveryResult:
    return discover(PRODUCT_ROOT)


# ---------------------------------------------------------------------------
# Contract tests over the shipped tree
# ---------------------------------------------------------------------------


@pytest.mark.process
def test_discovery_runs_against_the_shipped_tree(
    real_discovery: DiscoveryResult,
) -> None:
    """Discovery must run, and must find the declarations that exist."""
    assert real_discovery.ran is True
    assert real_discovery.reason is None
    assert real_discovery.sites_scanned > 0
    assert real_discovery.declarations


@pytest.mark.process
def test_every_bmad_dependent_capability_declares_its_degradation(
    real_discovery: DiscoveryResult,
) -> None:
    """Derived, not listed: every container naming a BMAD artifact declares.

    The expected set is derived from the tree by the same matcher Task 1 used,
    so a capability that gains a BMAD dependency later is caught without
    anyone editing a roster.
    """
    sites = declaration_sites(PRODUCT_ROOT)
    assert sites is not None

    declared_sites = {d.source for d in real_discovery.declarations}
    undeclared = [
        str(site.relative_to(PRODUCT_ROOT))
        for site in sites
        if _references_bmad_artifact(site.parent)
        and str(site.relative_to(PRODUCT_ROOT)) not in declared_sites
    ]
    assert undeclared == [], (
        "capability containers reference a BMAD-shipped artifact but carry no "
        f"degraded declaration: {undeclared}"
    )


@pytest.mark.process
def test_every_declaration_joins_to_a_dependency_that_declares_a_remedy(
    real_discovery: DiscoveryResult,
) -> None:
    """Surface A's ``depends_on`` resolves to a Surface B entry carrying a remedy.

    What this checks is the *join*: every declaration names a dependency, and
    that dependency has a declaration of its own whose ``upstream_source`` is
    populated. It is a schema test over the two surfaces.

    🔴 **What it does NOT check, stated because its previous name claimed
    otherwise.** It never reads a message. ``AC-1`` requires that the
    capability, when invoked with the dependency absent, *emits* text naming
    the missing dependency and what would provide it — and nothing here
    inspects the artifact that emits it. The old name,
    ``test_every_declaration_names_its_dependency_and_remedy``, read as an
    ``AC-1`` assertion and was cited as one, while passing green for a
    declaration whose ``degraded_behaviour`` was replaced with ``xyzzy.``.

    ``AC-1`` is asserted per capability, by the behavioural fixtures at the
    bottom of this module, against the artifact that actually carries the
    message. A declaration with no such fixture is marked ``not-yet-enforced``
    and counted — which is what ``AC-3`` requires and what this test must not
    be mistaken for.
    """
    unremedied = []
    for declaration in real_discovery.declarations:
        assert declaration.depends_on
        assert declaration.degraded_behaviour
        remedy = remedy_for(real_discovery, declaration)
        if remedy is None or not remedy.upstream_source:
            unremedied.append((declaration.capability, declaration.depends_on))
    assert unremedied == [], (
        "declarations name a dependency that no dependency declaration provides: "
        f"{unremedied}"
    )


@pytest.mark.process
def test_declaration_fields_are_valid(real_discovery: DiscoveryResult) -> None:
    """The marking is four-state or a test reference — never a bare boolean."""
    for declaration in real_discovery.declarations:
        marking = declaration.degraded_test
        assert marking.lower() not in {"true", "false", "yes", "no", "0", "1"}, (
            f"{declaration.capability}: degraded_test is a boolean, which is not a "
            "valid marking"
        )
        assert marking in ENFORCEMENT_STATES or "::" in marking, (
            f"{declaration.capability}: degraded_test {marking!r} is neither a test "
            f"reference nor one of {ENFORCEMENT_STATES}"
        )
        assert declaration.capability.startswith("cap:"), (
            f"{declaration.capability!r} is not namespaced: an identifier that reads as "
            "prose collides with the text around it"
        )
        assert (
            "/" not in declaration.capability
        ), "an identifier that is a path breaks when the file moves"


@pytest.mark.process
def test_declaration_test_references_resolve(real_discovery: DiscoveryResult) -> None:
    """A named test must exist. An untested detector is a hope with a checkmark."""
    for declaration in real_discovery.declarations:
        if "::" not in declaration.degraded_test:
            continue
        module, _, name = declaration.degraded_test.partition("::")
        path = PRODUCT_ROOT / module
        assert path.is_file(), f"{declaration.capability}: {module} does not exist"
        assert f"def {name}(" in path.read_text(
            encoding="utf-8"
        ), f"{declaration.capability}: {name} not found in {module}"


@pytest.mark.process
def test_no_shipped_artifact_lists_the_capabilities(
    real_discovery: DiscoveryResult,
) -> None:
    """AC-5: the set is discoverable, and nowhere written down as a list.

    Bounded to the pov tree inside this product root — never a glob from the
    workspace root, where sibling worktrees carry duplicate trees (AD-19).
    """
    identifiers = {d.capability for d in real_discovery.declarations}
    assert len(identifiers) > 1

    for base, _dirs, names in os.walk(PRODUCT_ROOT / POV_TREE):
        for name in names:
            path = Path(base) / name
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            present = {
                i
                for i in identifiers
                if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text)
            }
            assert len(present) <= 1, (
                f"{path.relative_to(PRODUCT_ROOT)} names {sorted(present)} — a shipped "
                "artifact carrying a roster of capabilities defeats derivation at its root"
            )


@pytest.mark.process
def test_dependency_site_declares_no_version_scope() -> None:
    """The version scope is read from the pin declaration, never restated."""
    text = (PRODUCT_ROOT / DEPENDENCY_DECLARATION_SITE).read_text(encoding="utf-8")
    for block in parse_blocks(
        text, DEPENDENCY_BEGIN, DEPENDENCY_END, DEPENDENCY_DECLARATION_SITE
    ):
        assert "version_scope" not in block
        for key, value in block.items():
            assert not re.search(r"\bv?\d+\.\d+(\.\d+)?\b", value), (
                f"{key} carries a version-shaped string {value!r}: a pinned value must "
                "carry its pin, and this file is not the pin declaration"
            )


@pytest.mark.process
def test_absent_status_field_is_not_reinstated(real_discovery: DiscoveryResult) -> None:
    """absent_status was removed deliberately; a constant cannot discriminate."""
    sites = declaration_sites(PRODUCT_ROOT)
    assert sites is not None
    for site in sites:
        text = site.read_text(encoding="utf-8")
        for block in parse_blocks(text, DECLARATION_BEGIN, DECLARATION_END, str(site)):
            assert "absent_status" not in block


# ---------------------------------------------------------------------------
# Unit tests — synthetic trees only
# ---------------------------------------------------------------------------


def _synthetic_tree(root: Path, blocks: dict[str, str]) -> None:
    """Build a minimal pov tree carrying *blocks* keyed by synthetic skill name."""
    skills = root / POV_TREE / "skills"
    skills.mkdir(parents=True)
    for skill_name, block in blocks.items():
        directory = skills / skill_name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"# {skill_name}\n\n{block}\n", encoding="utf-8"
        )


def _block(capability: str, **overrides: str) -> str:
    fields = {
        "capability": capability,
        "depends_on": "widget",
        "degraded_behaviour": "reports the dependency as unavailable",
        "degraded_test": "not-yet-enforced",
    }
    fields.update(overrides)
    body = "\n".join(f"{k}: {v}" for k, v in fields.items())
    return f"<!-- {DECLARATION_BEGIN}\n{body}\n{DECLARATION_END} -->"


def _dependency_site(
    root: Path, name: str = "widget", source: str = "https://example.invalid/widget"
) -> None:
    site = root / DEPENDENCY_DECLARATION_SITE
    site.parent.mkdir(parents=True, exist_ok=True)
    site.write_text(
        f"<!-- {DEPENDENCY_BEGIN}\ndependency: {name}\nupstream_source: {source}\n{DEPENDENCY_END} -->\n",
        encoding="utf-8",
    )


def test_fixture_pair_complete_declaration_passes(tmp_path: Path) -> None:
    """Direction one of the pair: a compliant declaration must not be flagged."""
    _synthetic_tree(tmp_path, {"synthetic-alpha": _block("cap:synthetic-alpha")})
    _dependency_site(tmp_path)
    result = discover(tmp_path)
    assert result.ran is True
    assert [d.capability for d in result.declarations] == ["cap:synthetic-alpha"]
    assert remedy_for(result, result.declarations[0]) is not None


def test_fixture_pair_incomplete_declaration_is_flagged(tmp_path: Path) -> None:
    """Direction two: a declaration missing a required field must be flagged."""
    incomplete = _block("cap:synthetic-beta").replace(
        "degraded_behaviour: reports the dependency as unavailable\n", ""
    )
    _synthetic_tree(tmp_path, {"synthetic-beta": incomplete})
    with pytest.raises(DeclarationError, match="degraded_behaviour"):
        discover(tmp_path)


def test_discovery_that_did_not_run_is_not_an_empty_result(tmp_path: Path) -> None:
    """An empty resolution is a result, not a silence (AD-6)."""
    result = discover(tmp_path)
    assert result.ran is False
    assert result.declarations == ()
    assert result.reason is not None


def test_discovery_that_found_nothing_reports_a_result(tmp_path: Path) -> None:
    _synthetic_tree(tmp_path, {"synthetic-gamma": "# no declaration here"})
    result = discover(tmp_path)
    assert result.ran is True
    assert result.declarations == ()
    assert result.sites_scanned == 1
    assert result.reason is None


def test_duplicate_capability_identifier_is_refused(tmp_path: Path) -> None:
    _synthetic_tree(
        tmp_path,
        {
            "synthetic-delta": _block("cap:synthetic-shared"),
            "synthetic-epsilon": _block("cap:synthetic-shared"),
        },
    )
    with pytest.raises(DeclarationError, match="already declared"):
        discover(tmp_path)


def test_unterminated_block_is_refused(tmp_path: Path) -> None:
    """A truncated declaration must not read as a valid short one."""
    truncated = f"<!-- {DECLARATION_BEGIN}\ncapability: cap:synthetic-zeta\n"
    _synthetic_tree(tmp_path, {"synthetic-zeta": truncated})
    with pytest.raises(DeclarationError, match="not terminated"):
        discover(tmp_path)


def test_version_scope_in_a_dependency_declaration_is_refused(tmp_path: Path) -> None:
    _synthetic_tree(tmp_path, {"synthetic-eta": _block("cap:synthetic-eta")})
    site = tmp_path / DEPENDENCY_DECLARATION_SITE
    site.parent.mkdir(parents=True, exist_ok=True)
    site.write_text(
        f"<!-- {DEPENDENCY_BEGIN}\ndependency: widget\nupstream_source: https://example.invalid/w\n"
        f"version_scope: 1.2.3\n{DEPENDENCY_END} -->\n",
        encoding="utf-8",
    )
    with pytest.raises(DeclarationError, match="version_scope"):
        discover(tmp_path)


def test_remedy_join_falls_back_to_the_product_root(tmp_path: Path) -> None:
    """Containment, not a mapping table: widget.part is served by widget."""
    _synthetic_tree(
        tmp_path,
        {"synthetic-theta": _block("cap:synthetic-theta", depends_on="widget.part")},
    )
    _dependency_site(tmp_path)
    result = discover(tmp_path)
    remedy = remedy_for(result, result.declarations[0])
    assert remedy is not None
    assert remedy.dependency == "widget"


def test_remedy_join_prefers_the_more_specific_entry(tmp_path: Path) -> None:
    _synthetic_tree(
        tmp_path,
        {"synthetic-iota": _block("cap:synthetic-iota", depends_on="widget.part")},
    )
    site = tmp_path / DEPENDENCY_DECLARATION_SITE
    site.parent.mkdir(parents=True, exist_ok=True)
    site.write_text(
        f"<!-- {DEPENDENCY_BEGIN}\ndependency: widget\nupstream_source: https://example.invalid/w\n{DEPENDENCY_END} -->\n"
        f"<!-- {DEPENDENCY_BEGIN}\ndependency: widget.part\nupstream_source: https://example.invalid/wp\n{DEPENDENCY_END} -->\n",
        encoding="utf-8",
    )
    result = discover(tmp_path)
    remedy = remedy_for(result, result.declarations[0])
    assert remedy is not None
    assert remedy.dependency == "widget.part"


def test_declaration_block_reads_the_same_from_a_shell_transport(
    tmp_path: Path,
) -> None:
    """One mechanism, every transport: a hash-commented block parses identically."""
    shell_form = "\n".join(
        [
            f"# {DECLARATION_BEGIN}",
            "# capability: cap:synthetic-kappa",
            "# depends_on: widget",
            "# degraded_behaviour: reports the dependency as unavailable",
            "# degraded_test: not-yet-enforced",
            f"# {DECLARATION_END}",
        ]
    )
    markdown_form = _block("cap:synthetic-kappa")
    from_shell = parse_blocks(
        shell_form, DECLARATION_BEGIN, DECLARATION_END, "synthetic.sh"
    )
    from_markdown = parse_blocks(
        markdown_form, DECLARATION_BEGIN, DECLARATION_END, "synthetic.md"
    )
    assert from_shell == from_markdown


def test_declaration_is_a_frozen_record() -> None:
    declaration = Declaration("cap:a", "b", "c", "d", "e")
    with pytest.raises(AttributeError):
        declaration.capability = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Round 2 — a declaration must not be able to disappear without a signal, and
# discovery must not crash on a site it cannot decode.
# ---------------------------------------------------------------------------


def _declaration(capability: str) -> str:
    return "\n".join(
        (
            f"<!-- {DECLARATION_BEGIN} -->",
            f"<!-- capability: {capability} -->",
            "<!-- depends_on: bmad -->",
            "<!-- degraded_behaviour: synthetic degraded statement -->",
            "<!-- degraded_test: not-yet-enforced -->",
        )
    )


def test_a_missing_end_marker_does_not_swallow_the_previous_capability(
    tmp_path: Path,
) -> None:
    """Two blocks, the first unterminated, must not silently become one.

    The reader treated a second begin marker as an ordinary ``key: value``
    line, so the second block's fields overwrote the first's and one
    capability left the enumeration with nothing raised and nothing logged.
    A capability that vanishes silently defeats AC-5 at its root.
    """
    text = "\n".join(
        (
            _declaration("cap:synthetic-lambda"),
            _declaration("cap:synthetic-mu"),
            f"<!-- {DECLARATION_END} -->",
        )
    )
    with pytest.raises(DeclarationError) as excinfo:
        parse_blocks(text, DECLARATION_BEGIN, DECLARATION_END, "synthetic-site")
    assert "cap:synthetic-lambda" in str(excinfo.value) or "nested" in str(
        excinfo.value
    )


def test_two_terminated_blocks_in_one_file_still_parse(tmp_path: Path) -> None:
    """The other direction: the guard must not refuse a legitimate pair."""
    text = "\n".join(
        (
            _declaration("cap:synthetic-lambda"),
            f"<!-- {DECLARATION_END} -->",
            _declaration("cap:synthetic-mu"),
            f"<!-- {DECLARATION_END} -->",
        )
    )
    blocks = parse_blocks(text, DECLARATION_BEGIN, DECLARATION_END, "synthetic-site")
    assert [b["capability"] for b in blocks] == [
        "cap:synthetic-lambda",
        "cap:synthetic-mu",
    ]


def test_undecodable_site_does_not_crash_discovery(tmp_path: Path) -> None:
    """Discovery reads bytes it did not write; it must degrade like the resolver.

    The registry reader passes ``errors="replace"``; this reader did not, so
    one undecodable byte anywhere under the pov tree took the whole
    enumeration down with an unhandled UnicodeDecodeError (AC-1).
    """
    site = tmp_path / POV_TREE / "skills" / "synthetic-skill"
    site.mkdir(parents=True)
    (site / "SKILL.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    result = discover(tmp_path)
    assert result.ran is True
    assert result.declarations == ()


def test_duplicate_dependency_identifier_is_refused(tmp_path: Path) -> None:
    """A duplicate dependency is refused for the reason a duplicate capability is.

    Two entries for one dependency make the remedy join order-dependent: the
    first match wins and the second is unreachable, so an operator is handed
    whichever remedy happened to be written first.
    """
    (tmp_path / POV_TREE).mkdir(parents=True)
    (tmp_path / DEPENDENCY_DECLARATION_SITE).write_text(
        "\n".join(
            (
                f"<!-- {DEPENDENCY_BEGIN} -->",
                "<!-- dependency: synthetic-dep -->",
                "<!-- upstream_source: the first source -->",
                f"<!-- {DEPENDENCY_END} -->",
                f"<!-- {DEPENDENCY_BEGIN} -->",
                "<!-- dependency: synthetic-dep -->",
                "<!-- upstream_source: a second, conflicting source -->",
                f"<!-- {DEPENDENCY_END} -->",
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeclarationError) as excinfo:
        discover(tmp_path)
    assert "synthetic-dep" in str(excinfo.value)


def test_distinct_dependencies_at_one_site_still_parse(tmp_path: Path) -> None:
    """The other direction: two different dependencies are legitimate."""
    (tmp_path / POV_TREE).mkdir(parents=True)
    (tmp_path / DEPENDENCY_DECLARATION_SITE).write_text(
        "\n".join(
            (
                f"<!-- {DEPENDENCY_BEGIN} -->",
                "<!-- dependency: synthetic-dep-one -->",
                "<!-- upstream_source: source one -->",
                f"<!-- {DEPENDENCY_END} -->",
                f"<!-- {DEPENDENCY_BEGIN} -->",
                "<!-- dependency: synthetic-dep-two -->",
                "<!-- upstream_source: source two -->",
                f"<!-- {DEPENDENCY_END} -->",
            )
        ),
        encoding="utf-8",
    )
    result = discover(tmp_path)
    assert [d.dependency for d in result.dependencies] == [
        "synthetic-dep-one",
        "synthetic-dep-two",
    ]


# Tests in this module that a declaration MAY cite as its degraded behaviour.
# Each drives a capability's own shipped artifact rather than the declaration
# records, so it discriminates between a capability that degrades correctly and
# one that does not.
#
# Default-deny by construction. What this narrows was a whole-module exclusion,
# which rejected every citation into this file — behavioural ones included. An
# allowlist narrows it without widening the hole it was guarding: a schema test
# added later is excluded because it was never admitted, not because someone
# remembered to deny it.
#
# Membership is tested against the criterion above, not against intent. A
# tree-wide test admitted here earlier — one asserting a superseded literal is
# absent anywhere under the pov tree — was removed: it is scoped to no
# capability's directory and returns the same verdict for every declaration, so
# it cannot discriminate, and admitting it was a standing route from an honest
# "not-yet-enforced" to a green citation carrying no capability-specific
# evidence.
_BEHAVIOURAL_TESTS_IN_THIS_MODULE = frozenset(
    {
        "test_agent_dispatch_gates_bmad_persona_routing_on_bmad_presence",
        "test_agent_lifecycle_gates_persona_activation_on_bmad_presence",
        "test_bmad_dispatch_requires_bmad_before_it_creates_a_pane",
        "test_cycle_agent_dispatch_gates_persona_activation_on_bmad_presence",
    }
)


def _schema_self_citations(
    declarations: tuple[Declaration, ...],
) -> list[tuple[str, str]]:
    """Declarations citing a test in this module that is not behavioural."""
    this_module = Path(__file__).name
    return [
        (d.capability, d.degraded_test)
        for d in declarations
        if "::" in d.degraded_test
        and d.degraded_test.split("::")[0].endswith(this_module)
        and d.degraded_test.split("::", 1)[1] not in _BEHAVIOURAL_TESTS_IN_THIS_MODULE
    ]


@pytest.mark.process
def test_a_declaration_may_not_cite_the_declaration_schema_as_its_behaviour(
    real_discovery: DiscoveryResult,
) -> None:
    """A declaration cannot be its own behavioural coverage.

    Round 1 pointed thirteen of sixteen declarations at a test in this module
    — one that asserts each declaration *names* a dependency and a remedy. That
    is a schema check over the declarations themselves: it passes whether or
    not the capability degrades correctly, and it would pass for a capability
    with no degraded path at all. Counting those as covered produced a "16
    covered / 0 marked" figure that no behaviour stood behind.

    A path with no behavioural test is not a failure — it is one of AD-20's
    four states, recorded honestly. Citing a schema test instead is what turns
    an unenforced path into a green checkmark.

    The exclusion was originally whole-module, which also refused the
    behavioural tests that live here — a test may sit in this file and still
    drive a capability's own artifact. It now names the tests it admits, and
    the pair below drives both directions so the narrowing is observed to
    refuse rather than assumed to.
    """
    circular = _schema_self_citations(real_discovery.declarations)
    assert circular == [], (
        "declarations cite this module's own schema tests as their degraded "
        f"behaviour, which cannot discriminate: {circular}. Mark them with one "
        "of AD-20's four enforcement states instead."
    )


def test_schema_self_citation_is_still_refused_by_the_narrowed_guard(
    tmp_path: Path,
) -> None:
    """Direction one: a genuine schema self-citation must still be caught."""
    cited = (
        f"tests/{Path(__file__).name}"
        "::test_every_declaration_joins_to_a_dependency_that_declares_a_remedy"
    )
    _synthetic_tree(
        tmp_path,
        {"synthetic-circular": _block("cap:synthetic-circular", degraded_test=cited)},
    )
    _dependency_site(tmp_path)
    result = discover(tmp_path)
    assert _schema_self_citations(result.declarations) == [
        ("cap:synthetic-circular", cited)
    ]


def test_behavioural_citation_into_this_module_is_admitted(tmp_path: Path) -> None:
    """Direction two: the narrowing must actually admit a behavioural test."""
    cited = (
        f"tests/{Path(__file__).name}"
        "::test_bmad_dispatch_requires_bmad_before_it_creates_a_pane"
    )
    _synthetic_tree(
        tmp_path,
        {"synthetic-live": _block("cap:synthetic-live", degraded_test=cited)},
    )
    _dependency_site(tmp_path)
    result = discover(tmp_path)
    assert [d.capability for d in result.declarations] == ["cap:synthetic-live"]
    assert _schema_self_citations(result.declarations) == []


@pytest.mark.process
def test_bmad_dispatch_requires_bmad_before_it_creates_a_pane() -> None:
    """The one dispatch path that needs BMAD must gate on it itself (AC-1).

    Separating BMAD's absence from CWD drift made the sentinel return 0 when
    only ``_bmad/`` is missing, which is right for the dispatch paths that
    never needed BMAD. It is wrong for this one: it exists to activate a BMAD
    agent, so on a BMAD-less machine the sentinel's success would carry it
    through to creating a pane and sending an activation that cannot resolve —
    a silent no-op wearing a successful dispatch's clothes.

    The declaration this test is cited by makes two claims — the generic paths
    keep working, and the bmad-dispatch path is reported unavailable rather than
    launching a pane — so both are asserted here. Asserting only the second
    leaves the first covered by nothing while the citation reads as whole.
    """
    step = (
        PRODUCT_ROOT
        / POV_TREE
        / "skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        / "step-02-launch-and-activate.md"
    )
    text = step.read_text(encoding="utf-8")

    gate = text.find("test -d _bmad")
    pane = text.find("tmux split-window")
    assert gate != -1, f"{step.name} creates a pane with no BMAD-presence gate"
    assert pane != -1, f"{step.name} no longer creates a pane — re-derive this test"
    assert gate < pane, (
        "the BMAD gate must run before pane creation: a pane created first is "
        "a resource spent on a dispatch that cannot complete"
    )

    gate_block = text[gate : gate + 600]
    assert "unavailable" in gate_block, "the gate must name the missing dependency"
    assert (
        "DEPENDENCIES.md" in gate_block
    ), "the gate must name what would provide it (AC-1)"
    assert "exit 1" in gate_block, (
        "the gate must terminate. Ordering alone does not hold the declared "
        "behaviour: a gate that reports and falls through still reaches pane "
        "creation, which is the 'instead of launching a pane' half of the claim"
    )
    assert "Non-BMAD dispatch" in gate_block, (
        "the gate must state that the generic paths are unaffected — the first "
        "clause of the declared behaviour, and the half an operator needs in "
        "order to know what still works"
    )


@pytest.mark.process
def test_agent_dispatch_gates_bmad_persona_routing_on_bmad_presence() -> None:
    """Generic routing survives BMAD's absence; persona routing is refused (AC-1).

    ``cap:agent-dispatch`` declares two things: that it routes generic
    dispatches only, and that it reports BMAD persona routing as unavailable
    instead of emitting a ``/bmad-*`` activation that cannot resolve. Both live
    in this skill's own prose — the BMAD-presence check is separated from the
    drift sentinel, and each gate site states both outcomes — so both are
    asserted, at every gate site rather than at one chosen by position.

    Position is what makes the second claim real: the tables emitting
    ``/bmad-agent-*`` are read by an agent that has already passed the routing
    gate. A gate read after them is a gate read too late to stop the activation
    it exists to prevent.

    Anchored to the gate's own line, not a byte window: the line is the unit the
    instruction is written in, so the assertion does not couple to the distance
    between one paragraph and the next.
    """
    skill = PRODUCT_ROOT / POV_TREE / "skills/aim-agent-dispatch/SKILL.md"
    text = skill.read_text(encoding="utf-8")

    gates = [m.start() for m in re.finditer(re.escape("test -d _bmad"), text)]
    persona = text.find("/bmad-agent-")
    assert gates, f"{skill.name} routes BMAD dispatches with no BMAD-presence gate"
    assert persona != -1, (
        f"{skill.name} no longer emits a /bmad-agent-* activation command — "
        "re-derive this test"
    )
    assert min(gates) < persona, (
        "the BMAD-presence gate must be read before the first /bmad-agent-* "
        "activation command: a command emitted first cannot resolve"
    )

    for gate in gates:
        line = text[text.rfind("\n", 0, gate) + 1 : text.find("\n", gate)]
        assert "unavailable" in line, (
            "every BMAD-presence gate must report the dependency as "
            f"unavailable: {line!r}"
        )
        assert "non-BMAD dispatch" in line, (
            "every BMAD-presence gate must state that generic dispatch "
            f"continues, or the absent path has no declared outcome: {line!r}"
        )
        assert "DEPENDENCIES.md" in line, (
            "every BMAD-presence gate must name what would provide the missing "
            "dependency, not merely that it is missing. AC-1 requires the "
            f"remedy half and a gate naming only the dependency fails it: {line!r}"
        )


# ---------------------------------------------------------------------------
# The superseded three-marker conjunction (TD-1130)
#
# Shape: ENUMERATE BROADLY -> READ EVERY HIT -> FAIL ON ANYTHING NOT DECLARED.
#
# The guard this replaces matched one literal command string. That literal
# occurs zero times in the pov tree -- the *command* form was fixed everywhere
# -- so it was green throughout while the same *semantic* rule was restated in
# prose at sites the matcher structurally could not reach. Four instruments
# then produced four different counts of those sites (0, 2, 4, 3), which is the
# actual finding: "how many sites" is not answerable by a pattern, and a longer
# pattern yields a fifth number rather than a closed set.
#
# So collection here is deliberately un-clever, and the judgment happens after
# it. The predicate is lexical, not semantic: every line naming the ``_bmad``
# directory marker, with a token boundary that drops ``_bmad-output`` and
# ``check_bmad_commands`` because those name other things -- or naming that same
# directory through the ``bmad_dir`` variable the sentinel holds it in.
#
# The second alternative is here because the first alone was not the closed set
# it read as: a stale three-marker mandate written ``test -d "${bmad_dir}"``
# carries no ``_bmad`` token and was collected nowhere. Lexical collection is
# still narrower than the class it polices -- a claim naming no identifier at
# all evades it -- and that is a bound on this guard, not a property of it.
#
# Every collected line must then match a declared exemption below or the test
# fails naming it. A new line about ``_bmad/`` therefore lands as an unexplained
# hit that someone must disposition, rather than as a silent pass. That is the
# point, and the friction is deliberate.
#
# Building it this way found six offenders where TD-1130's own enumeration
# named four: cwd_sentinel.sh's two FAIL messages both promise a three-marker
# expectation the code no longer tests. One of those two was also missed by an
# over-broad *phrasing* predicate tried first here (it carries no MUST, no
# conjunction word, no "all present"), which is this record's thesis landing
# inside its own instrument.
_MARKER_REFERENCE = re.compile(r"_bmad(?![A-Za-z0-9_-])|bmad_dir")

# Literals already known to be false under the corrected sentinel. An exemption
# cannot rescue a line carrying one of these: a line may hold a corrected clause
# and a stale claim at once, and matching the good half would exempt the bad.
# This list is a declared set of known offenders, not a guess at the class
# boundary -- collection above stays maximally broad and is what closes the
# class.
_SUPERSEDED_CLAIMS: tuple[str, ...] = (
    "test -d _ai-memory && test -d _bmad && test -d oversight",
    "3-marker sentinel",
    # The same mandate written through the variable that holds the path. It
    # carries no ``_bmad`` token, so before ``_MARKER_REFERENCE`` learned
    # ``bmad_dir`` it was collected nowhere; it is listed here as well because
    # collection alone is not disposition -- on a line that also matches an
    # exemption for this file, a collected-but-exempt stale mandate reads as
    # clean. Both brace spellings, since shell accepts either and a claim that
    # only catches one is a claim about punctuation.
    'test -d _ai-memory && test -d "${bmad_dir}" && test -d oversight',
    'test -d _ai-memory && test -d "$bmad_dir" && test -d oversight',
)

# Files the walk below must visit before any count taken over it means
# anything. MEASURED FROM THE WALK ITSELF at authoring time (2026-09-05),
# against ``_ai-memory/pov``: ``os.walk`` visits 542 files in a fresh checkout
# -- which is also what ``git archive`` and CI produce, and what ``git ls-tree
# -r`` reports for that path -- and 585 in a live worktree, where 34
# ``__pycache__`` entries are visited too (551 excluding them).
#
# It is a FLOOR, not an equality, and sits well below the smallest of those
# three deliberately. An equality would be a magic number: it fails on every
# ordinary file addition or removal, gets bumped without thought, and stops
# being read -- the failure mode this module already carries elsewhere. A floor
# only moves when the tree genuinely shrinks, so it can be left alone.
#
# What it exists to catch is NOT a mistaken or narrowed root, and NOT an
# unreadable subtree. Three other instruments hold those, each by a mechanism
# this one does not have. Measured at this SHA: narrow the root to any single
# subtree of the pov tree and the exemption-coverage check goes non-empty at
# all nine, while ``collected`` goes empty at the seven carrying no marker
# line. Make a subtree unreadable -- ``chmod 000`` on ``workflows/phases``,
# 101 files -- and ``_refuse`` raises PermissionError before any count is
# taken.
#
# 🔴 That last case is stated twice on purpose, because this floor is the
# obvious thing to credit for it and it cannot make the save. Swallow the walk
# error instead of raising it and the same chmod leaves visited at 441 --
# ABOVE this floor -- reporting collected=28, undeclared=0, unvisited=0. Clean,
# on every instrument including this one. A justification that says or implies
# the floor catches a subtree going unreadable is false, however carefully it
# is worded.
#
# The niche that is left is narrow, and worth stating exactly. A loss reaches
# this floor only if it is SILENT (no OSError, so ``_refuse`` never fires),
# LARGER than the floor's 142-file slack (542 - 400), and sparing all 8 files
# the exemption set names, so the coverage check stays empty while a marker
# line still stands and keeps ``collected`` non-empty. Measured: delete 286
# files from ``workflows/``, keeping the one exemption file it holds, and the
# walk reports visited=256, collected=28, undeclared=0, unvisited=0 -- every
# other instrument clean, this one refusing. That is the whole of it.
#
# Two corollaries, both previously written down wrongly. The floor is bounded
# below by its slack, so no silent collapse of 142 files or fewer reaches it:
# ``skills``, the second-largest subtree at 132 files, could vanish whole and
# leave this satisfied. And the wording this replaces said the largest subtree
# holds 287 files "so losing any one of them already lands below this" -- only
# ``workflows`` does, at 255 remaining; without ``skills`` the walk still
# visits 410 files, without ``constraints`` 450, and every other subtree is
# smaller again.
_POV_TREE_FILE_FLOOR = 400

# (path relative to PRODUCT_ROOT, distinctive fragment of the line, why it is fine)
#
# Default-deny: a line is exempt only by appearing here. Reasons are recorded so
# a later reader can re-judge the disposition instead of inheriting it.
_THREE_MARKER_EXEMPTIONS: tuple[tuple[str, str, str], ...] = (
    # -- Co-presence stated as the sentinel's *definition*, with the BMAD test
    #    separated in the same line or the one immediately following it.
    (
        f"{POV_TREE}/skills/aim-agent-dispatch/SKILL.md",
        "co-presence of",
        "defines the sentinel, then separates the BMAD test on the same line",
    ),
    (
        f"{POV_TREE}/skills/aim-agent-lifecycle/SKILL.md",
        "co-presence of",
        "defines the sentinel, then separates the BMAD test on the same line",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/claude-native/workflow.md",
        "co-presence of all three sentinel directories",
        "definition; reconciled in the next paragraph, which is exempted below",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "a single-marker check is",
        "definition; reconciled in the next paragraph, which is exempted below",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/tmux-dispatch/steps"
        "/step-02-launch-pane.md",
        "a single-marker check is",
        "definition; reconciled in the next paragraph, which is exempted below",
    ),
    # -- States the corrected semantics: BMAD's absence is not drift.
    (
        f"{POV_TREE}/skills/aim-agent-dispatch/SKILL.md",
        "separately for BMAD presence",
        "states the corrected two-marker drift test",
    ),
    (
        f"{POV_TREE}/skills/aim-agent-lifecycle/SKILL.md",
        "separately for BMAD presence",
        "states the corrected two-marker drift test",
    ),
    (
        f"{POV_TREE}/workflows/cycles/agent-dispatch/steps-c/step-02-spawn-agent.md",
        "separately for BMAD presence",
        "states the corrected two-marker drift test",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "or present except _bmad/ (degraded)",
        "documents the degraded exit code, which is the corrected behaviour",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "is shipped by BMAD, not by AI-Memory",
        "states why absence is a normal state rather than drift",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/claude-native/workflow.md",
        "is shipped by BMAD, not by AI-Memory",
        "states why absence is a normal state rather than drift",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "is shipped by BMAD, not by AI-Memory",
        "states why absence is a normal state rather than drift",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/tmux-dispatch/steps"
        "/step-02-launch-pane.md",
        "is shipped by BMAD, not by AI-Memory",
        "states why absence is a normal state rather than drift",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "The sentinel returns 0 when",
        "states the corrected return contract",
    ),
    # -- Corrected success criteria and gate messages: they name _bmad/ as
    #    optional, which is what the sentinel now implements.
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "_bmad/ is BMAD's own and is not required",
        "failure message names only the markers the gate actually tests",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "_bmad/ is not required here",
        "failure message names only the markers the gate actually tests",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "present or reported unavailable",
        "success criterion admits the degraded pass the sentinel now returns",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/tmux-dispatch/steps"
        "/step-02-launch-pane.md",
        "present or reported unavailable",
        "success criterion admits the degraded pass the sentinel now returns",
    ),
    (
        f"{POV_TREE}/skills/aim-parzival-team-builder/SKILL.md",
        "_bmad/ optional",
        "template comment marks the marker optional rather than mandatory",
    ),
    # -- Mechanical: names the directory, asserts nothing about the sentinel.
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "Directory to test for workspace-root markers",
        "usage text listing what the sentinel inspects, not what it aborts on",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        'bmad_dir="${required_root}/_bmad"',
        "variable assignment, absolute branch",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        'bmad_dir="_bmad"',
        "variable assignment, CWD-relative branch",
    ),
    # -- Newly collected once the predicate learned the ``bmad_dir`` variable.
    #    Fragments are deliberately long here: the exemption predicate licenses
    #    a file plus a fragment, not a line, so a short one would rescue text
    #    appended beside it.
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "local ai_memory_dir bmad_dir",
        "local variable declaration",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        'if test -d "$bmad_dir"',
        "the separated BMAD-presence test itself, which is the corrected shape",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "dispatch that does not need BMAD is unaffected",
        "the degraded message the sentinel emits, which is the corrected behaviour",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/scripts/lib/cwd_sentinel.sh",
        "(no ${bmad_dir}); workspace root is correct",
        "the loose variant of the same degraded message",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "if ! test -d _bmad; then",
        "the separated BMAD-presence gate itself",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "DEGRADED: dependency 'bmad' is unavailable",
        "the degraded message the gate emits",
    ),
    (
        f"{POV_TREE}/skills/aim-model-dispatch/workflows/bmad-dispatch/steps"
        "/step-02-launch-and-activate.md",
        "Reads `_bmad/bmm/config.yaml`",
        "names a BMAD config path, unrelated to the sentinel",
    ),
)


def _undeclared_marker_references(
    root: Path | None = None,
) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]], int]:
    """Every line under ``root`` naming the BMAD directory, the undeclared subset, files visited.

    "Naming" is the lexical test above: the ``_bmad`` marker at a token
    boundary, or the ``bmad_dir`` variable that holds the same path.

    Both halves are returned because the undeclared half cannot be asserted
    against on its own: an empty list is what a clean tree returns and also
    what a walk that collected nothing returns, and the two are the states this
    guard exists to tell apart.

    The third element -- the number of files the walk actually visited -- is
    returned for the same reason, one layer down. ``collected`` being non-empty
    proves the walk reached *something*, not how much of it: a walk narrowed to
    a single readable subtree still collects lines.

    What it does not do is hide, and the claim here that it does was measured
    false. Narrow the root to any one subtree of the pov tree at this SHA and
    the exemption-coverage check goes non-empty -- at all nine of them -- while
    ``collected`` goes empty at seven, so a narrowed root is refused by the
    assertions that name files, not by a count. The count is asserted at the
    shipped call site against ``_POV_TREE_FILE_FLOOR`` for the narrower case
    those two cannot see: a loss that is silent, larger than that floor's
    slack, and sparing every file they name. An unreadable subtree is not that
    case -- ``_refuse`` below raises on it first, and the floor measurably does
    not fire on it. The derivation lives on that constant.

    ``root`` defaults to the pov tree and exists so a fixture can drive this
    enumerator over a seeded tree rather than a second copy of it. The shipped
    call site passes nothing; widening the scope is not what the parameter is
    for.
    """
    collected: list[tuple[str, int, str]] = []
    undeclared: list[tuple[str, int, str]] = []
    visited = 0
    root = PRODUCT_ROOT / POV_TREE if root is None else Path(root)

    def _refuse(error: OSError) -> None:
        """A walk that cannot read part of its tree has not read the tree.

        ``os.walk`` swallows errors by default, so an unreadable directory
        removes its whole subtree from the enumeration and returns the same
        clean result a clean tree returns. Raising is what makes the two
        distinguishable.
        """
        raise error

    # ``followlinks=True`` because ``onerror`` cannot report what ``os.walk``
    # never attempts. A symlinked subtree is classified as a directory and then
    # not descended into, which raises nothing: the subtree leaves the
    # enumeration and the walk returns the clean result a clean tree returns.
    # That is the same silence ``_refuse`` exists to break, one level up, and the
    # handler is structurally unable to see it. Latent at this SHA -- the pov
    # tree carries zero symlinks, in the worktree and in the committed tree
    # alike -- so this closes a coverage claim rather than a live hole.
    for base, _dirs, names in os.walk(root, onerror=_refuse, followlinks=True):
        for name in sorted(names):
            visited += 1
            path = Path(base) / name
            # Deliberately not wrapped in ``except OSError: continue``. That
            # skipped an unreadable file silently, which is the same defect as
            # the swallowed walk error above one level down: the offender the
            # guard exists to find is exactly the file it would skip.
            text = path.read_text(encoding="utf-8", errors="ignore")
            rel = str(
                path.relative_to(PRODUCT_ROOT)
                if path.is_relative_to(PRODUCT_ROOT)
                else path.relative_to(root)
            )
            for number, line in enumerate(text.splitlines(), 1):
                if not _MARKER_REFERENCE.search(line):
                    continue
                collected.append((rel, number, line.strip()))
                if any(claim in line for claim in _SUPERSEDED_CLAIMS):
                    undeclared.append((rel, number, line.strip()))
                    continue
                if any(
                    rel == exempt_path and fragment in line
                    for exempt_path, fragment, _reason in _THREE_MARKER_EXEMPTIONS
                ):
                    continue
                undeclared.append((rel, number, line.strip()))
    return collected, undeclared, visited


@pytest.mark.process
def test_no_shipped_artifact_mandates_the_superseded_three_marker_conjunction() -> None:
    """A paragraph that contradicts its own command is worse than neither fixed.

    Sites had their prose updated to say a missing ``_bmad/`` alone is BMAD's
    absence rather than CWD drift, while a success criterion or failure message
    directly beside it still promised that all three markers must be present --
    a claim that is false in exactly the case the prose says to continue
    through. An operator following the criterion gets the behaviour the
    paragraph tells them is wrong, and this is the check a dispatcher runs
    before every spawn.

    Enumerated broadly and dispositioned against a declared exemption set
    rather than pattern-matched, for the reasons recorded above the set.
    """
    collected, undeclared, visited = _undeclared_marker_references()
    assert collected, (
        "the enumerator collected no lines at all. An empty undeclared list is "
        "what a clean tree returns and also what a collapsed walk returns; "
        "this assertion is what distinguishes them"
    )
    assert visited >= _POV_TREE_FILE_FLOOR, (
        f"the walk visited {visited} files, below the floor of "
        f"{_POV_TREE_FILE_FLOOR}. Every count below this line is taken over "
        "that walk, so a narrowed one makes them measurements of a tree that "
        "was never read -- and a narrowed walk reads here as a clean tree. "
        "Either the pov tree genuinely shrank by hundreds of files, in which "
        "case re-measure the floor from the walk and say so, or the walk did "
        "not reach it"
    )
    unvisited = sorted(
        {exempt_path for exempt_path, _fragment, _reason in _THREE_MARKER_EXEMPTIONS}
        - {path for path, _number, _line in collected}
    )
    assert unvisited == [], (
        "the walk never reached files that declared exemptions name, so those "
        "exemptions were tested against nothing and a narrowed enumeration "
        "reads here as a clean tree: " + "; ".join(unvisited)
    )
    assert undeclared == [], (
        "pov-tree lines name the _bmad/ marker without a declared disposition. "
        "Each is either a surviving three-marker claim to fix, or a legitimate "
        "reference to add to _THREE_MARKER_EXEMPTIONS with a stated reason: "
        + "; ".join(f"{path}:{number}: {line}" for path, number, line in undeclared)
    )


@pytest.mark.process
def test_the_exemption_set_is_live_and_none_of_it_is_stale() -> None:
    """An exemption that matches nothing is a claim about a line that has moved.

    The exemption set is the deliverable, so it needs its own guard: a stale
    entry silently widens the hole it was written to narrow, and reads as
    coverage while covering nothing.
    """
    dead = []
    for exempt_path, fragment, _reason in _THREE_MARKER_EXEMPTIONS:
        target = PRODUCT_ROOT / exempt_path
        if not target.exists():
            dead.append(f"{exempt_path} (file missing) :: {fragment}")
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        if not any(
            fragment in line and _MARKER_REFERENCE.search(line)
            for line in text.splitlines()
        ):
            dead.append(f"{exempt_path} :: {fragment}")
    assert dead == [], (
        "declared exemptions match no _bmad/ line in their file and are stale: "
        + "; ".join(dead)
    )


@pytest.mark.process
def test_the_marker_enumerator_can_actually_fail(tmp_path: Path) -> None:
    """Positive control: a guard never observed refusing is not a gate.

    Drives the REAL enumerator over a seeded tree instead of re-deriving the
    predicate here. A control that re-implements what it is testing proves only
    that a regex it has just typed works; if the walk or the encoding handling
    broke, a second implementation agreeing with itself would still pass.

    🔴 **Three probes, because the enumerator has three exits and one probe
    only ever reached the first.** A collected line leaves by the superseded
    branch, by the exemption branch, or by falling through to ``undeclared``.
    The original single probe carried ``_SUPERSEDED_CLAIMS[0]`` verbatim, so it
    left by the superseded branch and ``continue``d *before* the exemption
    ``any()`` was ever evaluated. The disposition logic was therefore executed
    by no test at all: replacing the whole exemption predicate with
    ``if True: continue`` -- the gate wholly dead, every offender in the tree
    waved through -- left this file green, and this docstring previously
    claimed that exact coverage in as many words.

    Probes B and C are the ones that hold it. Neither may carry a superseded
    literal, or it would short-circuit at the same branch and re-create the
    hole this exists to close.

    🔴 **Probe A is seeded at an EXEMPT path, which is the other half of the
    same finding.** Seeded at a non-exempt one it discriminated nothing: there
    the superseded branch and the fall-through both append to ``undeclared``,
    so the assertion passed either way. Deleting the superseded branch outright
    left this file green, and so did corrupting any one of the four
    ``_SUPERSEDED_CLAIMS`` entries -- all four, individually. At an exempt path
    whose own declared fragment matches the seeded line, the exemption would
    ``continue`` and the line would escape, so the superseded branch must take
    precedence over it or this fails. One seeded line per entry, because a
    probe carrying one entry observes one entry and leaves the rest unwatched.
    """

    def _licensed_by_fragment(path: str, line: str) -> bool:
        """True if a declared exemption licenses *line* at *path*.

        The real predicate, re-derived from the set rather than restated, so
        the probes below cannot drift away from what the enumerator does.
        """
        return any(
            path == exempt and fragment in line
            for exempt, fragment, _reason in _THREE_MARKER_EXEMPTIONS
        )

    # -- Probe A: the superseded literals, at an EXEMPT path, on lines the
    #    path's own declared fragment matches. Exits at the superseded branch,
    #    and is the only probe covering it. Both halves are load-bearing: the
    #    exemption is what that branch must take precedence over, and one line
    #    per entry is what puts every entry under observation.
    #
    #    Path and fragment are derived from the exemption set rather than
    #    written out, so they cannot name a file the set has stopped exempting.
    #    A path distinct from probe C's is required -- the two are separate
    #    files -- and probe C takes the first entry, so this takes the first
    #    entry naming a different file.
    probe_a_path, probe_a_fragment = next(
        (path, fragment)
        for path, fragment, _reason in _THREE_MARKER_EXEMPTIONS
        if path != _THREE_MARKER_EXEMPTIONS[0][0]
    )
    #    The claim text is copied literally, NOT generated from
    #    ``_SUPERSEDED_CLAIMS``. A probe derived from the list under test moves
    #    with it: a typo in an entry corrupts the probe in the same stroke, the
    #    two still match, and the control stays green while the guard has
    #    stopped recognising that offender in the real tree. The duplication is
    #    the point, and the assertion below is what keeps the two copies in
    #    step -- it fails when an entry is added or reworded, which is the
    #    review this control exists to force.
    probe_a_claims = (
        "test -d _ai-memory && test -d _bmad && test -d oversight",
        "3-marker sentinel",
        'test -d _ai-memory && test -d "${bmad_dir}" && test -d oversight',
        'test -d _ai-memory && test -d "$bmad_dir" && test -d oversight',
    )
    assert sorted(probe_a_claims) == sorted(_SUPERSEDED_CLAIMS), (
        "the seeded claims and _SUPERSEDED_CLAIMS have diverged, so an entry is "
        "either unobserved by this control or has been reworded under it. Copy "
        "the entry here as well rather than generating these from the list: "
        f"{sorted(set(_SUPERSEDED_CLAIMS) ^ set(probe_a_claims))}"
    )
    probe_a_lines = [
        f"{probe_a_fragment} the _bmad marker, and still mandates {claim}"
        for claim in probe_a_claims
    ]
    for probe_a in probe_a_lines:
        assert _MARKER_REFERENCE.search(probe_a), (
            "every probe A line must be collected before it can be "
            f"dispositioned: {probe_a!r}"
        )
        assert _licensed_by_fragment(probe_a_path, probe_a), (
            "every probe A line must be licensed by a declared exemption at "
            "its own path, or the superseded branch has nothing to take "
            f"precedence over and stops being observed: {probe_a!r}"
        )
    seeded_a = tmp_path / probe_a_path
    seeded_a.parent.mkdir(parents=True, exist_ok=True)
    seeded_a.write_text("\n".join(probe_a_lines) + "\n", encoding="utf-8")

    # -- Probe B: marker line, NO superseded literal, NON-EXEMPT path. Reaches
    #    the exemption ``any()``, matches nothing, falls through.
    probe_b = "the _bmad marker is asserted here with no disposition on file"
    (tmp_path / "seeded_undisposed.md").write_text(probe_b + "\n", encoding="utf-8")

    # -- Probe C: marker line at an EXEMPT path that the exemption's fragment
    #    does NOT cover. Reaches the ``any()``, matches the path but not the
    #    fragment, falls through. This is the probe that distinguishes a
    #    per-line exemption from a per-file one -- a file is licensed for a
    #    fragment, never wholesale.
    #
    #    The path is derived from the exemption set rather than written out, so
    #    it cannot name a file the set has stopped exempting.
    exempt_path = _THREE_MARKER_EXEMPTIONS[0][0]
    probe_c = "an unrelated _bmad sentence appended beside a licensed line"
    assert not _licensed_by_fragment(exempt_path, probe_c), (
        "probe C must not contain any fragment declared for its own path, or "
        f"it tests the exemption matching rather than escaping it: {exempt_path}"
    )
    seeded_c = tmp_path / exempt_path
    seeded_c.parent.mkdir(parents=True, exist_ok=True)
    seeded_c.write_text(probe_c + "\n", encoding="utf-8")

    collected, undeclared, visited = _undeclared_marker_references(tmp_path)

    # Whole records, not just the line text. Dropping the path and the line
    # number from these assertions cost real coverage: with only the text
    # compared, renumbering every reported line -- 0-based instead of 1-based --
    # left this green, and a report is a location or it is not actionable.
    expected = sorted(
        [(probe_a_path, number, line) for number, line in enumerate(probe_a_lines, 1)]
        + [("seeded_undisposed.md", 1, probe_b), (exempt_path, 1, probe_c)]
    )
    assert sorted(undeclared) == expected, (
        "the real enumerator did not flag every seeded probe at its own path "
        "and line, so either an exit of the disposition logic is executed by "
        "nothing, or the report cannot be acted on: "
        f"{sorted(undeclared)} != {expected}"
    )
    assert sorted(collected) == expected, (
        "the enumerator collected lines this test did not seed, so the "
        "collection half and the disposition half are no longer measuring the "
        f"same set of lines: {sorted(collected)}"
    )

    # Probe C's discriminating property, asserted on what the enumerator
    # actually reported rather than on the variable that seeded it. What makes
    # probe C different from probe B is that its path IS licensed and its line
    # is not: a file is licensed for a fragment, never wholesale. Retarget it
    # to a non-exempt path and it becomes a second probe B -- which was green,
    # because both fall through to the same exit. A repo-local TMPDIR breaks
    # the same property for real: the seeded tree lands under PRODUCT_ROOT and
    # the enumerator reports paths the exemption set does not name. Measured,
    # the record assertion above reaches that case first; both refuse it.
    licensed_but_unmatched = [
        (path, line)
        for path, _number, line in undeclared
        if any(path == exempt for exempt, _f, _r in _THREE_MARKER_EXEMPTIONS)
        and not _licensed_by_fragment(path, line)
    ]
    assert licensed_but_unmatched == [(exempt_path, probe_c)], (
        "no seeded line reached the enumerator at a licensed path that its "
        "licence does not cover, so the per-line half of the exemption "
        f"predicate is observed by nothing: {licensed_but_unmatched}"
    )
    assert visited == 3, (
        f"the walk visited {visited} files from a three-file seeded tree, so "
        "the count the shipped floor is asserted against is not a file count"
    )


@pytest.mark.process
def test_the_marker_enumerator_collects_only_marker_lines(tmp_path: Path) -> None:
    """Negative half of the control: it flags the marker line, not every line.

    Without this, the control above is satisfied by an enumerator that reports
    everything it walks.
    """
    (tmp_path / "seeded_clean.md").write_text(
        "MUST run the workspace-root sentinel before every spawn.\n",
        encoding="utf-8",
    )

    assert _undeclared_marker_references(tmp_path) == ([], [], 1)


@pytest.mark.process
def test_agent_lifecycle_gates_persona_activation_on_bmad_presence() -> None:
    """Generic spawn and monitoring survive BMAD's absence; activation is refused (AC-1).

    ``cap:agent-lifecycle`` is ``cap:agent-dispatch``'s structural twin: same
    dependency, same two-clause shape, same gate primitive. It declares that it
    spawns and monitors generic agents normally, and that it reports BMAD
    two-phase persona activation as unavailable instead of sending an
    activation command into a pane that cannot resolve it.

    Both clauses live in this skill's own Step 1 gate, so both are asserted
    here rather than one of them being left to read as covered.

    Position is what makes the second clause real. The gate is read before the
    ``tmux send-keys`` that puts a live ``/bmad-<role>`` command into a pane; a
    gate read after it is a gate read too late to stop the activation it exists
    to prevent, and the pane is already spent.

    Anchored to the gate's own line rather than a byte window, and asserted at
    every gate site rather than one chosen by position, so a gate added later
    that omits a clause is caught. Both departures follow the sibling fixture
    for ``cap:agent-dispatch``.
    """
    skill = PRODUCT_ROOT / POV_TREE / "skills/aim-agent-lifecycle/SKILL.md"
    text = skill.read_text(encoding="utf-8")

    gates = [m.start() for m in re.finditer(re.escape("test -d _bmad"), text)]
    activation = text.find("/bmad-")
    assert gates, f"{skill.name} spawns BMAD agents with no BMAD-presence gate"
    assert activation != -1, (
        f"{skill.name} no longer sends a /bmad-* activation command into a pane "
        "— re-derive this test"
    )
    assert min(gates) < activation, (
        "the BMAD-presence gate must be read before the /bmad-* activation "
        "command: a command sent first lands in a pane that cannot resolve it"
    )

    for gate in gates:
        line = text[text.rfind("\n", 0, gate) + 1 : text.find("\n", gate)]
        assert "unavailable" in line, (
            "every BMAD-presence gate must report the dependency as "
            f"unavailable: {line!r}"
        )
        assert "generic dispatch" in line, (
            "every BMAD-presence gate must state that generic spawn and "
            "monitoring continue, or the absent path has no declared "
            f"outcome: {line!r}"
        )
        assert "skip BMAD persona activation" in line, (
            "every BMAD-presence gate must state that persona activation is "
            "skipped. Reporting the dependency without refusing the activation "
            f"is the silent no-op the declaration exists to deny: {line!r}"
        )
        assert "DEPENDENCIES.md" in line, (
            "every BMAD-presence gate must name what would provide the missing "
            "dependency, not merely that it is missing. AC-1 requires the "
            f"remedy half and a gate naming only the dependency fails it: {line!r}"
        )


@pytest.mark.process
def test_cycle_agent_dispatch_gates_persona_activation_on_bmad_presence() -> None:
    """The dispatch cycle degrades to a generic spawn and says what would fix it (AC-1).

    ``cap:cycle-agent-dispatch`` declares that it runs the generic spawn and
    instruction steps and reports the BMAD activation step as unavailable
    instead of instructing an activation that cannot resolve. Its declaration
    lives on the cycle's ``workflow.md``; the message an operator actually reads
    lives one file down, in the spawn step's own sentinel line, so that line is
    what this asserts.

    Position is what makes the second clause real: the gate is read before the
    step instructs a ``bmad-<role>`` persona load. A gate read after it is a
    gate read too late to stop the activation it exists to prevent.

    The fourth clause is the one this capability shipped without. Naming the
    missing dependency without naming what would provide it leaves an operator
    on a BMAD-less machine told what is broken and not what to do, which is the
    half of AC-1 a message can omit while still looking complete.

    The gate's own imperative is asserted, and its termination is not. The
    sibling fixtures assert ``exit 1`` because their gate is shell; this one is
    a prose instruction, and more importantly ``workflow.md``'s declaration for
    this capability is *"Runs the generic spawn and instruction steps, and
    reports the BMAD activation step as unavailable"* -- fall-through is the
    declared behaviour here, so asserting termination would assert the opposite
    of what this capability declares. What can degrade silently is the
    imperative itself, which is what is asserted instead.
    """
    step = (
        PRODUCT_ROOT
        / POV_TREE
        / "workflows/cycles/agent-dispatch/steps-c/step-02-spawn-agent.md"
    )
    text = step.read_text(encoding="utf-8")

    gates = [m.start() for m in re.finditer(re.escape("test -d _bmad"), text)]
    activation = text.find("bmad-<role>")
    assert gates, f"{step.name} spawns BMAD agents with no BMAD-presence gate"
    assert activation != -1, (
        f"{step.name} no longer instructs a bmad-<role> persona load — "
        "re-derive this test"
    )
    assert min(gates) < activation, (
        "the BMAD-presence gate must be read before the bmad-<role> persona "
        "load: an activation instructed first cannot resolve"
    )

    for gate in gates:
        line = text[text.rfind("\n", 0, gate) + 1 : text.find("\n", gate)]
        assert "MUST run" in line, (
            "the gate must be mandatory. Without this the three clauses below "
            "are asserted on a line that no longer requires anything: a "
            "downgrade to MAY passes, and so does a MUST NOT, which inverts "
            f"the gate while satisfying every other assertion here: {line!r}"
        )
        assert "unavailable" in line, (
            "every BMAD-presence gate must report the dependency as "
            f"unavailable: {line!r}"
        )
        assert "without a BMAD persona" in line, (
            "every BMAD-presence gate must state that the spawn still happens "
            "without the persona, or the absent path has no declared "
            f"outcome: {line!r}"
        )
        assert "DEPENDENCIES.md" in line, (
            "every BMAD-presence gate must name what would provide the missing "
            "dependency, not merely that it is missing. AC-1 requires the "
            f"remedy half and a gate naming only the dependency fails it: {line!r}"
        )
