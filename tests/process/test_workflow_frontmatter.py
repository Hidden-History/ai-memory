"""Contract: workflow.md frontmatter schema and minimal section presence.

Parametrized over all 26 workflow.md files from both workflow roots:
  Root 1 (Section A): _ai-memory/pov/workflows/           — 22 files
  Root 2 (Section B): aim-model-dispatch/workflows/        —  4 files

Three assertions per workflow:
  1. name + description present and non-empty (all 26)
  2. firstStep present and non-null (24 of 26; 2 exempt — see FIRSTEP_EXEMPT)
  3. At least one H2 section (## ...) in the body (all 26)

The firstStep exemption covers workflows with no step chain (BP-017 §12):
  - claude-native : reference doc (type: reference)
  - session/status: single-step inline workflow (firstStep: null — by design)
Both are skipped via pytest.skip so they appear in the report as explicitly
skipped, not silently omitted.
"""

import pytest

from .conftest import (
    FIRSTEP_EXEMPT,
    _all_workflow_mds,
    _wf_id,
    parse_frontmatter,
)

_WORKFLOWS = _all_workflow_mds()


@pytest.mark.process
@pytest.mark.parametrize("wf_path", _WORKFLOWS, ids=_wf_id)
def test_workflow_name_and_description(wf_path):
    fm = parse_frontmatter(wf_path)
    assert fm.get("name"), f"Missing/empty 'name' in {wf_path}"
    assert fm.get("description"), f"Missing/empty 'description' in {wf_path}"


@pytest.mark.process
@pytest.mark.parametrize("wf_path", _WORKFLOWS, ids=_wf_id)
def test_workflow_firstStep_present(wf_path):
    if wf_path.resolve() in FIRSTEP_EXEMPT:
        pytest.skip(
            "inline/reference workflow — no step chain (documented non-feasible)"
        )
    fm = parse_frontmatter(wf_path)
    assert fm.get("firstStep"), f"Missing/null 'firstStep' in {wf_path}"


@pytest.mark.process
@pytest.mark.parametrize("wf_path", _WORKFLOWS, ids=_wf_id)
def test_workflow_has_h2_section(wf_path):
    text = wf_path.read_text(encoding="utf-8")
    h2_lines = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert h2_lines, f"{wf_path}: workflow.md has no '## ' sections"
