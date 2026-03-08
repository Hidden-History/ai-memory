---
name: 'step-07-approval-gate'
description: 'Route to approval gate for release sign-off and authorize deployment'
---

# Step 7: Approval Gate

## STEP GOAL
Route to {workflows_path}/cycles/approval-gate/workflow.md for release sign-off. On approval, route to Maintenance or Planning. This is the terminal step.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: All reviewed release artifacts
- Limits: Do not deploy without explicit sign-off. Approval authorizes deployment.

## MANDATORY SEQUENCE

### 1. Prepare Release Sign-Off Package

**Release:** [milestone name / version]
**Status:** Deployment verified -- rollback plan in place

**What is being released:** User-facing summary (features and value)

**Changes to existing behavior:** Explicit list or 'No changes'
**Breaking changes:** List or 'None'

**Deployment requirements:**
- Database migrations: [yes with count / no]
- Config changes needed: [yes with list / no]
- Maintenance required: [yes / no]
- Estimated deploy time: [N] minutes

**Rollback capability:**
- Rollback available: [yes / partial]
- Rollback time: [N] minutes
- Irreversible changes: [list or 'none']

**Release artifacts:** CHANGELOG.md, release notes, deployment checklist, rollback plan (with paths)

**After release:** Project moves to [Maintenance / Next sprint planning]

**Important:** Approving this sign-off authorizes deployment.

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- release authorized
- **[R] Reject** -- changes needed before release
- **[H] Hold** -- need to review something first

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md with release milestone
2. Update CHANGELOG.md with release date if not set
3. Confirm to user with deployment and rollback plan paths
4. Note post-deployment verification steps for user

Route based on project state:
- **A) Project continues:** Load WF-PLANNING for next sprint
- **B) Project enters maintenance:** Load {workflows_path}/phases/maintenance/workflow.md
- **C) Project is complete:** Archive, confirm completion

**IF REJECTED:**
- Documentation issue: return to SM for corrections
- Deployment risk: update checklist or rollback plan
- Pre-release implementation change: return to WF-EXECUTION, then re-integrate

**IF HELD:** Wait for user review.

### 4. Post-Release Monitoring Protocol
After deployment authorization:

**Immediate Post-Deployment:**
- Remind user of key verification items from deployment checklist
- Provide rollback plan location and rollback time estimate
- Request notification when deployment is stable or if issues arise

**Post-Deployment Issue Handling:**
- If user reports a post-deployment issue: route to WF-MAINTENANCE immediately
- If issue is CRITICAL: recommend rollback first, then diagnose
- If issue is non-critical: diagnose in maintenance workflow, deploy fix as patch

**Monitoring Period Note:**
Inform user: "The release is authorized. After deployment, please verify the key items from the deployment checklist and let me know when the deployment is stable. If any issues arise, we will handle them through the maintenance workflow. The rollback plan is at [path]."

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step. When approval is received, route to appropriate next workflow.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval gate invoked with complete package
- Deployment authorization implications communicated
- Correct next workflow loaded
- Post-release monitoring noted

### FAILURE:
- Deploying without sign-off
- Not communicating irreversible changes
- Missing post-deployment verification reminder
