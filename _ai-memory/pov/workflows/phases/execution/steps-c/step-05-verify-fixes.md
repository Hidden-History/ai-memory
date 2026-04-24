---
name: 'step-05-verify-fixes'
description: 'Verify all fixes against four sources: PRD, architecture, standards, and best practices'
nextStepFile: './step-06-prepare-summary.md'
---

# Step 5: Verify Fixes Against Project Requirements

**Progress: Step 5 of 7** — Next: Prepare User Summary

## STEP GOAL:

After the review cycle exits with zero issues, perform a final verification pass. Apply four-source verification to all significant fixes and confirm the full implementation against all acceptance criteria.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Review cycle summary, all fixes applied, PRD.md, architecture.md, project-context.md
- Focus: Four-source verification and final review only — not summary preparation
- Limits: If any source fails, return to review cycle. Do not present to user until all four sources pass.
- Dependencies: Review cycle summary with zero legitimate issues from Step 4

- Focus only on four-source verification and final implementation review
**Behavioral Constraints:**
- FORBIDDEN to present to user before all four sources pass
- Approach: Systematic source-by-source verification for all significant fixes
- If any source fails, return to review cycle with specific failure before proceeding

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Four-Source Fix Verification (GC-5)

For each significant fix applied during the review cycle:

**SOURCE 1 -- Project requirements (PRD.md):**
- Does the fix satisfy the relevant PRD requirement?
- Does the fix satisfy the story acceptance criteria?

**SOURCE 2 -- Project architecture (architecture.md):**
- Does the fix follow the architectural patterns?
- Does the fix respect architectural constraints?

**SOURCE 3 -- Project standards (project-context.md):**
- Does the fix follow coding standards?
- Does the fix follow naming conventions?

**SOURCE 4 -- Best practices for this stack:**
- Is the fix an established, correct approach for this technology?
- Does it introduce any known anti-patterns for this stack?

**IF ANY SOURCE FAILS:**
- Fix is not accepted
- Return to {workflows_path}/cycles/review-cycle/workflow.md with specific failure
- Do not present to user

---

### 2. Final Implementation Review

After four-source verification, review the full implementation:
- Does the implementation satisfy ALL acceptance criteria?
- Is the implementation complete -- no partial work, no TODOs?
- Are all specified tests written and passing?
- Are all files within scope -- nothing outside scope was modified?
- Is the implementation consistent with the rest of the codebase?
- Are there any security concerns not caught in review?
- Would this implementation pass a senior engineer's review?

**IF ALL PASS:** Proceed to summary preparation.
**IF ANY FAIL:** Re-enter review cycle with specific failures.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN all four-source checks and the final review pass, will you then read fully and follow: `{nextStepFile}` to begin summary preparation.
