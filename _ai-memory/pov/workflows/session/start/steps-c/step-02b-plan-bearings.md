---
name: 'step-02b-plan-bearings'
description: 'Load the active initiative plan, take resume-bearings, and apply the proportionate plan-gate'
nextStepFile: './step-03-present-and-wait.md'
---

# Step 2b: Plan Bearings

**Progress: Step 2b of 5** — Next: Present and Wait for Direction

## STEP GOAL:

Enrich the status report compiled in Step 2 with plan bearings: load the active per-initiative plan, identify the resume point, and apply the proportionate plan-gate so no initiative is dispatched into a vacuum.

**Scope:**
- Available context: The compiled status report from Step 2, plans under `{oversight_path}/plans/`
- Focus: Plan loading, resume-bearings, and gate evaluation only — do not present or start work
- Limits: Read-only — do not modify any plan file at session start
- Dependencies: Compiled status report from Step 2

- Load the active plan (front-matter + item table, capped) and fold its bearings into the report
**Behavioral Constraints:**
- FORBIDDEN to dispatch or start work — this step only informs the Step 3 recommendation
- Approach: Cheap machine read of front-matter first; pull item-table detail on demand
- If no plan applies (trivial/reactive/one-surface work), note "no plan required" and continue — do not fabricate a gate

## Sequence

### 1. Locate the Active Plan

Scan `{oversight_path}/plans/PLAN-*.md` filenames (no full reads yet). Identify the plan for the current initiative — the one whose front-matter `status:` is `active` or `approved` and whose subject matches the current task/initiative from the Step 2 report.

- If exactly one active/approved plan matches → that is the active plan.
- If none exists → record "no active plan" (feeds the gate in Section 3).
- If multiple match → the most recent by `plan_id` date; note the ambiguity in the report.

---

### 2. Load Plan Front-Matter + Resume-Bearings (Capped)

Read only the front-matter block and the `## 3. Work Items` table of the active plan (skip the prose sections — pulled on demand later):

- **Front-matter**: `plan_id`, `type`, `status`, `previous_plan`, `previous_completed`.
- **Resume point**: the highest-priority not-done item — the single `doing` item if present, else the first `todo`. Name it in the report. If more than one item is `doing`, flag it as an anomaly (same treatment as the adjacent baseline-drift flag) rather than silently assuming a single `doing` item.
- **Baseline check**: confirm the resume point still matches reality (the item's stated target still exists / is still open). Flag any drift between the plan and current tracking state as an anomaly (do not resolve it here).

Surface a one-line plan-status rollup into the compiled report:
`plan: <plan_id> — status <status>, resume at item #<n> "<item>" (<done>/<total> done)`

If all Work Items are `done` (close-out pending), surface instead: `plan: <plan_id> — all items done, pending close-out`.

If no active plan exists, surface instead: `plan: none active for current work`.

---

### 3. Apply the Proportionate Plan-Gate

Gate on **scope, never effort or time**. Classify the pending work:

- **SKIP the gate** (no plan required): one-file / single-surface / reversible / reactive one-off / pure discussion or status. Note "no plan required" and continue.
- **REQUIRE an approved plan** (initiative): multi-file / multi-surface, uncertain approach, a verification / research / ops initiative, multi-session, or work touching the runtime-under-test.

If the pending work is an **initiative** AND no `status: approved | active` plan exists for it, then the first recommended action in Step 3 MUST be **"draft a plan and get user approval before any task dispatch"** — ahead of any execution recommendation.

---

### 4. Hand Bearings to Step 3

Fold the plan-status rollup, the resume point, any plan/tracking anomaly, and the gate outcome into the compiled report so Step 3's recommendation reflects them. Do not present here.

## CRITICAL STEP COMPLETION NOTE

ONLY when the plan bearings and gate outcome are folded into the report, load and read fully {nextStepFile}
