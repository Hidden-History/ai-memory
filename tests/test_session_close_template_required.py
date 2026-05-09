"""TD-520 (F-C6): TD-500 enforcement hardening — template-required pre-condition.

Verifies that closeout step-02 AND step-03 both contain the explicit
pre-condition check for the handoff template's existence (belt-and-suspenders
per Q-D6 course-correction in recommendation-first-r1.md). The check is a
defensive guard against silent fallback paths that would emit a handoff
lacking the TD-500 Branch State block.

Test approach: static analysis of the workflow step files (Parzival workflow
steps are natural-language directives, not executable Python — same
precedent as ``tests/test_parzival_activation_step5.py``).

References:
    - TECH-DEBT-520 §"Fix Design"
    - oversight/tasks/pm285-v240-ship-fix/recommendation-first-r1.md §B-3
    - tests/test_parzival_activation_step5.py (static-analysis pattern)
"""

from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent

STEP_02_PATH = (
    _REPO_ROOT
    / "_ai-memory"
    / "pov"
    / "workflows"
    / "session"
    / "close"
    / "steps-c"
    / "step-02-update-tracking.md"
)
STEP_03_PATH = (
    _REPO_ROOT
    / "_ai-memory"
    / "pov"
    / "workflows"
    / "session"
    / "close"
    / "steps-c"
    / "step-03-create-handoff.md"
)
TEMPLATE_PATH_LITERAL = "_ai-memory/pov/templates/session-handoff.template.md"

# Stable substrings — operator-facing, change-resistant.
HARD_FAIL_PHRASE = "Handoff template missing"
RECOVERY_PHRASE = "Restore template"
TD500_REFERENCE = "TD-500"
TD520_REFERENCE = "TD-520"


@pytest.fixture(scope="module")
def step_02_text() -> str:
    assert STEP_02_PATH.exists(), f"step-02 file not found: {STEP_02_PATH}"
    return STEP_02_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step_03_text() -> str:
    assert STEP_03_PATH.exists(), f"step-03 file not found: {STEP_03_PATH}"
    return STEP_03_PATH.read_text(encoding="utf-8")


# ─── T1: step-02 contains the pre-condition check ──────────────────────────


def test_T1_step_02_contains_template_required_check(step_02_text: str):
    """step-02 must contain the hard-fail pre-condition for the handoff
    template, naming the template path and the recovery action.
    """
    assert HARD_FAIL_PHRASE in step_02_text, (
        f"step-02 must contain hard-fail phrase '{HARD_FAIL_PHRASE}'"
    )
    assert TEMPLATE_PATH_LITERAL in step_02_text, (
        f"step-02 must reference the canonical template path "
        f"'{TEMPLATE_PATH_LITERAL}'"
    )
    assert RECOVERY_PHRASE in step_02_text, (
        f"step-02 must give an actionable recovery instruction "
        f"('{RECOVERY_PHRASE}')"
    )


# ─── T2: step-03 contains the pre-condition check ──────────────────────────


def test_T2_step_03_contains_template_required_check(step_03_text: str):
    """step-03 must contain the same hard-fail pre-condition (belt-and-
    suspenders). Covers workflow refactors that bypass step-02 directly
    to step-03.
    """
    assert HARD_FAIL_PHRASE in step_03_text, (
        f"step-03 must contain hard-fail phrase '{HARD_FAIL_PHRASE}'"
    )
    assert TEMPLATE_PATH_LITERAL in step_03_text, (
        f"step-03 must reference the canonical template path "
        f"'{TEMPLATE_PATH_LITERAL}'"
    )
    assert RECOVERY_PHRASE in step_03_text, (
        f"step-03 must give an actionable recovery instruction "
        f"('{RECOVERY_PHRASE}')"
    )


# ─── T3: Both step files cite TD-500 explicitly ─────────────────────────────


def test_T3_both_steps_cite_td500_traceability(step_02_text: str, step_03_text: str):
    """Both step files must explicitly reference TD-500 so the link from
    template-required enforcement back to the empirical commits-ahead
    mandate is visible to operators auditing the workflow.
    """
    assert TD500_REFERENCE in step_02_text, "step-02 must cite TD-500"
    assert TD500_REFERENCE in step_03_text, "step-03 must cite TD-500"
    assert TD520_REFERENCE in step_02_text, "step-02 must cite TD-520"
    assert TD520_REFERENCE in step_03_text, "step-03 must cite TD-520"


# ─── T4: Recovery action is operator-actionable ─────────────────────────────


def test_T4_recovery_action_actionable(step_02_text: str, step_03_text: str):
    """The hard-fail message must give the operator a concrete recovery
    path (e.g., reference to ``git checkout`` or ``re-run installer``).
    Tests resilience: anything that names a recovery command suffices.
    """
    actionable_indicators = ["git checkout", "re-run installer", "Restore"]
    assert any(s in step_02_text for s in actionable_indicators), (
        f"step-02 must give operator-actionable recovery; "
        f"none of {actionable_indicators!r} found"
    )
    assert any(s in step_03_text for s in actionable_indicators), (
        f"step-03 must give operator-actionable recovery; "
        f"none of {actionable_indicators!r} found"
    )


# ─── T5: Pre-condition appears BEFORE existing happy path ──────────────────


def test_T5_precondition_precedes_happy_path_in_step_02(step_02_text: str):
    """In step-02, the pre-condition (§0) must appear BEFORE the existing
    §1 (Request Task Status Updates) — fail-fast semantics.
    """
    precondition_idx = step_02_text.find(HARD_FAIL_PHRASE)
    happy_path_idx = step_02_text.find("Request Task Status Updates")
    assert precondition_idx >= 0
    assert happy_path_idx >= 0
    assert precondition_idx < happy_path_idx, (
        "step-02 pre-condition must appear before the §1 happy path "
        "for fail-fast behavior"
    )


def test_T6_precondition_precedes_happy_path_in_step_03(step_03_text: str):
    """In step-03, the pre-condition (§0) must appear BEFORE the existing
    §1 (Load Template (If Available)) — covers the actual template-bound
    site against silent fallback to the inline format block.
    """
    precondition_idx = step_03_text.find(HARD_FAIL_PHRASE)
    fallback_path_idx = step_03_text.find("Load Template (If Available)")
    assert precondition_idx >= 0
    assert fallback_path_idx >= 0
    assert precondition_idx < fallback_path_idx, (
        "step-03 pre-condition must appear before the §1 'Load Template "
        "(If Available)' fallback section"
    )


# ─── T7: Template file actually exists in the repo (existing-state guard) ──


def test_T7_template_file_exists_in_repo():
    """Sanity check: the canonical template file must actually exist in
    the repository at the path the pre-condition advertises. If this
    fails, the pre-condition would falsely trigger on every session-close
    regardless of operator state.
    """
    template_path = _REPO_ROOT / TEMPLATE_PATH_LITERAL
    assert template_path.exists(), (
        f"Canonical handoff template missing at {template_path}. "
        "Pre-condition would falsely trigger on every session-close."
    )
