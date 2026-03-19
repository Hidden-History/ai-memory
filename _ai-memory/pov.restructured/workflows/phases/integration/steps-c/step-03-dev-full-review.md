---
name: 'step-03-dev-full-review'
description: 'Define integration review scope and dispatch DEV via agent-dispatch cycle'
nextStepFile: './step-04-architect-cohesion.md'
---

# Step 3: DEV Full Review Pass

**Progress: Step 3 of 8** — Next: Architect Cohesion Check

## STEP GOAL:

Define the integration review scope and dispatch DEV via the agent-dispatch cycle. DEV performs a comprehensive code review across the entire feature set -- not individual stories. This reviews everything: feature completeness, integration correctness, cross-feature consistency, test coverage, security, and performance.

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

- 🎯 Prepare comprehensive review instruction covering all seven areas — then dispatch via agent-dispatch cycle
- 🚫 FORBIDDEN to dispatch DEV directly — must use agent-dispatch workflow
- 💬 Approach: Structured dispatch with full context, receive and record report
- 📋 DEV reviews all seven areas — integration-level scope, not individual stories

## EXECUTION PROTOCOLS:

- 🎯 Dispatch DEV via agent-dispatch cycle with full context and seven-area review instruction
- 💾 Record DEV review report with issues and test plan pass/fail results
- 📖 Load next step only after DEV review report is fully received
- 🚫 FORBIDDEN to proceed without receiving DEV review report with test plan results

## CONTEXT BOUNDARIES:

- Available context: Integration scope, test plan, all story files, PRD.md, architecture.md, project-context.md
- Focus: DEV dispatch and receiving review report — do not classify findings yet
- Limits: DEV reviews and reports. Parzival classifies findings in Step 5.
- Dependencies: Integration scope (Step 1) and test plan (Step 2) are required

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare DEV Integration Review Instruction

DEV must cover seven review areas:

1. **Feature completeness** -- all acceptance criteria across all stories satisfied, no PRD gaps, no partial implementations
2. **Integration correctness** -- components interact correctly at boundaries, data passed correctly, error states handled at integration points
3. **Cross-feature consistency** -- patterns consistent, naming consistent, error handling consistent, auth applied consistently
4. **Test coverage** -- integration point tests exist, test plan scenarios implemented, edge cases covered across boundaries
5. **Security across full flow** -- auth enforced consistently, input validation consistent, sensitive data protected throughout
6. **Performance considerations** -- N+1 query patterns, unnecessary data fetching, bottlenecks at integration level
7. **Pre-existing issues** -- issues in existing code that interact with new features

Provide: all story IDs, all files created/modified, all component boundaries, PRD.md, architecture.md, project-context.md, test plan.

---

### 2. Dispatch DEV via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate DEV with the review instruction.

---

### 3. Receive Review Report

DEV returns:
- Issues found with location, description, scope, severity
- Test plan execution results: PASS or FAIL for each item
- Or explicit "zero issues found" confirmation

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN DEV review report is received, will you then read fully and follow: `{nextStepFile}` to begin the Architect cohesion check.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- DEV reviewed all seven areas
- Test plan items executed with clear pass/fail
- Issues reported with specific locations
- Dispatched through agent-dispatch workflow

### ❌ SYSTEM FAILURE:

- Spot-checking instead of full review
- Not executing test plan items
- Vague issue descriptions
- DEV dispatched directly

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
