---
name: session-handoff
description: 'Create a mid-session handoff document (state snapshot) without ending the session. Preserves context for recovery.'
firstStep: './steps/step-01-capture-state.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Mid-Session Handoff

**Goal:** Create a state snapshot mid-session so that context is preserved without ending the session. Useful before risky operations, at progress milestones, or when context may degrade in long sessions.

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

### Handoff vs. Closeout
- **Handoff** (this workflow): Mid-session snapshot. Session continues after.
- **Closeout** (`{workflows_path}/session/close/workflow.md`): Full session end protocol with tracking updates.

### Handoff Anti-Patterns
- Never create a handoff without capturing "context that would be lost"
- Never skip recovery instructions
- Never leave vague descriptions ("working on stuff")
- Never use this as a session end (use closeout for that)

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
