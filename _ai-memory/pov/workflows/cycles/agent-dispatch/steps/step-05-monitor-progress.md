---
name: 'step-05-monitor-progress'
description: 'Monitor teammate progress via idle notifications and TaskList, intervene if needed'
nextStepFile: './step-06-receive-output.md'
---

# Step 5: Monitor Progress

## STEP GOAL
Parzival monitors the teammate's progress while it works. Monitor via teammate idle notifications and TaskList for progress tracking. Intervene immediately if the agent goes out of scope or appears stuck.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The dispatched instruction, the agent's task scope, idle notifications, TaskList status
- Limits: Do not interrupt normal progress. Only intervene when specific conditions are met.

## MANDATORY SEQUENCE

### 1. Monitor via Idle Notifications and TaskList
Track teammate progress through:
- **Idle notifications:** Teammate signals when waiting for input or when done
- **TaskList:** Check task progress status periodically during long tasks

Monitor for:
- Is the agent still progressing?
- Has it hit a blocker it has not reported?
- Is it going out of scope?

### 2. Intervene Immediately If
- Agent appears to be working outside defined scope
- Agent is making assumptions it should be flagging
- Agent output is heading in a direction that contradicts project files
- Agent appears stuck without reporting a blocker

### 3. Do NOT Interrupt If
- Agent is progressing normally within scope
- Agent is asking clarifying questions (respond, do not redirect)

### 4. Handle Out-of-Scope Detection
If agent begins working outside defined scope:
1. Send a message to the agent immediately via SendMessage: "Stop -- that is outside scope for this task. Scope is limited to [IN SCOPE items from instruction]. Please complete only what was specified."
2. Log that the scope breach occurred
3. If scope breach was caused by ambiguous instruction: revise instruction and re-send

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
- Resume task

## CRITICAL STEP COMPLETION NOTE
ONLY when the agent signals completion (via idle notification or explicit completion message), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Progress tracked via idle notifications and TaskList
- Out-of-scope work detected and stopped immediately
- Blockers assessed and resolved (or escalated) promptly
- Normal progress not interrupted

### FAILURE:
- Not monitoring agent progress
- Missing out-of-scope work
- Ignoring reported blockers
- Interrupting normal agent progress
- Not escalating unresolvable blockers to user
