---
name: 'step-07-accept-or-loop'
description: 'Accept verified output or send correction instruction back to the agent'
nextStepFile: './step-08-shutdown-teammate.md'
correctionTemplate: '../../../../skills/aim-agent-lifecycle/templates/agent-correction.template.md'
---

# Step 7: Accept or Loop

**Progress: Step 7 of 9** — Next: Shut Down Teammate

## STEP GOAL:

Based on the output review from step-06, either accept the output (all checks pass) or send a correction instruction back to the agent. The correction loop continues until output meets all criteria.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on binary decision: accept all-pass output or send specific correction instruction
- 🚫 FORBIDDEN to accept output with any remaining check failures
- 💬 Approach: Corrections must be specific with cited locations and requirements
- 📋 Track correction loop count — multiple loops may indicate instruction quality issue

## EXECUTION PROTOCOLS:

- 🎯 Accept output (all checks pass) or build and send correction instruction using skills/aim-agent-lifecycle/templates/agent-correction.template.md
- 💾 Record correction loops, issues per loop, and final acceptance state
- 📖 On acceptance, load next step; on correction, return to step-05 for monitoring
- 🚫 FORBIDDEN to accept partial output or send vague corrections without specific locations

## CONTEXT BOUNDARIES:

- Available context: The output review result from step-06, the original instruction, the agent's output
- Focus: Accept/reject decision and correction construction only
- Limits: Only accept output when ALL checks pass. Corrections must be specific with cited requirements.
- Dependencies: Output review result from step-06 and original instruction from step-01

## Sequence of Instructions (Do not deviate, skip, or optimize)

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
- Return to step-02 (create team) to spawn the fresh agent, then step-05 (monitor)
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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Output accepted only when all criteria are met
- Corrections are specific with locations and requirements
- Correction loops are tracked
- No partial acceptance

### ❌ SYSTEM FAILURE:

- Accepting output with failed checks
- Sending vague corrections without specific issues
- Not tracking correction loops
- Accepting partial output

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
