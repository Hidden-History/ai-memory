---
name: 'step-02-present-to-user'
description: 'Present the approval package to the user in the appropriate format and wait for explicit response'
nextStepFile: './step-03-process-response.md'
taskApprovalTemplate: '{workflows_path}/cycles/approval-gate/templates/task-approval.md'
phaseApprovalTemplate: '{workflows_path}/cycles/approval-gate/templates/phase-milestone-approval.md'
decisionPointTemplate: '{workflows_path}/cycles/approval-gate/templates/decision-point.md'
---

# Step 2: Present to User

**Progress: Step 2 of 4** — Next: Process User Response

## STEP GOAL:

Present the assembled approval package to the user using the correct format for the approval type (task, phase milestone, or decision point). Wait for an explicit response. Never proceed without it.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The assembled approval package from step-01, the approval type
- Focus: Presentation and response collection only — do not process the response yet
- Limits: Present ONE approval at a time. Never stack multiple decisions. Always wait for explicit response.
- Dependencies: Completed approval package from step-01

- Focus on presenting one approval at a time in the correct format
**Behavioral Constraints:**
- FORBIDDEN to stack multiple decisions or proceed without explicit user response
- Approach: Clear structured presentation, wait for explicit response
- Handle pushback gracefully while maintaining the gate

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Select and Apply Presentation Format

**For Task Completion (after WF-REVIEW-CYCLE):**
Use {taskApprovalTemplate} containing:
- Task name, sprint, status
- What was completed (plain language, 2-4 sentences)
- Review summary (passes, issues found/fixed, final status)
- Issues fixed (if applicable -- skip if pass 1 was clean)
- Decisions needed (if applicable -- skip if none)
- Next step recommendation
- User options: [A] Approve, [R] Reject, [H] Hold

**For Phase Milestone (end of a phase):**
Use {phaseApprovalTemplate} containing:
- Phase name, primary deliverable, status
- Phase summary (3-6 sentences)
- Deliverables list with file paths and descriptions
- Key decisions made during this phase
- Assumptions and open questions (if any)
- Next phase and first action on approval
- User options: [A] Approve, [R] Reject, [H] Hold

**For Decision Point (mid-workflow):**
Use {decisionPointTemplate} containing:
- Current context and what is blocking
- The specific decision needed (one at a time)
- Options with pros, cons, and impact for each
- Parzival's recommendation with reasoning
- Open prompt for user decision

---

### 2. Handle Pushback on the Gate

If the user tries to skip the approval gate ("just proceed," "that's fine"):
- Provide an abbreviated summary in 2-3 sentences
- Ask for a quick confirm: "proceed to [next step]?"
- A single explicit "yes" satisfies the gate for straightforward approvals
- The gate still runs -- it may be fast, but it always runs

---

### 3. Wait for Explicit Response

Halt and wait. Do not proceed without the user's explicit response. Do not interpret silence as approval.

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the user provides an explicit response (Approve, Reject, or Hold), load and read fully `{nextStepFile}`
