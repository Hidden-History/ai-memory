---
name: 'step-05-verify-understanding'
description: 'Final completeness check to ensure the project picture is complete before presenting to user'
nextStepFile: './step-06-present-and-approve.md'
---

# Step 5: Verify Understanding Is Complete

**Progress: Step 5 of 6** — Next: Present and Approve

## STEP GOAL:

Before presenting to the user, verify that the project picture is complete. No assumptions are being carried into the next phase. The recommended exit route is clearly justified.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: All findings from Steps 1-4, branch work, updated baseline files
- Focus: Completeness verification only — do not begin presenting until all checks pass
- Limits: Do not exit this workflow with unresolved uncertainty. Address gaps before presenting.
- Dependencies: Steps 1-4 and branch work must all be complete before verification

- Focus on completeness verification — ensure no assumptions are carried forward
**Behavioral Constraints:**
- FORBIDDEN to present to user with known gaps or unresolved uncertainty
- Approach: Systematic completeness check against all verification criteria
- Failed checks must be addressed before proceeding — return to earlier steps if needed

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Run Completeness Check
Verify ALL of the following:
- The current phase is confirmed and documented
- The active task (if any) is identified and its state is understood
- All available documentation has been read
- Analyst audit is complete and reviewed
- Branch-specific steps are all completed
- Knowledge gaps are resolved or explicitly deferred with user awareness
- All baseline files are current and accurate
- No assumptions are being carried into the next phase
- The recommended exit route is clearly justified

---

### 2. Handle Failed Checks
**IF ANY CHECK FAILS:**
- Address the specific gap before presenting to user
- Do not exit this workflow with unresolved uncertainty
- Return to the appropriate earlier step if needed

---

### 3. Prepare Exit Route Justification
Document why the selected exit route is correct:
- What evidence supports routing to [selected workflow]?
- Are there alternative routes that were considered and rejected?
- What would need to be true for a different route to be correct?

---

### 4. Research Project Best Practices

Once all completeness checks pass, seed the project's knowledge base with best practices for the project's technology stack.

Run `/aim-best-practices-researcher` for each major technology identified during the audit. The Analyst audit (Step 2) and baseline files (Step 4) will have confirmed the actual stack in use.

**Why now**: Existing projects may have been built with outdated patterns. Seeding current (2024-2026) best practices into Qdrant ensures that when Parzival dispatches agents for future work, they receive up-to-date guidance via Tier 2 context injection — not just the project's existing conventions.

**Priority order**:
1. Primary language/framework (e.g., Python, React, Go)
2. Database/storage technology (e.g., PostgreSQL, Qdrant, Redis)
3. Infrastructure patterns (e.g., Docker, CI/CD, deployment)
4. Testing approach (e.g., pytest, Playwright, integration testing)

**Minimum**: Research at least the primary language/framework and the primary data store.

**If Qdrant is unavailable**: Note the gap and flag for user. File-only research still has value but won't be injected to agents.

## CRITICAL STEP COMPLETION NOTE

ONLY when all completeness checks pass AND best practices research is complete, load and read fully {nextStepFile}
