---
name: 'step-02-analyst-research'
description: 'Define Analyst research scope and dispatch via agent-dispatch cycle'
nextStepFile: './step-03-pm-creates-prd.md'
---

# Step 2: Analyst Research

**Progress: Step 2 of 7** — Next: PM Creates PRD Draft

## STEP GOAL:

Define the research scope for the Analyst agent, then dispatch via the agent-dispatch cycle. The Analyst gathers and organizes the raw material needed for PRD creation -- the PM will write the PRD in the next step.

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

- 🎯 Focus on defining research scope and dispatching Analyst via agent-dispatch cycle
- 🚫 FORBIDDEN to dispatch Analyst directly — must use agent-dispatch workflow
- 💬 Systematic review of research output against all six research areas
- 📋 Resolve all user questions before proceeding to PM PRD creation

## EXECUTION PROTOCOLS:

- 🎯 Prepare comprehensive Analyst instruction covering all six research areas
- 💾 Record any gaps, open questions, and user confirmations before proceeding
- 📖 Load next step only after research is complete and user questions are resolved
- 🚫 FORBIDDEN to proceed with invented requirements or unresolved user questions

## CONTEXT BOUNDARIES:

- Available context: goals.md, any existing docs, scenario classification from Step 1
- Focus: Analyst research scoping and dispatch — not PRD creation
- Limits: Analyst gathers and organizes research. Analyst does NOT write the PRD. No invented requirements -- only what can be sourced.
- Dependencies: Scenario classification from Step 1, goals.md and any existing documents

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Analyst dispatched through agent-dispatch workflow
- All six research areas covered
- Research is organized, not raw notes
- Gaps and open questions explicitly identified
- User questions resolved before proceeding to PRD

### ❌ SYSTEM FAILURE:

- Skipping research when input is thin
- Accepting invented requirements
- Not resolving user questions before PRD creation
- Analyst dispatched directly instead of through agent-dispatch

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
