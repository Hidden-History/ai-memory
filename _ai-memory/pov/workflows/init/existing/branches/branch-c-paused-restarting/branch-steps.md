---
name: 'branch-c-paused-restarting'
description: 'Onboarding steps for a paused project being restarted. Validate everything is still current before resuming.'
---

# Branch C: Paused / Restarting

## BRANCH GOAL
Verify the project state is still valid and nothing has changed externally before restarting work. Re-validate requirements and architecture.

## MANDATORY SEQUENCE

### 1. Identify Why the Project Was Paused
Check project-status.md notes and last session summary.
If reason is not documented, ask user:
"The project shows no recent activity. Can you tell me:
 - Why was this paused?
 - Has anything changed since it was paused?
 - Are the original requirements still valid?"

### 2. Validate Requirements Are Still Current
- Check PRD.md -- is any requirement now outdated or changed?
- Check architecture.md -- are tech decisions still valid?
- Check for dependency updates that may affect architecture
- Check for external API or service changes during the pause

### 3. Validate Sprint State
- Is sprint-status.yaml still accurate?
- Were any stories completed outside of tracking?
- Are priorities still correct or has business context shifted?

### 4. Assess External Changes
- Package/dependency updates since pause
- Any security advisories for dependencies in use
- Breaking changes in external services since pause

### 5. Produce Restart Assessment
Document:
- What is still valid and ready to continue
- What needs to be updated or reassessed
- Recommended starting point

### 6. Confirm Restart Plan with User
Present the restart assessment:

"Here is the current state after reviewing the pause period:

 Still valid:    [what can continue as-is]
 Needs update:   [what has changed or needs reassessment]
 Recommended:    [where to restart from]

 Does this match your understanding?
 Any priorities or requirements that have changed I should know about?"

### 7. Determine Exit Route
On user confirmation of restart plan:
- If sprint is valid and can continue: exit route is WF-EXECUTION
- If sprint needs reassessment: exit route is WF-PLANNING
- If requirements have changed significantly: exit route is WF-DISCOVERY

Record the confirmed exit route for use in step-06 approval package.

## BRANCH COMPLETION
When all branch steps are complete, return to the common path: step-04-establish-baseline.md
