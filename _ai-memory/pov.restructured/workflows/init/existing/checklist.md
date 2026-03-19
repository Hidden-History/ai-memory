---
name: 'init-existing-checklist'
description: 'Quality gate rubric for init-existing'
---

# Init Existing — Validation Checklist

## Pre-Execution Checks

- [ ] An existing project directory is accessible
- [ ] At least some project files (code or documentation) exist to read

## Step Completion Checks

### Step 1: Read Existing Files (step-01-read-existing-files)
- [ ] Every available project file was read in full (not skimmed)
- [ ] Findings are specific for each file (not vague summaries)
- [ ] Missing files are identified with criticality assessment
- [ ] Contradictions between documents are explicitly noted
- [ ] No agents were activated during this step

### Step 2: Run Analyst Audit (step-02-run-analyst-audit)
- [ ] Analyst was dispatched through the agent-dispatch workflow (not directly)
- [ ] All six audit areas are covered with specific findings
- [ ] Documentation vs. reality discrepancies are explicitly identified
- [ ] Parzival reviewed the audit output before proceeding
- [ ] Combined assessment merges Step 1 reading with Analyst findings

### Step 3: Identify Branch (step-03-identify-branch)
- [ ] Branch classification is based on specific audit findings (not guessing)
- [ ] Mixed signals handled by applying the more cautious branch
- [ ] User is informed of the classification with supporting evidence
- [ ] Correct branch file is loaded

### Step 4: Establish Baseline (step-04-establish-baseline)
- [ ] Every baseline file was individually verified or created
- [ ] All content traces to verified findings (not assumptions)
- [ ] Cross-file consistency is confirmed
- [ ] Missing files were created from appropriate templates
- [ ] Open items are consistently reflected

### Step 5: Verify Understanding (step-05-verify-understanding)
- [ ] Every completeness item was individually verified
- [ ] Failed checks were addressed before proceeding
- [ ] Exit route is justified with specific evidence
- [ ] No unresolved uncertainty is being carried forward

### Step 6: Present and Approve (step-06-present-and-approve)
- [ ] Complete approval package presented with all sections
- [ ] Approval gate was invoked (not bypassed)
- [ ] Correct phase workflow loaded based on audit findings
- [ ] Project status updated accurately on approval
- [ ] Clean handoff to the correct phase

## Workflow-Level Checks

- [ ] Baseline files are accurate and consistent with actual codebase
- [ ] Correct branch was identified and followed
- [ ] User approved routing to the correct phase
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT skim files instead of reading in full
- [ ] Did NOT activate an agent before reading is complete
- [ ] Did NOT assume documentation is accurate without noting it needs verification
- [ ] Did NOT skip the Analyst audit to save time
- [ ] Did NOT accept vague audit findings without requesting specifics
- [ ] Did NOT activate the Analyst without using agent-dispatch workflow
- [ ] Did NOT guess the branch without evaluating criteria
- [ ] Did NOT choose the least cautious branch when signals are mixed
- [ ] Did NOT leave baseline files outdated or inconsistent
- [ ] Did NOT create files with assumed content
- [ ] Did NOT skip cross-file consistency check
- [ ] Did NOT present to user with known gaps
- [ ] Did NOT carry assumptions into the next phase
- [ ] Did NOT choose exit route without justification
- [ ] Did NOT begin phase work without explicit user approval
- [ ] Did NOT route to the wrong phase workflow
- [ ] Did NOT bypass the approval gate
- [ ] Did NOT assume documentation is current — always verified against code
- [ ] Did NOT treat a paused sprint as valid without re-validation

_Validated by: Parzival Quality Gate on {date}_
