---
plan_id: PLAN-<SLUG>-<YYYY-MM-DD>
type: build | ops | maintenance | verification | research
status: draft | approved | active | done | superseded | abandoned
plan_role: standalone | master | session   # optional; default standalone
master_plan: <path to MASTER plan | none>  # required when plan_role: session
step_id: <ST-NN | ALL | none>              # required when plan_role: session (ALL = spine-wide verification/audit child)
previous_plan: <PLAN-… filename | none>
previous_completed: yes | no | n/a
approved_by: <user> | pending
approved_date: <YYYY-MM-DD> | pending
---
# <Plan Title>

> Per-initiative living plan + checklist. One plan per initiative. Chain to the predecessor via `previous_plan`; append every status change to the Continuity Log at closeout.

## 1. Goal

[1–2 sentences: what this initiative ships and why.]

## 2. Done-Condition

[Written FIRST. Testable, external, evidence-based — the observable end state an independent check can confirm, not "code written".]

## 3. Work Items

| # | Item | Owner | Status |
|---|------|-------|--------|
| 1 | [item] | [owner] | todo |
| 2 | [item] | [owner] | doing |
| 3 | [item] | [owner] | done |

_Status ∈ todo / doing / done / blocked. Exactly one item is `doing` at a time._

## 4. Out of Scope / Non-Goals

- [What this plan explicitly does NOT cover.]

## 5. Verification

[How the Done-Condition is confirmed by evidence or independent check — not by assertion.]

## 6. Open Questions

- [Unresolved question — mark RESOLVED with the answer, who decided, and when once closed.]

## 7. Continuity Log

- [YYYY-MM-DD] — [status change / items rolled forward to the next plan / supersession or abandonment reason.]
