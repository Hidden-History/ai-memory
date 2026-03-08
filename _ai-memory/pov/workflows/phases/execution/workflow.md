---
name: execution
description: 'Execution phase. Primary operating mode -- every story passes through implementation, review cycle, and user approval. Repeats until sprint is complete.'
firstStep: './steps/step-01-verify-story-requirements.md'
---

# Execution Phase

**Goal:** Execute every story from the sprint plan through a disciplined cycle: implementation instruction, DEV dispatch, review cycle, fix verification, and user approval. This cycle repeats until the sprint is complete. The only exit condition for any story: zero legitimate issues confirmed by review, user approves.

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
1. **step-01** -- Read and verify story requirements against current project state
2. **step-02** -- Prepare DEV implementation instruction
3. **step-03** -- Activate DEV agent via agent-dispatch workflow
4. **step-04** -- Run review cycle until zero legitimate issues
5. **step-05** -- Verify all fixes against project requirements (four-source)
6. **step-06** -- Prepare user summary
7. **step-07** -- Approval gate, then route to next story or milestone

### Story State Machine
Every story moves through: READY -> IN-PROGRESS -> IN-REVIEW -> PENDING-APPROVAL -> COMPLETE
Also possible: BLOCKED, ON-HOLD

### Execution Anti-Patterns
These apply across ALL steps in this workflow:
- Never dispatch DEV before verifying story requirements are current
- Never skip the implementation instruction and send story file directly
- Never accept DEV's self-certification without review
- Never let review cycle exit with uncertain issues unresolved
- Never skip four-source fix verification after review cycle
- Never allow DEV to implement outside story scope
- Never present to user before all acceptance criteria are confirmed
- Never advance to next story before user approves current story
- Never defer pre-existing legitimate issues found during review

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-EXECUTION
- Drop on exit: CONSTRAINTS-EXECUTION
- Exit to: WF-PLANNING (next story) or WF-INTEGRATION (milestone hit)

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
