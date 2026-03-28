---
name: aim-agent-lifecycle
description: Shared agent lifecycle management -- send, monitor, review, accept/loop, shutdown, summary
---

# Agent Lifecycle -- Steps 4-9 of Agent Dispatch

**Purpose**: Shared agent lifecycle management used by both aim-agent-dispatch and aim-bmad-dispatch after an agent is activated. Covers sending the instruction, monitoring progress, reviewing output, accepting or looping corrections, shutting down, and preparing the user summary.

---

## Embedded Constraints (Layer 3)

These constraints are active only during agent dispatch work:

- **GC-09 L3**: ALWAYS review agent output against DONE WHEN criteria and project requirements before accepting. Route implementation output through review cycle.
- **GC-10**: ALWAYS present summaries to user -- never raw agent output.
- **GC-12**: ALWAYS loop dev-review until zero legitimate issues confirmed.
- **Max 3 correction loops**: If 3 correction loops do not resolve issues, escalate to user. Do not continue unbounded loops.

---

## Step 4: Send Instruction

### Mode Check

Before sending an instruction, check the dispatch mode set by aim-bmad-dispatch:

**If execution mode** (default): Continue with the execution instructions below — send one-shot instruction, monitor, review, accept/loop, shutdown, summary.

**If planning mode** (BMAD agents in planning phases): Do NOT send a one-shot instruction. Instead, follow the Relay Protocol defined in aim-bmad-dispatch. The agent drives its own workflow — Parzival relays questions and answers between agent and user. Return to this lifecycle at Step 6 (review) when the agent produces its deliverable.

**Non-Claude provider agents** (launched via model-dispatch tmux): Monitor via `tmux capture-pane`. Send instructions/corrections via `tmux send-keys`. The model-dispatch skill's workflow handles the terminal details.

### Execution Mode Instructions

1. Use SendMessage with type: "message" to send the full instruction to the agent
2. Send the complete instruction -- do not abbreviate, summarize, or add conversational preamble
3. Do not modify the instruction format -- agents expect consistency
4. Send once -- do not re-send while agent is working

**Handle clarification requests:**
- Agent asks BEFORE starting: provide clarification with citation if possible. If you cannot clarify without checking project files, check files first. Never guess.
- Agent asks DURING work (blocker): assess if resolvable from project files. If YES, provide resolution with citation via SendMessage. If NO, apply research-protocol. If still unresolved, escalate to user.

Wait for agent acknowledgment before moving to monitoring.

---

## Step 5: Monitor Progress

Track agent progress through:
- Idle notifications: agent signals when waiting for input or when done
- TaskList: check task progress status periodically during long tasks

**Intervene immediately if:**
- Agent appears to be working outside defined scope
- Agent is making assumptions it should be flagging
- Agent output is heading in a direction that contradicts project files
- Agent appears stuck without reporting a blocker

**Do NOT interrupt if:**
- Agent is progressing normally within scope
- Agent is asking clarifying questions (respond, do not redirect)

**Handle out-of-scope detection:**
1. Send a message immediately: "Stop -- that is outside scope for this task. Scope is limited to [IN SCOPE items from instruction]. Please complete only what was specified."
2. Log that the scope breach occurred
3. If scope breach was caused by ambiguous instruction, revise and re-send

**Handle blocker escalation:**
- Assess: can project files or research-protocol resolve it?
- If resolvable: provide resolution with citation
- If not resolvable: pause agent work, update task status to blocked (if task_id set), prepare escalation summary for user (current task, which agent, what is blocking, options with trade-offs, recommendation)
- Once user provides resolution: document decision, send to agent, resume

---

## Step 6: Receive and Review Output

Run the output review checklist:
- Did the agent complete everything listed in DONE WHEN criteria?
- Does the output match the OUTPUT EXPECTED specification?
- Does the output comply with all cited requirements?
- Does the output follow the specified standards?
- Are there any issues in the output that need classification?
- Did the agent stay within scope?
- Is the output complete -- no partial implementations?

**Routing:**
- Implementation output (code, configuration) -- ALWAYS trigger review-cycle. Never accept without full review cycle.
- Planning/documentation output -- review against project requirements manually. Check for completeness, accuracy, internal consistency.

Record the review result: checklist items passed/failed, output type, routing decision.

---

## Step 7: Accept or Loop

**Accept when ALL of the following are true:**
- All DONE WHEN criteria are met
- All review checks pass
- Zero legitimate issues remain (implementation) or zero inaccuracies (docs)
- Output is complete -- not partial

On acceptance:
- Update task status to completed (if task_id set)
- Proceed to shutdown

**Send correction when ANY check fails:**
Build correction instruction using the correction template:
- State the review result
- For each issue: location, problem, required fix (cite source)
- Action required: fix all issues, re-review, report back with zero issues
- DO NOT: fix only some issues, introduce new changes outside scope

MUST shutdown the current agent and spawn a FRESH DEV agent to apply fixes -- never send corrections to the same agent (GC-21). MUST spawn FRESH reviewer agents for each re-review pass. Return to Step 5 (monitor) while the fresh agent applies fixes. When done, return to Step 6 (review) with fresh reviewers for re-review. Loop continues until accepted.

**Track correction loops:**
- Number of loops for this dispatch
- Issues identified per loop
- If loop count reaches 3 without resolution: escalate to user

---

## Step 8: Shutdown Agent

**Shut down when:**
- Agent task is fully complete and accepted
- Agent is no longer needed for current phase
- Session is ending
- Before dispatching fixes or re-reviews (GC-21: fresh agent per task)

**Keep active when:**
- Agent is waiting for Parzival's review decision within the SAME task (step 6/7 loop only)

MUST shutdown and spawn fresh for: new tasks, role changes, fix dispatches, re-review passes. Never reuse an agent across tasks or roles (GC-21).

To shut down:
- Use SendMessage with type: "shutdown_request"
- Wait for confirmation that shutdown completed cleanly
- Verify no pending work remains

**NEVER:**
- Leave an agent active with a pending failed task
- Run a new task with an agent that has unresolved prior output
- Shut down an agent while a task is still in progress

Update dispatch log with final status. Confirm no orphaned agents remain.

---

## Step 9: Prepare User Summary

Write the summary in Parzival's own words -- never copy-paste agent output.

**Summary format:**
- **COMPLETED:** What was accomplished
- **FOUND:** Any issues discovered during the work
- **FIXED:** What was resolved and the verified basis for each fix
- **DECISION NEEDED:** Anything requiring user input
- **NEXT STEP:** Recommended next action with options if applicable

**Quality check before presenting:**
- Written in Parzival's words (not copied from agent)?
- Accurate (matches verified output)?
- Concise (no unnecessary padding)?
- Decisions clearly stated?
- Next step specific?

**Update dispatch log:**
- Agent activated, task assigned, output received, review result, final status
- If TaskUpdate(completed) was not called in Step 7, call it now
- Route to next workflow based on task type

---

## Correction Template

See the correction template at [templates/agent-correction.template.md](templates/agent-correction.template.md) for the exact format to use.
