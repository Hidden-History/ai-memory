---
name: release
description: 'Release phase. Final gate before production -- documents changes, verifies deployment, ensures rollback capability.'
firstStep: './steps-c/step-01-compile-release.md'
---

# Release Phase

**Goal:** Ensure nothing is left implicit before work reaches production. Every change is documented. Every deployment step is verified. Every risk is surfaced. Release does not exit until: changelog is complete and accurate, rollback plan exists and is understood, deployment is verified, and the user explicitly signs off.

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

### Step Chain Overview
1. **step-01** -- Compile what is being released
2. **step-02** -- SM creates release notes and changelog
3. **step-03** -- Build deployment checklist
4. **step-04** -- Build rollback plan
5. **step-05** -- DEV deployment verification
6. **step-06** -- Parzival reviews all release artifacts
7. **step-07** -- Approval gate and route to Maintenance or Planning

### Release Anti-Patterns
These apply across ALL steps in this workflow:
- Never create changelog from memory instead of story records
- Never write deployment checklist as a generic guide
- Never skip rollback plan because of confidence
- Never mark irreversible changes as reversible
- Never skip DEV deployment verification
- Never release without explicit user sign-off
- Never omit behavior changes from changelog
- Never write release notes in technical language for stakeholders

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-RELEASE
- Drop on exit: CONSTRAINTS-RELEASE
- Exit to: WF-MAINTENANCE or WF-PLANNING

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
