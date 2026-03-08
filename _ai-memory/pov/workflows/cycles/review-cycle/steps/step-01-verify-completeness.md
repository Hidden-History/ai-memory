---
name: 'step-01-verify-completeness'
description: 'Verify that the implementation output is complete and on-spec before triggering any code review'
nextStepFile: './step-02-trigger-code-review.md'
incompletenessTemplate: '../templates/incompleteness-return.md'
---

# Step 1: Verify Implementation Completeness

## STEP GOAL
Before triggering any code review, Parzival verifies the implementation output is complete and on-spec. Code review only runs on complete implementations.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Current task instruction with DONE WHEN criteria, OUTPUT EXPECTED list, scope definition, and the implementation output from DEV
- Limits: Do not evaluate code quality at this stage — only completeness and scope compliance

## MANDATORY SEQUENCE

### 1. Read Implementation Output in Full
Read every file changed or created by the DEV agent. Do not skim. Understand what was produced.

### 2. Check Against Task Instruction DONE WHEN Criteria
For each criterion in the task instruction, verify:
- Every DONE WHEN criterion is met
- Every file specified in OUTPUT EXPECTED exists
- No partial implementations (half-finished functions, TODO stubs)
- Implementation stays within defined scope
- No files modified that were listed as OUT OF SCOPE
- Implementation aligns with cited requirements from instruction

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

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every DONE WHEN criterion has been verified individually
- Implementation output has been read in full, not skimmed
- Incomplete implementations are returned to DEV with specific direction
- Only complete implementations proceed to code review

### FAILURE:
- Triggering code review on incomplete implementation
- Skimming output instead of reading in full
- Sending vague incompleteness instructions without specific items
- Proceeding despite failed completeness checks
