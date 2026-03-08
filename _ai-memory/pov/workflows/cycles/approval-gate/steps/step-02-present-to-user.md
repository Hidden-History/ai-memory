---
name: 'step-02-present-to-user'
description: 'Present the approval package to the user in the appropriate format and wait for explicit response'
nextStepFile: './step-03-process-response.md'
taskApprovalTemplate: '../templates/task-approval.md'
phaseApprovalTemplate: '../templates/phase-milestone-approval.md'
decisionPointTemplate: '../templates/decision-point.md'
---

# Step 2: Present to User

## STEP GOAL
Present the assembled approval package to the user using the correct format for the approval type (task, phase milestone, or decision point). Wait for an explicit response. Never proceed without it.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The assembled approval package from step-01, the approval type
- Limits: Present ONE approval at a time. Never stack multiple decisions. Always wait for explicit response.

## MANDATORY SEQUENCE

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

### 2. Handle Pushback on the Gate
If the user tries to skip the approval gate ("just proceed," "that's fine"):
- Provide an abbreviated summary in 2-3 sentences
- Ask for a quick confirm: "proceed to [next step]?"
- A single explicit "yes" satisfies the gate for straightforward approvals
- The gate still runs -- it may be fast, but it always runs

### 3. Wait for Explicit Response
Halt and wait. Do not proceed without the user's explicit response. Do not interpret silence as approval.

## CRITICAL STEP COMPLETION NOTE
ONLY when the user provides an explicit response (Approve, Reject, or Hold), load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Correct format used for the approval type
- One approval presented at a time
- User provided explicit response before proceeding
- Pushback handled gracefully while maintaining the gate

### FAILURE:
- Stacking multiple decisions in one presentation
- Using wrong format for the approval type
- Proceeding without explicit user response
- Interpreting silence as approval
- Skipping the gate entirely
