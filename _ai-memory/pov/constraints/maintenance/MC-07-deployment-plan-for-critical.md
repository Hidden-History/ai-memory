---
id: MC-07
name: CRITICAL and HIGH Fixes Must Have a Deployment Plan Before Closing
severity: HIGH
phase: maintenance
---

# MC-07: CRITICAL and HIGH Fixes Must Have a Deployment Plan Before Closing

## Constraint

Severity CRITICAL and HIGH maintenance fixes require a deployment plan before the fix is approved.

## Explanation

DEPLOYMENT PLAN FOR MAINTENANCE FIXES:
- Does not require the full WF-RELEASE process
- Does require:
  - Confirmation of deployment steps for this specific fix
  - Brief rollback plan (abbreviated — not full release rollback)
  - Post-deployment verification steps
  - Estimate of deployment time
  - Any maintenance window needed

ABBREVIATED ROLLBACK FOR HOTFIX:
- Code rollback: [specific revert command]
- Database rollback (if migration): [specific down command]
- Rollback time estimate: [N] minutes
- Irreversible changes (if any): [explicit statement]

WHY CRITICAL/HIGH REQUIRE DEPLOYMENT PLAN:
- CRITICAL fixes go to production immediately — without planning, risk
- HIGH fixes affect core functionality — deployment must be intentional
- A hotfix without a rollback plan that fails doubles the incident

MEDIUM/LOW:
- Deployment plan not required per fix
- Included in next batch patch release
- Patch release follows abbreviated WF-RELEASE

PARZIVAL ENFORCES:
- Before presenting CRITICAL/HIGH fix for user approval:
  - Verify deployment plan exists (abbreviated is sufficient)
- Fix approved without deployment plan, create plan before deployment
- Never deploy a CRITICAL fix without knowing how to roll it back

## Examples

**Permitted**:
- CRITICAL/HIGH fix with an abbreviated deployment plan including rollback steps
- MEDIUM/LOW fixes batched into next patch release without individual deployment plans

**Never permitted**:
- Deploying a CRITICAL fix without a rollback plan
- Approving a HIGH fix without deployment steps documented
- Deploying a CRITICAL fix without knowing how to roll it back

## Enforcement

Parzival self-checks at every 10-message interval: "Do CRITICAL/HIGH fixes have a deployment plan before closing?"

## Violation Response

1. Block the fix approval or deployment
2. Create an abbreviated deployment plan
3. Include specific rollback steps
4. Verify plan exists before presenting to user
