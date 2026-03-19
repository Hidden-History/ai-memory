---
name: 'step-04-architect-cohesion'
description: 'Define cohesion check criteria and dispatch Architect via agent-dispatch cycle'
nextStepFile: './step-05-review-findings.md'
---

# Step 4: Architect Cohesion Check

**Progress: Step 4 of 8** — Next: Parzival Reviews All Findings

## STEP GOAL:

Define the cohesion check criteria and dispatch the Architect via the agent-dispatch cycle to verify the architecture is intact across the full feature set. Individual story reviews cannot catch system-level architecture drift.

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

- 🎯 Prepare six-area cohesion check instruction and dispatch Architect via agent-dispatch cycle
- 🚫 FORBIDDEN to dispatch Architect directly — must use agent-dispatch workflow
- 💬 Approach: Structured dispatch with architecture.md and DEV report, receive cohesion verdict
- 📋 Architect checks cohesion — Parzival classifies findings in next step

## EXECUTION PROTOCOLS:

- 🎯 Dispatch Architect via agent-dispatch cycle with architecture.md and DEV review report
- 💾 Record Architect cohesion assessment with CONFIRMED or ISSUES FOUND verdict
- 📖 Load next step only after Architect cohesion assessment is received
- 🚫 FORBIDDEN to proceed without receiving cohesion assessment from Architect

## CONTEXT BOUNDARIES:

- Available context: architecture.md, all modified files, DEV review report
- Focus: Architect dispatch and receiving cohesion verdict — do not classify findings yet
- Limits: Architect checks cohesion. Parzival classifies findings in next step.
- Dependencies: DEV review report from Step 3 is required

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Prepare Cohesion Check Instruction

Architect must cover six cohesion areas:

1. **Architectural pattern compliance** -- patterns documented in architecture.md actually used, deviations identified, contradictions found
2. **Component boundary integrity** -- boundaries maintained as designed, no inappropriate direct dependencies, coupling violations
3. **Data architecture compliance** -- data models as designed, access patterns following documented approach
4. **Security architecture compliance** -- authentication as designed, authorization model correct
5. **Infrastructure alignment** -- code deployable as specified, no contradicting assumptions
6. **Technical debt assessment** -- shortcuts that create architectural debt, patterns making future development harder

---

### 2. Dispatch Architect via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Architect. Provide architecture.md, all modified files, and DEV review report.

---

### 3. Receive Cohesion Assessment

Architect returns:

**COHESION: CONFIRMED** -- Architecture is intact across milestone.

**COHESION: ISSUES FOUND** -- For each issue:
- Location: [file/component]
- Violation: [which architecture decision is violated]
- Impact: [what this affects]
- Required fix: [what needs to change]

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN Architect cohesion assessment is received, will you then read fully and follow: `{nextStepFile}` to begin reviewing all findings.

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All six cohesion areas reviewed
- Clear CONFIRMED or ISSUES FOUND verdict
- Issues documented with architectural basis
- Dispatched through agent-dispatch workflow

### ❌ SYSTEM FAILURE:

- Skipping cohesion check
- Accepting vague cohesion assessment
- Not providing DEV review report as context
- Architect dispatched directly

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
