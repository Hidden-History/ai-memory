---
id: MC-06
name: CHANGELOG.md Must Be Updated for Every Approved Fix
severity: MEDIUM
phase: maintenance
---

# MC-06: CHANGELOG.md Must Be Updated for Every Approved Fix

## Constraint

Every approved maintenance fix — regardless of severity — gets documented in the changelog.

## Explanation

CHANGELOG UPDATE RULES FOR MAINTENANCE:
- CRITICAL/HIGH fixes: update immediately after approval
- MEDIUM/LOW fixes: update before next patch release
- Never accumulate undocumented fixes

FORMAT FOR MAINTENANCE FIXES:
Add under the next version or patch section:

### Fixed
- [Issue description in user-facing language]: [what was corrected]

### Security (if applicable)
- [Security fix description]: [what was addressed]

WHY EVERY FIX:
- Users and stakeholders need to know what changed
- An incomplete changelog erodes trust
- Undocumented changes create confusion in future debugging
- Compliance and audit requirements often require change logs

PARZIVAL ENFORCES:
- CHANGELOG.md update is part of the exit steps for every approved fix
- No maintenance cycle closes without changelog updated
- "It was a small fix" does not exempt it from documentation

## Examples

**Permitted**:
- Updating CHANGELOG.md immediately after a CRITICAL/HIGH fix is approved
- Updating CHANGELOG.md before next patch release for MEDIUM/LOW fixes

**Never permitted**:
- Accumulating undocumented fixes
- Skipping changelog update because "it was a small fix"
- Closing a maintenance cycle without updating the changelog

## Enforcement

Parzival self-checks at every 10-message interval: "Has CHANGELOG.md been updated for all approved fixes?"

## Violation Response

1. Update CHANGELOG.md immediately for the approved fix
2. Use user-facing language for the entry
3. Include security section if applicable
4. Do not close the maintenance cycle without the update
