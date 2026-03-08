---
name: 'step-03-dev-full-review'
description: 'Activate DEV for comprehensive code review across the entire feature set'
nextStepFile: './step-04-architect-cohesion.md'
---

# Step 3: DEV Full Review Pass

## STEP GOAL
DEV performs a comprehensive code review across the entire feature set -- not individual stories. This reviews everything: feature completeness, integration correctness, cross-feature consistency, test coverage, security, and performance.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Integration scope, test plan, all story files, PRD.md, architecture.md, project-context.md
- Limits: DEV reviews and reports. Parzival classifies findings in Step 5.

## MANDATORY SEQUENCE

### 1. Prepare DEV Integration Review Instruction
DEV must cover seven review areas:

1. **Feature completeness** -- all acceptance criteria across all stories satisfied, no PRD gaps, no partial implementations
2. **Integration correctness** -- components interact correctly at boundaries, data passed correctly, error states handled at integration points
3. **Cross-feature consistency** -- patterns consistent, naming consistent, error handling consistent, auth applied consistently
4. **Test coverage** -- integration point tests exist, test plan scenarios implemented, edge cases covered across boundaries
5. **Security across full flow** -- auth enforced consistently, input validation consistent, sensitive data protected throughout
6. **Performance considerations** -- N+1 query patterns, unnecessary data fetching, bottlenecks at integration level
7. **Pre-existing issues** -- issues in existing code that interact with new features

Provide: all story IDs, all files created/modified, all component boundaries, PRD.md, architecture.md, project-context.md, test plan.

### 2. Dispatch DEV via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate DEV with the review instruction.

### 3. Receive Review Report
DEV returns:
- Issues found with location, description, scope, severity
- Test plan execution results: PASS or FAIL for each item
- Or explicit "zero issues found" confirmation

## CRITICAL STEP COMPLETION NOTE
ONLY when DEV review report is received, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- DEV reviewed all seven areas
- Test plan items executed with clear pass/fail
- Issues reported with specific locations
- Dispatched through agent-dispatch workflow

### FAILURE:
- Spot-checking instead of full review
- Not executing test plan items
- Vague issue descriptions
- DEV dispatched directly
