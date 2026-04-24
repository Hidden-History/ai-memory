---
name: 'step-04-rollback-plan'
description: 'Build the rollback plan with specific steps, irreversible change warnings, and time estimates'
nextStepFile: './step-05-dev-deployment-verification.md'
---

# Step 4: Build Rollback Plan

**Progress: Step 4 of 7** — Next: DEV Deployment Verification

## STEP GOAL:

Build a rollback plan that can be executed if deployment goes wrong. Must exist and be understood before any release proceeds. Irreversible changes must be explicitly flagged.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Deployment checklist, architecture.md, database migrations
- Focus: Rollback plan creation — honest about limitations
- Limits: Rollback must be honest about limitations. Never mark irreversible changes as reversible.
- Dependencies: Deployment checklist from Step 3

- Focus on building an honest, executable rollback plan
**Behavioral Constraints:**
- FORBIDDEN to mark irreversible changes as reversible
- Approach: Honest about limitations — never aspirational rollback
- Rollback time estimate must be realistic

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Define When to Rollback

- Rollback trigger conditions (from deployment checklist)
- Who makes the rollback decision
- Time for rollback decision after deployment

---

### 2. Code Rollback Steps

Specific steps to revert the deployment:
- Revert deployment command
- Restart services if needed
- Expected result after rollback

---

### 3. Database Rollback Steps (if applicable)

- Down migration commands
- Schema verification steps
- IMPORTANT: Flag any irreversible data changes
  - What cannot be undone
  - Impact if rollback is attempted after these ran
  - Mitigation (e.g., restore from backup)

---

### 4. Configuration Rollback Steps (if applicable)

- Revert configuration changes
- Verify old configuration is active

---

### 5. Post-Rollback Verification

- Key features: confirm working on previous version
- Database: confirm schema matches previous version
- Logs: no new errors after rollback

---

### 6. Document Rollback Limitations

- Rollback time estimate
- Data or state that will be lost on rollback
- External systems that may have been affected
- User-facing impact of rollback

## CRITICAL STEP COMPLETION NOTE

ONLY when rollback plan is complete with honest limitation documentation, load and read fully `{nextStepFile}`
