---
name: init-new
description: 'New project initialization. Establishes project baseline from scratch when no prior project files exist.'
firstStep: './steps-c/step-01-gather-project-info.md'
---

# Init New Project

**Goal:** Run exactly once when Parzival is activated for a project that does not yet exist. Establish the foundation that every subsequent workflow depends on. No implementation begins. No architecture is designed. This workflow ends when the project has a solid, verified baseline and the user has confirmed readiness to move into Discovery.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

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
