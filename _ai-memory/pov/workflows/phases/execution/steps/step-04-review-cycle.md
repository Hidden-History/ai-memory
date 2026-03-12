---
name: 'step-04-review-cycle'
description: 'Route to review cycle workflow for implementation verification until zero legitimate issues'
nextStepFile: './step-05-verify-fixes.md'
---

# Step 4: Review Cycle

## STEP GOAL
Route to {workflows_path}/cycles/review-cycle/workflow.md when DEV signals implementation complete. The review cycle runs until zero legitimate issues remain.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Story file, implementation instruction, DEV completion report, architecture.md, project-context.md
- Limits: The review cycle handles the review loop. Parzival monitors for red flags.

## MANDATORY SEQUENCE

### 1. Prepare Review Cycle Inputs
Provide to {workflows_path}/cycles/review-cycle/workflow.md:
- The story file (acceptance criteria for verification)
- The implementation instruction (DONE WHEN criteria)
- The DEV completion report
- architecture.md reference (patterns to check against)
- project-context.md reference (standards to check against)

### 2. Invoke Review Cycle
Load and execute {workflows_path}/cycles/review-cycle/workflow.md.

The review cycle will:
- Verify completeness against DONE WHEN criteria
- Trigger DEV code review
- Classify all issues found
- Build correction instructions for legitimate issues
- Loop until zero legitimate issues
- Return clean review cycle summary

### 3. Monitor Review Cycle
During the review cycle, Parzival tracks:
- Number of passes (each pass = implement, review, classify, fix)
- Issues per pass (decreasing trend = progress)
- Pre-existing issues surfaced (added to fix list)
- Uncertain issues (research protocol running in parallel)

**RED FLAGS:**
- Same issue appearing in multiple passes (fix not resolving)
- New issues increasing per pass (fixes introducing more problems)
- DEV claiming zero issues on complex implementation (scrutinize)
- Uncertain issues stalling (escalate to user)

### 4. Handle Non-Converging Review

**At pass 2+** (fix required more than one attempt):
Run `/aim-best-practices-researcher` for the specific technology or pattern causing the failure. The fact that a fix did not resolve on the first attempt is a signal that current best practices may not be in the knowledge base, or DEV is working from outdated patterns.

- Research the specific pattern that failed (e.g., "Python async error handling 2026", "React state management best practices 2026")
- Include the research findings in the next correction instruction to DEV
- This ensures DEV has current guidance, not just the reviewer's critique

If not converging after 4+ passes:
- Assess: are fixes addressing root cause or just symptoms?
- Verify best practices research was done (if not, do it now — this is mandatory)
- Provide more specific fix guidance informed by best practices
- Break down fixes into smaller steps
- If still not converging, escalate to user with options

### 5. Handle Edge-Case Scenarios

**Acceptance Criterion Cannot Be Met As Specified:**
1. DEV reports criterion [X] cannot be met because [reason]
2. Verify the constraint — is DEV correct?
3. If genuinely impossible as written:
   - Apply WF-RESEARCH-PROTOCOL to find the correct approach
   - If criterion needs updating, bring to user with specific recommendation
   - Update PRD and story if user approves the change
4. If DEV is incorrect:
   - Clarify the criterion with citation
   - Provide specific implementation guidance
   - DEV continues

**Pre-Existing Issues Keep Multiplying:**
1. Each review pass surfaces more pre-existing issues
2. Classify each issue per WF-LEGITIMACY-CHECK — no shortcuts
3. All legitimate pre-existing issues enter the fix list
4. If pre-existing issues are extensive:
   - Notify user: "We are finding significant pre-existing issues in the codebase surrounding this story. [N] legitimate issues identified so far beyond the story scope. These will all be fixed in this cycle per our zero-debt policy. Estimated additional review passes needed: [N]."
5. Continue — do not cap the fix cycle
6. Update project-status.md: open_issues count

### 6. Receive Clean Review Summary
Review cycle exits with zero legitimate issues and a clean summary.

## CRITICAL STEP COMPLETION NOTE
ONLY when the review cycle exits with zero legitimate issues, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Review cycle invoked with all required inputs
- Red flags monitored during the cycle
- Non-convergence handled proactively
- Zero legitimate issues confirmed at exit

### FAILURE:
- Skipping the review cycle
- Not monitoring for red flags
- Accepting review exit with unresolved issues
- Not escalating non-convergence
