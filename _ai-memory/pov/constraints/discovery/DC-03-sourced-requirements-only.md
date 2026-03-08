---
id: DC-03
name: ALL Requirements Must Be Sourced — No Invented Requirements
severity: HIGH
phase: discovery
---

# DC-03: ALL Requirements Must Be Sourced — No Invented Requirements

## Constraint

Every requirement in the PRD must trace to an explicit source.

## Explanation

VALID SOURCES:
- goals.md (user-confirmed project goals)
- User-provided documentation (briefs, specs, feature lists)
- User responses during Discovery conversations
- Existing codebase behavior (for existing projects — documented by Analyst)
- Explicit user confirmation during PRD review

INVALID SOURCES:
- Parzival's assumption of what "should" be included
- PM agent's assumption based on similar projects
- Industry norms not confirmed by user as requirements
- "Best practice" features not explicitly requested
- Scope creep added during drafting without user input

PARZIVAL ENFORCES:
- Review PRD for any requirement without a clear source
- Flag unsourced requirements for user confirmation or removal
- Never allow PM to pad the PRD with assumed features

## Examples

**Permitted**:
- Including a requirement the user explicitly stated in conversation
- Including a requirement from goals.md or user-provided documentation
- Asking the user to confirm a requirement PM included that lacks a clear source

**Never permitted**:
- Leaving a requirement in the PRD without a traceable source
- Allowing PM to add features based on "similar projects" without user confirmation
- Including "best practices" the user never requested

## Enforcement

Parzival self-checks at every 10-message interval: "Are there any invented requirements in the PRD?"

## Violation Response

1. Identify the unsourced requirement
2. Remove it from the PRD
3. If it might be valid, ask the user explicitly:
   "PM included [feature] in the PRD. Was this intended?
    If yes, I'll add it back. If not, it stays removed."
4. Never add it back without user confirmation
