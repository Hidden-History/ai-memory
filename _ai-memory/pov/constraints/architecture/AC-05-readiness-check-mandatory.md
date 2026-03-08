---
id: AC-05
name: Implementation Readiness Check Cannot Be Skipped
severity: CRITICAL
phase: architecture
---

# AC-05: Implementation Readiness Check Cannot Be Skipped

## Constraint

The Architect's implementation readiness check is mandatory before Architecture exits.

## Explanation

THE CHECK VALIDATES:
- PRD requirements are fully covered by stories
- Architecture is sufficient for all story technical contexts
- No stories require decisions not made in architecture
- No contradictions between documents
- No implementation blockers exist

WHY IT CANNOT BE SKIPPED:
- Gaps discovered during implementation are expensive
- A gap that takes 30 minutes to fix in Architecture takes days to fix after implementation is underway
- The readiness check exists precisely to catch these gaps

IF READINESS CHECK RETURNS NOT READY:
- Fix the identified gaps before exiting Architecture
- Do not route to Planning with known blockers
- Re-run readiness check after fixes

PARZIVAL ENFORCES:
- Architecture does not exit without a READY result
- READY result must come from the Architect agent after reviewing all three document sets together

## Examples

**Permitted**:
- Running the readiness check before exiting Architecture
- Fixing gaps identified by the readiness check and re-running it

**Never permitted**:
- Exiting Architecture without a READY result from the Architect
- Routing to Planning with known blockers
- Skipping the readiness check because "the architecture looks complete"

## Enforcement

Parzival self-checks at every 10-message interval: "Has implementation readiness check been run and passed?"

## Violation Response

1. Block the Architecture exit
2. Run the readiness check
3. Fix any identified gaps
4. Re-run readiness check until READY result is returned
