---
name: 'step-05-dev-deployment-verification'
description: 'Activate DEV to verify the deployment checklist is complete, accurate, and executable'
nextStepFile: './step-06-parzival-reviews-artifacts.md'
---

# Step 5: DEV Deployment Verification

## STEP GOAL
Before release sign-off, DEV verifies the deployment checklist and rollback plan are executable. DEV performs a dry-run or verification to confirm all items can be followed.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Deployment checklist, rollback plan, architecture.md
- Limits: DEV verifies executability. Does not deploy.

## MANDATORY SEQUENCE

### 1. Prepare Verification Instruction
DEV must verify five areas:

1. **Deployment steps executable** -- Can each step be followed without additional info? Are commands correct? Are expected results achievable?
2. **Database migrations ready** -- Do files exist? Tested on staging? Reversible migrations actually reversible? Irreversible changes marked?
3. **Environment and config** -- All required env vars documented with correct names? Current values confirmed?
4. **Post-deployment verification** -- Are checks specific enough? Can each confirm pass/fail clearly?
5. **Rollback steps executable** -- Can steps be followed? Database rollback tested?

### 2. Dispatch DEV via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md with the verification instruction.

### 3. Receive Verification Assessment
DEV returns: **DEPLOYMENT READY** or **NOT READY** with specific issues.

For each issue:
- Item: [which checklist item]
- Problem: [what is wrong or missing]
- Fix: [what needs to be corrected]

### 4. Handle NOT READY
If DEV returns issues:
1. Classify each issue (legitimate gap vs false alarm)
2. Fix legitimate gaps (correct commands, add missing steps, update verification)
3. Re-verify after fixes
4. Do not proceed to sign-off with outstanding issues

## CRITICAL STEP COMPLETION NOTE
ONLY when DEV confirms DEPLOYMENT READY, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- All five verification areas checked
- DEPLOYMENT READY confirmed
- Any issues found were fixed and re-verified
- DEV dispatched through agent-dispatch workflow

### FAILURE:
- Skipping deployment verification
- Proceeding with NOT READY assessment
- Not re-verifying after fixes
- DEV dispatched directly
