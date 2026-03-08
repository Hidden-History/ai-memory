---
name: 'step-05-user-review-iteration'
description: 'Present PRD to user for review and iterate until user has no more changes'
nextStepFile: './step-06-prd-finalization.md'
---

# Step 5: User Review and Iteration

## STEP GOAL
Present the reviewed PRD to the user for feedback. Iterate until the user indicates they have no more changes. Every piece of feedback is addressed -- nothing is dismissed.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Reviewed PRD.md, goals.md, Analyst research
- Limits: User feedback drives changes. Parzival does not dismiss feedback. All corrections are batched before sending to PM.

## MANDATORY SEQUENCE

### 1. Present PRD for User Review
Present with key points to review:
- Features included (list Must Have features)
- Features excluded (out of scope list)
- Open questions still needing input
- Success metrics

Ask the user to review:
1. Are all required features included?
2. Is anything included that should be out of scope?
3. Are the acceptance criteria for each feature correct?
4. Are there any requirements that are unclear or ambiguous?
5. Are the priorities (Must/Should/Nice) correct?

### 2. Wait for User Feedback
Halt and wait for user response.

### 3. Process User Feedback
For each piece of feedback:
- Understand exactly what the user wants changed
- Confirm understanding before sending to PM
- Classify change type:
  - **Correction:** Something is wrong -- fix it
  - **Addition:** New requirement -- add with acceptance criteria
  - **Removal:** Something is out of scope -- remove it
  - **Clarification:** Requirement is ambiguous -- sharpen it
  - **Priority change:** Reprioritize -- update priority field

### 4. Send Complete Correction List to PM
Batch all corrections into a single instruction. Dispatch to PM via {workflows_path}/cycles/agent-dispatch/workflow.md. Do not send piecemeal corrections.

### 5. Re-Review After PM Updates
After PM returns the updated PRD:
- Parzival re-reviews against the same checklist from Step 4
- Only then present updated version to user

### 6. Repeat Until Satisfied
Repeat the present-feedback-correct cycle until the user indicates they have no more changes.

## CRITICAL STEP COMPLETION NOTE
ONLY when the user indicates no more changes are needed, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- PRD presented with clear review guidance
- Every piece of user feedback was addressed
- Corrections batched (not piecemeal)
- Updated PRD re-reviewed by Parzival before re-presenting
- Iteration continued until user expressed satisfaction

### FAILURE:
- Dismissing user feedback
- Sending corrections piecemeal to PM
- Presenting updated PRD without Parzival re-review
- Assuming user is satisfied without explicit confirmation
