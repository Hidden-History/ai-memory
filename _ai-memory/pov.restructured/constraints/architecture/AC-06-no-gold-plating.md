---
id: AC-06
name: No Gold-Plating — Architecture Must Fit Project Scale
severity: MEDIUM
phase: architecture
---

# AC-06: No Gold-Plating — Architecture Must Fit Project Scale

## Constraint

Architecture complexity must be justified by project requirements, not aspirational engineering.

## Explanation

GOLD-PLATING INDICATORS:
- Microservices for a project with 2-3 bounded contexts
- Event sourcing for a simple CRUD application
- Multi-region deployment for a prototype
- Complex caching layers when scale doesn't require them
- Abstraction layers with no current justification

THE TEST:
- For every architectural decision: which PRD requirement justifies this?
- If the answer is "future scalability" for a current-scale project that doesn't require it, that is gold-plating
- If the answer is "best practice" without a specific requirement, that is gold-plating

PARZIVAL ENFORCES:
- Flag any over-engineered components during architecture review
- Ask Architect: "Which PRD requirement justifies [pattern]?"
- If justification is weak, simplify the architecture
- Complexity is a cost — it must earn its place

EXCEPTION:
- Enterprise track projects have different scale expectations
- User-stated future requirements that are confirmed and documented are acceptable justification for additional complexity

## Examples

**Gold-plating**:
- Microservices for a project with 2-3 bounded contexts
- Event sourcing for a simple CRUD application
- Multi-region deployment for a prototype

**Justified complexity**:
- Microservices when PRD specifies independent scaling of 10+ distinct services
- Caching when PRD performance requirements cannot be met without it

## Enforcement

Parzival self-checks at every 10-message interval: "Is there any gold-plating without PRD justification?"

## Violation Response

1. Identify the over-engineered component
2. Ask Architect: "Which PRD requirement justifies [pattern]?"
3. If justification is weak, simplify the architecture
4. If user has confirmed future requirements that justify it, document and accept
