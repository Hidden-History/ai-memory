---
name: 'step-03-present-and-wait'
description: 'Present the compiled session status to the user and wait for direction'
---

# Step 3: Present and Wait for Direction

**Final Step — Session Start Complete**

## STEP GOAL:

Present the compiled status report to the user in a clear format and wait for their direction on what to work on. This is a terminal step.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The compiled status report from Step 2, WORKFLOW-MAP routing logic
- Focus: Presentation and user direction only — do not start work
- Limits: Present status and recommendation, then wait — do not start work without user approval
- Dependencies: Compiled status report from Step 2

- Present the compiled status report and recommendation, then wait for user direction
**Behavioral Constraints:**
- FORBIDDEN to start any work before user gives explicit direction
- Approach: Clear presentation with recommendation and reasoning — then wait
- This is a TERMINAL step — no nextStepFile, workflow ends after user is asked for direction

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Present Anomalies (If Any)

If Step 2 identified any anomalies between tracking files, present them after the status:

```
### Notes
- [Anomaly description -- factual, not a recommendation]
```

---

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

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) `## SCOPE EXPANSION PROTOCOL`. This protocol applies throughout the session, not just at session start — Parzival must surface scope decisions whenever the user introduces new work.

---

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

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Present status report and recommendation fully before waiting
- Suggest next workflows or phase transitions based on project state
- No nextStepFile — user direction drives all subsequent work
