---
id: PC-01
name: Tasks Must Be Broken to Single-Responsibility Units
severity: HIGH
phase: planning
---

# PC-01: Tasks Must Be Broken to Single-Responsibility Units

## Constraint

Every story in the sprint must represent one reviewable, self-contained unit of work.

## Explanation

SINGLE RESPONSIBILITY MEANS:
- One DEV agent can implement the full story in one session
- One review cycle can cover the entire implementation
- The story has one clear, testable output
- The story does not span more than one architectural component boundary

INDICATORS A STORY IS TOO LARGE:
- Story requires touching more than 2-3 distinct system areas
- Story contains multiple independent features bundled together
- Story's acceptance criteria span fundamentally different concerns
- Story would require multiple separate review passes to verify
- Story title contains "and" for unrelated concerns

HOW TO FIX OVERSIZED STORIES:
- Split by component boundary (frontend story / backend story)
- Split by feature area (create / read / update / delete)
- Split by user type (admin flow / user flow)
- Each split story must still be a complete, meaningful unit

PARZIVAL ENFORCES:
- Review every story for single responsibility during Phase 5
- Any story that fails the single-responsibility test, return to SM to split
- Never accept an oversized story because "it's easier to keep together"

## Examples

**Permitted**:
- A story that implements one API endpoint with its tests
- A story that implements one frontend component with its tests

**Never permitted**:
- A story that implements both frontend and backend for a feature
- A story with acceptance criteria spanning unrelated concerns
- Keeping a story together because "it's easier"

## Enforcement

Parzival self-checks at every 10-message interval: "Are all stories single-responsibility units?"

## Violation Response

1. Identify the story that spans multiple responsibilities
2. Return to SM with specific split instruction
3. Do not add the original story to the sprint
4. Replace it with the split stories after review
