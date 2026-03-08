---
id: IC-07
name: Security Full-Flow Verification Is Required for All Applicable Integrations
severity: CRITICAL
phase: integration
---

# IC-07: Security Full-Flow Verification Is Required for All Applicable Integrations

## Constraint

Any integration milestone that includes auth, data handling, or external calls requires end-to-end security verification.

## Explanation

FULL-FLOW SECURITY MEANS:
- Not just "each endpoint has auth checks" (that is story-level)
- The full user journey through multiple features is secure
- Data remains protected across all component boundaries
- Auth/authz is consistent across all new features together

REQUIRED SECURITY CHECKS AT INTEGRATION:
- Authentication flow: end-to-end from login to protected resource
- Authorization: privilege escalation possibilities across features
- Data protection: sensitive data does not leak across feature boundaries
- Session management: sessions handled consistently across features
- Input validation: consistent across all new features
- Error responses: do not expose sensitive information across features

WHEN THIS APPLIES:
- Any milestone that includes authentication or authorization features
- Any milestone that includes user data handling
- Any milestone that includes external API integration
- Any milestone that includes payment or sensitive data flows

PARZIVAL ENFORCES:
- Security full-flow is a section in the integration test plan
- DEV integration review instruction includes security full-flow checklist
- Any security finding in integration is automatically CRITICAL priority

## Examples

**Permitted**:
- Including security full-flow as a section in the integration test plan
- Running end-to-end security checks across all new features

**Never permitted**:
- Skipping security full-flow for milestones with auth or data handling
- Treating integration security findings as non-critical

## Enforcement

Parzival self-checks at every 10-message interval: "Is security full-flow verification included for applicable integrations?"

## Violation Response

1. Add security full-flow section to the integration test plan
2. Include security full-flow checklist in DEV instruction
3. Execute all security checks
4. Any security finding is automatically CRITICAL priority
