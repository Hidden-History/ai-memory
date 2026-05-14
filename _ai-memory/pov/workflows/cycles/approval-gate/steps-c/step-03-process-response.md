---
name: 'step-03-process-response'
description: 'Process the user response (Approve, Reject, Hold) and route accordingly'
nextStepFile: './step-04-record-outcome.md'
---

# Step 3: Receive and Process User Response

**Progress: Step 3 of 4** — Next: Record Outcome

## STEP GOAL:

Process the user's explicit response and route to the appropriate action. Approve advances to next step. Reject returns to the appropriate workflow. Hold pauses all work until the user resumes.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The user's response, the approval package, the current task/phase context
- Focus: Response classification and routing only — do not begin execution of next work
- Limits: Only act on the user's explicit response. Never assume, guess, or interpret ambiguous responses.
- Dependencies: User's explicit response from step-02

- Classify and route the user's response to the appropriate action
**Behavioral Constraints:**
- FORBIDDEN to act without confirming understanding of rejection feedback
- Approach: Precise routing based on response type — Approve, Reject, or Hold
- Always confirm rejection interpretation before routing back

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Identify Response Type

**APPROVE:**
1. Record approval with session marker
2. Update project-status.md:
   - Mark task as complete (if task approval)
   - Advance current_phase (if phase approval)
   - Update active_task to next task
   - Update last_session_summary
3. Close the current review cycle records cleanly
4. Route to next workflow per WORKFLOW-MAP.md
5. Confirm next action to user: "Approved. Moving to: [next task/phase]. Starting: [first action]"

**REJECT with Feedback:**
1. Read the feedback in full -- do not proceed until fully understood
2. Classify the feedback:
   - **Quality issue:** Something in the implementation is wrong
     -> Return to WF-REVIEW-CYCLE with specific direction
     -> The issue was missed -- classify per WF-LEGITIMACY-CHECK
   - **Requirements mismatch:** Output does not match what was wanted
     -> Check if requirement was in PRD/story -- was it missed?
     -> If missed: return to WF-EXECUTION with corrected instruction
     -> If not in requirements: this may be a scope change
   - **Scope change:** User wants something different than what was specified
     -> Acknowledge the change, assess impact
     -> Update requirements before re-executing
     -> May require PRD or story update
   - **Preference change:** User prefers a different approach
     -> Confirm this is a preference, not a requirement
     -> If it becomes a documented standard: update project-context.md
     -> Re-execute with updated direction
3. Confirm understanding before acting:
   "Understood. To confirm what I'm taking back:
    [Restate the feedback in Parzival's words]
    [State what will be done to address it]
    [State which workflow will handle it]
    Is this correct?"
4. Wait for confirmation before routing back
5. Never assume you understood the feedback correctly -- confirm first

**HOLD:**
1. Acknowledge the hold immediately:
   "Understood. Task [name] is on hold. No work will proceed until you confirm. When ready, just say 'resume' and I'll pick up from here."
2. Record hold in project-status.md:
   - active_task: [task name] -- ON HOLD
   - notes: [reason for hold if user provided one]
3. Close active agent sessions cleanly
4. Do not start any other work without explicit instruction
5. When user resumes: re-read project-status.md, confirm state, then present the pending approval again before proceeding

---

### 2. Handle Session End with Pending Approval

If a session ends with an approval pending:
- Update project-status.md: active_task -- PENDING APPROVAL
- At next session start: re-present the approval package before any new work begins
- Do not start new tasks while an approval is pending

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the user's response has been fully processed and the appropriate action is determined, load and read fully `{nextStepFile}`
