---
name: 'step-01-determine-type'
description: 'Determine the verification type based on the work item and user input'
nextStepFile: './step-02-load-checklist.md'
---

# Step 1: Determine Verification Type

## STEP GOAL
Identify which verification type to run based on the work item being verified and any explicit user direction.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User's input describing the work item to verify, task tracker at `{oversight_path}/tracking/task-tracker.md`
- Limits: Determine the type only -- do not begin verification

## MANDATORY SEQUENCE

### 1. Identify the Work Item
From the user's input, determine:
- What specific work item is being verified
- Task ID (if referenced)
- What was produced (code, documentation, configuration, etc.)

### 2. Select Verification Type

**If the user explicitly specified a type** (story, code, production), use that type.

**If not specified**, determine from context:

| Work Item Type | Verification Type |
|----------------|-------------------|
| Completed user story or feature | Story verification |
| Code changes, refactoring, bug fixes | Code verification |
| Deployment, release, infrastructure changes | Production verification |

**If ambiguous**, ask the user:
```
Which verification type should I run?
1. **Story** -- verify against acceptance criteria and DONE WHEN
2. **Code** -- verify code quality, standards, and correctness
3. **Production** -- verify deployment readiness and operational checks
```

### 3. Confirm Selection
State the selected verification type and the work item being verified. Proceed only if the user confirms or does not object.

## CRITICAL STEP COMPLETION NOTE
ONLY when the verification type is determined, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Verification type is determined from user input or clarified via question
- Work item is clearly identified
- Ambiguity is resolved before proceeding

### FAILURE:
- Guessing the verification type when ambiguous
- Starting verification before confirming the type
- Combining multiple verification types
