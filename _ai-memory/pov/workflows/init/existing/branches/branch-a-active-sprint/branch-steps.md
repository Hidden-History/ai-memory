---
name: 'branch-a-active-sprint'
description: 'Onboarding steps for a project with an active sprint in progress. Understand sprint state without disrupting work.'
---

# Branch A: Active Mid-Sprint

## BRANCH GOAL
Understand exactly where the sprint stands and what is in progress before doing anything. Do not disrupt in-progress work.

## MANDATORY SEQUENCE

### 1. Read Sprint Status in Full
Read sprint-status.yaml completely:
- Which stories are complete?
- Which stories are in progress?
- Which stories are not yet started?
- Are there any blockers logged?

### 2. Read All In-Progress Story Files
For each in-progress story:
- What was the implementation instruction?
- What has been done so far?
- Where did work stop?
- What remains to complete the story?

### 3. Verify Story Requirements Against PRD
For each in-progress story:
- Does the story still align with current PRD requirements?
- Have requirements changed since the story was written?
- Are acceptance criteria still valid?

### 4. Assess In-Progress Code
If partial implementation exists:
- Is the partial implementation sound?
- Are there issues in what has already been done?
- Note any issues for the review cycle

### 5. Confirm Active Task with User
Present the findings:

"The active sprint shows [story name] in progress.
 Here is the current state:
 [Summary of what is done and what remains]

 Is this accurate? Should we continue this story or
 do you want to reassess the sprint first?"

### 6. Determine Exit Route
On user confirmation of sprint state:
- If continuing current story: exit route is WF-EXECUTION
- If sprint needs reassessment: exit route is WF-PLANNING

Record the confirmed exit route for use in step-06 approval package.

## BRANCH COMPLETION
When all branch steps are complete, return to the common path: step-04-establish-baseline.md
