"""Contract: step chain forward link resolution.

For every workflow.md with a firstStep, walks the firstStep→nextStepFile spine
and asserts each referenced file exists (no dangling refs).

NO reverse-reachability (orphan) test: the corpus contains branch/mode steps
(steps-e/, steps-v/, branches/branch-a..d/, route/step-01-resolve-backend.md)
that are reached by prose routing in step bodies, not by the linear nextStepFile
spine.  A corpus-wide reverse-reachability check would false-fail on all of them.
The forward link-resolution contract below is the false-positive-free equivalent:
every path that IS referenced resolves; unreferenced paths are not asserted.
See INDEX.md §Coverage Notes for the full rationale.

Parametrized over all 26 workflow.md files; FIRSTEP_EXEMPT workflows are skipped.
"""

import pytest

from .conftest import (
    FIRSTEP_EXEMPT,
    _all_workflow_mds,
    _wf_id,
    walk_step_chain,
)

_WORKFLOWS = _all_workflow_mds()


@pytest.mark.process
@pytest.mark.parametrize("wf_path", _WORKFLOWS, ids=_wf_id)
def test_step_chain_resolves(wf_path):
    """Walk the full firstStep→nextStepFile chain; assert no dangling refs or cycles."""
    if wf_path.resolve() in FIRSTEP_EXEMPT:
        pytest.skip(
            "inline/reference workflow — no step chain (documented non-feasible)"
        )
    chain = walk_step_chain(wf_path)
    assert len(chain) >= 1, f"Workflow {wf_path} has no reachable steps"
