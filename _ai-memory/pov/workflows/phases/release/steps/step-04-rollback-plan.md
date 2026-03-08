---
name: 'step-04-rollback-plan'
description: 'Build the rollback plan with specific steps, irreversible change warnings, and time estimates'
nextStepFile: './step-05-dev-deployment-verification.md'
---

# Step 4: Build Rollback Plan

## STEP GOAL
Build a rollback plan that can be executed if deployment goes wrong. Must exist and be understood before any release proceeds. Irreversible changes must be explicitly flagged.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Deployment checklist, architecture.md, database migrations
- Limits: Rollback must be honest about limitations. Never mark irreversible changes as reversible.

## MANDATORY SEQUENCE

### 1. Define When to Rollback
- Rollback trigger conditions (from deployment checklist)
- Who makes the rollback decision
- Time for rollback decision after deployment

### 2. Code Rollback Steps
Specific steps to revert the deployment:
- Revert deployment command
- Restart services if needed
- Expected result after rollback

### 3. Database Rollback Steps (if applicable)
- Down migration commands
- Schema verification steps
- IMPORTANT: Flag any irreversible data changes
  - What cannot be undone
  - Impact if rollback is attempted after these ran
  - Mitigation (e.g., restore from backup)

### 4. Configuration Rollback Steps (if applicable)
- Revert configuration changes
- Verify old configuration is active

### 5. Post-Rollback Verification
- Key features: confirm working on previous version
- Database: confirm schema matches previous version
- Logs: no new errors after rollback

### 6. Document Rollback Limitations
- Rollback time estimate
- Data or state that will be lost on rollback
- External systems that may have been affected
- User-facing impact of rollback

## CRITICAL STEP COMPLETION NOTE
ONLY when rollback plan is complete with honest limitation documentation, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Rollback steps are specific (not "revert the deployment")
- Irreversible changes explicitly flagged
- Impact of rollback clearly stated
- Time estimate is realistic
- Rollback is actually achievable

### FAILURE:
- Marking irreversible changes as reversible
- Vague rollback steps
- No time estimate
- Aspirational rollback (not actually achievable)
