---
name: 'step-07-accept-or-loop'
description: 'Accept verified output or send correction instruction back to the agent'
nextStepFile: './step-08-shutdown-teammate.md'
correctionTemplate: '{skills_path}/aim-agent-lifecycle/templates/agent-correction.template.md'
---

# Step 7: Accept or Loop

**Progress: Step 7 of 9** — Next: Shut Down Teammate

## STEP GOAL:

Based on the output review from step-06, either accept the output (all checks pass) or send a correction instruction back to the agent. The correction loop continues until output meets all criteria.

**Scope:**
- Available context: The output review result from step-06, the original instruction, the agent's output
- Focus: Accept/reject decision and correction construction only
- Limits: Only accept output when ALL checks pass. Corrections must be specific with cited requirements.
- Dependencies: Output review result from step-06 and original instruction from step-01

- Focus on binary decision: accept all-pass output or send specific correction instruction
**Behavioral Constraints:**
- FORBIDDEN to accept output with any remaining check failures
- Approach: Corrections must be specific with cited locations and requirements
- Track correction loop count — multiple loops may indicate instruction quality issue

## Sequence

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
Build a correction instruction using skills/aim-agent-lifecycle/templates/agent-correction.template.md

---

### 2. Build Correction Instruction (if needed)

Using skills/aim-agent-lifecycle/templates/agent-correction.template.md:
- State the review result
- For each issue found:
  - Location (file, function, line if applicable)
  - Problem (what is wrong)
  - Required (what it should be -- cite source if possible)
- Action required: fix all issues, re-review, report back with zero issues
- DO NOT: fix only some issues, introduce new changes outside scope, proceed to other tasks

---

### 3. Send Correction and Monitor

- MUST shutdown the current agent before dispatching fixes (GC-21: fresh agent per task)
- Spawn a FRESH DEV agent to apply fixes -- never send corrections to the same agent
- Spawn FRESH reviewer agents for each re-review pass -- never reuse reviewers
- Return to step-02 (spawn) to spawn the fresh agent, then step-05 (monitor)
- When agent reports completion, return to step-06 (receive output) for re-review
- The loop continues until output is accepted

---

### 4. Track Correction Loops

Record:
- Number of correction loops for this dispatch
- Issues identified in each loop
- Final acceptance state

---

## CRITICAL STEP COMPLETION NOTE

ONLY when output is accepted (all checks pass), load and read fully {nextStepFile}. If corrections are needed, loop back to step-05 for monitoring.
