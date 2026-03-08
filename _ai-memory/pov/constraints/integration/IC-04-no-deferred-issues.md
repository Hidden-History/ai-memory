---
id: IC-04
name: Integration Issues Cannot Be Deferred to Next Sprint
severity: CRITICAL
phase: integration
---

# IC-04: Integration Issues Cannot Be Deferred to Next Sprint

## Constraint

All legitimate issues found during integration must be resolved before Release proceeds.

## Explanation

WHY NO DEFERRAL:
- Integration is the last quality gate before Release
- Issues found here have been through individual story reviews and still exist — they are structural, not incidental
- Deferring them means shipping known issues
- Known issues compound — they become harder to fix after release

THIS APPLIES TO:
- Test plan failures
- Architecture cohesion issues
- Cross-feature consistency issues
- Security issues found in full-flow review
- Pre-existing issues surfaced during integration review

DEFERRAL IS NOT ACCEPTABLE EVEN FOR:
- Issues rated LOW priority
- Pre-existing issues that "were always there"
- Issues "outside" the milestone scope but found during review
- Issues estimated to be small

EXCEPTION:
- If an issue is genuinely out of scope for THIS release and does not affect release quality, create a tracked story, document it, and confirm with user explicitly before continuing
- User must explicitly acknowledge the issue and confirm deferral
- Parzival does not unilaterally defer any issue

PARZIVAL ENFORCES:
- No integration issue is silently deferred
- Every issue is classified and either fixed or explicitly user-deferred
- User-deferred issues are documented in open_issues with reason

## Examples

**Permitted**:
- Fixing all integration issues before Release
- User-deferred issues that are documented with explicit user acknowledgment

**Never permitted**:
- Silently deferring integration issues
- Deferring issues because they are LOW priority or "were always there"
- Parzival unilaterally deferring any issue

## Enforcement

Parzival self-checks at every 10-message interval: "Are all integration issues being fixed (none silently deferred)?"

## Violation Response

1. Identify the deferred issue
2. Classify it
3. Either fix it or get explicit user acknowledgment for deferral
4. Document user-deferred issues in open_issues with reason
