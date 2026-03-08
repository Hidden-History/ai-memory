---
id: AC-03
name: Architecture Must Satisfy ALL PRD Non-Functional Requirements
severity: HIGH
phase: architecture
---

# AC-03: Architecture Must Satisfy ALL PRD Non-Functional Requirements

## Constraint

Every non-functional requirement in the PRD must be explicitly addressed in the architecture.

## Explanation

COMMON NON-FUNCTIONAL REQUIREMENTS TO CHECK:
- Performance: response time targets — how does architecture achieve them?
- Scale: concurrent user targets — where is the scaling strategy?
- Security: auth model, data protection — where is each addressed?
- Availability: uptime requirements — what redundancy exists?
- Compliance: regulatory requirements — where are they addressed?
- Accessibility: if stated in PRD — where is it addressed?

PARZIVAL ENFORCES:
- Cross-reference every non-functional requirement from PRD against architecture sections
- For each requirement: identify which section addresses it
- If any requirement is unaddressed, return to Architect
- "Architecture satisfies non-functional requirements" is only acceptable when every requirement has a specific architectural answer

## Examples

**Permitted**:
- Architecture that explicitly addresses every non-functional requirement from the PRD
- Each requirement mapped to a specific architecture section

**Never permitted**:
- Architecture that omits non-functional requirements
- Generic claims like "architecture satisfies non-functional requirements" without specific mappings

## Enforcement

Parzival self-checks at every 10-message interval: "Does architecture address all PRD non-functional requirements?"

## Violation Response

1. List all unaddressed non-functional requirements
2. Return to Architect with specific requirements to address
3. Do not present to user until all are addressed
