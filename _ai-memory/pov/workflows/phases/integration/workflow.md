---
name: integration
description: 'Integration and quality gate phase. Full review across the entire feature set to verify everything works together before release.'
firstStep: './steps/step-01-establish-scope.md'
---

# Integration Phase

**Goal:** Verify that everything works together. Individual stories have been completed and reviewed in isolation. Integration verifies the sum of the parts is coherent, complete, and production-ready. Integration does not exit until the full test plan passes, the Architect confirms cohesion, zero legitimate issues remain, and the user approves.

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
1. **step-01** -- Establish integration scope
2. **step-02** -- Prepare integration test plan
3. **step-03** -- DEV full review pass
4. **step-04** -- Architect cohesion check
5. **step-05** -- Parzival reviews all findings
6. **step-06** -- Fix cycle for all legitimate issues
7. **step-07** -- Final verification pass
8. **step-08** -- Approval gate and route to Release or Execution

### Integration Anti-Patterns
These apply across ALL steps in this workflow:
- Never run integration as a spot check on a few files
- Never skip the test plan and just run a code review
- Never accept "mostly passing" test plan
- Never skip Architect cohesion check
- Never treat integration issues as optional to fix
- Never re-run only fixed sections of the test plan
- Never present raw DEV or Architect output to user
- Never start release before integration approval

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-INTEGRATION
- Drop on exit: CONSTRAINTS-INTEGRATION
- Exit to: WF-RELEASE (pass) or WF-EXECUTION (issues found)

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
