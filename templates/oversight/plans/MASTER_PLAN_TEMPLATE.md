---
plan_id: PLAN-MASTER-<DOMAIN>
plan_role: master
type: build | ops
status: draft | active | done | superseded
previous_plan: <PLAN-… | none>
previous_completed: yes | no | n/a
approved_by: <user> | pending
approved_date: <YYYY-MM-DD> | pending
pattern_of_record: <BP-… | link>
canonical_order_source: <path to the authoritative step/stage map>
last_updated: <YYYY-MM-DD>
---
# MASTER Plan — Step-Ordered Spine (Single Source of Truth)

> The ONE step-ordered status table for a multi-step build (pipeline, migration, staged rollout). Per-step **session child-plans** (see `SESSION_STEP_PLAN_TEMPLATE.md`) do the work and **close back into a row here**. This table is the only place status lives; everything else links to it.

## Ordering rule (gate BUILD/VERIFY, not thought)

> **"No downstream step may enter BUILD or claim any verification status while any upstream step is not GREEN (i.e. RED, YELLOW, or `—`/NOT_STARTED). Read-only design / research / story-authoring for a downstream step is permitted and encouraged."**

**Current step** = the first row in canonical order whose Status is not GREEN. (Full serialization of *all* thought is the documented stage-gate rigidity anti-pattern — gate commitment, not exploration.)

## Status semantics (derived, evidence-linked — never hand-set)

- **`Built?` and `Verified? (mocked)` and `Live-verified?` are separate columns.** Each carries **evidence**, never a bare ✅: Built = merge SHA / path; Verified?(mocked) = test-suite/CI ref; **Live-verified? = a real-run evidence link + date** (anti-watermelon — encodes "green ≠ runnable").
- **Status (RAG) is DERIVED from those columns:**
  - **GREEN** = all of the step's gate exit criteria met, each with linked evidence.
  - **YELLOW** = built but not live-verified (incl. merged-dark / verification-owed), or a criterion explicitly waived (waiver noted).
  - **RED** = a **required** step not built, or broken, or verification failed. Define "required" for your domain.
  - **`—` (NOT_STARTED)** = no status yet; distinct from RED, **but still gates downstream BUILD**.

## SSoT discipline

- **This table is the ONLY status table.** Other docs link rows here; they never restate status.
- **ONE open child plan per step**, closing back into its master row **the same session**. *Exception:* a spine-wide *verification/audit* child may span all rows (its job is to populate them); **build** children are one-step-scoped.
- Lean pointer rows only (inherit the project's doc caps); detail lives in linked design/story/child files. Omit a `depends_on` column while the spine is linear; add it only if the graph branches.

---

## Master spine (one row per canonical step, in order)

| step_id | Step — one-line desc | Origin refs | Gate exit criteria (link) | Design / doc / story links | Built? (+SHA) | Verified? (mocked) | Live-verified? (evidence+date) | Status (derived) | Child plan | Open issue ids | Updated |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ST-01 | <step> | <BP/DEC/design> | <link, not inlined> | <links> | — | — | — | — | — | — | <date> |
| ST-02 | <step> | | | | — | — | — | — | — | — | <date> |

---

## Row-maintenance rules

1. **step_ids are stable and never reused**; if a step is redefined, version it (`ST-02_v2`) — don't recycle.
2. Gate exit criteria are **linked, not inlined**.
3. Every cell change stamps the row's **Updated** date.
4. Omit priority (canonical order subsumes it), per-row sign-off, and test-case-ID granularity (they live in the story/verification layer).

## Continuity Log

- [<YYYY-MM-DD>] — <created / row status changes / supersession reason>.
