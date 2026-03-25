---
name: 'step-07-approval-gate'
description: 'Route to approval gate for release sign-off and authorize deployment'
---

# Step 7: Approval Gate

**Final Step — Release Complete**

## STEP GOAL:

Route to `{workflows_path}/cycles/approval-gate/workflow.md` for release sign-off. On approval, route to Maintenance or Planning. This is the terminal step.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on presenting complete sign-off package and routing based on approval result
- 🚫 FORBIDDEN to deploy without explicit approval sign-off
- 💬 Approach: Complete package communicating deployment implications clearly
- 📋 Post-deployment monitoring protocol must be communicated upon approval

## EXECUTION PROTOCOLS:

- 🎯 Prepare complete release sign-off package and invoke approval gate cycle
- 💾 Update project-status.md and CHANGELOG.md with release date upon approval
- 📖 Route to appropriate next workflow based on approval result and project state
- 🚫 FORBIDDEN to authorize deployment before explicit sign-off received

## CONTEXT BOUNDARIES:

- Available context: All reviewed release artifacts
- Focus: Approval gate and post-approval routing
- Limits: Do not deploy without explicit sign-off. Approval authorizes deployment.
- Dependencies: All four reviewed artifacts from Step 6

## Sequence of Instructions (Do not deviate, skip, or optimize)

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

---

### 2. Route to Approval Gate

Invoke `{workflows_path}/cycles/approval-gate/workflow.md`.

Options:
- **[A] Approve** -- release authorized
- **[R] Reject** -- changes needed before release
- **[H] Hold** -- need to review something first

---

### 3. Handle Approval Result

**IF APPROVED:**
1. Update project-status.md with release milestone
2. Update CHANGELOG.md with release date if not set
3. Confirm to user with deployment and rollback plan paths
4. Note post-deployment verification steps for user

Route based on project state:
- **A) Project continues:** Load WF-PLANNING for next sprint
  - Drop: `{constraints_path}/release/` constraints (RC-01 through RC-07)
  - Load: `{constraints_path}/planning/` constraints
- **B) Project enters maintenance:** Load `{workflows_path}/phases/maintenance/workflow.md`
  - Drop: `{constraints_path}/release/` constraints (RC-01 through RC-07)
  - Load: `{constraints_path}/maintenance/` constraints
- **C) Project is complete:** Archive, confirm completion
  - Drop: `{constraints_path}/release/` constraints (RC-01 through RC-07)
  - No new constraints to load

**IF REJECTED:**
- Documentation issue: return to SM for corrections
- Deployment risk: update checklist or rollback plan
- Pre-release implementation change: return to WF-EXECUTION, then re-integrate

**IF HELD:** Wait for user review.

---

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

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — release workflow completion required
- Update tracking files (project-status.md, CHANGELOG.md) with release milestone information
- Route to appropriate next workflow: WF-PLANNING, WF-MAINTENANCE, or project archive
- Mark release as complete with deployment authorization in project-status.md

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Approval gate invoked with complete package
- Deployment authorization implications communicated
- Correct next workflow loaded
- Post-release monitoring noted

### ❌ SYSTEM FAILURE:

- Deploying without sign-off
- Not communicating irreversible changes
- Missing post-deployment verification reminder

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
