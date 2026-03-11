---
name: 'step-07-accept-or-loop'
description: 'Accept verified output or send correction instruction back to the agent'
nextStepFile: './step-08-shutdown-teammate.md'
correctionTemplate: '../templates/agent-correction.md'
---

# Step 7: Accept or Loop

## STEP GOAL
Based on the output review from step-06, either accept the output (all checks pass) or send a correction instruction back to the agent. The correction loop continues until output meets all criteria.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The output review result from step-06, the original instruction, the agent's output
- Limits: Only accept output when ALL checks pass. Corrections must be specific with cited requirements.

## MANDATORY SEQUENCE

### 1. Determine Acceptance or Correction

**Accept Output when ALL of the following are true:**
- All DONE WHEN criteria are met
- All review checks pass
- Zero legitimate issues remain (implementation) or zero inaccuracies (docs)
- Output is complete -- not partial

If accepted:
- If task_id is set: call **TaskUpdate** with task_id, status = `completed`
  - This fires the TaskCompleted hook (if configured) and makes completion visible cross-session
  - If task_id is null (CLAUDE_CODE_TASK_LIST_ID not set): skip and note in dispatch log
- Proceed to {nextStepFile}

**Send Correction when ANY check fails:**
Build a correction instruction using {correctionTemplate}

### 2. Build Correction Instruction (if needed)
Using {correctionTemplate}:
- State the review result
- For each issue found:
  - Location (file, function, line if applicable)
  - Problem (what is wrong)
  - Required (what it should be -- cite source if possible)
- Action required: fix all issues, re-review, report back with zero issues
- DO NOT: fix only some issues, introduce new changes outside scope, proceed to other tasks

### 3. Send Correction and Monitor
- Send the correction instruction to the agent via SendMessage
- Return to step-05 (monitor) while agent applies fixes
- When agent reports completion, return to step-06 (receive output) for re-review
- The loop continues until output is accepted

### 4. Track Correction Loops
Record:
- Number of correction loops for this dispatch
- Issues identified in each loop
- Final acceptance state

## CRITICAL STEP COMPLETION NOTE
ONLY when output is accepted (all checks pass), load and read fully {nextStepFile}. If corrections are needed, loop back to step-05 for monitoring.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Output accepted only when all criteria are met
- Corrections are specific with locations and requirements
- Correction loops are tracked
- No partial acceptance

### FAILURE:
- Accepting output with failed checks
- Sending vague corrections without specific issues
- Not tracking correction loops
- Accepting partial output
