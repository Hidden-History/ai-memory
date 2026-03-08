---
name: 'step-05-verify-fixes'
description: 'Verify all fixes against four sources: PRD, architecture, standards, and best practices'
nextStepFile: './step-06-prepare-summary.md'
---

# Step 5: Verify Fixes Against Project Requirements

## STEP GOAL
After the review cycle exits with zero issues, perform a final verification pass. Apply four-source verification to all significant fixes and confirm the full implementation against all acceptance criteria.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Review cycle summary, all fixes applied, PRD.md, architecture.md, project-context.md
- Limits: If any source fails, return to review cycle. Do not present to user until all four sources pass.

## MANDATORY SEQUENCE

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
ONLY when all four-source checks and the final review pass, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Four-source verification applied to all significant fixes
- Every source individually checked
- Final implementation review confirms all criteria satisfied
- No issues remain before user presentation

### FAILURE:
- Skipping four-source verification
- Accepting fixes that fail any source
- Presenting to user with unverified fixes
- Not running final implementation review
