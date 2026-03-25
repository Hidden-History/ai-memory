---
name: 'step-04-create-maintenance-task'
description: 'Create a scoped maintenance task document with acceptance criteria, fix approach, and testing requirements'
nextStepFile: './step-05-dev-implements-fix.md'
---

# Step 4: Create Maintenance Task

**Progress: Step 4 of 7** — Next: DEV Implements Fix

## STEP GOAL:

Create a maintenance task document that scopes the fix precisely. Every maintenance fix has a task document -- not just a verbal description. This ensures the fix is scoped, reviewable, and tracked.

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

- 🎯 Focus on creating a complete, scoped maintenance task document
- 🚫 FORBIDDEN to expand scope beyond the reported issue
- 💬 Approach: Tight scope, specific acceptance criteria, explicit out-of-scope
- 📋 Every maintenance fix must have a task document before any code changes begin

## EXECUTION PROTOCOLS:

- 🎯 Build complete maintenance task document with all required sections
- 💾 Save the task document with STATUS: ready before proceeding
- 📖 Load next step only after the complete task document is produced
- 🚫 FORBIDDEN to dispatch DEV without a complete task document

## CONTEXT BOUNDARIES:

- Available context: Triage summary, Analyst diagnosis (if ran), architecture.md, project-context.md
- Focus: Task creation only — do not implement the fix
- Limits: Task scope is tight. Fix addresses the reported issue only. Improvements beyond the fix require a separate story.
- Dependencies: Triage summary and Analyst diagnosis (if ran) from prior steps

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Build Maintenance Task Document

```
MAINTENANCE TASK
Task ID: MAINT-[N]
Severity: [CRITICAL / HIGH / MEDIUM / LOW]

ISSUE:
  [Clear description of the problem]

ROOT CAUSE:
  [From Analyst diagnosis or known cause]

FIX SCOPE:
  Files to modify: [specific files]
  Files NOT to touch: [explicit exclusions]

ACCEPTANCE CRITERIA:
  - [How we know the bug is fixed]
  - [Regression test that must pass]
  - [No new issues introduced]

TECHNICAL APPROACH:
  [Specific what-to-change-and-how, citing architecture.md or project-context.md]

TESTING REQUIRED:
  - Reproduce original issue -> confirm fixed
  - Regression test: [specific behavior that must still work]
  - Edge cases: [related edge cases]

OUT OF SCOPE:
  [What this fix deliberately does NOT address]
  [Adjacent improvements NOT part of this task]

RISK NOTES:
  [What could go wrong]
  [How to detect if fix introduced new issue]

STATUS: ready
```

---

### 2. Determine Fix Protocol

**HOTFIX (CRITICAL severity):**
- Skip staging
- Accelerate review cycle (one focused pass)
- Deploy immediately after approval
- Document as patch release in CHANGELOG.md
- Post-hotfix: create story for proper regression test coverage

**STANDARD FIX (HIGH / MEDIUM / LOW):**
- Normal review cycle applies
- No expedited handling
- Deploy with next release or as a patch

## CRITICAL STEP COMPLETION NOTE

ONLY when the maintenance task is complete, load and read fully `{nextStepFile}`

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Task document has all required sections
- Fix scope is tight (not expanding into refactor)
- Acceptance criteria are specific
- Fix protocol matches severity
- Out of scope is explicit

### ❌ SYSTEM FAILURE:

- Missing acceptance criteria
- Scope expanding beyond the reported issue
- No testing requirements
- Wrong fix protocol for severity

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
