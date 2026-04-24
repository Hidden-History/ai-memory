---
name: 'step-04-architect-cohesion'
description: 'Define cohesion check criteria and dispatch Architect via agent-dispatch cycle'
nextStepFile: './step-05-review-findings.md'
---

# Step 4: Architect Cohesion Check

**Progress: Step 4 of 8** — Next: Parzival Reviews All Findings

## STEP GOAL:

Define the cohesion check criteria and dispatch the Architect via the agent-dispatch cycle to verify the architecture is intact across the full feature set. Individual story reviews cannot catch system-level architecture drift.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: architecture.md, all modified files, DEV review report
- Focus: Architect dispatch and receiving cohesion verdict — do not classify findings yet
- Limits: Architect checks cohesion. Parzival classifies findings in next step.
- Dependencies: DEV review report from Step 3 is required

- Prepare six-area cohesion check instruction and dispatch Architect via agent-dispatch cycle
**Behavioral Constraints:**
- FORBIDDEN to dispatch Architect directly — must use agent-dispatch workflow
- Approach: Structured dispatch with architecture.md and DEV report, receive cohesion verdict
- Architect checks cohesion — Parzival classifies findings in next step

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
