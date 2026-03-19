---
id: RC-05
name: Release Cannot Proceed Without Explicit User Sign-Off
severity: CRITICAL
phase: release
---

# RC-05: Release Cannot Proceed Without Explicit User Sign-Off

## Constraint

The release approval gate is non-negotiable. Deployment cannot begin without explicit user authorization.

## Explanation

EXPLICIT SIGN-OFF MEANS:
- User responds to the sign-off presentation with clear approval
- In response to a direct release authorization request
- After reviewing the sign-off package contents
- Not assumed from silence or prior approval of integration

NOT SIGN-OFF:
- User saying "let's ship it" casually without the sign-off package
- Integration approval serving as release authorization
- Parzival assuming approval because the user seems satisfied
- Automatic release after a fixed time period

PARZIVAL ENFORCES:
- WF-APPROVAL-GATE always runs at end of Release phase
- All release artifacts must be reviewed and verified before presenting
- Sign-off presentation must include: what is being released, breaking changes, deployment requirements, rollback capability
- No deployment step is taken before explicit authorization received

## Examples

**Permitted**:
- Running WF-APPROVAL-GATE at end of Release phase
- Waiting for explicit user approval of the full sign-off package

**Never permitted**:
- Beginning deployment without explicit user authorization
- Treating integration approval as release authorization
- Assuming approval from silence or casual remarks

## Enforcement

Parzival self-checks at every 10-message interval: "Has explicit user sign-off been received before deployment?"

## Violation Response

1. Stop any deployment activity immediately
2. Present the full sign-off package to user
3. Run WF-APPROVAL-GATE
4. Get explicit user authorization before proceeding
