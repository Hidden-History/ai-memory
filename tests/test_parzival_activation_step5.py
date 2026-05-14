"""
Regression tests for parzival.md activation step 5 decision logic (BUG-291).

T5-T8 verify step 5 text content and conditional branching directives.
T1-T4 (init-sanctum.py file-level idempotency) are covered by
aim-agent-sanctum-init/tests/test_init_sanctum_idempotency.py (Phase D).

Test approach: static analysis of step 5 instruction text extracted from
parzival.md. Since step 5 is natural-language agent directives (not executable
code), correctness is verified by asserting required phrases are present in the
extracted step text.
"""

import re
from pathlib import Path

import pytest

PARZIVAL_MD = (
    Path(__file__).parent.parent / "_ai-memory" / "pov" / "agents" / "parzival.md"
)

EIGHT_REQUIRED_FILES = [
    "CREED.md",
    "PERSONA.md",
    "INDEX.md",
    "BOND.md",
    "LORE.md",
    "MEMORY.md",
    "CAPABILITIES.md",
    "PULSE.md",
]

BOND_SCAFFOLD_MARKER_PREFIX = "_Filled during First Breath"
SANCTUM_INIT_SKILL = "aim-agent-sanctum-init"
FIRST_BREATH_WORKFLOW = "first-breath/workflow.md"
FAILURE_MODE_INDICATOR = "W-04 self-heal"


def _extract_step5(content: str) -> str:
    """Extract the full <step n="5">...</step> block from parzival.md content."""
    match = re.search(r'<step n="5">(.*?)</step>', content, re.DOTALL)
    assert (
        match is not None
    ), 'Could not find <step n="5">...</step> block in parzival.md'
    return match.group(1)


@pytest.fixture(scope="module")
def step5_text():
    assert PARZIVAL_MD.exists(), f"parzival.md not found at {PARZIVAL_MD}"
    content = PARZIVAL_MD.read_text(encoding="utf-8")
    return _extract_step5(content)


def test_T5_step5_directs_sanctum_init_when_files_missing(step5_text):
    """T5 (BUG-291): step 5 contains conditional invocation of aim-agent-sanctum-init
    when ≥1 of 8 required sanctum files is missing.

    Verifies:
    - All 8 required file names listed in step 5
    - aim-agent-sanctum-init skill is referenced for repair
    - Condition is 'if any missing' (conditional, not unconditional)
    - Detection directive appears before repair invocation (check-then-invoke ordering)
    """
    # All 8 required files must be enumerated
    for filename in EIGHT_REQUIRED_FILES:
        assert (
            filename in step5_text
        ), f"Required sanctum file '{filename}' not listed in step 5"

    # Conditional invocation: must say "if any missing" or equivalent before the skill
    assert (
        "any missing" in step5_text.lower() or "if any" in step5_text.lower()
    ), "step 5 must conditionally invoke sanctum-init only when files are missing"

    # Repair skill must be named
    assert (
        SANCTUM_INIT_SKILL in step5_text
    ), f"step 5 must reference '{SANCTUM_INIT_SKILL}' for repair invocation"

    # Idempotency must be stated (file-level idempotency is a PLAN-027 W-04 invariant)
    assert (
        "idempotent" in step5_text.lower()
    ), "step 5 must state that aim-agent-sanctum-init is idempotent"

    # Detection must precede repair invocation (check-then-invoke ordering)
    missing_check_idx = step5_text.lower().index("any missing")
    sanctum_init_idx = step5_text.index(SANCTUM_INIT_SKILL)
    assert (
        missing_check_idx < sanctum_init_idx
    ), "step 5 must direct check-then-invoke order: detect missing files before invoking repair"


