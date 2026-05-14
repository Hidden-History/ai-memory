---
name: 'step-04-record-classification'
description: 'Record the classification with full reasoning in the standard format'
nextStepFile: './step-05-assign-priority.md'
---

# Step 4: Record the Classification

**Progress: Step 4 of 5** — Next: Assign Priority

## STEP GOAL:

Every issue, regardless of classification, must be recorded with full reasoning using the standard classification record format. This ensures traceability and prevents classification drift.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The issue understanding (step-01), project file findings (step-02), the classification determination (step-03)
- Focus: Recording the classification factually — no new analysis or interpretation
- Limits: Record factually. Do not editorialize or add interpretation beyond what was determined in prior steps.
- Dependencies: Issue understanding (step-01), project file findings (step-02), classification determination (step-03)

- Focus only on recording the classification — no new analysis or re-classification
**Behavioral Constraints:**
- FORBIDDEN to add interpretation or editorializing beyond what was determined in prior steps
- Approach: Complete every field in the standard format — no blanks, no TBD
- Route based on classification: LEGITIMATE proceeds to next step; others return to calling workflow

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Verify Record Completeness

Confirm every field is populated. No field should be left blank or marked TBD.

---

### 3. Route Based on Classification

- LEGITIMATE: proceed to `{nextStepFile}` for priority assignment
- NON-ISSUE: record is complete. Return to calling workflow.
- UNCERTAIN: WF-RESEARCH-PROTOCOL has been triggered. Hold this issue. Return to calling workflow.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN the classification record is complete and verified, will you then proceed based on classification: LEGITIMATE issues read fully and follow `{nextStepFile}`; NON-ISSUE and UNCERTAIN return to the calling workflow.
