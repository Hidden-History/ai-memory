---
name: 'step-02-load-checklist'
description: 'Load the appropriate verification checklist template based on the selected type'
nextStepFile: './step-03-execute-checks.md'
storyTemplate: '{project-root}/templates/oversight/verification/checklists/story-complete.md'
codeTemplate: '{project-root}/templates/oversight/verification/checklists/code-review.md'
productionTemplate: '{project-root}/templates/oversight/verification/checklists/production-ready.md'
---

# Step 2: Load Verification Checklist

**Progress: Step 2 of 4** — Next: Execute Verification Checks

## STEP GOAL:

Load the appropriate verification checklist template so that all checks are defined before execution begins.

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

- 🎯 Focus on loading and preparing the correct checklist — do not execute any checks
- 🚫 FORBIDDEN to use a generic template without customizing to the specific work item
- 💬 Approach: Two-tier lookup (project-specific first, framework fallback second)
- 📋 User must confirm the checklist before proceeding to execution

## EXECUTION PROTOCOLS:

- 🎯 Load the appropriate checklist using two-tier lookup, with inline fallback if neither exists
- 💾 Record which checklist was loaded (project-specific, framework template, or inline fallback)
- 📖 Load next step only after user confirms the checklist
- 🚫 FORBIDDEN to begin executing checks before checklist is confirmed

## CONTEXT BOUNDARIES:

- Available context: Verification type from Step 1, template files at `{oversight_path}/verification/checklists/` and `{project-root}/templates/oversight/verification/checklists/`
- Focus: Load and prepare the checklist only — do not execute any checks
- Limits: Do not begin executing checks; do not modify checklist templates
- Dependencies: Verification type determined in Step 1

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Load Checklist Based on Type

Use a two-tier lookup: project-specific checklist first, framework template as fallback.

| Verification Type | Project Checklist (try first) | Framework Fallback |
|---|---|---|
| Story | `{oversight_path}/verification/checklists/story-complete.md` | `{storyTemplate}` |
| Code | `{oversight_path}/verification/checklists/code-review.md` | `{codeTemplate}` |
| Production | `{oversight_path}/verification/checklists/production-ready.md` | `{productionTemplate}` |

1. Try to read the project checklist from `{oversight_path}/verification/checklists/`
2. If it exists — use it. Project checklists take priority over framework templates.
3. If it does not exist — load the framework template from `{project-root}/templates/oversight/verification/checklists/`
4. If neither exists — use the inline fallback checklist defined below in this step file.

Read the selected checklist in full before proceeding.

---

### 2. Handle Missing Template

If the template file does not exist, use the appropriate fallback checklist:

**Story verification fallback:**
1. All acceptance criteria met
2. All DONE WHEN criteria satisfied
3. All expected outputs exist
4. No partial implementations or TODO stubs
5. Implementation stays within defined scope
6. No out-of-scope files modified

**Code verification fallback:**
1. Code compiles/runs without errors
2. All tests pass
3. No lint or style violations
4. No security vulnerabilities introduced
5. Error handling is complete
6. Edge cases are handled
7. No hardcoded values that should be configurable
8. Code follows project standards

**Production verification fallback:**
1. Deployment procedure documented
2. Rollback procedure documented and tested
3. Monitoring and alerting configured
4. Health checks in place
5. Performance within acceptable thresholds
6. Data migration verified (if applicable)
7. Feature flags configured (if applicable)

---

### 3. Customize Checklist to Work Item

Adapt the template checklist to the specific work item:
- Add checks specific to the work item's requirements
- Note which checks may not apply (mark as N/A with reason)
- Ensure all criteria from the task definition are covered

---

### 4. Present Checklist for Confirmation

Show the user the checklist that will be executed:
```
## Verification Checklist ([Type])

Work Item: [description]

Checks to execute:
1. [Check description]
2. [Check description]
...

Proceed with verification?
```

## CRITICAL STEP COMPLETION NOTE

ONLY when the checklist is loaded, customized, and confirmed, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Correct template is loaded for the verification type
- Missing templates are handled with fallback checklists
- Checklist is customized to the specific work item
- User confirms the checklist before execution

### ❌ SYSTEM FAILURE:

- Loading the wrong template for the verification type
- Failing to handle a missing template
- Using a generic checklist without customization
- Starting execution before the checklist is confirmed

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
