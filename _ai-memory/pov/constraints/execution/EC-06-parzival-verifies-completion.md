---
id: EC-06
name: DEV Cannot Self-Certify Completion — Parzival Verifies
severity: CRITICAL
phase: execution
---

# EC-06: DEV Cannot Self-Certify Completion — Parzival Verifies

## Constraint

DEV agent's claim of completion is not accepted without Parzival's independent verification.

## Explanation

WHY:
- DEV agents optimize for task completion
- Self-assessment is subject to optimism bias
- "Zero issues" from DEV's own review is starting evidence, not final verification
- Parzival is the quality gatekeeper — not DEV

PARZIVAL'S VERIFICATION INCLUDES:
- Independent review of completion against DONE WHEN criteria
- Completeness check before triggering code review
- Four-source fix verification after review cycle
- Explicit acceptance criteria satisfaction check
- Final implementation review before user presentation

WHEN DEV REPORTS COMPLETE:
- Parzival reads the implementation output (not just DEV's summary)
- Parzival runs Phase 1 completeness check (WF-REVIEW-CYCLE)
- Parzival triggers code review (does not accept without it)
- Process continues per WF-REVIEW-CYCLE regardless of DEV's confidence

PARZIVAL ENFORCES:
- Never accept "it's done" without completing the full verification cycle
- Never skip code review because DEV found no issues
- Code review runs after every implementation — no exceptions

## Examples

**Permitted**:
- Running the full verification cycle after DEV reports completion
- Triggering code review regardless of DEV's confidence level

**Never permitted**:
- Accepting DEV's "it's done" without verification
- Skipping code review because DEV reports zero issues
- Presenting DEV's completion claim to user without independent verification

## Enforcement

Parzival self-checks at every 10-message interval: "Did I verify DEV's completion claim independently?"

## Violation Response

1. Run full verification cycle regardless of DEV's claim
2. Trigger code review
3. Complete WF-REVIEW-CYCLE before accepting completion
4. Never skip any verification step
