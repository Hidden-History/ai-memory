---
name: 'step-01-determine-type'
description: 'Determine the verification type based on the work item and user input'
nextStepFile: './step-02-load-checklist.md'
---

# Step 1: Determine Verification Type

**Progress: Step 1 of 4** — Next: Load Verification Checklist

## STEP GOAL:

Identify which verification type to run based on the work item being verified and any explicit user direction.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: User's input describing the work item to verify, task tracker at `{oversight_path}/tracking/task-tracker.md`
- Focus: Determine verification type only — do not begin loading checklists or executing checks
- Limits: Determine the type only — do not begin verification
- Dependencies: None — this is the first step of the session-verify workflow

- Focus on determining verification type — do not begin loading checklists or executing checks
**Behavioral Constraints:**
- FORBIDDEN to guess or assume the verification type when ambiguous
- Approach: Systematic determination using work item type and explicit user direction
- Confirm selected type with user before proceeding to next step

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Identify the Work Item

From the user's input, determine:
- What specific work item is being verified
- Task ID (if referenced)
- What was produced (code, documentation, configuration, etc.)

---

### 2. Select Verification Type

**If the user explicitly specified a type** (story, code, production), use that type.

**If not specified**, determine from context:

| Work Item Type | Verification Type |
|----------------|-------------------|
| Completed user story or feature | Story verification |
| Code changes, refactoring, bug fixes | Code verification |
| Deployment, release, infrastructure changes | Production verification |

**If ambiguous**, ask the user:
```
Which verification type should I run?
1. **Story** -- verify against acceptance criteria and DONE WHEN
2. **Code** -- verify code quality, standards, and correctness
3. **Production** -- verify deployment readiness and operational checks
```

---

### 3. Confirm Selection

State the selected verification type and the work item being verified. Proceed only if the user confirms or does not object.

## CRITICAL STEP COMPLETION NOTE

ONLY when the verification type is determined, load and read fully {nextStepFile}