def test_T6_step5_invokes_first_breath_when_bond_scaffold_marker_present(step5_text):
    """T6 (BUG-291): step 5 directs invocation of the First Breath workflow when
    BOND.md contains the scaffold marker prefix `_Filled during First Breath`.

    Verifies:
    - Marker prefix `_Filled during First Breath` is used (matches both ## Owner and
      ## Working Style sections in BOND-template.md)
    - First Breath workflow path is referenced
    - Invocation is conditional on marker presence (if-window anchored between marker
      and workflow path, not any prior `if` in step 5)
    """
    # Scaffold marker prefix must be present in step 5 text
    assert BOND_SCAFFOLD_MARKER_PREFIX in step5_text, (
        f"step 5 must check for the scaffold marker prefix '{BOND_SCAFFOLD_MARKER_PREFIX}' "
        f"— matches both ## Owner and ## Working Style markers in BOND-template.md"
    )

    # First Breath workflow must be referenced
    assert (
        FIRST_BREATH_WORKFLOW in step5_text
    ), f"step 5 must invoke '{FIRST_BREATH_WORKFLOW}' when scaffold marker is found"

    # Conditional check anchored between marker and workflow path
    # (avoids false-positive match on earlier `if` clauses in step 5)
    first_breath_idx = step5_text.index(FIRST_BREATH_WORKFLOW)
    marker_idx = step5_text.index(BOND_SCAFFOLD_MARKER_PREFIX)
    window = step5_text[marker_idx:first_breath_idx].lower()
    assert re.search(
        r"\bif\b", window
    ), "step 5 must conditionally invoke First Breath based on scaffold marker presence"


def test_T7_step5_first_breath_invocation_is_conditional(step5_text):
    """T7 (BUG-291): step 5 First Breath invocation is conditional — not unconditional.

    Verifies:
    - No unconditional invocation pattern (no 'always invoke first-breath' etc.)
    - Scaffold marker check appears before the First Breath workflow path reference
      (structural ordering: detect marker → conditional → invoke)
    """
    # Scaffold marker must be referenced (prerequisite — T6 must pass first)
    assert (
        BOND_SCAFFOLD_MARKER_PREFIX in step5_text
    ), "Prerequisite: scaffold marker prefix must be in step 5 (T6 must pass first)"

    # Step must NOT unconditionally invoke first-breath
    unconditional_patterns = [
        "always invoke.*first.breath",
        "unconditionally.*first.breath",
        "invoke.*first.breath.*always",
    ]
    for pattern in unconditional_patterns:
        assert not re.search(
            pattern, step5_text, re.IGNORECASE
        ), f"step 5 must NOT unconditionally invoke First Breath (found pattern: {pattern!r})"

    # Scaffold marker check must appear before the First Breath workflow path reference
    marker_idx = step5_text.index(BOND_SCAFFOLD_MARKER_PREFIX)
    first_breath_idx = step5_text.index(FIRST_BREATH_WORKFLOW)
    assert (
        marker_idx < first_breath_idx
    ), "step 5 must check for the scaffold marker before referencing the First Breath workflow"


def test_T8_step5_has_failure_mode_handling_for_sanctum_init_error(step5_text):
    """T8 (BUG-291): step 5 contains explicit failure-mode handling for
    aim-agent-sanctum-init non-zero exit (W-04 self-heal pattern).

    Verifies:
    - W-04 self-heal indicator present
    - WARN-and-continue verbiage present (matching caps of surrounding bullets)
    - 'does not block' clause present (activation proceeds on scaffolding failure)
    - Failure-mode bullet is positionally AFTER sanctum-init invocation and
      BEFORE the re-check step (so error path still reaches the diagnostic re-check)
    """
    assert (
        FAILURE_MODE_INDICATOR in step5_text
    ), f"step 5 must contain W-04 self-heal indicator '{FAILURE_MODE_INDICATOR}'"
    assert "WARN-and-continue" in step5_text, (
        "step 5 must use 'WARN-and-continue' (caps) for failure-mode handling, "
        "matching neighboring WARN bullet style"
    )
    assert (
        "does not block" in step5_text.lower()
    ), "step 5 must state activation does NOT block on scaffolding failure"

    # Positional ordering: failure-mode bullet AFTER sanctum-init invocation,
    # BEFORE re-check step (error path must not skip the diagnostic re-check)
    sanctum_init_idx = step5_text.index(SANCTUM_INIT_SKILL)
    failure_mode_idx = step5_text.index(FAILURE_MODE_INDICATOR)
    recheck_idx = step5_text.lower().index("re-check the required set")

    assert (
        sanctum_init_idx < failure_mode_idx
    ), "failure-mode bullet must appear AFTER the sanctum-init invocation bullet"
    assert failure_mode_idx < recheck_idx, (
        "failure-mode bullet must appear BEFORE the re-check step "
        "(error path must still reach the diagnostic re-check)"
    )
