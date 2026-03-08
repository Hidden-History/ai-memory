---
id: RC-04
name: Breaking Changes Must Be Explicitly Surfaced to User
severity: CRITICAL
phase: release
---

# RC-04: Breaking Changes Must Be Explicitly Surfaced to User

## Constraint

Any change that breaks existing API contracts, user workflows, or data compatibility must be explicitly shown to the user before sign-off.

## Explanation

BREAKING CHANGES INCLUDE:
- API changes that break existing consumers
- Removal of features that users may depend on
- Changes to data formats or structures that break compatibility
- Changes to user workflows that require user re-learning
- Database schema changes that are irreversible

SURFACING MEANS:
- Listed prominently in the sign-off presentation
- Not buried in the changelog
- Impact described in plain language ("users will need to...")
- Mitigation described if available ("we recommend communicating...")

NOT ACCEPTABLE:
- Breaking changes mentioned only in technical changelog
- Breaking changes described in developer language without user impact
- Breaking changes omitted from sign-off presentation

PARZIVAL ENFORCES:
- Breaking changes are identified during Phase 1 compilation
- Breaking changes appear in a dedicated section of the sign-off presentation
- If no breaking changes exist, explicitly state "None" (not omit the section)
- User cannot unknowingly approve a breaking change

## Examples

**Permitted**:
- Breaking changes listed prominently in sign-off presentation with plain-language impact
- Explicitly stating "None" when no breaking changes exist

**Never permitted**:
- Breaking changes buried in the technical changelog
- Breaking changes omitted from sign-off presentation
- User unknowingly approving a breaking change

## Enforcement

Parzival self-checks at every 10-message interval: "Are breaking changes explicitly surfaced in the sign-off?"

## Violation Response

1. Identify all breaking changes
2. Add to a dedicated section of the sign-off presentation
3. Describe impact in plain language
4. Describe mitigation if available
5. Present to user before sign-off
