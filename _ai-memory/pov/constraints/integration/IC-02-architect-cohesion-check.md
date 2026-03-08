---
id: IC-02
name: Architect Cohesion Check Is Mandatory
severity: CRITICAL
phase: integration
---

# IC-02: Architect Cohesion Check Is Mandatory

## Constraint

The Architect agent must run a cohesion check before integration can pass.

## Explanation

WHY THIS CANNOT BE SKIPPED:
- Individual story reviews verify code quality per story
- They cannot verify system-level architectural integrity
- Architecture drift accumulates across stories and only becomes visible at the integration level
- If architectural issues reach Release, they become production problems

THE CHECK CANNOT BE REPLACED BY:
- Parzival's own review of architecture compliance
- DEV agent's assessment of architectural correctness
- Assumption that "the stories passed their reviews"

COHESION CHECK MUST COVER:
- Pattern compliance (architecture patterns actually used)
- Component boundary integrity (no inappropriate coupling)
- Data architecture compliance (models and access patterns)
- Security architecture compliance (auth/authz as designed)
- Infrastructure alignment (code is deployable as designed)

AFTER FIXES:
- If architectural issues were found and fixed, re-run cohesion check
- Cohesion check re-runs until CONFIRMED result is returned
- A CONFIRMED result from before fixes does not carry forward

PARZIVAL ENFORCES:
- Phase 4 Architect instruction is sent before integration can advance
- CONFIRMED result (or re-confirmed after fixes) required to exit

## Examples

**Permitted**:
- Running the Architect cohesion check before integration advances
- Re-running the cohesion check after architectural fixes

**Never permitted**:
- Skipping the Architect cohesion check
- Replacing it with Parzival's own review or DEV's assessment
- Carrying forward a CONFIRMED result from before fixes

## Enforcement

Parzival self-checks at every 10-message interval: "Has the Architect cohesion check been run or scheduled?"

## Violation Response

1. Block integration advancement
2. Send Phase 4 Architect instruction
3. Wait for CONFIRMED result
4. If issues found, fix and re-run until CONFIRMED
