---
id: AC-02
name: CANNOT Choose Stack Without User Approval
severity: HIGH
phase: architecture
---

# AC-02: CANNOT Choose Stack Without User Approval

## Constraint

Architecture technology choices are not finalized until the user explicitly approves them.

## Explanation

THIS APPLIES TO:
- Primary language and runtime
- Frameworks (frontend and backend)
- Database selection
- Infrastructure and hosting approach
- Any third-party service that incurs cost or creates lock-in
- Any technology that requires specific expertise

USER MUST BE AWARE OF:
- What was chosen and why
- What alternatives were considered
- Any significant trade-offs or lock-in risks
- Cost implications if applicable

PARZIVAL ENFORCES:
- Present tech stack summary clearly in architecture review
- Highlight any choices with significant trade-offs
- Never advance to epics/stories until user has approved architecture
- If user requests a different tech choice, assess impact, update, re-review

## Examples

**Permitted**:
- Presenting tech stack summary to user with rationale and trade-offs
- Waiting for explicit user approval before advancing to story creation

**Never permitted**:
- Advancing to epics/stories without user approval of the tech stack
- Finalizing technology choices without presenting alternatives considered

## Enforcement

Parzival self-checks at every 10-message interval: "Has user approved the tech stack choices?"

## Violation Response

1. Stop any story creation or downstream work
2. Present tech stack summary to user with rationale
3. Highlight significant trade-offs
4. Get explicit user approval before proceeding
