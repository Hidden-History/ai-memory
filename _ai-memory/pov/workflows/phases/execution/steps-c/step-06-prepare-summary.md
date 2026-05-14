---
name: 'step-06-prepare-summary'
description: 'Compile the story completion summary from review cycle records for user presentation'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Prepare User Summary

**Progress: Step 6 of 7** — Next: Approval Gate

## STEP GOAL:

After verification passes, compile the story completion summary. This summarizes what was built, how the review cycle went, and confirms all acceptance criteria are satisfied.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Review cycle records, implementation details, acceptance criteria
- Focus: Summary compilation only — do not present or request approval yet
- Limits: Summary is in Parzival's words, not copied from DEV output.
- Dependencies: All four-source verification passed from Step 5

- Focus only on compiling the accurate story completion summary
**Behavioral Constraints:**
- FORBIDDEN to copy DEV output directly into the summary
- Approach: Compile in Parzival's words with all required fields accurate
- Verify summary accuracy against actual review cycle records before proceeding

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Compile Story Completion Summary

**Story:** [Story ID] -- [Title]
**Sprint:** [N]

**Implementation:**
- What was built (concrete description)
- Files created: [list]
- Files modified: [list]
- Implementation approach (key decisions made, if any)

**Review cycle:**
- Total passes: [N]
- Total issues found: [N]
- Legitimate issues fixed: [N]
- Non-issues documented: [N]
- Pre-existing issues fixed: [N]
- Final status: Zero legitimate issues confirmed

**Acceptance criteria status:**
- [Criterion 1]: Satisfied
- [Criterion 2]: Satisfied
- [Criterion N]: Satisfied
(All criteria must show satisfied)

**Notable findings:**
- Significant pre-existing issues fixed
- Implementation decisions affecting architecture.md
- decisions.md updates made

---

### 2. Verify Summary Accuracy

- Does the summary accurately reflect what happened?
- Are all acceptance criteria listed and confirmed?
- Is the review cycle data accurate?
- Are notable findings genuinely notable (not noise)?

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the summary is complete and verified, will you then read fully and follow: `{nextStepFile}` to begin the approval gate.
