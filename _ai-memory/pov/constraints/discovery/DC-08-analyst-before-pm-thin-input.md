---
id: DC-08
name: Analyst Research Must Precede PM When Input Is Thin
severity: MEDIUM
phase: discovery
---

# DC-08: Analyst Research Must Precede PM When Input Is Thin

## Constraint

When goals.md is the only input, Analyst must run before PM begins.

## Explanation

THIN INPUT INDICATORS:
- goals.md is the only document available
- Goals are high-level without feature specifics
- User has said "figure out what features we need"
- No existing codebase or documentation to draw from

IN THESE CASES:
- Analyst researches requirements (Phase 2 of WF-DISCOVERY)
- PM receives Analyst output as input alongside goals.md
- PM does NOT begin from goals.md alone

VIOLATION:
- Activating PM with only goals.md when input is thin
- Results in a PRD filled with invented requirements
- The PM agent will make reasonable assumptions that may be wrong

PARZIVAL ENFORCES:
- Assess input quality in Phase 1 of WF-DISCOVERY
- If thin, Analyst runs first, no exceptions
- If rich, PM can begin with provided material

## Examples

**Permitted**:
- Running Analyst research before PM when goals.md is the only input
- Activating PM directly when rich input is available (briefs, specs, existing codebase)

**Never permitted**:
- Activating PM with only goals.md when input is thin
- Skipping Analyst research because "PM can figure it out"

## Enforcement

Parzival self-checks at every 10-message interval: "Did I check input quality before activating PM?"

## Violation Response

1. Pause PM if already activated with thin input
2. Run Analyst research first
3. Provide Analyst output to PM alongside goals.md
4. Resume PM with enriched input
