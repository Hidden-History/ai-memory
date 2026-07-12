---
plan_id: PLAN-<SESSION>-<STEP-SLUG>
plan_role: session
master_plan: <path to the MASTER plan this child serves>
step_id: <ST-NN from the master spine — the one step this child advances>
session: <session id>
type: build | verification
status: draft | active | done
previous_plan: <PLAN-… | none>
previous_completed: yes | no | n/a
approved_by: <user> | pending
approved_date: <YYYY-MM-DD> | pending
---
# <Session> Step-Plan — <Step name>

> Session-scoped child under the master spine. It advances exactly **one** master step (`step_id` above) and **closes back** into that row at session end. (Exception: a spine-wide *verification/audit* child may set `step_id: ALL` and populate every row.)

## 1. Goal

[1–2 sentences: what this step ships this session and why.]

## 2. Done-Condition

[Testable, evidence-based — the observable end state an independent check can confirm. This is what turns the master row toward GREEN.]

## 3. Work Items

| # | Item | Owner | Status |
|---|------|-------|--------|
| 1 | [item] | [owner] | todo |

_Status ∈ todo / doing / done / blocked. Exactly one item is `doing` at a time._

## 4. Out of Scope / Non-Goals

- [What this plan explicitly does NOT cover.]

## 5. Verification

[How the Done-Condition is confirmed by evidence / independent check — not assertion.]

## 6. Close-back (MANDATORY — what this plan writes into the master row at close)

At session close, this plan updates master row `<step_id>`:
1. `Built? (+SHA)` from the merge/commit evidence.
2. `Verified? (mocked)` from the test/CI evidence (a ref, not a bare ✅).
3. `Live-verified?` as an evidence link + date (or leave ☐ with the reason — never a bare ✅).
4. **Derives** `Status` (RAG) from 1–3 — never hand-set.
5. Updates the row's open-issue ids + `Updated` date.
6. **If the step does not complete this session:** the row keeps its prior status, this plan's Continuity Log marks it **carried-over**, and the master's open-child pointer keeps referencing this plan (no silent orphan — orphan child plans are the #1 way the master stops being SSoT).

## 7. Open Questions

- [Unresolved question — mark RESOLVED with the answer + who decided + when.]

## 8. Continuity Log

- [<YYYY-MM-DD>] — [status change / rolled forward / supersession reason].
