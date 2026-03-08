---
name: 'step-04-architect-cohesion'
description: 'Activate Architect to verify architectural cohesion across the completed milestone'
nextStepFile: './step-05-review-findings.md'
---

# Step 4: Architect Cohesion Check

## STEP GOAL
After DEV's review, activate the Architect to verify the architecture is intact across the full feature set. Individual story reviews cannot catch system-level architecture drift.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: architecture.md, all modified files, DEV review report
- Limits: Architect checks cohesion. Parzival classifies findings in next step.

## MANDATORY SEQUENCE

### 1. Prepare Cohesion Check Instruction
Architect must cover six cohesion areas:

1. **Architectural pattern compliance** -- patterns documented in architecture.md actually used, deviations identified, contradictions found
2. **Component boundary integrity** -- boundaries maintained as designed, no inappropriate direct dependencies, coupling violations
3. **Data architecture compliance** -- data models as designed, access patterns following documented approach
4. **Security architecture compliance** -- authentication as designed, authorization model correct
5. **Infrastructure alignment** -- code deployable as specified, no contradicting assumptions
6. **Technical debt assessment** -- shortcuts that create architectural debt, patterns making future development harder

### 2. Dispatch Architect via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the Architect. Provide architecture.md, all modified files, and DEV review report.

### 3. Receive Cohesion Assessment
Architect returns:

**COHESION: CONFIRMED** -- Architecture is intact across milestone.

**COHESION: ISSUES FOUND** -- For each issue:
- Location: [file/component]
- Violation: [which architecture decision is violated]
- Impact: [what this affects]
- Required fix: [what needs to change]

## CRITICAL STEP COMPLETION NOTE
ONLY when Architect cohesion assessment is received, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All six cohesion areas reviewed
- Clear CONFIRMED or ISSUES FOUND verdict
- Issues documented with architectural basis
- Dispatched through agent-dispatch workflow

### FAILURE:
- Skipping cohesion check
- Accepting vague cohesion assessment
- Not providing DEV review report as context
- Architect dispatched directly
