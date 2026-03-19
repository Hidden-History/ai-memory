---
name: 'step-05-monitor-progress'
description: 'Monitor teammate progress via idle notifications and TaskList, intervene if needed'
nextStepFile: './step-06-receive-output.md'
---

# Step 5: Monitor Progress

**Progress: Step 5 of 9** — Next: Receive and Review Output

## STEP GOAL:

Parzival monitors the teammate's progress while it works. Monitor via teammate idle notifications and TaskList for progress tracking. Intervene immediately if the agent goes out of scope or appears stuck.

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

- 🎯 Focus on monitoring scope adherence and progress — intervene only when required
- 🚫 FORBIDDEN to interrupt normal agent progress without specific trigger conditions
- 💬 Approach: Passive monitoring until intervention condition is triggered
- 📋 Blocker escalation must include options and Parzival's recommendation before presenting to user

## EXECUTION PROTOCOLS:

- 🎯 Monitor via idle notifications and TaskList; intervene on scope breach or unreported blocker
- 💾 Document any scope breaches, blockers escalated, and resolutions provided
- 📖 Load next step only when agent signals completion via idle notification or explicit message
- 🚫 FORBIDDEN to accept completion signal without confirming agent task is within scope

## CONTEXT BOUNDARIES:

- Available context: The dispatched instruction, the agent's task scope, idle notifications, TaskList status
- Focus: Progress monitoring and intervention only — do not accept output yet
- Limits: Do not interrupt normal progress. Only intervene when specific conditions are met.
- Dependencies: Dispatched instruction from step-04, active teammate from step-03

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Monitor via Idle Notifications and TaskList

Track teammate progress through:
- **Idle notifications:** Teammate signals when waiting for input or when done
- **TaskList:** Check task progress status periodically during long tasks

Monitor for:
- Is the agent still progressing?
- Has it hit a blocker it has not reported?
- Is it going out of scope?

---

### 2. Intervene Immediately If

- Agent appears to be working outside defined scope
- Agent is making assumptions it should be flagging
- Agent output is heading in a direction that contradicts project files
- Agent appears stuck without reporting a blocker

---

### 3. Do NOT Interrupt If

- Agent is progressing normally within scope
- Agent is asking clarifying questions (respond, do not redirect)

---

### 4. Handle Out-of-Scope Detection

If agent begins working outside defined scope:
1. Send a message to the agent immediately via SendMessage: "Stop -- that is outside scope for this task. Scope is limited to [IN SCOPE items from instruction]. Please complete only what was specified."
2. Log that the scope breach occurred
3. If scope breach was caused by ambiguous instruction: revise instruction and re-send

---

### 5. Handle Blocker Escalation

When an agent reports a blocker that Parzival cannot resolve:

**Step A:** Assess the blocker
- Can project files resolve this?
- Can WF-RESEARCH-PROTOCOL resolve this?

**Step B:** If resolvable -- provide resolution with citation
- Send resolution to agent via SendMessage
- Document what was resolved and how

**Step C:** If not resolvable -- escalate to user
- Pause all agent work on this task
- If task_id is set: call **TaskUpdate** with task_id, status = `blocked`
  - This signals the TaskCompleted hook that the task is blocked (not abandoned)
- If task_id is null: skip TaskUpdate, note "task list not updated — CLAUDE_CODE_TASK_LIST_ID not configured" in blocker log
- Prepare escalation summary:
  - Current task
  - Which agent hit the blocker
  - Specific description of what is blocking
  - What project files were reviewed
  - Options with trade-offs
  - Parzival's recommendation
  - What is needed from user

**Step D:** Once user provides resolution
- Document the decision in project files
- Send resolution to agent via SendMessage
- If task_id is set: call **TaskUpdate** with task_id, status = `in_progress` to resume
- If task_id is null: skip TaskUpdate, note "task list not updated — CLAUDE_CODE_TASK_LIST_ID not configured" in dispatch log
- Resume task

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the agent signals completion (via idle notification or explicit completion message), load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Progress tracked via idle notifications and TaskList
- Out-of-scope work detected and stopped immediately
- Blockers assessed and resolved (or escalated) promptly
- Normal progress not interrupted

### ❌ SYSTEM FAILURE:

- Not monitoring agent progress
- Missing out-of-scope work
- Ignoring reported blockers
- Interrupting normal agent progress
- Not escalating unresolvable blockers to user

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
