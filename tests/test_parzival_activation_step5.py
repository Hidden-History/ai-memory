"""
Regression tests for parzival.md activation step 5 decision logic (BUG-291).

T5-T7 verify step 5 text content and conditional branching directives.
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

EXACT_BOND_SCAFFOLD_MARKER = "_Filled during First Breath:"
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


def test_T6_step5_invokes_first_breath_when_bond_scaffold_marker_present(step5_text):
    """T6 (BUG-291): step 5 directs invocation of the First Breath workflow when
    BOND.md contains the literal scaffold marker '_Filled during First Breath:'.

    Verifies:
    - Exact marker text '_Filled during First Breath:' is used (not a broad pattern)
    - First Breath workflow path is referenced
    - Invocation is conditional on marker presence
    """
    # Exact scaffold marker must be present in step 5 text
    assert EXACT_BOND_SCAFFOLD_MARKER in step5_text, (
        f"step 5 must check for the literal marker '{EXACT_BOND_SCAFFOLD_MARKER}' "
        f"(not a broad pattern) — per BOND-template.md actual marker text"
    )

    # First Breath workflow must be referenced
    assert (
        FIRST_BREATH_WORKFLOW in step5_text
    ), f"step 5 must invoke '{FIRST_BREATH_WORKFLOW}' when scaffold marker is found"

    # The First Breath invocation must be conditional ("if the marker is present" or equivalent)
    # Check that "if" precedes the first-breath reference in step text
    first_breath_idx = step5_text.index(FIRST_BREATH_WORKFLOW)
    preceding_text = step5_text[:first_breath_idx].lower()
    assert (
        "if" in preceding_text
    ), "step 5 must conditionally invoke First Breath (not unconditionally)"


def test_T7_step5_skips_first_breath_when_bond_marker_absent(step5_text):
    """T7 (BUG-291): step 5 SKIPS the First Breath workflow when BOND.md does NOT
    contain the scaffold marker (i.e., owner has already filled BOND with specifics).

    Verifies that the First Breath invocation is conditional, not triggered
    unconditionally every activation:
    - The step uses 'if ... marker is present' logic (conditional branch)
    - It does NOT say 'always invoke first-breath' or equivalent unconditional text
    """
    # The directive must be conditional — skip if marker absent
    # Verify "if the marker is present" or equivalent conditional form
    assert (
        EXACT_BOND_SCAFFOLD_MARKER in step5_text
    ), "Prerequisite: exact marker must be in step 5 (T6 must pass first)"

    # Step must NOT unconditionally invoke first-breath — look for conditional phrasing
    unconditional_patterns = [
        "always invoke.*first.breath",
        "unconditionally.*first.breath",
        "invoke.*first.breath.*always",
    ]
    for pattern in unconditional_patterns:
        assert not re.search(
            pattern, step5_text, re.IGNORECASE
        ), f"step 5 must NOT unconditionally invoke First Breath (found pattern: {pattern!r})"

    # The First Breath invocation must be guarded by a conditional on marker presence
    # Verify the text structure: marker check → conditional → workflow invocation
    marker_idx = step5_text.index(EXACT_BOND_SCAFFOLD_MARKER)
    first_breath_idx = step5_text.index(FIRST_BREATH_WORKFLOW)

    # The marker check must appear before the first-breath invocation reference
    assert (
        marker_idx < first_breath_idx
    ), "step 5 must check for the scaffold marker before referencing the First Breath workflow"

    # Must contain failure-mode handling (W-04 self-heal) — confirms step 5 handles
    # both the skip case (no marker) AND the error case (init-sanctum.py failure)
    assert FAILURE_MODE_INDICATOR in step5_text, (
        f"step 5 must contain W-04 self-heal failure-mode handling "
        f"('{FAILURE_MODE_INDICATOR}') for init-sanctum.py non-zero exit"
    )
