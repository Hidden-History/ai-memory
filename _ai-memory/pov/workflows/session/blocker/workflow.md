---
name: session-blocker
description: 'Analyze a blocker, propose resolution options, and log it to the blockers tracking file.'
firstStep: './steps/step-01-capture-blocker.md'
---

# Blocker Analysis

**Goal:** When a blocker is encountered, capture it precisely, analyze root cause with resolution options, and log it to tracking so it is visible across sessions.

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

### Blocker Analysis Anti-Patterns
- Never log a blocker without attempting root cause analysis
- Never propose only one resolution option (minimum 2)
- Never skip logging because "the blocker will be resolved soon"
- Never mark a blocker as resolved without user confirmation
- Never log vague blocker descriptions (must be specific and actionable)

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
