---
name: 'step-08-finalize'
description: 'Finalize architecture files, update project context and tracking files'
nextStepFile: './step-09-approval-gate.md'
---

# Step 8: Finalization

**Progress: Step 8 of 9** — Next: Approval Gate

## STEP GOAL:

Confirm all files are at correct locations, update project-context.md with confirmed architecture decisions, update tracking files, and prepare the approval package.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: architecture.md, PRD.md, epic files, readiness confirmation
- Focus: File verification and tracking updates only — no architecture content changes
- Limits: Do not modify architecture content. Only verify locations and update tracking files.
- Dependencies: Step 7 complete — readiness check returned READY and Parzival confirmed

- Focus on file verification and tracking updates — no architecture content changes
**Behavioral Constraints:**
- FORBIDDEN to modify architecture content during finalization
- Approach: Systematic verification of file locations, then update tracking files, then compile approval summary
- Approval summary must be complete before routing to approval gate

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Confirm File Locations

Verify all files exist at correct locations:
- PRD.md (from Discovery)
- architecture.md
- Epic files (all epic files)
- UX design artifacts (if applicable)

---

### 2. Update project-context.md

Update with confirmed architecture decisions:
- Technology stack (specific versions)
- Code organization patterns
- Naming conventions from architecture
- Testing approach confirmed

---

### 3. Update decisions.md

Record key architecture decisions with rationale.

---

### 4. Update project-status.md

Update:
- key_files.architecture: [path]
- key_files.project_context: [path]

---

### 5. Prepare Architecture Approval Summary

Compile:
- Stack: [language + framework + database]
- API: [approach]
- Auth: [approach]
- Hosting: [approach]
- Key pattern: [primary architectural pattern]
- Epics: [count]
- Stories: [total count]
- Must Have coverage: [count of stories covering Must Have features]
- Readiness check: PASSED
- Top 5-7 decisions that lock in direction
- Known trade-offs

## CRITICAL STEP COMPLETION NOTE

ONLY when finalization is complete, load and read fully {nextStepFile}
