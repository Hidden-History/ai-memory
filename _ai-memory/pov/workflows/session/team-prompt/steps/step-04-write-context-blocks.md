---
name: 'step-04-write-context-blocks'
description: 'Write complete manager and worker context blocks with review protocol, quality gates, and token budgets'
nextStepFile: './step-05-assemble-prompt.md'
---

# Step 4: Write Context Blocks

## STEP GOAL
Write the complete context blocks for every manager (10 elements) and every worker (8 elements), then verify each block passes the context quality gate and respects token budgets.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Approved design from Step 3 (roster, ownership map, contracts), project files read in Step 1
- Limits: Write context blocks only — do not assemble the final prompt yet

## MANDATORY SEQUENCE

### 1. Write Manager Context Blocks (3-Tier)

For EACH manager, write ALL 10 elements:

**Element 1 — ROLE**: "You are a workflow manager (foreman) for [domain]. You spawn workers, enforce quality gates, and return verified work to the team lead. You do NOT implement anything yourself. You do NOT write code, edit files, or run tests directly."

**Element 2 — OBJECTIVE**: Specific, measurable deliverable for this domain.

**Element 3 — SCOPE**: File boundaries from the ownership map. Include "DO NOT allow workers to modify files outside their assigned sets."

**Element 4 — WORKER ROSTER**: Complete 8-element spawn prompts for each worker (see section 2 below). Each worker is spawned via **Agent tool** (subagent_type='general-purpose', no team_name), NOT as a teammate.

**Element 5 — REVIEW PROTOCOL**: Full review cycle:
- a. After EACH worker completes: spawn a review subagent (Agent tool, subagent_type='general-purpose') with a review prompt targeting this worker's deliverable
- b. If verdict is NEEDS REVISION: distill findings into a targeted fix prompt, spawn a new worker subagent with the fix prompt (fresh context), re-spawn review subagent
- c. Repeat until review returns APPROVED (zero issues)
- d. HARD LIMIT: Maximum 3 review-fix cycles per deliverable. After 3 failures, ESCALATE to lead with: what was attempted (3 cycle summaries), what keeps failing and why, assessment of the blocker
- e. Only mark task complete when review returns APPROVED

**Element 6 — TASK CHECKLIST**: Ordered list, each maps to a worker session. Include "Do NOT skip tasks. Do NOT reorder without explicit instruction."

**Element 7 — QUALITY GATES**: Domain-specific criteria the manager verifies before reporting complete. Always include: all tasks checked off, each deliverable passed review with zero issues, intra-domain integration verified (if workers interact).

**Element 8 — CONSTRAINTS**: Always include: "DO NOT implement anything yourself", "DO NOT skip review cycles", "DO NOT communicate with other managers — report ONLY to lead", "DO NOT exceed 3 review-fix cycles — escalate after 3". Add domain-specific constraints from project standards.

**Element 9 — CONTEXT FOR WORKERS**: Shared background to include in every worker spawn prompt — project context, architecture decisions, tech stack, known issues, cross-cutting conventions.

**Element 10 — REPORTING**: "When all tasks complete and all reviews pass, send a message to lead with: summary (2-3 sentences), files modified, quality metrics (X tasks, Y review cycles, Z issues fixed), issues encountered and resolved, integration risks."

### 2. Write Worker Context Blocks (All Tiers)

**BMAD Role Reference**: When a worker's role corresponds to a BMAD agent (see roster from Step 2), read the agent definition file to extract persona qualities for the ROLE and CONSTRAINTS elements. Specifically extract:
- `<role>` and `<identity>` — inject into Element 1 (ROLE) as expertise description
- `<principles>` — inject into Element 4 (CONSTRAINTS) as domain-specific rules
- `<capabilities>` — inform Element 8 (SELF-VALIDATION) with domain-appropriate checks

Do NOT include the BMAD agent's interactive activation sequence (menu, config.yaml loading, workflow.xml references, user confirmation loops). These are single-session interactive features that do not apply to headless team workers. Extract the expertise, strip the interactivity.

For EACH worker, write ALL 8 elements:

**Element 1 — ROLE**: Agent type and specialization (enriched with BMAD agent expertise when applicable).
**Element 2 — OBJECTIVE**: Specific task to complete.
**Element 3 — SCOPE**: File boundaries from ownership map. Include "DO NOT modify any files outside this list."
**Element 4 — CONSTRAINTS**: Forbidden files, required project patterns, additional standards.
**Element 5 — BACKGROUND**: Context relevant to this worker's task — architecture decisions, tech stack, known issues.
**Element 6 — DELIVERABLE**: Exactly what the worker produces, format, and where to put it.
**Element 7 — COORDINATION**: "Report completion to your caller when done. If blocked, report the blocker to your caller. Do NOT coordinate with other workers directly."
**Element 8 — SELF-VALIDATION**: Domain-specific checks:

| Domain | Typical Checks |
|--------|---------------|
| Database | Schema creates cleanly, CRUD works, indexes exist, FK cascades correct |
| Backend/API | Server starts, all endpoints respond, request/response shapes match contract, error codes correct |
| Frontend/UI | TypeScript/build succeeds, dev server starts, components render without console errors |
| Infrastructure | Services start, health checks pass, ports accessible, configs loaded |
| Tests | All test suites pass, coverage meets threshold, no flaky tests |
| Review/Audit | All files in scope reviewed, findings categorized, zero unchecked items |

Include "Do NOT report done until all checks pass."

### 3. Context Quality Gate

**For each MANAGER context, verify:**
- [ ] A fresh agent with ZERO prior context could orchestrate this entire domain using only this prompt
- [ ] All 10 elements are filled in completely
- [ ] Worker prompts within Element 4 are complete (all 8 worker elements each)
- [ ] Review prompts within Element 5 are specific to this domain's deliverables
- [ ] File paths are project-root-relative, not abbreviated
- [ ] No references to "what we discussed" or "the current approach"
- [ ] Architecture constraints are stated explicitly, not by document name alone
- [ ] The task checklist is ordered and complete

**For each WORKER context, verify:**
- [ ] A fresh agent with ZERO prior context could complete this task using only this prompt
- [ ] File paths are project-root-relative
- [ ] Self-validation checks are specific to this worker's domain (not generic "run tests")
- [ ] The deliverable format is specific, not vague

If any block fails, revise before proceeding.

### 4. Context Token Budgets

Each tier compresses context for the next. Verify approximate compliance:

| Direction | Token Budget | What to Include |
|-----------|-------------|----------------|
| Parzival -> Manager | ~2,000-3,000 | Task description, acceptance criteria, file boundaries, review protocol, worker prompts |
| Manager -> Worker | ~1,500-2,500 | Subtask spec, file boundaries, coding standards, relevant patterns |
| Worker -> Manager | ~500-1,000 | Structured completion report, test results, files changed |
| Manager -> Lead | ~300-500 | Domain status, quality metrics, blockers, summary |

**Critical rules**:
- Workers should NEVER see Parzival's full plan
- Managers should NEVER see other managers' work
- Context isolation prevents cross-contamination and error amplification

## CRITICAL STEP COMPLETION NOTE
ONLY when all context blocks are written and pass the quality gate, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every manager has all 10 elements complete
- Every worker has all 8 elements complete
- Review protocol includes 3-cycle cap and escalation procedure
- Context quality gate passes for all blocks
- Token budgets are approximately respected

### FAILURE:
- Leaving context blocks incomplete (missing elements)
- Reducing review protocol to a one-liner without cycle details
- Referencing conversation history in context blocks
- Using generic self-validation checks instead of domain-specific
- Not verifying token budgets
