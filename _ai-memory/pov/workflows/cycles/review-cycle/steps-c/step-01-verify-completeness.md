---
name: 'step-01-verify-completeness'
description: 'Verify that the implementation output is complete and on-spec before triggering any code review'
nextStepFile: './step-02-trigger-code-review.md'
incompletenessTemplate: '{workflows_path}/cycles/review-cycle/templates/incompleteness-return.md'
---

# Step 1: Verify Implementation Completeness

**Progress: Step 1 of 7** — Next: Trigger DEV Code Review

## STEP GOAL:

Before triggering any code review, Parzival verifies the implementation output is complete and on-spec. Code review only runs on complete implementations.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Current task instruction with DONE WHEN criteria, OUTPUT EXPECTED list, scope definition, and the implementation output from DEV
- Focus: Completeness verification only — do not evaluate code quality
- Limits: Do not evaluate code quality at this stage — only completeness and scope compliance
- Dependencies: None — this step receives implementation output directly from DEV

- Focus on completeness verification only — do not evaluate code quality at this stage
**Behavioral Constraints:**
- FORBIDDEN to trigger code review on incomplete implementations
- Approach: Read every file in full, check against DONE WHEN criteria individually
- Use {incompletenessTemplate} for return instructions — never improvise format

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Read Implementation Output in Full

Read every file changed or created by the DEV agent. Do not skim. Understand what was produced.

---

### 2. Check Against Task Instruction DONE WHEN Criteria

For each criterion in the task instruction, verify:
- Every DONE WHEN criterion is met
- Every file specified in OUTPUT EXPECTED exists
- No partial implementations (half-finished functions, TODO stubs)
- Implementation stays within defined scope
- No files modified that were listed as OUT OF SCOPE
- Implementation aligns with cited requirements from instruction

---

### 3. Handle Check Result

**IF ALL CHECKS PASS:**
- Implementation is verified as complete
- Proceed to trigger code review (next step)

**IF ANY CHECK FAILS:**
- Do NOT trigger code review
- Build an incompleteness return instruction using {incompletenessTemplate}
- Send instruction to DEV with specific items that are missing or incomplete
- Wait for DEV to complete the missing items
- When DEV reports back, return to sequence item 1 and re-verify from scratch

## CRITICAL STEP COMPLETION NOTE

ONLY when all completeness checks pass, load and read fully {nextStepFile}
