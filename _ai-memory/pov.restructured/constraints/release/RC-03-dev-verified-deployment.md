---
id: RC-03
name: Deployment Checklist Must Be DEV-Verified Before Sign-Off
severity: HIGH
phase: release
---

# RC-03: Deployment Checklist Must Be DEV-Verified Before Sign-Off

## Constraint

The deployment checklist is not a self-reported document — it must be verified by the DEV agent.

## Explanation

VERIFICATION MEANS:
- DEV reviews each checklist item for executability
- DEV confirms migration files exist and are correct
- DEV confirms environment variable names are accurate
- DEV confirms deployment steps are specific and executable
- DEV confirms post-deployment verification steps are meaningful
- DEV returns DEPLOYMENT READY assessment

NOT VERIFIED:
- Parzival reviewing the checklist without DEV validation
- SM creating the checklist without DEV review
- User approving deployment steps without DEV confirmation

WHY:
- Deployment checklists written without DEV verification contain gaps that only surface during deployment
- DEV knows which commands are correct for the current stack
- DEV can flag steps that will fail before they fail in production

PARZIVAL ENFORCES:
- Phase 5 DEV verification instruction is mandatory
- DEPLOYMENT READY assessment required before Phase 6
- Any issues found by DEV, fix and re-verify before sign-off

## Examples

**Permitted**:
- DEV reviewing and verifying each deployment checklist item
- Getting a DEPLOYMENT READY assessment from DEV before sign-off

**Never permitted**:
- Presenting deployment checklist to user without DEV verification
- Parzival reviewing the checklist alone without DEV validation
- SM creating the checklist without DEV review

## Enforcement

Parzival self-checks at every 10-message interval: "Has the deployment checklist been DEV-verified?"

## Violation Response

1. Send Phase 5 DEV verification instruction
2. Wait for DEPLOYMENT READY assessment
3. Fix any issues found by DEV
4. Re-verify before proceeding to sign-off
