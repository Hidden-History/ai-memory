---
name: 'branch-b-messy-undocumented'
description: 'Onboarding steps for a legacy or undocumented project. Document reality before directing any work.'
---

# Branch B: Legacy / Undocumented

## BRANCH GOAL:
Document the actual current state of the project before any work can be directed. Cannot act without documentation.

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Generate Project Context
Activate Analyst via {workflows_path}/cycles/agent-dispatch/workflow.md to generate project-context.md by scanning the codebase:
- Technology stack and versions
- Code organization patterns
- Naming conventions
- Testing approaches
- Framework-specific patterns

---

### 2. Review and Verify Generated Context
Parzival reviews the generated project-context.md:
- Is the stack correctly identified?
- Are patterns accurately described?
- Are there patterns the scan missed?
- Correct any inaccuracies before using

---

### 3. Assess PRD State
**IF no PRD exists:**
- Cannot proceed to Architecture without one
- Must run WF-DISCOVERY to create PRD from current codebase reality
- Exit route: WF-DISCOVERY

**IF PRD exists but is outdated:**
- Identify specific gaps and inaccuracies
- Activate PM via agent dispatch to update PRD based on audit findings
- User must approve updated PRD before proceeding

---

### 4. Assess Architecture State
**IF no architecture.md:**
- Must run WF-ARCHITECTURE after Discovery is complete
- Note as required step

**IF architecture.md exists but is outdated:**
- Identify specific discrepancies from Analyst audit
- Flag for Architect to update in Architecture phase

---

### 5. Verify _ai-memory/ Installation
Check for _ai-memory/ directory:
- If present and complete: verify against constraint IN-04
- If missing or incomplete: alert user that installation is needed

---

### 6. Create Missing Baseline Files
Create any missing required files:
- project-status.md (if missing)
- goals.md (if missing -- extract from existing docs + user input)
- decisions.md (if missing -- initialize empty)

---

### 7. Determine Exit Route
Based on documentation state:
- No valid PRD: exit route is WF-DISCOVERY
- PRD exists but no architecture: exit route is WF-ARCHITECTURE
- Both exist and are valid: exit route is WF-PLANNING

Record the confirmed exit route for use in step-06 approval package.

## BRANCH COMPLETION
When all branch steps are complete, return to the common path: step-04-establish-baseline.md

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Project context generated and verified against actual codebase
- PRD and architecture state assessed, missing or outdated files addressed
- Missing baseline files (project-status.md, goals.md, decisions.md) created
- Exit route is clearly determined and recorded

### ❌ SYSTEM FAILURE:

- Skipping Analyst audit and accepting generated context without verification
- Accepting unverified generated context as accurate without review
- Proceeding without confirming findings with user

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
