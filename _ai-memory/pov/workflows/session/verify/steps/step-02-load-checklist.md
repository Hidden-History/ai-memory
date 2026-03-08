---
name: 'step-02-load-checklist'
description: 'Load the appropriate verification checklist template based on the selected type'
nextStepFile: './step-03-execute-checks.md'
storyTemplate: '{project-root}/_ai-memory/pov/templates/verification-story.template.md'
codeTemplate: '{project-root}/_ai-memory/pov/templates/verification-code.template.md'
productionTemplate: '{project-root}/_ai-memory/pov/templates/verification-production.template.md'
---

# Step 2: Load Verification Checklist

## STEP GOAL
Load the appropriate verification checklist template so that all checks are defined before execution begins.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Verification type from Step 1, template files
- Limits: Load and prepare the checklist -- do not begin executing checks

## MANDATORY SEQUENCE

### 1. Load Template Based on Type

| Verification Type | Template Path |
|-------------------|---------------|
| Story | `{storyTemplate}` |
| Code | `{codeTemplate}` |
| Production | `{productionTemplate}` |

Read the selected template file in full.

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

### 3. Customize Checklist to Work Item

Adapt the template checklist to the specific work item:
- Add checks specific to the work item's requirements
- Note which checks may not apply (mark as N/A with reason)
- Ensure all criteria from the task definition are covered

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

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Correct template is loaded for the verification type
- Missing templates are handled with fallback checklists
- Checklist is customized to the specific work item
- User confirms the checklist before execution

### FAILURE:
- Loading the wrong template for the verification type
- Failing to handle a missing template
- Using a generic checklist without customization
- Starting execution before the checklist is confirmed
