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

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

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
