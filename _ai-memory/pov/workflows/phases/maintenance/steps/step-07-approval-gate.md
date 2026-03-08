---
name: 'step-07-approval-gate'
description: 'Route to approval gate for maintenance fix sign-off and determine next action'
---

# Step 7: Approval Gate

## STEP GOAL
Route to {workflows_path}/cycles/approval-gate/workflow.md for fix sign-off. On approval, update tracking, handle deployment, and check for queued issues. This is the terminal step per issue -- workflow loops back to step-01 for the next queued issue.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Review cycle summary, maintenance task, fix details
- Limits: Approval required before deployment. CRITICAL/HIGH recommend immediate deployment.

## MANDATORY SEQUENCE

### 1. Prepare Maintenance Fix Approval Package

**Task:** MAINT-[N] -- [issue title]
**Severity:** [CRITICAL / HIGH / MEDIUM / LOW]
**Status:** Zero legitimate issues -- ready for approval

**Fix summary:**
- Issue: plain language description
- Cause: plain language root cause
- Fix: what was changed and why

**Review summary:**
- Review passes, issues found, legitimate fixed, pre-existing fixed
- Regression tests: all passed
- Final status: zero legitimate issues

**Acceptance criteria:** All satisfied (listed)

**Additional issues found and fixed:** Pre-existing issues or 'None'

**Related issues identified (not fixed):** Out-of-scope issues logged or 'None'

**Deployment:**
- CRITICAL/HIGH: Recommend immediate deployment
- MEDIUM/LOW: Can deploy with next release or patch

### 2. Route to Approval Gate
Invoke {workflows_path}/cycles/approval-gate/workflow.md.

Options:
- **[A] Approve** -- fix confirmed, proceed to deployment
- **[R] Reject** -- feedback needed
- **[H] Hold** -- need to verify something first

### 3. Handle Approval Result

**IF APPROVED -- CRITICAL/HIGH:**
1. Update CHANGELOG.md with patch entry
2. Update project-status.md with fix, update open_issues
3. If hotfix: proceed directly to deployment (minimal release process)
4. Confirm fix approved and documented
5. Check for more queued issues

**IF APPROVED -- MEDIUM/LOW:**
1. Update project-status.md with fix
2. Add to patch release queue
3. Check for more queued issues

**IF MORE QUEUED ISSUES:**
- Loop back to step-01 with next issue
- Process in severity order

**IF NO MORE ISSUES:**
- Remain in Maintenance (passive) until next issue
- Or route to WF-PLANNING if new feature work is needed

**IF REJECTED:** Address feedback and re-submit.

### 4. Escalation to Full Release
If multiple maintenance fixes accumulate (3+ ready to deploy):
- Group into a patch release
- Update CHANGELOG.md with all fixes
- Create abbreviated deployment checklist
- Create rollback plan
- Run abbreviated release process

## CRITICAL STEP COMPLETION NOTE
This is the TERMINAL step per issue. For next issue: loop back to step-01. If no more issues: remain in Maintenance or route to WF-PLANNING.

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Approval gate invoked with complete package
- Deployment recommendation matches severity
- CHANGELOG.md updated for approved fixes
- Queue management applied for multiple issues
- Patch release triggered when appropriate

### FAILURE:
- Deploying without approval
- Not updating CHANGELOG.md
- Not checking issue queue after fix
- Silently deferring LOW issues
