---
name: session-decision
description: 'Structure a decision with options, tradeoffs, and recommendation. Present using approval gate format and log the outcome.'
firstStep: './steps-c/step-01-structure-decision.md'
decisionLogTemplate: '{project-root}/_ai-memory/pov/templates/decision-log.template.md'
---

# Decision Request

**Goal:** When a decision is needed, structure it clearly with context, options, tradeoffs, and a recommendation so the user can make an informed choice. Log the outcome for future reference.

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

### Decision Anti-Patterns
- Never present a decision with only one option
- Never hide tradeoffs to steer toward a preferred option
- Never skip the "do nothing" option when it is viable
- Never make the decision on behalf of the user
- Never log a decision outcome the user did not explicitly choose
- Never present a decision without stating what constraints apply

---

## Supporting References

- Decision lifecycle states and transitions: `knowledge/decision-status-workflow.md`
- Decision log template: `{project-root}/_ai-memory/pov/templates/decision-log.template.md`

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
