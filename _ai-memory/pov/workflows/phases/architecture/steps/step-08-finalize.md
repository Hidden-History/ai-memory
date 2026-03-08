---
name: 'step-08-finalize'
description: 'Finalize architecture files, update project context and tracking files'
nextStepFile: './step-09-approval-gate.md'
---

# Step 8: Finalization

## STEP GOAL
Confirm all files are at correct locations, update project-context.md with confirmed architecture decisions, update tracking files, and prepare the approval package.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: architecture.md, PRD.md, epic files, readiness confirmation
- Limits: Do not modify architecture content. Only verify locations and update tracking files.

## MANDATORY SEQUENCE

### 1. Confirm File Locations
Verify all files exist at correct locations:
- PRD.md (from Discovery)
- architecture.md
- Epic files (all epic files)
- UX design artifacts (if applicable)

### 2. Update project-context.md
Update with confirmed architecture decisions:
- Technology stack (specific versions)
- Code organization patterns
- Naming conventions from architecture
- Testing approach confirmed

### 3. Update decisions.md
Record key architecture decisions with rationale.

### 4. Update project-status.md
Update:
- key_files.architecture: [path]
- key_files.project_context: [path]

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

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All files verified at correct locations
- project-context.md updated with confirmed architecture
- decisions.md updated with architecture decisions
- project-status.md tracking files updated
- Approval summary is complete

### FAILURE:
- Files at wrong locations
- project-context.md not updated
- decisions.md not updated with architecture decisions
- Incomplete approval summary
