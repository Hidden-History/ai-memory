"""Contract: step file frontmatter schema and reference resolution.

Parametrized over all step*.md files from both workflow roots (211 total).

Three assertions per step file:
  1. name + description present and non-empty
  2. nextStepFile resolves to a real file when present
     (resolved relative to the *step file's* parent — not workflow root; BP-017 §12)
  3. All template/path frontmatter keys resolve to real files

Placeholder substitution for template refs (BP-017 §8):
  {workflows_path} → WORKFLOWS_ROOT
  {skills_path}    → SKILLS_ROOT
  {project-root}   → REPO_ROOT
"""

import pytest

from .conftest import (
    _all_step_mds,
    _step_id,
    parse_frontmatter,
    resolve_template_ref,
)

# Frontmatter keys that cite paths to other files (templates, scaffolds, etc.)
_TEMPLATE_KEYS = frozenset(
    {
        "scaffold",
        "handoffTemplate",
        "correctionTemplate",
        "storyTemplate",
        "productionTemplate",
        "phaseApprovalTemplate",
        "taskApprovalTemplate",
        "decisionLogTemplate",
        "decisionPointTemplate",
        "codeTemplate",
        "codeReviewTemplate",
        "analystInstructionTemplate",
        "instructionTemplate",
        "incompletenessTemplate",
        "exitStepFile",
    }
)

_STEPS = _all_step_mds()


@pytest.mark.process
@pytest.mark.parametrize("step_path", _STEPS, ids=_step_id)
def test_step_name_and_description(step_path):
    fm = parse_frontmatter(step_path)
    assert fm.get("name"), f"Missing/empty 'name' in {step_path}"
    assert fm.get("description"), f"Missing/empty 'description' in {step_path}"


@pytest.mark.process
@pytest.mark.parametrize("step_path", _STEPS, ids=_step_id)
def test_step_nextStepFile_resolves(step_path):
    fm = parse_frontmatter(step_path)
    ref = fm.get("nextStepFile")
    if not ref:
        pytest.skip("terminal step: no nextStepFile")
    resolved = (step_path.parent / ref).resolve()
    assert resolved.exists(), f"Dangling nextStepFile '{ref}' in {step_path}"


@pytest.mark.process
@pytest.mark.parametrize("step_path", _STEPS, ids=_step_id)
def test_step_template_refs_resolve(step_path):
    fm = parse_frontmatter(step_path)
    present_keys = _TEMPLATE_KEYS & fm.keys()
    for key in sorted(present_keys):
        ref = fm[key]
        if not ref or ref is False:
            continue
        resolved = resolve_template_ref(str(ref), step_path)
        assert (
            resolved.exists()
        ), f"Step {step_path}: frontmatter key '{key}' → non-existent: {resolved}"
