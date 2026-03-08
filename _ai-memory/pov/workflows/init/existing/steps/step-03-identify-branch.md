---
name: 'step-03-identify-branch'
description: 'Classify the project into one of four branches based on audit findings and route to the appropriate branch steps'
---

# Step 3: Identify Branch and Route

## STEP GOAL
Based on the combined assessment from Steps 1 and 2, determine which of the four branches applies to this project. Report the classification to the user and route to the appropriate branch-specific steps. After branch work completes, continue to step-04.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Combined assessment from Steps 1 and 2 (reading findings + Analyst audit)
- Limits: If signals are mixed, apply the more cautious branch. Ask the user to confirm if branch is still ambiguous after assessment.

## MANDATORY SEQUENCE

### 1. Evaluate Branch Criteria

**BRANCH A -- Active Mid-Sprint**
Signals:
- sprint-status.yaml exists with incomplete stories
- Story files exist with work-in-progress status
- Recent commits in the last few days/weeks
- project-status.md shows active execution phase

Key concern: Do not disrupt in-progress work.

**BRANCH B -- Legacy / Undocumented**
Signals:
- Codebase exists but PRD, architecture.md, or project-context.md missing
- Existing documentation is severely outdated or sparse
- No structured project management present
- Analyst audit reveals significant undocumented behavior

Key concern: Cannot act without documentation.

**BRANCH C -- Paused / Restarting**
Signals:
- project-status.md shows last activity beyond acceptable gap
- Work is incomplete but not actively in progress
- Sprint may be stale or sprint-status.yaml may be outdated
- Clear stopping point visible in code or docs

Key concern: Verify nothing has changed externally since pause.

**BRANCH D -- Team Handoff**
Signals:
- Documentation exists but Parzival has zero prior context
- project-status.md present but created by another system/agent
- User explicitly states this is a handoff
- Codebase and docs exist but their reliability is unknown

Key concern: Never trust inherited documentation without verification.

### 2. Handle Mixed Signals
If signals point to more than one branch:
- Apply the more cautious branch
- Branch B (legacy) takes precedence if documentation is severely lacking
- Branch D (handoff) applies whenever prior context is zero
- Ask the user to confirm if branch is still ambiguous

### 3. Report Branch Classification to User
Present the classification:

"Audit complete. Based on what I found, this project falls into:

Branch [A/B/C/D]: [Branch Name]

Key findings:
  [3-5 specific findings that led to this classification]

Proceeding with [branch name] onboarding protocol.
No changes will be made until we have a complete picture."

### 4. Route to Branch-Specific Steps
Load the appropriate branch file:

- **Branch A:** Load `./branches/branch-a-active-sprint/branch-steps.md`
- **Branch B:** Load `./branches/branch-b-messy-undocumented/branch-steps.md`
- **Branch C:** Load `./branches/branch-c-paused-restarting/branch-steps.md`
- **Branch D:** Load `./branches/branch-d-handoff-from-team/branch-steps.md`

### 5. After Branch Work Completes
When the branch-specific steps are complete, continue to:
Load `./step-04-establish-baseline.md`

## CRITICAL STEP COMPLETION NOTE
This step routes to a branch file. After the branch file completes, load step-04-establish-baseline.md to continue the common completion path.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Branch classification is based on specific audit findings (not guessing)
- Mixed signals are handled by applying the more cautious branch
- User is informed of the classification with supporting evidence
- Correct branch file is loaded

### FAILURE:
- Guessing the branch without evaluating criteria
- Choosing the least cautious branch when signals are mixed
- Not reporting the classification to the user
- Skipping branch-specific steps
