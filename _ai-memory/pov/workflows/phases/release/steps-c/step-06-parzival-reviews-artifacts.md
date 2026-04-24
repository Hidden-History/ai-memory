---
name: 'step-06-parzival-reviews-artifacts'
description: 'Parzival reviews all release artifacts before presenting to user'
nextStepFile: './step-07-approval-gate.md'
---

# Step 6: Parzival Reviews All Release Artifacts

**Progress: Step 6 of 7** — Next: Approval Gate

## STEP GOAL:

Before presenting to the user, review every artifact produced in this phase: changelog, release notes, deployment checklist, and rollback plan. Return to producing agent for corrections if needed.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: All release artifacts, story files for cross-reference
- Focus: Artifact review — not presenting to user yet
- Limits: Do not present to user until all artifacts are clean.
- Dependencies: All four artifacts from Steps 1-5

- Focus on reviewing all four artifact categories against specific criteria
**Behavioral Constraints:**
- FORBIDDEN to present artifacts to user until all pass review
- Approach: Systematic review with return-to-producer for corrections
- Artifacts must be consistent with each other across all four categories

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Review CHANGELOG.md

- All completed stories represented
- No items that were not implemented
- Behavior changes to existing features documented
- Breaking changes prominently flagged (if any)
- Language is clear and accurate

---

### 2. Review Release Notes

- Written in plain language (no technical jargon)
- User-facing features described by value, not implementation
- Existing workflow changes noted
- Required user actions noted (if any)

---

### 3. Review Deployment Checklist

- All steps are specific and executable
- Database steps account for all migrations
- Configuration changes are complete
- Post-deployment verification steps are meaningful
- Rollback trigger conditions are defined
- DEV verification: DEPLOYMENT READY

---

### 4. Review Rollback Plan

- Steps are specific (not generic)
- Irreversible changes are explicitly noted
- Impact of rollback is clearly stated
- Time estimate is realistic
- Rollback is actually achievable

---

### 5. Handle Issues

If any artifact has issues:
- Return to producing agent with specific corrections
- Do not present to user until all artifacts are clean
- Re-review after corrections

## CRITICAL STEP COMPLETION NOTE

ONLY when all artifacts pass review, load and read fully `{nextStepFile}`
