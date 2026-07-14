---
name: 'step-02b-update-plan'
description: 'Update the active initiative plan and run the completeness / supersession audit'
nextStepFile: './step-03-create-handoff.md'
---

# Step 2b: Update Active Plan

**Progress: Step 2b of 6** — Next: Create Handoff Document

## STEP GOAL:

Bring the active per-initiative plan into sync with what actually happened this session: update item statuses, run the completeness / supersession audit so no plan ends with silent open items, roll a session child back into its master spine row, and confirm the done-condition by evidence when the plan is done.

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

**Exclude any `plan_role: master` plan from this candidate set** — a master is the spine, never "the active plan" being closed; it is updated via Section 4 (Master-Row Roll-Up), not selected here. When no master spine exists, apply the selection below unchanged.

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

### 4. Master-Row Roll-Up (when the active plan is a session child)

If the active plan's front-matter is `plan_role: session`, it MUST roll back into its master spine the **same session** — an unrolled child is an orphan (the #1 way the master stops being SSoT). Using the plan's `master_plan` + `step_id` link, update that master row from **git + live evidence as truth**:

- `Built? (+SHA)` from the merge / commit evidence.
- `Verified? (mocked)` from the test / CI evidence (a ref, not a bare ✅).
- `Live-verified?` **only** with an evidence link + date — **never** mark a step Live-verified without one (anti-watermelon: green ≠ runnable). If there is no live-run evidence, leave it unset with the reason.
- **Derive** the row's `Status` (RAG: `GREEN` / `YELLOW` / `RED` / `—`) from those columns — never hand-set it.
- Stamp the row's open-issue ids + `Updated` date.

**`step_id: ALL` carve-out:** a spine-wide verification/audit child (`step_id: ALL`) rolls up into **every** master row (a documented exception, not one row), applying the same evidence rules per row.

If the step did not complete this session, the row keeps its prior status, this plan's Continuity Log marks it **carried-over**, and the master's open-child pointer keeps referencing this plan. Flag any session child that closes without rolling into its master row as an orphan anomaly.

If the active plan has no master (`plan_role: standalone` or absent), skip this section.

---

### 5. Verify Plan State

After updates, confirm:
- Item statuses match the session's actual outcomes; at most one item is `doing`
- Every open item is accounted for (rolled forward, or plan superseded/abandoned with a reason)
- Continuity Log records each status change and any supersession/abandonment reason
- A `done` plan's done-condition was confirmed by evidence before the status flip
- A `plan_role: session` child rolled up into its master row this session (evidence-linked; no `Live-verified?` without an evidence link + date), or is explicitly marked carried-over (N/A for a standalone plan / no master)

## CRITICAL STEP COMPLETION NOTE

ONLY when the active plan is updated and the completeness / supersession audit is clean, load and read fully {nextStepFile}
