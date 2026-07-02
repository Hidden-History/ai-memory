---
name: 'step-02b-update-plan'
description: 'Update the active initiative plan and run the completeness / supersession audit'
nextStepFile: './step-03-create-handoff.md'
---

# Step 2b: Update Active Plan

**Progress: Step 2b of 6** — Next: Create Handoff Document

## STEP GOAL:

Bring the active per-initiative plan into sync with what actually happened this session: update item statuses, run the completeness / supersession audit so no plan ends with silent open items, and confirm the done-condition by evidence when the plan is done.

**Scope:**
- Available context: Session summary from Step 1, updated tracking from Step 2, plans under `{oversight_path}/plans/`
- Focus: Active-plan update and audit only — do not create the handoff document yet
- Limits: Only the active plan is touched; superseded/abandoned plans are not rewritten
- Dependencies: Session summary from Step 1 and updated tracking from Step 2

- Update the active plan's item statuses and append every status change to the Continuity Log
**Behavioral Constraints:**
- FORBIDDEN to close a plan `done` without confirming the done-condition by evidence (verify, do not assert)
- Approach: Update statuses → audit for open items → resolve every open item explicitly (roll forward, or supersede/abandon with a reason)
- If no active plan applies to this session's work, note "no active plan" and continue

## Sequence

### 0. Locate the Active Plan

Identify the active plan for this session's work under `{oversight_path}/plans/` — the one whose front-matter `status:` is `active` or `approved` and whose subject matches the worked initiative.

- If none applies (trivial/reactive work with no plan) → note "no active plan" and advance to `{nextStepFile}`.
- If one applies → proceed.
- If multiple match → the most recent by `plan_id` date; note the ambiguity in the Continuity Log.

---

### 1. Update Item Statuses

For each `## 3. Work Items` row touched this session, update `Status` to reflect reality (`todo` / `doing` / `done` / `blocked`). Preserve the single-`doing` invariant — at most one item `doing` when the session ends. Append a dated line to the `## 7. Continuity Log` for every status change.

---

### 2. Completeness / Supersession Audit

A plan MUST NOT end a session with silent open items. For every item still `todo`, `doing`, or `blocked`, resolve it explicitly by one of:

- **Roll forward** — carry the open item into the successor plan. The successor's front-matter sets `previous_plan:` to this plan's filename; record the roll-forward in this plan's Continuity Log. If ALL of this plan's remaining open items are rolled forward, set THIS plan's `status: superseded` (naming the successor) and log the reason in the Continuity Log — a plan must never stay `active`/`approved` with its work moved into a successor.
- **Supersede** — set this plan's `status: superseded` WITH a reason in the Continuity Log (and name the superseding plan).
- **Abandon** — set this plan's `status: abandoned` WITH a reason in the Continuity Log.

Never leave an open item unaccounted for.

---

### 3. Confirm Done-Condition on Completion (Verify-Not-Assert)

If all items are `done` and the plan is being closed:

- Re-read the plan's `## 2. Done-Condition` and confirm it is met **by evidence** (independent check / observable end state), not by assertion that the work was performed.
- Only then set front-matter `status: done`.
- In the successor plan (if the initiative continues), set `previous_completed: yes`. If the done-condition is NOT confirmed, do NOT set `status: done` — instead add a new Work Item (status `todo`) capturing the unmet gap, keep the plan `active`, and record it in the Continuity Log.

---

### 4. Verify Plan State

After updates, confirm:
- Item statuses match the session's actual outcomes; at most one item is `doing`
- Every open item is accounted for (rolled forward, or plan superseded/abandoned with a reason)
- Continuity Log records each status change and any supersession/abandonment reason
- A `done` plan's done-condition was confirmed by evidence before the status flip

## CRITICAL STEP COMPLETION NOTE

ONLY when the active plan is updated and the completeness / supersession audit is clean, load and read fully {nextStepFile}
