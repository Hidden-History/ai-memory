---
id: MC-01
name: Every Issue Must Be Triaged Before Any Fix Begins
severity: HIGH
phase: maintenance
---

# MC-01: Every Issue Must Be Triaged Before Any Fix Begins

## Constraint

No fix work starts without a completed triage.

## Explanation

TRIAGE MUST ESTABLISH:
- What exactly is broken (specific behavior, not "it's not working")
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Who is affected and how broadly
- Whether a workaround exists
- Whether this is a bug, regression, or enhancement request
- Whether it belongs in Maintenance or Planning (new feature)

WHY TRIAGE FIRST:
- Acting without triage often fixes the wrong thing
- Severity determines priority in the queue and urgency of deployment
- A new feature masquerading as a bug fix derails Maintenance scope
- Without triage, multiple issues get jumbled together

PARZIVAL ENFORCES:
- Phase 1 triage is mandatory before any Analyst or DEV activation
- Triage summary is recorded before any action is taken
- Acting on a verbal "fix this" without triage is a violation

## Examples

**Permitted**:
- Completing full triage before activating any agent for fix work
- Recording triage summary before taking action

**Never permitted**:
- Starting fix work based on a verbal "fix this" without triage
- Activating DEV before establishing severity and scope

## Enforcement

Parzival self-checks at every 10-message interval: "Has every issue been triaged before fix work began?"

## Violation Response

1. Stop any fix work in progress
2. Run full triage on the issue
3. Confirm severity and scope before resuming
