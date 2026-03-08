---
name: session-close
description: 'Full session closeout protocol. Summarizes work, updates all tracking files, creates handoff, and saves to Qdrant with graceful degradation.'
firstStep: './steps/step-01-summarize-session.md'
handoffTemplate: '{project-root}/_ai-memory/pov/templates/session-handoff.template.md'
---

# Session Closeout

**Goal:** End the current session cleanly by summarizing all work done, updating every tracking file, creating a handoff document for the next session, and saving to Qdrant (with graceful degradation if unavailable).

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

### Closeout vs. Handoff
- **Closeout** (this workflow): Full session end. Updates tracking, creates handoff, saves to Qdrant.
- **Handoff** (`{workflows_path}/session/handoff/workflow.md`): Mid-session snapshot only. Session continues.

### Qdrant Integration Pattern
- File write is PRIMARY (always happens, this is the record of truth)
- Qdrant save is SECONDARY (attempted if available, graceful fail if not)
- Pattern: Write handoff to file. Then attempt Qdrant save. If Qdrant unavailable, log and continue.

### Closeout Anti-Patterns
- Never end a session without creating a handoff document
- Never skip tracking file updates
- Never block closeout because Qdrant is unavailable
- Never create a handoff with empty sections
- Never update task status without user confirmation
- Never close without asking about pending decisions and documentation

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
