---
name: init-new
description: 'New project initialization. Establishes project baseline from scratch when no prior project files exist.'
firstStep: './steps-c/step-01-gather-project-info.md'
---

# Init New Project

**Goal:** Run exactly once when Parzival is activated for a project that does not yet exist. Establish the foundation that every subsequent workflow depends on. No implementation begins. No architecture is designed. This workflow ends when the project has a solid, verified baseline and the user has confirmed readiness to move into Discovery.

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
1. **step-01** -- Gather project information from user (all required fields upfront)
2. **step-02** -- Validate and clarify gathered information (no assumptions)
3. **step-03** -- Verify _ai-memory/ installation completeness (constraint IN-04)
4. **step-04** -- Create baseline project files (project-status.md, goals.md, etc.)
5. **step-05** -- Establish Claude Code teams session structure
6. **step-06** -- Verify baseline is complete (full checklist)
7. **step-07** -- Present to user and route to approval gate

### Init Anti-Patterns
These apply across ALL steps in this workflow:
- Never start Discovery before baseline is verified
- Never ask for information already provided
- Never treat user preferences as confirmed decisions
- Never create files with assumed content
- Never skip installation verification
- Never move to Discovery without user approval via approval gate
- Never fill goals.md with generic content -- every line must come from the user

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-INIT
- Drop on exit: CONSTRAINTS-INIT
- Exit to: WF-DISCOVERY

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
