---
name: session-verify
description: 'Run verification protocol on completed work. Supports story, code, and production verification types.'
firstStep: './steps-c/step-01-determine-type.md'
storyTemplate: '{project-root}/_ai-memory/pov/templates/verification-story.template.md'
codeTemplate: '{project-root}/_ai-memory/pov/templates/verification-code.template.md'
productionTemplate: '{project-root}/_ai-memory/pov/templates/verification-production.template.md'
---

# Verification Protocol

**Goal:** Run a structured verification on completed work to ensure it meets the defined criteria before approval. Parzival validates; the user approves.

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

### Verification Types
This workflow supports three verification types:
1. **Story verification**: Verifies a completed story against its acceptance criteria
2. **Code verification**: Verifies code quality, standards compliance, and correctness
3. **Production verification**: Verifies production readiness (deployment, monitoring, rollback)

### Verification Anti-Patterns
- Never approve work that Parzival has not verified
- Never skip checks because "the changes were small"
- Never mark uncertain checks as PASS
- Never approve without user's explicit decision
- Never verify against criteria that do not exist (verify only what is defined)
- Never combine verification types in a single run

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
