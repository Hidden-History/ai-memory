"""Vacuous-green guard: corpus discovery must find minimum expected file counts.

If either path anchor in conftest.py breaks (e.g. WORKFLOWS_ROOT no longer
exists), rglob returns [] → 0 tests collected across the parametrized suite →
false green.  This non-parametrized sentinel catches that failure mode by
asserting hard minimums against the known corpus size.

Minimums reflect the corpus at time of authoring (TASK-071 Phase 4):
  - workflow.md : 26  (22 under WORKFLOWS_ROOT + 4 under MODEL_DISPATCH_ROOT)
  - step*.md    : 211 (183 under WORKFLOWS_ROOT + 28 under MODEL_DISPATCH_ROOT)
"""

import pytest

from .conftest import _all_step_mds, _all_workflow_mds


@pytest.mark.process
def test_corpus_sentinel(workflows_root):
    """Discovery functions must find the minimum expected corpus size.

    Uses the workflows_root fixture to also validate that the path anchor is a
    real directory.  If the anchor breaks, this test — not a silent 0-collected
    run — is the failure signal.
    """
    wf_count = len(_all_workflow_mds())
    step_count = len(_all_step_mds())

    assert wf_count >= 26, (
        f"workflow.md discovery returned {wf_count} files — expected >= 26. "
        f"Check WORKFLOWS_ROOT / MODEL_DISPATCH_ROOT anchors in conftest.py."
    )
    assert step_count >= 211, (
        f"step*.md discovery returned {step_count} files — expected >= 211. "
        f"Check WORKFLOWS_ROOT / MODEL_DISPATCH_ROOT anchors in conftest.py."
    )
