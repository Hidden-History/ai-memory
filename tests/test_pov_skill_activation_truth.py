"""Content invariants for the two POV dispatch skills.

These assert against repo-resident SKILL.md files only, so they run everywhere.
That is deliberate: the repo's .claude/skills/ ships 22 aim-* skills and ZERO
bmad-*, so any check requiring live BMAD resolution would skip in CI and report
green while asserting nothing. The live-resolution counterpart lives in
check_bmad_commands.sh --check-deprecated, which graceful-degrades by design.

Covers:
  TD-911 -- the slash form is REQUIRED, and the retired "bare /bmad-* activates
            the lead" theory must not return. A /bmad-* activation failure means
            CWD drift (PM #415 measured this; the theory was retired).
  TD-971 -- no deprecated BMAD shim may be referenced by the dispatch tables.
  TD-890 defect 4 -- Anthropic models are dispatched by TIER ALIAS, never a
            pinned ID (which has rotted twice). The non-Anthropic verbatim
            example must survive so the rule's exception stays illustrated.

Scope/blindness, stated: SKILL.md only. These do not read scripts/, workflows/,
templates/ or references/ in either skill directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_POV = Path(__file__).resolve().parent.parent / "_ai-memory/pov/skills"
DISPATCH = _POV / "aim-agent-dispatch/SKILL.md"
TEAM_BUILDER = _POV / "aim-parzival-team-builder/SKILL.md"

# Shims confirmed against their own frontmatter. A body mention of the word
# "deprecation" is prose, not a shim marker -- /bmad-create-story says
# "Performance improvements or deprecations" and is NOT a shim.
DEPRECATED_SHIMS = (
    "/bmad-create-prd",
    "/bmad-validate-prd",
    "/bmad-edit-prd",
    "/bmad-create-architecture",
)

# The theory PM #415 measured as false and retired.
RETIRED_THEORY = "activates the lead, not the persona"


@pytest.fixture(scope="module")
def dispatch_text() -> str:
    assert DISPATCH.exists(), f"missing: {DISPATCH}"
    return DISPATCH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def team_builder_text() -> str:
    assert TEAM_BUILDER.exists(), f"missing: {TEAM_BUILDER}"
    return TEAM_BUILDER.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# TD-911 -- activation truth
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["dispatch", "team_builder"])
def test_retired_activation_theory_absent(name, request) -> None:
    text = request.getfixturevalue(f"{name}_text")
    assert RETIRED_THEORY not in text, (
        f"{name}: the retired bare-name activation theory has returned. "
        "PM #415 measured the slash as REQUIRED; an activation failure means "
        "CWD drift, not an unavailable skill."
    )


def test_dispatch_teaches_slash_form(dispatch_text: str) -> None:
    assert "the leading `/` is required" in dispatch_text.lower()
    assert "Use the Skill tool to load /bmad-agent-dev" in dispatch_text


def test_team_builder_teaches_slash_form(team_builder_text: str) -> None:
    assert "The leading `/` is required." in team_builder_text
    assert "Use the Skill tool to load /bmad-agent-dev" in team_builder_text


def test_team_builder_does_not_name_a_nonexistent_skill(
    team_builder_text: str,
) -> None:
    """`bmad-dev` does not exist; the real persona skill is `bmad-agent-dev`."""
    assert "load bmad-dev" not in team_builder_text
    assert "`bmad-dev`" not in team_builder_text


def test_team_builder_allows_grep_and_bash(team_builder_text: str) -> None:
    """Frontmatter must not under-declare the tools the skill actually uses."""
    assert "allowed-tools: Read, Grep, Bash" in team_builder_text


def test_dual_review_pair_exception_documented(team_builder_text: str) -> None:
    assert "dual-review pair (2) is sanctioned" in team_builder_text


# --------------------------------------------------------------------------
# TD-971 -- no deprecated shim referenced
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shim", DEPRECATED_SHIMS)
def test_no_deprecated_shim_dispatched(dispatch_text: str, shim: str) -> None:
    """No TABLE ROW may dispatch a shim.

    Scoped to markdown table rows on purpose. A file-wide match would also fire
    on prose that names a shim in order to explain why it is forbidden -- which
    would make documenting the rule impossible. The invariant is about what gets
    dispatched, not about which names may be written down.
    """
    rows = [ln for ln in dispatch_text.splitlines() if ln.lstrip().startswith("|")]
    offenders = [ln for ln in rows if f"`{shim}`" in ln]
    assert not offenders, (
        f"{shim} is a deprecated back-compat shim and must not be dispatched. "
        f"Point the row at the successor named in the shim's description. "
        f"Offending row(s): {offenders}"
    )


def test_successor_commands_present(dispatch_text: str) -> None:
    assert "`/bmad-prd`" in dispatch_text
    assert "`/bmad-architecture`" in dispatch_text


# --------------------------------------------------------------------------
# TD-890 defect 4 -- tier alias, not pinned ID
# --------------------------------------------------------------------------


def test_no_pinned_anthropic_model_id(team_builder_text: str) -> None:
    assert "claude-sonnet-4-6" not in team_builder_text, (
        "Anthropic models are dispatched by tier alias (opus/sonnet/haiku). "
        "A pinned ID has rotted twice, once running both Opus reviewers two "
        "generations behind on a gate."
    )


def test_non_anthropic_verbatim_example_retained(team_builder_text: str) -> None:
    """The exception must stay illustrated: non-Anthropic IDs ARE verbatim."""
    assert "glm-5.1:cloud" in team_builder_text
