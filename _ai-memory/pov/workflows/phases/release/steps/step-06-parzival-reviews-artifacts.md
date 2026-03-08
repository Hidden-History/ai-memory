---
name: 'step-06-parzival-reviews-artifacts'
description: 'Parzival reviews all release artifacts before presenting to user'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Parzival Reviews All Release Artifacts

## STEP GOAL
Before presenting to the user, review every artifact produced in this phase: changelog, release notes, deployment checklist, and rollback plan. Return to producing agent for corrections if needed.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All release artifacts, story files for cross-reference
- Limits: Do not present to user until all artifacts are clean.

## MANDATORY SEQUENCE

### 1. Review CHANGELOG.md
- All completed stories represented
- No items that were not implemented
- Behavior changes to existing features documented
- Breaking changes prominently flagged (if any)
- Language is clear and accurate

### 2. Review Release Notes
- Written in plain language (no technical jargon)
- User-facing features described by value, not implementation
- Existing workflow changes noted
- Required user actions noted (if any)

### 3. Review Deployment Checklist
- All steps are specific and executable
- Database steps account for all migrations
- Configuration changes are complete
- Post-deployment verification steps are meaningful
- Rollback trigger conditions are defined
- DEV verification: DEPLOYMENT READY

### 4. Review Rollback Plan
- Steps are specific (not generic)
- Irreversible changes are explicitly noted
- Impact of rollback is clearly stated
- Time estimate is realistic
- Rollback is actually achievable

### 5. Handle Issues
If any artifact has issues:
- Return to producing agent with specific corrections
- Do not present to user until all artifacts are clean
- Re-review after corrections

## CRITICAL STEP COMPLETION NOTE
ONLY when all artifacts pass review, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All four artifact categories reviewed
- Issues corrected before user presentation
- Artifacts are consistent with each other
- Language is appropriate for audience

### FAILURE:
- Presenting artifacts with known issues
- Not reviewing all four categories
- Inconsistencies between artifacts
