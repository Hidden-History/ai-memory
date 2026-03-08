---
name: 'step-02-classify-issue'
description: 'Classify whether the issue is a maintenance fix or a new feature requiring sprint planning'
nextStepFile: './step-03-analyst-diagnosis.md'
---

# Step 2: Classify -- Maintenance Fix or New Feature?

## STEP GOAL
Not everything that arrives as an "issue" is a maintenance fix. Classify to prevent Maintenance from becoming unplanned development. New features route to Planning.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Triage summary from Step 1, PRD.md
- Limits: Classification determines routing. Be honest about what is a fix vs. a feature.

## MANDATORY SEQUENCE

### 1. Apply Classification Decision Tree

**Is this a bug -- system fails to do what it was designed to do?**
YES -> Maintenance fix

**Is this a performance regression from a known baseline?**
YES -> Maintenance fix

**Is this a security vulnerability in existing functionality?**
YES -> Maintenance fix (CRITICAL priority)

**Is this a request for new behavior not in the PRD?**
YES -> New feature -> route to WF-PLANNING

**Is this a significant enhancement that changes product scope?**
YES -> New feature -> route to WF-PLANNING

**Is this a minor UX improvement or small enhancement to existing behavior?**
-> Maintenance fix (LOW priority)

**Is this tech debt that has become blocking?**
-> Maintenance fix (priority based on impact)

### 2. Handle New Feature Classification
If classified as new feature:
- Inform user: "This request introduces new behavior not in the current PRD. It will be treated as a new feature rather than a maintenance fix."
- Create a story for it in the backlog
- Route to WF-PLANNING when appropriate
- Continue with maintenance queue

**IF NEW FEATURE:** Do not continue to step-03. Route appropriately and process next maintenance issue.

### 3. Confirm Maintenance Fix Classification
Record the classification with reasoning. Proceed to diagnosis or fix.

## CRITICAL STEP COMPLETION NOTE
If classified as new feature: route to WF-PLANNING and stop this chain.
If classified as maintenance fix: load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Decision tree applied honestly
- New features correctly identified and routed
- Maintenance scope stays tight
- Classification reasoning documented

### FAILURE:
- Treating new features as maintenance fixes
- Expanding maintenance scope without user approval
- Not routing new features to Planning
