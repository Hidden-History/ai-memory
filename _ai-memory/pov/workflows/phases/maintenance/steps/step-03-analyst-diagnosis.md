---
name: 'step-03-analyst-diagnosis'
description: 'Activate Analyst for root cause diagnosis when the issue is complex or unclear (skip when obvious)'
nextStepFile: './step-04-create-maintenance-task.md'
---

# Step 3: Analyst Diagnosis (When Needed)

## STEP GOAL
Activate the Analyst agent for root cause diagnosis when the issue is complex, spans multiple components, is a regression, or has an unclear cause. Skip when the fix is obvious.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Triage summary, codebase
- Limits: Analyst diagnoses. Does not fix. Provides actionable fix recommendation.

## MANDATORY SEQUENCE

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

**IF SKIPPING:** Proceed directly to {nextStepFile}

### 2. Prepare Diagnosis Instruction
Analyst must provide:
1. **Root cause** -- specific cause, not "the code is wrong"
2. **Location** -- specific files, functions, lines
3. **Scope** -- how many places need to change
4. **Fix recommendation** -- specific approach with rationale
5. **Risk** -- what could go wrong with the fix
6. **Related issues** -- anything likely to surface after fix

### 3. Dispatch Analyst via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Analyst.

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
Whether diagnosis ran or was skipped, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Correct decision about whether diagnosis is needed
- Diagnosis produces specific root cause and actionable fix
- Risk assessment included
- Related issues identified

### FAILURE:
- Skipping diagnosis for complex issues
- Accepting vague root cause
- Fix recommendation addresses symptom not cause
