---
name: 'step-04-build-correction-instruction'
description: 'Build a single comprehensive correction instruction covering all legitimate issues in priority order'
nextStepFile: './step-05-receive-fixes.md'
correctionTemplate: '{workflows_path}/cycles/review-cycle/templates/correction-instruction.md'
---

# Step 4: Build Correction Instruction

**Progress: Step 4 of 7** — Next: Receive Fix Report and Re-Review

## STEP GOAL:

When legitimate issues are found, Parzival builds a single, comprehensive correction instruction covering ALL legitimate issues in priority order. One correction instruction per pass. No partial instructions.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: All classified issues from step-03 (LEGITIMATE, NON-ISSUE, UNCERTAIN), pass number, prior pass records if applicable
- Focus: Correction instruction construction and dispatch — do not re-classify here
- Limits: Only legitimate issues go on the fix list. Non-issues are documented but excluded. Uncertain issues are held pending resolution.
- Dependencies: Classified issues from step-03 (LEGITIMATE, NON-ISSUE, UNCERTAIN lists with priorities)

- Build one comprehensive correction instruction covering all legitimate issues
**Behavioral Constraints:**
- FORBIDDEN to send partial instructions or split across multiple messages
- Approach: Priority-ordered instruction using the correction template at `skills/aim-agent-lifecycle/templates/agent-correction.template.md`
- Hold uncertain issues separately — never include in fix instruction until resolved

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Organize Issues by Priority

Sort all legitimate issues in priority order:
- CRITICAL: Fix immediately before anything else (security vulnerabilities, bugs breaking core functionality, blockers)
- HIGH: Fix in current cycle before task closes (architecture violations, requirements violations, breakage risks)
- MEDIUM: Fix after CRITICAL and HIGH (standards violations, near-term tech debt, pre-existing non-blocking bugs)
- LOW: Fix last in current cycle (longer-term tech debt, pre-existing minimal-risk issues)

All priorities get fixed. Priority only determines order within the cycle.

---

### 2. Build Correction Instruction

Using the correction template (`skills/aim-agent-lifecycle/templates/agent-correction.template.md`), construct the correction instruction containing:
- Pass number
- Review summary: total issues found, legitimate count, non-issues count, uncertain count
- All legitimate issues listed in priority order with: location, problem description, required fix (with project file citation), and classification basis
- Non-issues section: documented with B1-B4 reasoning
- Uncertain section: held issues with status (research in progress / awaiting user decision)
- Action required: fix all legitimate issues, self-review after fixes, report back with fix confirmation and review result

---

### 3. Send Correction Instruction to DEV

- Send the complete instruction to DEV
- Do not abbreviate or split across multiple messages
- One correction instruction covers all classified issues for this pass
- Send once and wait for DEV to apply fixes and re-review

## CRITICAL STEP COMPLETION NOTE

ONLY when the correction instruction has been sent and DEV is working on fixes, load and read fully {nextStepFile}
