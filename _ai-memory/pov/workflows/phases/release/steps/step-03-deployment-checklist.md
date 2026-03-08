---
name: 'step-03-deployment-checklist'
description: 'Build the release-specific deployment checklist with pre-deployment, deployment, and post-deployment steps'
nextStepFile: './step-04-rollback-plan.md'
---

# Step 3: Build Deployment Checklist

## STEP GOAL
Build a step-by-step deployment guide specific to this release. Not a generic deployment guide -- specific to the changes in this release, including database migrations, configuration changes, and post-deployment verification.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Release summary, architecture.md deployment section
- Limits: Parzival builds this. Steps must be specific and executable.

## MANDATORY SEQUENCE

### 1. Pre-Deployment Section
- All milestone stories confirmed complete
- Integration test plan passed with date
- Integration approval received with date
- Rollback plan reviewed (from Step 4)
- Team notified of deployment (if applicable)

### 2. Database Preparation (if applicable)
- Backup database before migration (specific command)
- Review migration files (list names)
- Verify migrations are reversible (note irreversible ones)
- Test on staging first (if available)
- Confirm migration runtime estimate

### 3. Configuration Section (if applicable)
- New environment variables: name, purpose, where to set
- Configuration file changes: file, what changes, value

### 4. Deployment Steps
Each step with:
- Specific action
- Exact command (if applicable)
- Expected result (what success looks like)

### 5. Post-Deployment Verification
- Key features: verify working with specific checks
- Existing features: regression checks
- Database: verify migrations ran
- Logs: check for unexpected errors
- Performance: key metrics within range

### 6. Rollback Trigger Conditions
- Conditions that should trigger rollback
- Specific thresholds for errors and performance

### 7. Deployment Window
- Estimated deployment time
- Maintenance required: yes/no
- Communication needed: yes/no

## CRITICAL STEP COMPLETION NOTE
ONLY when the deployment checklist is complete, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Checklist is specific to this release
- Database steps account for all migrations
- Post-deployment verification is meaningful
- Rollback triggers are defined

### FAILURE:
- Generic deployment guide
- Missing database migration steps
- Vague verification ("check it works")
- No rollback triggers defined
