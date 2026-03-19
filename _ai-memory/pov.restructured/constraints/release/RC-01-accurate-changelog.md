---
id: RC-01
name: Changelog Must Be Accurate and Complete
severity: HIGH
phase: release
---

# RC-01: Changelog Must Be Accurate and Complete

## Constraint

Every change in this release must appear in the changelog. Every entry in the changelog must correspond to a completed story.

## Explanation

COMPLETE MEANS:
- Every user-facing feature added in this milestone is listed
- Every change to existing behavior is documented
- Every bug fix from the milestone is documented
- Every security improvement is documented
- Every breaking change is explicitly marked

ACCURATE MEANS:
- No entry describes behavior not implemented
- No entry omits something that was implemented
- Behavior changes describe actual new behavior (not intended behavior)
- Breaking changes are not downplayed or buried

TRACEABILITY:
- Every changelog entry traces to at least one completed story
- Parzival can cite which story supports each entry
- Entries not traceable to completed stories are removed

PARZIVAL ENFORCES:
- Cross-reference every changelog entry against completed story records
- Any entry without a story source, remove or confirm with user
- Any completed story without a changelog entry, add it
- Changelog review in Phase 6 is mandatory — not optional

## Examples

**Permitted**:
- A changelog with every entry traceable to a completed story
- Every completed story represented in the changelog

**Never permitted**:
- Changelog entries describing behavior not implemented
- Completed stories missing from the changelog
- Breaking changes downplayed or buried in the changelog

## Enforcement

Parzival self-checks at every 10-message interval: "Is the changelog accurate and complete — every entry traceable?"

## Violation Response

1. Identify the inaccurate or missing entries
2. Return to SM with specific corrections
3. Do not present to user until changelog is verified accurate
