---
name: 'step-01-capture-blocker'
description: 'Capture blocker details including what is blocked, the impact, and severity'
nextStepFile: './step-02-analyze-and-resolve.md'
---

# Step 1: Capture Blocker Details

## STEP GOAL
Precisely capture what is blocked, the impact on current work, and the severity level so that analysis can proceed on solid ground.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: User's description of the blocker, current task context from `{oversight_path}/tracking/task-tracker.md`
- Limits: Capture only -- do not analyze or propose resolutions in this step

## MANDATORY SEQUENCE

### 1. Identify What Is Blocked
From the user's input, extract:
- **What is failing or blocked**: The specific operation, task, or capability that cannot proceed
- **Expected behavior**: What should have happened
- **Actual behavior**: What is actually happening
- **Error messages**: Any error output, if applicable

If the user's description is insufficient, ask targeted questions to fill gaps. Do not proceed with vague descriptions.

### 2. Assess Impact
Determine:
- **Affected task(s)**: Which task ID(s) are blocked by this
- **Downstream impact**: What other work depends on unblocking this
- **Scope of impact**: Is this blocking one task, one sprint, or the entire project

### 3. Assign Severity
Use this severity scale:
- **Critical**: Project cannot proceed at all until resolved
- **High**: Current task is fully blocked, but other tasks can proceed
- **Medium**: Current task is partially blocked, workaround possible
- **Low**: Inconvenience, not truly blocking progress

### 4. Check for Similar Past Issues
Read `{oversight_path}/tracking/blockers-log.md` for previously logged blockers with similar characteristics. Note any matches.

If `{oversight_path}/learning/failure-pattern-library.md` exists, search it for known patterns.

### 5. Compile Blocker Record
Assemble the captured details:
- Blocker ID: BLK-[next sequential number from blockers log]
- Description: [specific, actionable description]
- Affected task: [task ID]
- Severity: [Critical/High/Medium/Low]
- Error/symptom: [specific error or observable behavior]
- Similar past issues: [references or "None found"]

## CRITICAL STEP COMPLETION NOTE
ONLY when all blocker details are captured and compiled, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Blocker description is specific and actionable
- Severity is assigned using the defined scale
- Impact is assessed with affected task IDs
- Past issues were checked
- No analysis or resolution was attempted in this step

### FAILURE:
- Accepting vague blocker descriptions
- Skipping severity assessment
- Not checking for similar past issues
- Attempting to solve the blocker before fully capturing it
