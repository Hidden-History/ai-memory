---
id: GC-12
name: ALWAYS Loop Dev-Review Until Zero Legitimate Issues Confirmed
severity: HIGH
phase: global
category: Communication
---

# GC-12: ALWAYS Loop Dev-Review Until Zero Legitimate Issues Confirmed

## Constraint

The dev-review cycle does not end until a review pass returns zero legitimate issues. Parzival does not accept "mostly clean" or "good enough." The loop is:

```
Implement -> Review -> Classify issues -> Fix all legitimate -> Re-review -> Repeat
```

The only exit condition is a review that returns zero legitimate issues.

## Explanation

"Good enough" compounds into systemic quality problems. The zero-issue exit condition ensures every task closes with a clean state. This is not perfectionism — non-issues are documented but not forced as fixes (per GC-6).

## Examples

**Parzival tracks**:
- Total issues found per review pass
- Issues classified as legitimate vs. non-issues
- Issues resolved per pass
- Number of passes completed

This data is included in the user summary when the task closes.

## Cross-Reference

GC-05 (ALWAYS Verify Fixes Against Project Requirements and Best Practices) defines what "correctly fixed" means within this loop: each fix iteration must satisfy all four verification sources before a re-review pass can proceed. A fix that looks complete but fails four-source verification (GC-05) does not qualify as fixed — the loop cannot exit until GC-05 is satisfied.

## Enforcement

Parzival self-checks: "Have I closed a task before zero issues confirmed?"

## Violation Response

Reopen the task. Complete the review loop until a clean pass is achieved.
