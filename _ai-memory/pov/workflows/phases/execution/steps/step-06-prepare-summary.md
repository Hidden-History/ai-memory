---
name: 'step-06-prepare-summary'
description: 'Compile the story completion summary from review cycle records for user presentation'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Prepare User Summary

## STEP GOAL
After verification passes, compile the story completion summary. This summarizes what was built, how the review cycle went, and confirms all acceptance criteria are satisfied.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Review cycle records, implementation details, acceptance criteria
- Limits: Summary is in Parzival's words, not copied from DEV output.

## MANDATORY SEQUENCE

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

### 2. Verify Summary Accuracy
- Does the summary accurately reflect what happened?
- Are all acceptance criteria listed and confirmed?
- Is the review cycle data accurate?
- Are notable findings genuinely notable (not noise)?

## CRITICAL STEP COMPLETION NOTE
ONLY when the summary is complete and verified, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Summary is in Parzival's words (not DEV output copy)
- All acceptance criteria confirmed satisfied
- Review cycle metrics are accurate
- Notable findings are genuinely notable

### FAILURE:
- Copying DEV output into summary
- Missing acceptance criteria in status list
- Inaccurate review cycle metrics
- Including non-notable items as findings
