---
name: architecture
description: 'Architecture phase. Translates the approved PRD into a technical blueprint, produces epics/stories, and confirms implementation readiness.'
firstStep: './steps-c/step-01-assess-inputs.md'
---

# Architecture Phase

**Goal:** Translate the approved PRD into a technical blueprint. Every decision made here -- stack, patterns, data models, API design, infrastructure -- becomes the foundation every DEV agent builds on. Architecture is not done when a document exists. It is done when the Architect confirms implementation readiness and the user approves.

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
1. **step-01** -- Assess inputs and resolve pre-architecture ambiguities
2. **step-02** -- Architect designs architecture
3. **step-03** -- UX design (if applicable -- optional)
4. **step-04** -- Parzival reviews architecture.md
5. **step-05** -- User review and iteration
6. **step-06** -- PM creates epics and stories
7. **step-07** -- Architect runs implementation readiness check
8. **step-08** -- Finalize architecture and epics
9. **step-09** -- Approval gate and route to Planning

### Architecture Anti-Patterns
These apply across ALL steps in this workflow:
- Never allow undocumented architecture decisions
- Never gold-plate -- architecture fits the project scale
- Never write stories before architecture is approved
- Never skip implementation readiness check
- Never let Architect make decisions that violate PRD constraints
- Never accept architecture without reviewing for PRD alignment
- Never treat architecture as fixed when a major PRD requirement is missed
- Never activate PM for stories without first passing architecture to them

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-ARCHITECTURE
- Drop on exit: CONSTRAINTS-ARCHITECTURE
- Exit to: WF-PLANNING

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
