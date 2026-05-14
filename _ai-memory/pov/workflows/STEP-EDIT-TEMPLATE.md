---
name: 'STEP-EDIT-TEMPLATE'
description: 'Shared edit mode template — standard assess-and-apply process for all workflows. Referenced by each workflow step-e-01-assess.md and step-e-02-apply-edit.md stub.'
---

# Shared Edit Mode Template

This file defines the standard two-step edit mode process used by every workflow. Each workflow's `steps-e/` stubs reference this file rather than repeating identical content.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

---

## EDIT ASSESSMENT (step-e-01)

**Goal:** Assess current output, identify what needs to change, and propose specific edits for user approval.

**Behavioral Constraints:**
- FORBIDDEN to apply any changes in this step — assessment only
- Approach: Analytical — present findings with specific file:line references
- All proposed changes require user approval before proceeding

### 1. Load Current Output

Read the workflow output files that need editing. If a validation report exists, load it to understand what failed.

---

### 2. Identify Required Changes

For each issue found:
- **File**: Which file needs changing
- **Location**: Specific section or line
- **Current**: What exists now
- **Proposed**: What it should be changed to
- **Reason**: Why this change is needed

---

### 3. Present Change Proposal

**Proposed Changes for [this workflow]:**

| # | File | Change | Reason |
|---|------|--------|--------|
| 1 | [file] | [current → proposed] | [reason] |

**Select an Option:** [C] Approve and Continue to Apply [R] Revise Proposals [X] Cancel Edit

#### Menu Handling Logic:

- IF C: Record approved changes, then proceed to apply step (step-e-02)
- IF R: Revise proposals based on user feedback, redisplay menu
- IF X: Cancel edit mode, return to calling workflow
- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed to apply step when user selects 'C'

---

## EDIT APPLICATION (step-e-02)

**Goal:** Apply only the user-approved changes from the assessment step.

**Behavioral Constraints:**
- FORBIDDEN to make additional unapproved changes
- Report each change as it is applied
- Verify the file is correct after each edit

### 1. Review Approved Changes

Confirm the list of approved changes from the assessment step.

---

### 2. Apply Changes

For each approved change:
1. Read the target file
2. Apply the specific edit
3. Verify the edit was applied correctly
4. Report: "Applied change #N: [description]"

---

### 3. Present Completion Summary

| # | File | Change Applied | Verified |
|---|------|---------------|----------|
| 1 | [file] | [description] | ✓ |

**All approved changes applied.**

- This is a FINAL step — edit mode complete
- Return control to the calling workflow or validation mode
- No further steps to load
