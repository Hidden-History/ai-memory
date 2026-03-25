---
name: 'session-verify-checklist'
description: 'Quality gate rubric for session-verify'
---

# Session Verify — Validation Checklist

## Pre-Execution Checks

- [ ] Work item to verify is clearly identified
- [ ] Verification criteria (checklist or acceptance criteria) are available for the work item

## Step Completion Checks

### Step 1: Determine Type (step-01-determine-type)
- [ ] Verification type is determined from user input or clarified via question
- [ ] Work item is clearly identified
- [ ] Ambiguity is resolved before proceeding

### Step 2: Load Checklist (step-02-load-checklist)
- [ ] Correct template is loaded for the verification type
- [ ] Missing templates are handled with fallback checklists
- [ ] Checklist is customized to the specific work item
- [ ] User confirms the checklist before execution

### Step 3: Execute Checks (step-03-execute-checks)
- [ ] Every check in the checklist was executed
- [ ] Results are honest (UNCERTAIN is used when appropriate)
- [ ] Evidence is documented for every result
- [ ] All checks were executed even after failures
- [ ] No checks were skimmed

### Step 4: Report Results (step-04-report-results)
- [ ] Report is presented in the defined format
- [ ] All check results are included
- [ ] Failed checks have detailed explanations with suggested fixes
- [ ] Recommendation is proportional to findings
- [ ] User makes the approval decision
- [ ] Verification outcome is recorded

## Workflow-Level Checks

- [ ] Verification type was confirmed before execution
- [ ] Every checklist item was individually executed
- [ ] User made the final approval decision
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT guess the verification type when ambiguous
- [ ] Did NOT start verification before confirming the type
- [ ] Did NOT combine multiple verification types in a single run
- [ ] Did NOT load the wrong template for the verification type
- [ ] Did NOT fail to handle a missing template
- [ ] Did NOT use a generic checklist without customization
- [ ] Did NOT start execution before the checklist was confirmed
- [ ] Did NOT skip any checks
- [ ] Did NOT mark uncertain results as PASS
- [ ] Did NOT stop after the first FAIL (all checks must run)
- [ ] Did NOT provide results without evidence
- [ ] Did NOT skim files instead of reading them fully
- [ ] Did NOT omit check results from the report
- [ ] Did NOT approve without user's explicit decision
- [ ] Did NOT present a recommendation that contradicts the findings
- [ ] Did NOT approve work that Parzival has not independently verified
- [ ] Did NOT verify against criteria that do not exist
- [ ] Did NOT fail to detail failed checks (Expected/Actual/Impact/Fix)
- [ ] Did NOT skip the user decision step

_Validated by: Parzival Quality Gate on {date}_
