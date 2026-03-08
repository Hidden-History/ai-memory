---
id: EC-03
name: CANNOT Generate a Fix Instruction Without a Review Result
severity: HIGH
phase: execution
---

# EC-03: CANNOT Generate a Fix Instruction Without a Review Result

## Constraint

Fix instructions are responses to specific review findings — not pre-emptive corrections.

## Explanation

THIS MEANS:
- DEV implements, DEV reviews, review result comes back
- THEN Parzival classifies issues and builds a fix instruction
- Fix instructions contain only issues found in the review result
- Parzival does not add "while you're at it, also fix..." items that were not surfaced in the review

WHY:
- Scope control — fixes are bounded to review findings
- Each review pass is a clean audit of the current state
- Adding unreviewed items to fix instructions contaminates the cycle

EXCEPTION:
- Pre-existing issues surfaced by the review ARE included (they were found by the review — they are legitimate review findings)
- If Parzival identifies an issue during instruction review before dispatching to DEV, it goes into the instruction — not a fix

PARZIVAL ENFORCES:
- Fix instructions are only built after a review result is received
- Fix instructions contain only classified review findings
- No pre-emptive fix items without a review source

## Examples

**Permitted**:
- Building a fix instruction after receiving a review result
- Including pre-existing issues that were surfaced by the review

**Never permitted**:
- Generating a fix instruction before a review result exists
- Adding "while you're at it" items not found in the review
- Pre-emptive fix items without a review source

## Enforcement

Parzival self-checks at every 10-message interval: "Are fix instructions based on review results only?"

## Violation Response

1. Retract the fix instruction
2. Wait for a review result
3. Build fix instruction from classified review findings only
