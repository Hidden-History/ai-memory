---
name: research-protocol
description: 'Verified research process for resolving uncertainty. Three-layer research with escalation to user when all layers are exhausted.'
firstStep: './steps/step-01-define-question.md'
---

# Research Protocol

**Goal:** When Parzival encounters something he cannot answer with confidence from project files alone, find a verified, sourced, project-appropriate answer through a structured three-layer research process -- never a generic assumption, never a guess presented as fact.

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

### Research Anti-Patterns
These apply across ALL steps in this workflow:
- Never skip Layer 1 and go straight to external docs
- Never use a source from a different version of the technology
- Never accept the first answer found without checking for conflicts
- Never treat a blog post or forum answer as authoritative
- Never stop research when an answer "sounds right" -- stop when it is sourced and verified
- Never proceed on UNCERTAIN confidence
- Never fail to document the answer after finding it
- Never ask the user before exhausting all three layers

### Triggers
This protocol triggers whenever:
- A question cannot be answered from project files alone
- WF-LEGITIMACY-CHECK returns UNCERTAIN on an issue
- An agent hits a blocker requiring a technical decision
- Parzival's confidence level drops below INFORMED on any recommendation
- A fix is proposed but its correctness for this specific project is unclear

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
