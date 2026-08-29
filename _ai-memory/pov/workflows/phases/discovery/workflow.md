---
name: discovery
description: 'Discovery phase. Produces the PRD -- the single source of truth for all requirements. Everything built in subsequent phases traces back to this document.'
firstStep: './steps-c/step-01-assess-existing-inputs.md'
---

# Discovery Phase

**Goal:** Define what is being built and why. Produce the PRD -- the single source of truth for all requirements, features, acceptance criteria, and success metrics. Discovery is not done when a document exists. It is done when the user explicitly approves the scope.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

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

<!-- ai-memory:degraded-declaration
capability: cap:phase-discovery
depends_on: bmad
degraded_behaviour: Runs discovery without the BMAD PM and analyst personas and reports each as unavailable.
degraded_test: not-yet-enforced
ai-memory:end-degraded-declaration -->
