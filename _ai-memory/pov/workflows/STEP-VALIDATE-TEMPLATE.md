---
name: 'STEP-VALIDATE-TEMPLATE'
description: 'Shared validation template — standard verify-against-checklist process for all workflows. Referenced by each workflow step-v-01-validate.md stub.'
---

# Shared Validation Template

This file defines the standard validation process used by every workflow. Each workflow's `steps-v/` stub references this file rather than repeating identical content. The workflow-specific `checklist.md` is the authoritative source of what to check.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Behavioral Constraints:**
- Validation only — do not fix issues, only report them
- Approach: Systematic check of each criterion; cite evidence for every result
- Do not accept a PASS without specific evidence

---

## VALIDATION SEQUENCE

### 1. Load Checklist

Read the calling workflow's `checklist.md` to obtain the validation criteria. The checklist is authoritative — it defines exactly what must be true for the workflow output to be valid.

---

### 2. Load Workflow Output

Identify and read the output artifacts produced by the calling workflow's create mode (`steps-c/`). The checklist.md guides what to look for — use it to determine which files and artifacts are relevant.

---

### 3. Apply Validation Criteria

Check each criterion from the checklist against the actual output.

For each criterion, record:
- **Check**: What was checked
- **Result**: PASS / FAIL / WARNING
- **Evidence**: File path and line, or specific reasoning

---

### 4. Present Validation Report

**Validation Results:**

| Check | Result | Evidence |
|-------|--------|----------|
| [Dynamic — populated at runtime from checklist.md] | | |

**Summary**: X PASS / Y FAIL / Z WARNING

**Select an Option:** [C] Continue (no FAILs — WARNINGs are informational) [E] Switch to Edit Mode (FAIL found)

#### Menu Handling Logic:

- IF C (all PASS): Workflow validated successfully. Return to calling workflow.
- IF E (FAIL found): Load `steps-e/step-e-01-assess.md` to begin edit mode.
- IF user asks questions: Answer and redisplay menu.

#### EXECUTION RULES:

- ALWAYS halt and wait for user input after presenting menu
- ONLY proceed when user selects an option
