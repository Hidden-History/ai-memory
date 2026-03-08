---
name: discovery
description: 'Discovery phase. Produces the PRD -- the single source of truth for all requirements. Everything built in subsequent phases traces back to this document.'
firstStep: './steps/step-01-assess-existing-inputs.md'
---

# Discovery Phase

**Goal:** Define what is being built and why. Produce the PRD -- the single source of truth for all requirements, features, acceptance criteria, and success metrics. Discovery is not done when a document exists. It is done when the user explicitly approves the scope.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

### Step Chain Overview
1. **step-01** -- Assess what already exists (goals.md, prior docs, audit findings)
2. **step-02** -- Analyst research (if input is thin -- Scenarios B and C)
3. **step-03** -- PM creates PRD draft
4. **step-04** -- Parzival reviews PRD draft
5. **step-05** -- User review and iteration
6. **step-06** -- PRD finalization
7. **step-07** -- Approval gate and route to Architecture

### Discovery Anti-Patterns
These apply across ALL steps in this workflow:
- Never let PM invent requirements not sourced from user input
- Never accept vague acceptance criteria
- Never include implementation details in requirements
- Never skip Analyst research when input is thin
- Never present PRD to user without Parzival's review
- Never treat user feedback as optional
- Never move to Architecture with open questions unresolved
- Never approve scope informally -- explicit approval required

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-DISCOVERY
- Drop on exit: CONSTRAINTS-DISCOVERY
- Exit to: WF-ARCHITECTURE

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
