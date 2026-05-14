---
name: session-handoff
description: 'Create a mid-session handoff document (state snapshot) without ending the session. Preserves context for recovery.'
firstStep: './steps-c/step-01-capture-state.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Mid-Session Handoff

**Goal:** Create a state snapshot mid-session so that context is preserved without ending the session. Useful before risky operations, at progress milestones, or when context may degrade in long sessions.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

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
