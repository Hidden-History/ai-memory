---
name: 'step-02-check-project-files'
description: 'Check project files for requirements that directly address the issue before applying classification criteria'
nextStepFile: './step-03-classify-issue.md'
---

# Step 2: Check Project Files

## STEP GOAL
Before applying classification criteria, check whether project files speak directly to this issue. The classification must be grounded in project file citations, not in Parzival's opinion.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The fully understood issue from step-01, project files (PRD.md, architecture.md, project-context.md, story/epic files)
- Limits: Only check for direct relevance to the specific issue. Do not perform a general project file audit.

## MANDATORY SEQUENCE

### 1. Check PRD.md
- Does a requirement directly address this behavior?
- Does this issue violate an acceptance criterion?
- Record finding or "no direct guidance"

### 2. Check architecture.md
- Does this violate an architectural decision?
- Does this contradict a documented pattern or constraint?
- Record finding or "no direct guidance"

### 3. Check project-context.md
- Does this violate a coding standard or naming convention?
- Does this contradict an implementation rule?
- Record finding or "no direct guidance"

### 4. Check Story/Epic File (if applicable)
- Does this violate a story's acceptance criteria?
- Was this behavior explicitly specified?
- Record finding or "no direct guidance"

### 5. Record All Citations
If a project file speaks directly to the issue, record the specific file and section. This citation will ground the classification in the next step.

## CRITICAL STEP COMPLETION NOTE
ONLY when all relevant project files have been checked and findings recorded, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All four file categories checked in order
- Findings recorded with specific file and section citations
- Direct relevance to the specific issue identified where it exists

### FAILURE:
- Skipping project file checks
- Checking files out of order
- Not recording specific citations
- Classifying without completing this step
