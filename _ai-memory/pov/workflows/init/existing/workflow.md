---
name: init-existing
description: 'Existing project onboarding. Audits project state, classifies into one of four branches, and establishes verified baseline before any work begins.'
firstStep: './steps-c/step-01-read-existing-files.md'
---

# Init Existing Project

**Goal:** Run when Parzival is activated on a project that already exists in some form. The project may be actively running, abandoned, handed off, or undocumented. Parzival's first obligation is to understand before acting. No agent is directed to build or change anything until a verified, accurate picture of the current state exists.

---

## WORKFLOW ARCHITECTURE

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) for Step Processing Rules and Critical Rules.

### Step Chain Overview (Common Path)
1. **step-01** -- Read all existing project files personally
2. **step-02** -- Run Analyst audit of actual codebase state
3. **step-03** -- Identify which branch applies and route

### Branch Files (Loaded from step-03 based on classification)
- **Branch A** -- Active Mid-Sprint: `./branches/branch-a-active-sprint/branch-steps.md`
- **Branch B** -- Legacy/Undocumented: `./branches/branch-b-messy-undocumented/branch-steps.md`
- **Branch C** -- Paused/Restarting: `./branches/branch-c-paused-restarting/branch-steps.md`
- **Branch D** -- Team Handoff: `./branches/branch-d-handoff-from-team/branch-steps.md`

### Common Completion Steps (After branch work)
4. **step-04** -- Establish or update baseline files
5. **step-05** -- Verify understanding is complete
6. **step-06** -- Present to user and route to approval gate

### Onboarding Anti-Patterns
These apply across ALL steps in this workflow:
- Never assume documentation is current -- always verify against code
- Never start work before the audit is complete
- Never carry assumptions into the next phase
- Never treat a paused sprint as still valid without re-validation
- Never skip the Analyst audit to save time
- Never route to a phase without confirming it with the user
- Always document knowledge gaps and their resolutions
- Always ask rather than assume when project intent is unclear

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-INIT
- Drop on exit: CONSTRAINTS-INIT
- Exit to: Correct phase workflow based on audit findings

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}

<!-- ai-memory:degraded-declaration
capability: cap:init-existing
depends_on: bmad
degraded_behaviour: Runs the existing-project init without the BMAD analyst persona and its project-documentation skills, reporting each as unavailable.
degraded_test: not-yet-enforced
ai-memory:end-degraded-declaration -->
