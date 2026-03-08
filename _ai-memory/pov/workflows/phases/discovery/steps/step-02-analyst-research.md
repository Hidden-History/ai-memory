---
name: 'step-02-analyst-research'
description: 'Activate Analyst agent for requirements research when input is thin or codebase needs documenting'
nextStepFile: './step-03-pm-creates-prd.md'
---

# Step 2: Analyst Research

## STEP GOAL
Activate the Analyst agent to research and organize the raw material needed for PRD creation. The Analyst gathers and organizes -- the PM will write the PRD in the next step.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: goals.md, any existing docs, scenario classification from Step 1
- Limits: Analyst gathers and organizes research. Analyst does NOT write the PRD. No invented requirements -- only what can be sourced.

## MANDATORY SEQUENCE

### 1. Prepare Analyst Research Instruction
Build the instruction covering six research areas:

1. **User and stakeholder needs** -- Who are the users? What do they need? Pain points?
2. **Functional requirements surface** -- Explicit features from goals.md, implied features, edge cases
3. **Non-functional requirements** -- Performance, scale, security, compliance expectations
4. **Integration requirements** -- External systems, APIs, data sources
5. **Constraints and boundaries** -- What is out of scope, technical constraints, business constraints
6. **Existing behavior documentation** (for existing codebase projects) -- What the current system does, what is complete/partial/missing, known issues

### 2. Dispatch Analyst via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Analyst with the prepared instruction.

### 3. Review Analyst Research Output
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

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Analyst dispatched through agent-dispatch workflow
- All six research areas covered
- Research is organized, not raw notes
- Gaps and open questions explicitly identified
- User questions resolved before proceeding to PRD

### FAILURE:
- Skipping research when input is thin
- Accepting invented requirements
- Not resolving user questions before PRD creation
- Analyst dispatched directly instead of through agent-dispatch
