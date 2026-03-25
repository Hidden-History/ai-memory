---
name: 'step-07-present-and-approve'
description: 'Present the verified baseline to the user and route to approval gate for sign-off before Discovery'
---

# Step 7: Present and Approve

**Final Step — Init New Complete**

## STEP GOAL:

Present the complete project baseline to the user via {workflows_path}/cycles/approval-gate/workflow.md. On approval, update project status and route to WF-DISCOVERY. This is the terminal step of the init-new workflow.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step with 'C', ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus only on presenting the baseline and routing through the approval gate
- 🚫 FORBIDDEN to begin Discovery work before receiving explicit approval
- 💬 Approach: Clear, complete presentation of baseline with structured approval options
- 📋 This is a TERMINAL step -- on approval, route to WF-DISCOVERY; on rejection, route back for corrections

## EXECUTION PROTOCOLS:

- 🎯 Present complete approval package with all baseline information
- 💾 Update project-status.md on approval (baseline_complete: true)
- 📖 Route to WF-DISCOVERY on approval, back to corrections on rejection
- 🚫 DO NOT begin Discovery work until explicit approval is received

## CONTEXT BOUNDARIES:

- Available context: All verified baseline files, complete project foundation summary
- Focus: Approval presentation and gate handling only -- no new creation work
- Limits: Do not begin Discovery work until approval is received. Do not skip the approval gate.
- Dependencies: Step 6 verification must be complete with all checks passed

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Update project-status.md with baseline_complete: true
- Route to WF-DISCOVERY on approval
- Drop init constraints, load discovery constraints

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Approval Package

Build the approval package with the following information:

**Project:** [name]
**Track:** [Quick Flow / Standard Method / Enterprise]
**Status:** Baseline established -- ready to begin Discovery

**Completed items:**
- _ai-memory/ installation verified
- Project baseline files created:
  - project-status.md (project tracking)
  - goals.md (project goals and constraints)
  - project-context.md (stub -- populated in Architecture)
  - decisions.md (decision log -- initialized)
- Claude Code teams session structure established

**Project foundation:**
- Goal: [primary goal]
- Type: [project type]
- Stack: [confirmed decisions / TBD items]
- Constraints: [list or 'none stated']

**Open items for Discovery:**
[List of anything deferred -- to be resolved in Discovery]
[Or: 'None -- all foundation information confirmed']

**Next step on approval:**
Begin WF-DISCOVERY. First action: Activate Analyst for requirements research, then PM for PRD creation. Deliverable: PRD.md -- approved product requirements document.

---

### 2. Route to Approval Gate

Invoke {workflows_path}/cycles/approval-gate/workflow.md with the prepared package.

---

### 3. Present MENU OPTIONS

**Select an Option:**
- **[A] Approve** -- begin Discovery
- **[R] Reject** -- corrections needed
- **[H] Hold** -- user needs to add something first

#### Menu Handling Logic:

- IF A (Approved):
  1. Update project-status.md:
     - baseline_complete: true
     - current_phase: discovery
     - last_updated: [current date]
     - last_session_summary: "Baseline established. Beginning Discovery."
  2. Confirm to user:
     "Foundation approved. Loading WF-DISCOVERY.
      Activating Analyst agent to begin requirements research."
  3. Load: {workflows_path}/phases/discovery/workflow.md
  4. Load: {constraints_path}/discovery/ constraints
  5. Drop: {constraints_path}/init/ constraints

- IF R (Rejected):
  - Receive specific corrections from user
  - Return to the appropriate prior step to address corrections
  - Re-verify (Step 6) after corrections
  - Re-present for approval

- IF H (Hold):
  - Wait for user to provide additional input
  - Incorporate input into baseline files
  - Re-verify (Step 6) after changes
  - Re-present for approval

- IF user asks questions: Answer and redisplay menu

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed when user selects 'A' (Approve), 'R' (Reject), or 'H' (Hold)

## CRITICAL STEP COMPLETION NOTE

This is the TERMINAL step. When approval is received, route to WF-DISCOVERY. Do not load another step file from this workflow.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Complete approval package presented with all required sections
- Approval gate was invoked (not bypassed)
- User explicitly approved before any Discovery work began
- Project status updated accurately on approval
- Clean handoff to WF-DISCOVERY
- Menu presented and user input handled correctly

### ❌ SYSTEM FAILURE:

- Beginning Discovery without explicit user approval
- Bypassing the approval gate
- Not updating project-status.md on approval
- Presenting an incomplete approval package
- Proceeding without user selecting an approval gate option

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
