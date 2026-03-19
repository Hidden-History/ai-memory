---
name: 'step-09-approval-gate'
description: 'Route to approval gate for architecture sign-off before Sprint Planning begins'
---

# Step 9: Approval Gate

**Final Step — Architecture Complete**

## STEP GOAL:

Route to {workflows_path}/cycles/approval-gate/workflow.md for architecture sign-off. On approval, update project status and route to WF-PLANNING. This is the terminal step.

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

- 🎯 Focus on presenting the complete approval package and communicating the technical lock implications
- 🚫 FORBIDDEN to begin Planning work before receiving explicit user approval
- 💬 Approach: Present package, route through approval gate, handle result and transition cleanly
- 📋 Approving locks the technical foundation — this must be communicated clearly before the user decides

## EXECUTION PROTOCOLS:

- 🎯 Present the full architecture approval package compiled in Step 8
- 💾 Update project-status.md and decisions.md immediately upon approval
- 📖 Route to WF-PLANNING only after approval is confirmed
- 🚫 FORBIDDEN to bypass the approval gate or proceed to Planning without explicit approval

## CONTEXT BOUNDARIES:

- Available context: Architecture approval summary from Step 8
- Focus: Approval gate invocation and routing to WF-PLANNING on approval
- Limits: Do not begin Planning work until approval is received. Approving locks the technical foundation.
- Dependencies: Step 8 complete — finalization done and approval summary prepared

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Architecture Approval Package

**Phase:** Architecture
**Outputs:** architecture.md + epics + implementation readiness confirmed
**Status:** All documents reviewed and cohesion confirmed

**Architecture summary:** Stack, API, Auth, Hosting, Key pattern

**Implementation plan:** Epic count, story count, Must Have coverage, readiness check PASSED

**Key decisions locked in:** Top 5-7 decisions with brief rationale

**Known trade-offs:** Trade-offs the user should explicitly accept

**Next phase: Sprint Planning**
On approval, Parzival will activate the SM agent to initialize sprint planning from the approved epics.

**Important:** Approving this locks the technical foundation. Architecture changes after implementation begins require full impact assessment across all in-progress and completed stories.

---

### 2. Route to Approval Gate

Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- begin Sprint Planning
- **[R] Reject** -- changes needed
- **[H] Hold** -- need to review documents first

---

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md:
   - phases_complete.architecture: true
   - current_phase: planning
   - last_updated: [current date]
   - last_session_summary: "Architecture approved. Beginning Sprint Planning."

2. Update decisions.md with final architecture decisions

3. Confirm to user:
   "Architecture approved. Loading WF-PLANNING.
    Activating SM agent to initialize sprint."

4. Load: {workflows_path}/phases/planning/workflow.md
5. Load: {constraints_path}/planning/ constraints
6. Drop: {constraints_path}/architecture/ constraints

**IF REJECTED:**
- Return to step-05 for user review and iteration

**IF HELD:**
- Wait for user to complete review

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — Architecture phase complete on approval
- Update project-status.md: phases_complete.architecture: true, current_phase: planning
- Route to WF-PLANNING via {workflows_path}/phases/planning/workflow.md on approval
- Drop architecture constraints and load planning constraints on transition

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Approval gate invoked with complete package
- Technical lock implications clearly communicated
- User explicitly approved
- Project status updated
- Clean handoff to WF-PLANNING

### ❌ SYSTEM FAILURE:

- Beginning Planning without explicit approval
- Not communicating technical lock implications
- Bypassing the approval gate

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
