---
name: 'step-09-prepare-summary'
description: 'Prepare the user-facing summary of what the agent accomplished. Raw agent output never reaches the user.'
---

# Step 9: Prepare User Summary

**Final Step — Agent Dispatch Complete**

## STEP GOAL:

After agent output is accepted, Parzival prepares the summary for the user. Raw agent output never reaches the user directly. The summary is written in Parzival's own words and follows the standard format.

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

- 🎯 Focus on composing the user-facing summary in Parzival's own words
- 🚫 FORBIDDEN to copy or paste agent output directly into the summary
- 💬 Approach: Synthesize verified, reviewed output into the standard 5-section summary format
- 📋 Route to appropriate next workflow based on task type before closing dispatch log

## EXECUTION PROTOCOLS:

- 🎯 Build the 5-section summary from the accepted, verified output
- 💾 Update dispatch log with final status before presenting summary to user
- 📖 No next step — this is the terminal step; route to appropriate next workflow after summary
- 🚫 FORBIDDEN to present summary before dispatch log is updated with final status

## CONTEXT BOUNDARIES:

- Available context: The accepted agent output, the dispatch log for this task, any issues found and resolved, any decisions made
- Focus: Summary composition and dispatch log finalization only
- Limits: Write in Parzival's own words. Never copy-paste agent output. Present only verified, reviewed information.
- Dependencies: Accepted output from step-07, task_id for TaskUpdate confirmation, teammate shutdown confirmed in step-08

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Build the Summary

Compose the user summary covering:
- **COMPLETED:** What the agent accomplished -- in Parzival's words
- **FOUND:** Any issues discovered during the work
- **FIXED:** What was resolved and the verified basis for each fix
- **DECISION NEEDED:** Anything requiring user input
- **NEXT STEP:** Recommended next action with options if applicable

---

### 2. Verify Summary Quality

Before presenting:
- Is this written in Parzival's words -- not copied from agent output?
- Is it accurate -- does it match the verified output?
- Is it concise -- no unnecessary padding?
- Are any needed decisions clearly stated?
- Is the recommended next step specific?

---

### 3. Update Dispatch Log

Record final dispatch entry for this session:
- Agent activated
- Task assigned
- Output received: yes
- Review result: accepted (or number of correction loops)
- Final status: complete
- Task list status: [completed | blocked-then-resolved | skipped — task_id null]
  - If TaskUpdate(completed) was NOT called in step-07 for any reason:
    call TaskUpdate now before updating the dispatch log
  - If task_id is null: note "task list not updated — CLAUDE_CODE_TASK_LIST_ID not configured"

This log feeds into the end-of-session summary and project-status.md update.

---

### 4. Route to Next Workflow

Based on the task type:
- Implementation task: summary feeds into WF-APPROVAL-GATE
- Planning/documentation task: summary may feed directly to user or to next workflow step

---

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — no next step file, agent dispatch cycle ends here
- Update dispatch log with all final status fields before presenting summary to user
- Call TaskUpdate(completed) now if not already called in step-07
- Route to WF-APPROVAL-GATE (implementation) or directly to user/next workflow (planning/docs)
- Mark agent dispatch cycle as complete in project context

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Summary written in Parzival's own words
- All five summary sections addressed (skip any marked N/A)
- Dispatch log updated with final status
- Routed to appropriate next workflow

### ❌ SYSTEM FAILURE:

- Copying agent output into summary
- Missing summary sections
- Not updating dispatch log
- Not routing to next workflow

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
