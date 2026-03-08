---
name: 'step-05-assign-priority'
description: 'Assign priority to legitimate issues to determine fix order within the current cycle'
---

# Step 5: Priority Assignment for Legitimate Issues

## STEP GOAL
All legitimate issues go on the fix list. Priority determines the fix order within the current cycle. All priorities get fixed -- LOW priority does not mean "maybe later," it means "last in this cycle."

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The classification record from step-04, the issue details from steps 01-03
- Limits: Priority only determines order within the cycle. All priorities are fixed. Do not defer any legitimate issue.

## MANDATORY SEQUENCE

### 1. Determine Priority Level

**CRITICAL -- Fix immediately before anything else**
- Security vulnerabilities (any severity)
- Bugs that break core functionality
- Issues that block the current task from completing

**HIGH -- Fix in current cycle, before task closes**
- Architecture violations
- Requirements violations
- Issues that will cause breakage

**MEDIUM -- Fix in current cycle, after CRITICAL and HIGH**
- Standards violations
- Tech debt that complicates near-term work
- Pre-existing bugs not blocking current task

**LOW -- Fix in current cycle, last**
- Tech debt with longer-term impact
- Pre-existing issues with minimal immediate risk

### 2. Handle Pre-Existing Issue Priority
When a legitimate issue predates the current task:
- Blocks current task: CRITICAL priority, fix first
- Does not block: assign appropriate priority based on criteria above, fix in cycle

### 3. Update Classification Record
Add the assigned priority to the classification record's RESOLUTION field.

### 4. Handle Batch Classification
When classifying multiple issues simultaneously:
1. List all issues first -- do not classify while listing
2. Classify each issue individually using the full criteria
3. Do not let one issue's classification influence another's
4. Record all classifications before sending any to fix list
5. Prioritize the fix list after all classifications are complete
6. Present the full classified list in one correction instruction

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step of the legitimacy check workflow. When priority is assigned and the classification record is updated, return to the calling workflow with the complete classification.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Priority is assigned from exactly one of: CRITICAL, HIGH, MEDIUM, LOW
- Priority assignment follows the defined criteria
- Pre-existing issues are prioritized based on impact, not age
- Classification record is updated with the priority
- Each issue in a batch is classified independently

### FAILURE:
- Deferring any legitimate issue regardless of priority
- Assigning priority based on opinion rather than criteria
- Letting one issue's classification influence another in batch processing
- Not updating the classification record with priority
