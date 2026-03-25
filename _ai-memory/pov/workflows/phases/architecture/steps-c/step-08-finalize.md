---
name: 'step-08-finalize'
description: 'Finalize architecture files, update project context and tracking files'
nextStepFile: './step-09-approval-gate.md'
---

# Step 8: Finalization

**Progress: Step 8 of 9** — Next: Approval Gate

## STEP GOAL:

Confirm all files are at correct locations, update project-context.md with confirmed architecture decisions, update tracking files, and prepare the approval package.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on file verification and tracking updates — no architecture content changes
- 🚫 FORBIDDEN to modify architecture content during finalization
- 💬 Approach: Systematic verification of file locations, then update tracking files, then compile approval summary
- 📋 Approval summary must be complete before routing to approval gate

## EXECUTION PROTOCOLS:

- 🎯 Verify all files at correct locations before updating tracking documents
- 💾 Update project-context.md, decisions.md, and project-status.md with confirmed architecture data
- 📖 Load next step only after approval summary is complete and all tracking files updated
- 🚫 FORBIDDEN to route to approval gate with incomplete or missing tracking updates

## CONTEXT BOUNDARIES:

- Available context: architecture.md, PRD.md, epic files, readiness confirmation
- Focus: File verification and tracking updates only — no architecture content changes
- Limits: Do not modify architecture content. Only verify locations and update tracking files.
- Dependencies: Step 7 complete — readiness check returned READY and Parzival confirmed

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

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All files verified at correct locations
- project-context.md updated with confirmed architecture
- decisions.md updated with architecture decisions
- project-status.md tracking files updated
- Approval summary is complete

### ❌ SYSTEM FAILURE:

- Files at wrong locations
- project-context.md not updated
- decisions.md not updated with architecture decisions
- Incomplete approval summary

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
