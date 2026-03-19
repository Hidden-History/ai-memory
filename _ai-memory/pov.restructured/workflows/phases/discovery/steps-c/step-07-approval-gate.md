---
name: 'step-07-approval-gate'
description: 'Route to approval gate for explicit PRD sign-off before Architecture phase begins'
---

# Step 7: Approval Gate

**Final Step — Discovery Complete**

## STEP GOAL:

Route to {workflows_path}/cycles/approval-gate/workflow.md for explicit PRD sign-off. On approval, update project status and route to WF-ARCHITECTURE. This is the terminal step.

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

- 🎯 Focus on presenting complete approval package and routing through approval gate
- 🚫 FORBIDDEN to begin Architecture work before explicit user approval
- 💬 Present scope lock implications clearly before user approves
- 📋 All three approval outcomes (Approve/Reject/Hold) must be handled explicitly

## EXECUTION PROTOCOLS:

- 🎯 Invoke approval-gate workflow with complete, accurate approval package
- 💾 Update project-status.md and decisions.md immediately upon approval
- 📖 Route to WF-ARCHITECTURE on approval; return to step-05 on rejection
- 🚫 FORBIDDEN to route to Architecture phase without explicit user approval

## CONTEXT BOUNDARIES:

- Available context: Finalized PRD.md, scope summary, key decisions summary
- Focus: Approval gate execution and phase transition to Architecture
- Limits: Do not begin Architecture work until approval is received. Signing off locks scope.
- Dependencies: Complete approval package from Step 6 finalization

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Discovery Approval Package

**Phase:** Discovery
**Output:** PRD.md
**Status:** PRD complete and reviewed -- ready for sign-off

**Scope summary:**
- Must Have features: [count and brief list]
- Should Have: [count and brief list]
- Nice to Have: [count and brief list]
- Explicitly out of scope: [key exclusions]

**Key decisions locked in:**
[What signing off commits to -- scope, priorities, success metrics]

**Open questions:**
[Any remaining or 'None -- all questions resolved']

**Next phase: Architecture**
On approval, Parzival will activate the Architect agent to design the technical architecture based on this PRD. Deliverable: architecture.md.

**Important:** Signing off on this PRD locks in scope. Changes after this point require a formal scope change that will be assessed for impact on architecture and timeline.

---

### 2. Route to Approval Gate

Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin Architecture phase
- **[R] Reject** -- more changes needed
- **[H] Hold** -- need more time to review

---

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - phases_complete.discovery: true
   - current_phase: architecture
   - last_updated: [current date]
   - last_session_summary: "PRD approved. Beginning Architecture phase."

2. Update decisions.md with key PRD decisions

3. Confirm to user:
   "PRD approved. Loading WF-ARCHITECTURE.
    Activating Architect agent to design technical architecture."

4. Load: {workflows_path}/phases/architecture/workflow.md
5. Load: {constraints_path}/architecture/ constraints
6. Drop: {constraints_path}/discovery/ constraints

**IF REJECTED:**
- Return to step-05 for additional user review and iteration

**IF HELD:**
- Wait for user to complete review
- Resume approval process when ready

## SCOPE CHANGE PROTOCOL (POST-APPROVAL)

If the user requests a scope change after PRD approval, follow this protocol:

1. **Capture the change request** — document exactly what is being requested
2. **Impact assessment** — evaluate how the change affects:
   - Existing PRD requirements (additions, modifications, removals)
   - Architecture decisions already made (if in Architecture phase)
   - Stories already written or in progress (if in Planning/Execution)
   - Timeline and sprint scope
3. **Classify the change**:
   - **Minor**: Does not affect architecture or existing stories -> update PRD, note the change
   - **Moderate**: Affects architecture or multiple stories -> requires Architect review and re-assessment
   - **Major**: Fundamentally changes project direction -> requires full re-planning from affected phase
4. **Present assessment to user** with recommendation and tradeoffs
5. **Get explicit user approval** before implementing any scope change

This protocol applies even after PRD sign-off. Scope changes are allowed but must be assessed, not silently absorbed.

## TERMINATION STEP PROTOCOLS:

- This is the TERMINAL step of the Discovery phase — no nextStepFile exists in this workflow
- On APPROVED: Update project-status.md (phases_complete.discovery: true, current_phase: architecture), update decisions.md with key PRD decisions, load WF-ARCHITECTURE, load architecture constraints, drop discovery constraints
- On REJECTED: Return to step-05-user-review-iteration.md — do not proceed to Architecture
- On HELD: Pause workflow completely — wait for user to resume the approval process; do not load any next step

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Approval gate invoked with complete package
- Scope implications clearly communicated
- User explicitly approved before Architecture work began
- Project status updated accurately
- Clean handoff to WF-ARCHITECTURE

### ❌ SYSTEM FAILURE:

- Beginning Architecture without explicit approval
- Not communicating scope lock implications
- Bypassing the approval gate
- Not updating project-status.md

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
