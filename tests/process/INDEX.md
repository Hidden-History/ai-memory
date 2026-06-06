# Process Test Index — TASK-071 Phase 4

**Authored**: feat/task071-process-tests  
**Work order**: `oversight/specs/TASK-071-PHASE4-PROCESS-TEST-WORK-ORDER.md`  
**Harness authority**: `oversight/knowledge/best-practices/BP-017-pytest-contract-testing-markdown-step-file-workflows.md`

All 30 processes from the Phase-2 Lane-5 inventory are listed below with their
coverage status.  Testable processes are covered by the parametrized contract
suite in `tests/process/` — no dedicated per-process test files.

---

## Coverage Notes

### Cyclic workflows — handled gracefully

`cycles/review-cycle` intentionally loops: `step-03→step-04→step-05→step-03`.
The exit condition is prose-controlled via `exitStepFile: ./step-07-exit-cycle.md`.
`walk_step_chain()` terminates on revisit (cycle is not an error — all referenced
files resolve).  The forward link-resolution contract still holds: every
`nextStepFile` reference in the loop resolves to a real file.

### Reverse-reachability (orphan) test — NOT implemented

The corpus contains branch/mode steps that are reached by prose routing in step
bodies rather than the linear `firstStep`→`nextStepFile` spine:

- `steps-e/` (edit-mode steps)
- `steps-v/` (validate-mode steps)
- `branches/branch-a..d/` (conditional branches)
- `route/step-01-resolve-backend.md` (shared routing step)

A corpus-wide reverse-reachability check (`all step*.md − linear-reachable == ∅`)
would false-fail on all of these.  The forward link-resolution contract
(`test_step_chain.py` + `test_step_frontmatter.py::test_step_nextStepFile_resolves`)
is the false-positive-free equivalent: every *referenced* path resolves; prose-routed
paths that are intentionally unreachable from the linear spine are not asserted.

### FIRSTEP_EXEMPT set

Two workflows have no executable step chain and are skipped for `firstStep`-presence
and chain-walk assertions (they still pass name/description/H2 checks):

| Workflow | Reason |
|---|---|
| `session/status/workflow.md` | Single-step inline workflow — `firstStep: null` by design |
| `model-dispatch/claude-native/workflow.md` | Reference doc — no step chain |

### aim-best-practices-researcher — core skill root

`aim-best-practices-researcher` lives under `_ai-memory/skills/` (core skills root),
not `_ai-memory/pov/skills/` (pov skills root).  `test_skill_procedures.py` uses
explicit per-skill paths for all three Section-C skills to accommodate both roots.

---

## Process Coverage Table

| # | Process ID | Root File | Section | Coverage | Test File / Notes |
|---|---|---|---|---|---|
| 1 | cycles/agent-dispatch | `_ai-memory/pov/workflows/cycles/agent-dispatch/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 2 | cycles/approval-gate | `_ai-memory/pov/workflows/cycles/approval-gate/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 3 | cycles/legitimacy-check | `_ai-memory/pov/workflows/cycles/legitimacy-check/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 4 | cycles/research-protocol | `_ai-memory/pov/workflows/cycles/research-protocol/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 5 | cycles/review-cycle | `_ai-memory/pov/workflows/cycles/review-cycle/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 6 | first-breath | `_ai-memory/pov/workflows/first-breath/workflow.md` | A | ✅ Contract suite (structural); behavioral testing non-feasible | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 7 | init/existing | `_ai-memory/pov/workflows/init/existing/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 8 | init/new | `_ai-memory/pov/workflows/init/new/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 9 | phases/architecture | `_ai-memory/pov/workflows/phases/architecture/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 10 | phases/discovery | `_ai-memory/pov/workflows/phases/discovery/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 11 | phases/execution | `_ai-memory/pov/workflows/phases/execution/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 12 | phases/integration | `_ai-memory/pov/workflows/phases/integration/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 13 | phases/maintenance | `_ai-memory/pov/workflows/phases/maintenance/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 14 | phases/planning | `_ai-memory/pov/workflows/phases/planning/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 15 | phases/release | `_ai-memory/pov/workflows/phases/release/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 16 | session/blocker | `_ai-memory/pov/workflows/session/blocker/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 17 | session/close | `_ai-memory/pov/workflows/session/close/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 18 | session/decision | `_ai-memory/pov/workflows/session/decision/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 19 | session/handoff | `_ai-memory/pov/workflows/session/handoff/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 20 | session/start | `_ai-memory/pov/workflows/session/start/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 21 | session/status | `_ai-memory/pov/workflows/session/status/workflow.md` | A | ⚠️ Partial — EXEMPT | name/description/H2 tested; `firstStep`+chain SKIPPED (`firstStep: null` — single-step inline workflow by design) |
| 22 | session/verify | `_ai-memory/pov/workflows/session/verify/workflow.md` | A | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 23 | model-dispatch/api-dispatch | `_ai-memory/pov/skills/aim-model-dispatch/workflows/api-dispatch/workflow.md` | B | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 24 | model-dispatch/bmad-dispatch | `_ai-memory/pov/skills/aim-model-dispatch/workflows/bmad-dispatch/workflow.md` | B | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 25 | model-dispatch/tmux-dispatch | `_ai-memory/pov/skills/aim-model-dispatch/workflows/tmux-dispatch/workflow.md` | B | ✅ Contract suite | `test_workflow_frontmatter.py`, `test_step_frontmatter.py`, `test_step_chain.py` |
| 26 | model-dispatch/claude-native | `_ai-memory/pov/skills/aim-model-dispatch/workflows/claude-native/workflow.md` | B | ⚠️ Partial — EXEMPT | name/description/H2 tested; `firstStep`+chain SKIPPED (reference doc, no step chain — documented non-feasible) |
| 27 | skill/aim-agent-sanctum-init | `_ai-memory/pov/skills/aim-agent-sanctum-init/SKILL.md` | C | ✅ Existing test | `tests/test_install_sanctum_preservation.py` (idempotency) — not duplicated here per work-order §5 |
| 28 | skill/aim-agent-dispatch | `_ai-memory/pov/skills/aim-agent-dispatch/SKILL.md` | C | ✅ Skill procedures | `test_skill_procedures.py` |
| 29 | skill/aim-agent-lifecycle | `_ai-memory/pov/skills/aim-agent-lifecycle/SKILL.md` | C | ✅ Skill procedures | `test_skill_procedures.py` |
| 30 | skill/aim-best-practices-researcher | `_ai-memory/skills/aim-best-practices-researcher/SKILL.md` | C | ✅ Skill procedures | `test_skill_procedures.py` — core skill root (`_ai-memory/skills/`), distinct from pov skills root |
