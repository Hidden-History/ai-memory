---
name: 'step-01-read-issue'
description: 'Read and fully understand the issue before any classification attempt'
nextStepFile: './step-02-check-project-files.md'
---

# Step 1: Read the Issue in Full

## STEP GOAL
Before classifying, Parzival must fully understand what is being reported. Never classify an issue you have not fully read and understood.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The issue being assessed, the review report it came from, the implementation context
- Limits: Do NOT begin classification at this stage. This step is understanding only.

## MANDATORY SEQUENCE

### 1. Complete the Understanding Checklist
For the issue being assessed, determine:
- What exactly is the issue? (not a summary -- the specific problem)
- Where does it occur? (file, function, line, module)
- What is the current behavior?
- What is the expected behavior?
- What is the potential impact if not fixed?
- Is this a new issue or pre-existing?
- Was this introduced by the current task or does it predate it?

### 2. Verify Full Understanding
Before proceeding, confirm you can answer every item in the checklist. If any item is unclear, re-read the relevant source material until it is clear.

Do NOT proceed to classification until every checklist item is answered.

## CRITICAL STEP COMPLETION NOTE
ONLY when every item in the understanding checklist is answered, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Every understanding checklist item is answered
- The specific problem is identified, not just summarized
- Location is precisely identified
- Current vs expected behavior is clear
- Origin (new vs pre-existing) is determined

### FAILURE:
- Proceeding to classification without full understanding
- Skipping checklist items
- Summarizing instead of understanding the specific problem
- Not determining issue origin
