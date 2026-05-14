---
name: 'step-03-identify-branch'
description: 'Classify the project into one of four branches based on audit findings and route to the appropriate branch steps'
---

# Step 3: Identify Branch and Route

**Progress: Step 3 of 6** — Next: Establish Baseline (after branch)

## STEP GOAL:

Based on the combined assessment from Steps 1 and 2, determine which of the four branches applies to this project. Report the classification to the user and route to the appropriate branch-specific steps. After branch work completes, continue to step-04.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Combined assessment from Steps 1 and 2 (reading findings + Analyst audit)
- Focus: Branch classification and routing only — do not begin branch-specific work in this step
- Limits: If signals are mixed, apply the more cautious branch. Ask user to confirm if still ambiguous.
- Dependencies: Steps 1 and 2 must be complete — combined assessment required for classification

- Focus on classifying the project into exactly one branch based on audit evidence
**Behavioral Constraints:**
- FORBIDDEN to guess the branch without evaluating all criteria against findings
- Approach: Evaluate branch criteria systematically, apply most cautious when mixed signals
- Always present branch classification with supporting evidence to user before routing

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Handle Mixed Signals
If signals point to more than one branch:
- Apply the more cautious branch
- Branch B (legacy) takes precedence if documentation is severely lacking
- Branch D (handoff) applies whenever prior context is zero
- Ask the user to confirm if branch is still ambiguous

---

### 3. Report Branch Classification to User
Present the classification:

"Audit complete. Based on what I found, this project falls into:

Branch [A/B/C/D]: [Branch Name]

Key findings:
  [3-5 specific findings that led to this classification]

Proceeding with [branch name] onboarding protocol.
No changes will be made until we have a complete picture."

---

### 4. Route to Branch-Specific Steps
Load the appropriate branch file:

- **Branch A:** Load `{workflows_path}/init/existing/branches/branch-a-active-sprint/branch-steps.md`
- **Branch B:** Load `{workflows_path}/init/existing/branches/branch-b-messy-undocumented/branch-steps.md`
- **Branch C:** Load `{workflows_path}/init/existing/branches/branch-c-paused-restarting/branch-steps.md`
- **Branch D:** Load `{workflows_path}/init/existing/branches/branch-d-handoff-from-team/branch-steps.md`

---

### 5. After Branch Work Completes
When the branch-specific steps are complete, continue to:
Load `./step-04-establish-baseline.md`

## CRITICAL STEP COMPLETION NOTE

This step routes to a branch file. After the branch file completes, load step-04-establish-baseline.md to continue the common completion path.
