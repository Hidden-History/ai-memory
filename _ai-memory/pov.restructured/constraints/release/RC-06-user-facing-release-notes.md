---
id: RC-06
name: Release Notes Must Be Written for the User/Stakeholder Audience
severity: MEDIUM
phase: release
---

# RC-06: Release Notes Must Be Written for the User/Stakeholder Audience

## Constraint

Release notes are not technical documentation. They are written for people who need to understand what changed and why it matters.

## Explanation

USER/STAKEHOLDER AUDIENCE MEANS:
- Plain language — no implementation details
- Focus on what users can now DO (not what was built)
- Describe value, not mechanism
- Explain impact on existing workflows
- Note any action required from users

TECHNICAL LANGUAGE NOT ALLOWED IN RELEASE NOTES:
- "Refactored the authentication service"
- "Added an index to the users table"
- "Implemented JWT token refresh"
- "Fixed N+1 query in the product listing"

EQUIVALENT USER-FACING LANGUAGE:
- "Login is now more reliable and stays active longer"
- "Product pages load significantly faster"
- "You can now stay logged in without being unexpectedly signed out"

PARZIVAL ENFORCES:
- Release notes are reviewed in Phase 6 for audience appropriateness
- Technical entries, return to SM for user-facing rewrite
- Every technical improvement must have a user-facing translation or be grouped under "Performance and reliability improvements"

## Examples

**Technical (not permitted)**:
- "Refactored the authentication service"
- "Added an index to the users table"
- "Implemented JWT token refresh"
- "Fixed N+1 query in the product listing"

**User-facing (permitted)**:
- "Login is now more reliable and stays active longer"
- "Product pages load significantly faster"
- "You can now stay logged in without being unexpectedly signed out"

## Enforcement

Parzival self-checks at every 10-message interval: "Are release notes written for user/stakeholder audience?"

## Violation Response

1. Identify technical entries in release notes
2. Return to SM for user-facing rewrite
3. Group pure technical improvements under "Performance and reliability improvements"
4. Ensure every entry focuses on user value, not mechanism
