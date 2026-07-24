---
name: 'step-02b-plan-bearings'
description: 'Load the active initiative plan, take resume-bearings, and apply the proportionate plan-gate'
nextStepFile: './step-03-present-and-wait.md'
---

# Step 2b: Plan Bearings

**Progress: Step 2b of 5** — Next: Present and Wait for Direction

## STEP GOAL:

Enrich the status report compiled in Step 2 with plan bearings: read any master spine first, load the active per-initiative plan, identify the resume point, and apply the proportionate plan-gate (including the stage-gate ordering guard) so no initiative is dispatched into a vacuum.

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

### 0. Master-First Spine Read (only when a master plan exists)

Before locating a single active plan, check for a master spine: scan the front-matter of plan files under `{oversight_path}/plans/*.md` — those carrying plan front-matter (a `plan_id` or `plan_role` field present) — for a plan with `plan_role: master`. Skip any file with no plan front-matter (e.g. `README.md` / `INDEX.md`), any `*_TEMPLATE.md` file, and any file whose plan front-matter is still an unfilled placeholder (bracketed `<…>` tokens or the template's literal placeholder values, e.g. `plan_id: PLAN-MASTER-<DOMAIN>`) — the installer ships `MASTER_PLAN_TEMPLATE.md` (which carries a placeholder `plan_role: master`) into `{oversight_path}/plans/`, so it must never be mistaken for a real master. A master need not be named `PLAN-*` (e.g. `MASTER-PIPELINE-PLAN.md`) and is still detected this way.

- **If no `plan_role: master` plan exists** → skip this section and use the single-plan logic in Sections 1–4 unchanged. This preserves today's behavior for projects with no master spine.
- **If a `plan_role: master` plan exists** → read it FIRST, ahead of any single active plan:
  1. **Current step** = the first master-spine row, in canonical order, whose `Status` is not `GREEN` (i.e. `RED`, `YELLOW`, or `—`/NOT_STARTED).
  2. **Recommended resume point** = that current step's open **session child** — the `plan_role: session` plan whose `master_plan` + `step_id` link back to this master row — not merely "the most recent active plan."
  3. **Plan-role & orphan-child check (F-10):** flag two plan-integrity anomalies here (same treatment as the baseline-drift anomaly below; do not resolve them here): **(a) invalid role** — any plan whose `plan_role` is not one of `standalone`, `master`, or `session`; **(b) orphan child** — a `plan_role: session` plan, or a plan carrying an invalid role, that is missing `master_plan` or `step_id` (an orphan child — the #1 SSoT-killer). `master`- and `standalone`-role plans are exempt from this orphan check — they legitimately carry no `master_plan`/`step_id`. Do not key this off `plan_role: session` alone.
  4. **`step_id: ALL` carve-out:** a spine-wide verification/audit child may set `step_id: ALL` (a documented exception — it maps to **every** master row, not one). Treat it as a valid session child for the current step, not a mismatch or an orphan.

Fold the spine rollup — current step, recommended session child, any orphan anomaly — into the report, then continue to Section 1 to confirm the active plan against this bearing.

---

### 1. Locate the Active Plan

Scan `{oversight_path}/plans/PLAN-*.md` filenames (no full reads yet). Identify the plan for the current initiative — the one whose front-matter `status:` is `active` or `approved` and whose subject matches the current task/initiative from the Step 2 report.

**When Section 0 found a master spine:** exclude any `plan_role: master` plan from this candidate set (a master is the spine, never "the active plan") and prefer the current step's session child — the Section 0 resume point — as the active plan. When no master spine exists, apply the selection below unchanged.

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

If the pending work is an **initiative** AND no `status: approved | active` plan exists for it, then Step 3 MUST recommend **"draft a plan and get user approval before any task dispatch"** as the first plan/execution-tier action — ahead of any execution or task-continuation recommendation, but after any blocker or pending-updates recommendation that Step 3 states ahead of it.

**Stage-gate ordering (F-09 — applies only when a master spine was read in Section 0):** if the recommended or user-requested next action targets a master step *downstream* of the current step while an upstream row is `RED`, `YELLOW`, or `—`, that downstream step's BUILD / verify-claims work is **gated**. Surface a WARN and require an explicit user override before recommending it in Step 3 — e.g. "upstream ST-NN is not GREEN; downstream BUILD is gated — proceed read-only, or override with a reason." Read-only design / research / story-authoring look-ahead for the downstream step is **not** gated. This is a warn-and-override, not a hard block. F-09 is a session-start-routing guard — evaluated at `[ST]` against the recommended or user-requested next action — not a mid-session dispatch-time hook.

---

### 4. Hand Bearings to Step 3

Fold the plan-status rollup, the resume point (the current step's session child when a master spine applies), any plan/tracking or orphan-child anomaly, and the gate outcome — including any F-09 stage-gate WARN — into the compiled report so Step 3's recommendation reflects them. Do not present here.

## CRITICAL STEP COMPLETION NOTE

ONLY when the plan bearings and gate outcome are folded into the report, load and read fully {nextStepFile}
