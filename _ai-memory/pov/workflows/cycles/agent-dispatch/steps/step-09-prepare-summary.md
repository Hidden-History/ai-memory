---
name: 'step-09-prepare-summary'
description: 'Prepare the user-facing summary of what the agent accomplished. Raw agent output never reaches the user.'
---

# Step 9: Prepare User Summary

## STEP GOAL
After agent output is accepted, Parzival prepares the summary for the user. Raw agent output never reaches the user directly. The summary is written in Parzival's own words and follows the standard format.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The accepted agent output, the dispatch log for this task, any issues found and resolved, any decisions made
- Limits: Write in Parzival's own words. Never copy-paste agent output. Present only verified, reviewed information.

## MANDATORY SEQUENCE

### 1. Build the Summary
Compose the user summary covering:
- **COMPLETED:** What the agent accomplished -- in Parzival's words
- **FOUND:** Any issues discovered during the work
- **FIXED:** What was resolved and the verified basis for each fix
- **DECISION NEEDED:** Anything requiring user input
- **NEXT STEP:** Recommended next action with options if applicable

### 2. Verify Summary Quality
Before presenting:
- Is this written in Parzival's words -- not copied from agent output?
- Is it accurate -- does it match the verified output?
- Is it concise -- no unnecessary padding?
- Are any needed decisions clearly stated?
- Is the recommended next step specific?

### 3. Update Dispatch Log
Record final dispatch entry for this session:
- Agent activated
- Task assigned
- Output received: yes
- Review result: accepted (or number of correction loops)
- Final status: complete

This log feeds into the end-of-session summary and project-status.md update.

### 4. Route to Next Workflow
Based on the task type:
- Implementation task: summary feeds into WF-APPROVAL-GATE
- Planning/documentation task: summary may feed directly to user or to next workflow step

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step of the agent dispatch workflow. When the summary is prepared and the dispatch log is updated, hand off to the appropriate next workflow.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Summary written in Parzival's own words
- All five summary sections addressed (skip any marked N/A)
- Dispatch log updated with final status
- Routed to appropriate next workflow

### FAILURE:
- Copying agent output into summary
- Missing summary sections
- Not updating dispatch log
- Not routing to next workflow
