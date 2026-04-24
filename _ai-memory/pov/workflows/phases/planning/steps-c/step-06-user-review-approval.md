---
name: 'step-06-user-review-approval'
description: 'Present sprint plan to user for review and iterate until satisfied'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: User Review and Approval

**Progress: Step 6 of 7** — Next: Approval Gate

## STEP GOAL:

Present the sprint plan to the user for review. Handle any requested changes. Iterate until the user is satisfied.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Reviewed sprint plan, story files
- Focus: User review and iteration — not execution
- Limits: User feedback drives changes. Re-review after any changes.
- Dependencies: Reviewed sprint plan and story files from Step 5

- Present sprint plan clearly and handle all user feedback before proceeding
**Behavioral Constraints:**
- FORBIDDEN to proceed without explicit user confirmation of satisfaction
- Approach: Present structured sprint plan, iterate on feedback, re-review after changes
- Re-review after any changes before presenting again

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Present Sprint Plan

Present stories grouped by priority with execution order:

"Sprint [N] plan is ready for your review.

SPRINT [N] STORIES ([count] total):

Priority 1 -- Foundation:
  [Story ID]: [title] -- [one line description]

Priority 2 -- Core Features:
  [Story ID]: [title] -- [one line description]

Dependencies noted: [cross-story dependencies]
Estimated scope: [assessment based on story count and complexity]

Please confirm:
  1. Is the story selection correct?
  2. Is the priority order correct?
  3. Any stories to add or remove?
  4. Any stories needing scope adjustment?"

---

### 2. Wait for User Feedback

---

### 3. Process User Feedback

For each change:
- **Story removed:** Update sprint-status.yaml
- **Story added:** Check if story file exists; if not, create it
- **Priority reordered:** Update sprint-status.yaml sequence
- **Story scope changed:** Update story file, re-review
- **Story split:** Create two stories, update epic file

---

### 4. Re-Review After Changes

After any changes:
- Re-review affected story files
- Update sprint-status.yaml
- Confirm sprint is still coherent before presenting again

---

### 5. Repeat Until Satisfied

## CRITICAL STEP COMPLETION NOTE

ONLY when user confirms the sprint plan, load and read fully {nextStepFile}
