---
name: 'step-03-execute-checks'
description: 'Execute each verification check, recording PASS, FAIL, or UNCERTAIN for each'
nextStepFile: './step-04-report-results.md'
---

# Step 3: Execute Verification Checks

**Progress: Step 3 of 4** — Next: Report Verification Results

## STEP GOAL:

Systematically execute every check in the prepared checklist, recording the result and evidence for each.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The customized checklist from Step 2, all project files relevant to the work item
- Focus: Execute checks only — do not generate the final report yet
- Limits: Do not generate the final report or make approval recommendations — that is Step 4's responsibility
- Dependencies: Customized and confirmed checklist from Step 2

- Execute every check in the prepared checklist completely and honestly
**Behavioral Constraints:**
- FORBIDDEN to mark uncertain results as PASS or stop after first FAIL
- Approach: Evidence-based evaluation with explicit PASS/FAIL/UNCERTAIN/N/A classification
- Read all relevant files fully — no skimming

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Execute Each Check in Order

For every check in the checklist:

**a. Read the relevant evidence**
- Read files, examine code, review outputs
- Do not skim -- read completely

**b. Evaluate against the criterion**
- Is the criterion met? Partially met? Not met?

**c. Record the result**
- **PASS**: Criterion is fully met, with evidence
- **FAIL**: Criterion is not met, with specific failure description
- **UNCERTAIN**: Cannot definitively determine, with explanation of what is unclear
- **N/A**: Check does not apply to this work item, with reason

**d. Document evidence**
- File paths examined
- Specific findings
- For FAIL: exactly what was expected vs. what was found
- For UNCERTAIN: what would be needed to make a determination

---

### 2. Track Running Totals

As checks are executed, maintain:
- Total checks executed
- PASS count
- FAIL count
- UNCERTAIN count
- N/A count

---

### 3. Do Not Stop on First Failure

Execute ALL checks regardless of individual results. The full picture is needed for the report. Do not short-circuit after a FAIL.

---

### 4. Compile Check Results

Organize results into a structured table:

| # | Check | Status | Evidence/Notes |
|---|-------|--------|----------------|
| 1 | [Check] | PASS/FAIL/UNCERTAIN/N/A | [Details] |

## CRITICAL STEP COMPLETION NOTE

ONLY when ALL checks have been executed and results recorded, load and read fully {nextStepFile}
