---
name: 'step-01-establish-scope'
description: 'Define exactly what is being integrated -- features, integration points, and known risks'
nextStepFile: './step-02-prepare-test-plan.md'
---

# Step 1: Establish Integration Scope

## STEP GOAL
Before any agent is activated, Parzival defines exactly what is being integrated. Compile the scope from sprint status, feature definitions, and integration points.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: sprint-status.yaml, story files, epic files, architecture.md, PRD.md
- Limits: Only define scope. Do not activate agents. Do not begin review.

## MANDATORY SEQUENCE

### 1. Read Sprint Completion Status
From sprint-status.yaml:
- All milestone stories: confirmed complete and user-approved?
- Any carryover stories that should be in this milestone?
- Any stories explicitly excluded?

### 2. Define Feature Set
- Which epics are part of this integration milestone?
- Which features are being integrated for the first time?
- Which existing features may be affected by new work?

### 3. Identify Integration Points
- **New to New:** How do new features interact with each other?
- **New to Existing:** How does new code interact with pre-existing code?
- **External:** How does the system interact with external services/APIs?
- **Data:** How does data flow through the full feature set?

### 4. Identify Known Risks
- Issues deferred during story reviews needing integration attention
- Implementation decisions that could affect system-wide behavior
- Performance concerns from individual story reviews

### 5. Compile Integration Scope Document
```
INTEGRATION MILESTONE: [name]
SPRINT/STORIES INCLUDED: [list]
FEATURES BEING INTEGRATED: [list]
INTEGRATION POINTS:
  Internal: [component-to-component touchpoints]
  External: [external service touchpoints]
KNOWN RISKS: [from development phase]
EXCLUDED: [what is intentionally not part of this pass]
```

## CRITICAL STEP COMPLETION NOTE
ONLY when integration scope is fully defined, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All milestone stories confirmed complete
- Integration points specifically identified
- Known risks documented
- Scope is comprehensive (not a spot check)

### FAILURE:
- Missing milestone stories from scope
- Not identifying integration points
- Ignoring known risks from development
