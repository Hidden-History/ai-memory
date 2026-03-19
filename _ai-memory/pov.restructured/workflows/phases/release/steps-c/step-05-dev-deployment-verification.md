---
name: 'step-05-dev-deployment-verification'
description: 'Define deployment verification scope and dispatch DEV via agent-dispatch cycle'
nextStepFile: './step-06-parzival-reviews-artifacts.md'
---

# Step 5: DEV Deployment Verification

**Progress: Step 5 of 7** — Next: Parzival Reviews All Release Artifacts

## STEP GOAL:

Define the deployment verification scope and dispatch DEV via the agent-dispatch cycle. Before release sign-off, DEV verifies the deployment checklist and rollback plan are executable. DEV performs a dry-run or verification to confirm all items can be followed.

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

- 🎯 Focus on scoping verification and dispatching DEV via agent-dispatch
- 🚫 FORBIDDEN to proceed with NOT READY assessment from DEV
- 💬 Approach: Five verification areas must all be checked — no partial verification
- 📋 Issues found must be fixed and re-verified before DEPLOYMENT READY is confirmed

## EXECUTION PROTOCOLS:

- 🎯 Prepare complete verification instruction covering five areas, dispatch via agent-dispatch
- 💾 Record DEV verification assessment and any issues found/fixed
- 📖 Load next step only after DEV confirms DEPLOYMENT READY
- 🚫 FORBIDDEN to proceed without DEPLOYMENT READY confirmation

## CONTEXT BOUNDARIES:

- Available context: Deployment checklist, rollback plan, architecture.md
- Focus: Deployment verification dispatch — does not deploy
- Limits: DEV verifies executability only. Does not deploy.
- Dependencies: Deployment checklist from Step 3, rollback plan from Step 4

## Sequence of Instructions (Do not deviate, skip, or optimize)

### Parzival's Responsibility (Layer 1)

#### 1. Prepare Verification Instruction

DEV must verify five areas:

1. **Deployment steps executable** -- Can each step be followed without additional info? Are commands correct? Are expected results achievable?
2. **Database migrations ready** -- Do files exist? Tested on staging? Reversible migrations actually reversible? Irreversible changes marked?
3. **Environment and config** -- All required env vars documented with correct names? Current values confirmed?
4. **Post-deployment verification** -- Are checks specific enough? Can each confirm pass/fail clearly?
5. **Rollback steps executable** -- Can steps be followed? Database rollback tested?

---

### Execution (via agent-dispatch cycle)

#### 2. Dispatch DEV via Agent Dispatch

Invoke `{workflows_path}/cycles/agent-dispatch/workflow.md` with the verification instruction.

---

### Parzival's Responsibility (Layer 1)

#### 3. Receive Verification Assessment

DEV returns: **DEPLOYMENT READY** or **NOT READY** with specific issues.

For each issue:
- Item: [which checklist item]
- Problem: [what is wrong or missing]
- Fix: [what needs to be corrected]

---

#### 4. Handle NOT READY

If DEV returns issues:
1. Classify each issue (legitimate gap vs false alarm)
2. Fix legitimate gaps (correct commands, add missing steps, update verification)
3. Re-verify after fixes
4. Do not proceed to sign-off with outstanding issues

## CRITICAL STEP COMPLETION NOTE

ONLY when DEV confirms DEPLOYMENT READY, load and read fully `{nextStepFile}`

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- All five verification areas checked
- DEPLOYMENT READY confirmed
- Any issues found were fixed and re-verified
- DEV dispatched through agent-dispatch workflow

### ❌ SYSTEM FAILURE:

- Skipping deployment verification
- Proceeding with NOT READY assessment
- Not re-verifying after fixes
- DEV dispatched directly

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
