---
id: AC-07
name: Existing Technology Must Be Respected
severity: HIGH
phase: architecture
---

# AC-07: Existing Technology Must Be Respected

## Constraint

For projects with existing codebases, architecture cannot contradict what is already built without explicit user authorization.

## Explanation

THIS APPLIES TO:
- Existing language or runtime in use
- Existing database in production
- Existing infrastructure in place
- Existing patterns throughout the codebase

PARZIVAL ENFORCES:
- Architect instruction must include Analyst audit findings about existing technology
- If Architect recommends changing existing technology:
  - Flag this explicitly to user before proceeding
  - "The architecture recommends migrating from [X] to [Y].
     This requires [assessment of scope]. Do you approve this change?"
- Never change existing technology silently
- If user does not approve the change, architecture must work with existing technology

EXCEPTION:
- If existing technology is specifically listed as out-of-scope or a known problem to be solved in the PRD, change is authorized

## Examples

**Permitted**:
- Architecture that works with the existing technology stack
- Recommending a technology change with explicit user approval
- Changing technology that is specifically listed in the PRD as a problem to solve

**Never permitted**:
- Silently changing existing technology in the architecture
- Assuming user approval for technology changes
- Contradicting existing codebase patterns without user authorization

## Enforcement

Parzival self-checks at every 10-message interval: "Is existing technology being respected (if applicable)?"

## Violation Response

1. Identify the technology change that contradicts existing codebase
2. Flag explicitly to user with scope assessment
3. If user does not approve, revise architecture to work with existing technology
