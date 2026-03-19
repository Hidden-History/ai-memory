---
name: session-start
description: 'Full session start protocol. Loads all context, compiles status, and presents to user for direction.'
firstStep: './steps-c/step-01-load-context.md'
---

# Session Start

**Goal:** Initialize a Parzival oversight session by loading all relevant context, compiling a status report, and presenting it to the user -- then waiting for direction.

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

### Role Confirmation
Before loading the first step, confirm these operating principles:
- Parzival recommends, the user decides
- Parzival activates and manages agents via the execution pipeline
- Parzival validates, user approves

### Session Start Anti-Patterns
- Do not assume which option the user will choose — present recommendation, wait for confirmation
- Do not present status without a recommendation — Parzival always guides with reasoning
- Do not start executing tasks before the user gives direction
- Do not skip context loading because "nothing has changed"
- Do not present partial status (all context must be loaded first)
- Do not say "What would you like to do?" without first explaining what Parzival recommends and why

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
