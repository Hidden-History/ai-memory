---
name: 'step-03-analyst-diagnosis'
description: 'Activate Analyst for root cause diagnosis when the issue is complex or unclear (skip when obvious)'
nextStepFile: './step-04-create-maintenance-task.md'
---

# Step 3: Analyst Diagnosis (When Needed)

**Progress: Step 3 of 7** — Next: Create Maintenance Task

## STEP GOAL:

Activate the Analyst agent for root cause diagnosis when the issue is complex, spans multiple components, is a regression, or has an unclear cause. Skip when the fix is obvious.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Triage summary from Step 1, maintenance fix classification from Step 2, codebase
- Focus: Root cause diagnosis — not implementing the fix
- Limits: Analyst diagnoses only. Does not fix. Provides actionable recommendation.
- Dependencies: Maintenance fix classification from Step 2

- Focus on determining if diagnosis is needed and dispatching Analyst correctly
**Behavioral Constraints:**
- FORBIDDEN to accept vague root cause or diagnosis addressing only symptoms
- Approach: Evidence-based decision on diagnosis need, specific requirements
- If diagnosis is skipped, root cause must already be known and documented

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine If Diagnosis Is Needed

**Activate Analyst when:**
- Root cause is unclear
- Issue may span multiple components
- Regression requires identifying what changed
- Performance issue needs profiling
- Security vulnerability requires understanding attack surface

**Skip Analyst when:**
- Root cause is obvious from bug report and code
- Fix is clear and contained to a known location
- User or monitoring already identified specific cause

**IF SKIPPING:** Proceed directly to `{nextStepFile}`

---

### 2. Prepare Diagnosis Instruction

Analyst must provide:
1. **Root cause** -- specific cause, not "the code is wrong"
2. **Location** -- specific files, functions, lines
3. **Scope** -- how many places need to change
4. **Fix recommendation** -- specific approach with rationale
5. **Risk** -- what could go wrong with the fix
6. **Related issues** -- anything likely to surface after fix

---

### 3. Dispatch Analyst via Agent Dispatch

Invoke `{workflows_path}/cycles/agent-dispatch/workflow.md` to activate the Analyst.

---

### 4. Review Diagnosis

Parzival reviews for:
- Is root cause specific?
- Is fix recommendation actionable?
- Does fix address root cause (not just symptom)?
- Is risk assessment realistic?
- Are related issues noted?

**IF vague or incomplete:** Return to Analyst for specifics.
**IF clear:** Proceed to maintenance task creation.

## CRITICAL STEP COMPLETION NOTE

Whether diagnosis ran or was skipped, load and read fully `{nextStepFile}`
