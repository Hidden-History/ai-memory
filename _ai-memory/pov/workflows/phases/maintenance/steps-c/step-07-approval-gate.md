---
name: 'step-07-approval-gate'
description: 'Route to approval gate for maintenance fix sign-off and determine next action'
---

# Step 7: Approval Gate

**Final Step — Maintenance Complete**

## STEP GOAL:

Route to `{workflows_path}/cycles/approval-gate/workflow.md` for fix sign-off. On approval, update tracking, handle deployment, and check for queued issues. This is the terminal step per issue -- workflow loops back to step-01 for the next queued issue.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Review cycle summary, maintenance task, fix details
- Focus: Approval gate and post-approval routing
- Limits: Approval required before deployment. CRITICAL/HIGH recommend immediate deployment.
- Dependencies: Clean review cycle summary from Step 6

- Focus on presenting complete approval package and routing based on approval result
**Behavioral Constraints:**
- FORBIDDEN to deploy without explicit sign-off
- Approach: Complete package with fix summary, review summary, and deployment recommendation
- Queue management applies — loop to step-01 for next queued issue if present

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Route to Approval Gate

Invoke `{workflows_path}/cycles/approval-gate/workflow.md`.

Options:
- **[A] Approve** -- fix confirmed, proceed to deployment
- **[R] Reject** -- feedback needed
- **[H] Hold** -- need to verify something first

---

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
- Remain in Maintenance (passive) until next issue (keep maintenance constraints active)
- Or route to WF-PLANNING if new feature work is needed:
  - Drop: `{constraints_path}/maintenance/` constraints (MC-01 through MC-07)
  - Load: `{constraints_path}/planning/` constraints

**IF REJECTED:** Address feedback and re-submit.

---

### 4. Escalation to Full Release

If multiple maintenance fixes accumulate (3+ ready to deploy):
- Group into a patch release
- Update CHANGELOG.md with all fixes
- Create abbreviated deployment checklist
- Create rollback plan
- Run abbreviated release process

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step per issue — workflow loops back to step-01 for next queued issue
- Update tracking files (CHANGELOG.md, project-status.md) with fix completion information
- Route to next action: loop to step-01 (next issue), WF-PLANNING (feature work), or remain in Maintenance
- Mark maintenance issue as complete in project-status.md
