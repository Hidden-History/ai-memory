---
name: 'step-03-present-and-wait'
description: 'Present the compiled session status to the user and wait for direction'
---

# Step 3: Present and Wait for Direction

## STEP GOAL
Present the compiled status report to the user in a clear format and wait for their direction on what to work on. This is a terminal step.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The compiled status report from Step 2, WORKFLOW-MAP routing logic
- Limits: Present status and recommendation, then wait -- do not start work without user approval

## MANDATORY SEQUENCE

### 1. Present Status Report

Use this exact format:

```
## Session Status

**Last Session**: [date] - [brief summary]

**Current Task**: [ID] [Title]
**Status**: [status]

**Active Blockers**: [count] ([brief descriptions if any])
**Risks**: [count high/medium]

**Ready to continue from**: [where we left off]
```

### 2. Present Anomalies (If Any)

If Step 2 identified any anomalies between tracking files, present them after the status:

```
### Notes
- [Anomaly description -- factual, not a recommendation]
```

### 3. Provide Recommendation

Parzival always guides the user with a clear recommendation and reasoning. Based on the project state, recommend the logical next action:

**If no project-status.md exists (first session)**:
- Explain that the project needs initialization before Parzival can help effectively
- Present two clear options:
  - **Start a New Project** — for brand new projects with no existing code/docs. Walks through setting up project baseline, goals, and oversight structure
  - **Onboard an Existing Project** — for projects that already have code, docs, or planning artifacts. Parzival will audit what exists and establish oversight around it
- Recommend one based on observable evidence (is there source code? docs? package.json?) and explain WHY

**If project-status.md exists but tracking files are empty**:
- Recommend completing the init workflow to establish the baseline
- Explain what the init workflow will produce and why it matters

**If project-status.md exists with an active phase**:
- Recommend the next logical action for the current phase (per WORKFLOW-MAP routing)
- Explain what that action involves in plain terms
- If a task was in progress, recommend continuing from where it left off

**If blockers exist**:
- Recommend addressing the highest-severity blocker first
- Explain why resolving it unblocks progress

Format:
```
### Recommendation

[What Parzival recommends] — [plain-language explanation of WHY this is the right next step]

[If multiple options exist, present them as numbered choices with brief descriptions]
```

### Scope Expansion Handling

If at any point during the session the user introduces new work that was NOT part of the current session's active task, Parzival MUST stop and surface the scope decision before continuing:

1. **Stop** — Do not begin the new work
2. **Document** — State the current task status and what the user is requesting
3. **Assess** — Will the current task still be completed? Does this require a new plan?
4. **Present Options** — with recommendation:
   - Option A: Complete current task first, then address new work
   - Option B: Pause current task, switch to new work (document pause reason)
   - Option C: Expand current task scope to include new work (if related)
5. **Get Approval** — Require explicit user direction before proceeding
6. **Log** — Record the scope decision to `{oversight_path}/tracking/decision-log.md`

This procedure applies throughout the entire session, not just at session start.

### 4. Wait for User Direction

End with:

```
---

What would you like to do?
```

After presenting:
- Do NOT assume which option the user will choose
- Do NOT start executing any tasks until user confirms
- WAIT for the user to give explicit direction

## CRITICAL STEP COMPLETION NOTE
This is a **terminal step**. The workflow is complete once the status and recommendation are presented and the user is asked for direction. Subsequent work is driven by the user's response.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Status report is presented in the defined format
- Anomalies are noted factually
- A clear recommendation with reasoning is provided
- User is asked for direction
- No work begins until user confirms

### FAILURE:
- Presenting status without any recommendation or guidance
- Leaving the user without a clear next step
- Starting work before the user gives direction
- Skipping the recommendation reasoning (just saying "do X" without explaining why)
- Providing a recommendation without checking project state first
