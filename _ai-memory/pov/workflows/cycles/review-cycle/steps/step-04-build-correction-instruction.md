---
name: 'step-04-build-correction-instruction'
description: 'Build a single comprehensive correction instruction covering all legitimate issues in priority order'
nextStepFile: './step-05-receive-fixes.md'
correctionTemplate: '../templates/correction-instruction.md'
---

# Step 4: Build Correction Instruction

## STEP GOAL
When legitimate issues are found, Parzival builds a single, comprehensive correction instruction covering ALL legitimate issues in priority order. One correction instruction per pass. No partial instructions.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All classified issues from step-03 (LEGITIMATE, NON-ISSUE, UNCERTAIN), pass number, prior pass records if applicable
- Limits: Only legitimate issues go on the fix list. Non-issues are documented but excluded. Uncertain issues are held pending resolution.

## MANDATORY SEQUENCE

### 1. Organize Issues by Priority
Sort all legitimate issues in priority order:
- CRITICAL: Fix immediately before anything else (security vulnerabilities, bugs breaking core functionality, blockers)
- HIGH: Fix in current cycle before task closes (architecture violations, requirements violations, breakage risks)
- MEDIUM: Fix after CRITICAL and HIGH (standards violations, near-term tech debt, pre-existing non-blocking bugs)
- LOW: Fix last in current cycle (longer-term tech debt, pre-existing minimal-risk issues)

All priorities get fixed. Priority only determines order within the cycle.

### 2. Build Correction Instruction
Using {correctionTemplate}, construct the correction instruction containing:
- Pass number
- Review summary: total issues found, legitimate count, non-issues count, uncertain count
- All legitimate issues listed in priority order with: location, problem description, required fix (with project file citation), and classification basis
- Non-issues section: documented with B1-B4 reasoning
- Uncertain section: held issues with status (research in progress / awaiting user decision)
- Action required: fix all legitimate issues, self-review after fixes, report back with fix confirmation and review result

### 3. Send Correction Instruction to DEV
- Send the complete instruction to DEV
- Do not abbreviate or split across multiple messages
- One correction instruction covers all classified issues for this pass
- Send once and wait for DEV to apply fixes and re-review

## CRITICAL STEP COMPLETION NOTE
ONLY when the correction instruction has been sent and DEV is working on fixes, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All legitimate issues included in one instruction
- Issues organized by priority (CRITICAL -> HIGH -> MEDIUM -> LOW)
- Each issue has location, problem, required fix, and basis
- Non-issues documented but excluded from fix list
- Uncertain issues held separately with status

### FAILURE:
- Sending partial correction instruction (only some issues)
- Not organizing by priority
- Missing location or basis for any issue
- Including non-issues in the fix list
- Sending fix instructions for uncertain issues before resolution
