---
name: 'step-02-analyst-research'
description: 'Define Analyst research scope and dispatch via agent-dispatch cycle'
nextStepFile: './step-03-pm-creates-prd.md'
---

# Step 2: Analyst Research

**Progress: Step 2 of 7** — Next: PM Creates PRD Draft

## STEP GOAL:

Define the research scope for the Analyst agent, then dispatch via the agent-dispatch cycle. The Analyst gathers and organizes the raw material needed for PRD creation -- the PM will write the PRD in the next step.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: goals.md, any existing docs, scenario classification from Step 1
- Focus: Analyst research scoping and dispatch — not PRD creation
- Limits: Analyst gathers and organizes research. Analyst does NOT write the PRD. No invented requirements -- only what can be sourced.
- Dependencies: Scenario classification from Step 1, goals.md and any existing documents

- Focus on defining research scope and dispatching Analyst via agent-dispatch cycle
**Behavioral Constraints:**
- FORBIDDEN to dispatch Analyst directly — must use agent-dispatch workflow
- Systematic review of research output against all six research areas
- Resolve all user questions before proceeding to PM PRD creation

## Sequence of Instructions (Do not deviate, skip, or optimize)

### Parzival's Responsibility (Layer 1)

#### 1. Prepare Analyst Research Instruction

Build the instruction covering six research areas:

1. **User and stakeholder needs** -- Who are the users? What do they need? Pain points?
2. **Functional requirements surface** -- Explicit features from goals.md, implied features, edge cases
3. **Non-functional requirements** -- Performance, scale, security, compliance expectations
4. **Integration requirements** -- External systems, APIs, data sources
5. **Constraints and boundaries** -- What is out of scope, technical constraints, business constraints
6. **Existing behavior documentation** (for existing codebase projects) -- What the current system does, what is complete/partial/missing, known issues

---

### Execution (via agent-dispatch cycle)

#### 2. Dispatch Analyst via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Analyst with the prepared instruction.

---

### Parzival's Responsibility (Layer 1)

#### 3. Review Analyst Research Output

Parzival reviews for:
- Are all research areas covered?
- Are requirements sourced (from goals, user input, codebase)?
- Are gaps and open questions explicitly called out?
- Is anything invented rather than sourced? Remove it.
- Are there questions for the user before PRD begins?

**IF incomplete:** Return to Analyst with specific gaps.
**IF user questions exist:** Ask them before PM begins.
**IF complete:** Proceed to PM PRD creation.

## CRITICAL STEP COMPLETION NOTE

ONLY when research is complete and any user questions are resolved, load and read fully {nextStepFile}
