---
name: 'step-06-prd-finalization'
description: 'Finalize the PRD with a final review pass and prepare for approval gate'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: PRD Finalization

**Progress: Step 6 of 7** — Next: Approval Gate

## STEP GOAL:

When the user has no more changes, run a final review, verify the PRD is saved correctly, and update project tracking files in preparation for the approval gate.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Final PRD.md, project-status.md, decisions.md
- Focus: Final review, file verification, and approval package preparation
- Limits: Do not modify the PRD beyond what the review checklist identifies. The user has signed off on content.
- Dependencies: User-approved PRD.md from Step 5 iteration cycle

- Focus on final review, PRD save verification, and approval package preparation
**Behavioral Constraints:**
- FORBIDDEN to modify PRD content beyond what the final review checklist identifies
- Systematic final pass using the same four checklists from Step 4
- Prepare complete approval package before routing to Step 7

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Run Final Parzival Review

Apply the full review checklist from Step 4 one final time:
- Completeness, quality, accuracy, alignment
- Verify all user feedback has been incorporated

---

### 2. Verify PRD Is Saved Correctly

Confirm PRD.md is at the correct location and accessible.

---

### 3. Update project-status.md

Update key_files.prd with the PRD file path.

---

### 4. Prepare Scope Summary for Approval

Compile:
- Must Have features: [count and brief list]
- Should Have features: [count and brief list]
- Nice to Have features: [count and brief list]
- Explicitly out of scope: [key exclusions]
- Open questions: [any remaining or 'None -- all resolved']

---

### 5. Prepare Key Decisions Summary

Document what signing off on this PRD commits to:
- Scope boundaries
- Priority rankings
- Success metrics
- Constraints acknowledged

## CRITICAL STEP COMPLETION NOTE

ONLY when finalization is complete and approval package is prepared, load and read fully {nextStepFile}
