---
name: 'step-01-read-issue'
description: 'Read and fully understand the issue before any classification attempt'
nextStepFile: './step-02-check-project-files.md'
---

# Step 1: Read the Issue in Full

**Progress: Step 1 of 5** — Next: Check Project Files

## STEP GOAL:

Before classifying, Parzival must fully understand what is being reported. Never classify an issue you have not fully read and understood.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: The issue being assessed, the review report it came from, the implementation context
- Focus: Understanding only — do not begin classification at this stage
- Limits: Do NOT begin classification at this stage. This step is understanding only.
- Dependencies: None — this is the first step of the legitimacy check workflow

- Focus only on reading and understanding the issue — no classification yet
**Behavioral Constraints:**
- FORBIDDEN to begin classification before completing the understanding checklist
- Approach: Systematic checklist — answer every item before proceeding
- Confirm understanding is complete before loading next step

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Complete the Understanding Checklist

For the issue being assessed, determine:
- What exactly is the issue? (not a summary -- the specific problem)
- Where does it occur? (file, function, line, module)
- What is the current behavior?
- What is the expected behavior?
- What is the potential impact if not fixed?
- Is this a new issue or pre-existing?
- Was this introduced by the current task or does it predate it?

---

### 2. Verify Full Understanding

Before proceeding, confirm you can answer every item in the checklist. If any item is unclear, re-read the relevant source material until it is clear.

Do NOT proceed to classification until every checklist item is answered.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN every item in the understanding checklist is answered, will you then read fully and follow: `{nextStepFile}` to begin checking project files.
