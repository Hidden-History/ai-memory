---
name: 'step-04-record-classification'
description: 'Record the classification with full reasoning in the standard format'
nextStepFile: './step-05-assign-priority.md'
---

# Step 4: Record the Classification

## STEP GOAL
Every issue, regardless of classification, must be recorded with full reasoning using the standard classification record format. This ensures traceability and prevents classification drift.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The issue understanding (step-01), project file findings (step-02), the classification determination (step-03)
- Limits: Record factually. Do not editorialize or add interpretation beyond what was determined in prior steps.

## MANDATORY SEQUENCE

### 1. Build the Classification Record
Complete every field in the following format:

```
ISSUE CLASSIFICATION RECORD

ISSUE ID:      [sequential number for this review pass]
LOCATION:      [file + function + line if applicable]
DESCRIPTION:   [clear description of the issue]
ORIGIN:        [new -- introduced by current task | pre-existing]
REPORTED BY:   [DEV review | Architect audit | Maintenance report | Other]

CLASSIFICATION: [LEGITIMATE | NON-ISSUE | UNCERTAIN]

BASIS:
  [For LEGITIMATE]:
    Criterion met: [A1-A8 -- which criterion applies]
    Project file:  [cite specific file and section]
    Impact:        [what happens if not fixed]

  [For NON-ISSUE]:
    Criteria checked: [B1-B4 -- confirm all four are met]
    Reasoning: [why this does not meet any A criterion]

  [For UNCERTAIN]:
    Uncertainty reason: [which C criterion applies]
    Action: WF-RESEARCH-PROTOCOL triggered
    Escalation: [yes/no -- if yes, what was presented to user]

RESOLUTION:
  [LEGITIMATE]: Added to fix list -- priority [CRITICAL/HIGH/MEDIUM/LOW]
  [NON-ISSUE]:  Documented -- excluded from fix list
  [UNCERTAIN]:  Pending research / Pending user decision
```

### 2. Verify Record Completeness
Confirm every field is populated. No field should be left blank or marked TBD.

### 3. Route Based on Classification
- LEGITIMATE: proceed to {nextStepFile} for priority assignment
- NON-ISSUE: record is complete. Return to calling workflow.
- UNCERTAIN: WF-RESEARCH-PROTOCOL has been triggered. Hold this issue. Return to calling workflow.

## CRITICAL STEP COMPLETION NOTE
ONLY when the classification record is complete and verified, proceed based on classification: LEGITIMATE issues load {nextStepFile}; NON-ISSUE and UNCERTAIN return to calling workflow.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every field in the record is populated
- Classification matches the determination from step-03
- Basis includes specific criteria and project file citations
- Resolution action is clear and specific

### FAILURE:
- Incomplete records (blank fields)
- Classification without documented basis
- Missing project file citations for LEGITIMATE classifications
- Not triggering WF-RESEARCH-PROTOCOL for UNCERTAIN classifications
