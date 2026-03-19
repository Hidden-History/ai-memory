---
id: DC-01
name: MUST Produce a PRD Before Exiting Discovery
severity: CRITICAL
phase: discovery
---

# DC-01: MUST Produce a PRD Before Exiting Discovery

## Constraint

Discovery does not exit without a complete, approved PRD (or tech-spec for Quick Flow).

## Explanation

REQUIRED OUTPUT:
- BMad Method / Enterprise: `_bmad-output/planning-artifacts/PRD.md`
- Quick Flow: `_bmad-output/planning-artifacts/tech-spec.md`

CANNOT EXIT IF:
- Document does not exist
- Document is incomplete (missing required sections)
- Document has not been reviewed by Parzival
- User has not explicitly approved

NO EXCEPTIONS:
- "We'll refine it later" is not acceptable
- A partial PRD is not an approved PRD
- Moving to Architecture without PRD approval is a CRITICAL violation

## Examples

**Permitted**:
- Exiting Discovery after user explicitly approves a complete PRD
- Iterating on the PRD until all required sections are present and reviewed

**Never permitted**:
- Advancing to Architecture with a partial or unapproved PRD
- Accepting "we'll refine it later" as a reason to proceed
- Skipping Parzival's review of the PRD before user approval

## Enforcement

Parzival self-checks at every 10-message interval: "Is the PRD on track to be complete? Any missing sections?"

## Violation Response

1. Stop the phase transition immediately
2. Identify what is missing from the PRD
3. Return to PM with specific completion instruction
4. Do not present for approval until complete
