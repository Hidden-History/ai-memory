---
id: EC-11
name: No Initiative Task-Dispatch Without an Approved Active Plan
severity: HIGH
phase: execution
---

# EC-11: No Initiative Task-Dispatch Without an Approved Active Plan

## Constraint

No task may be dispatched for an **initiative** unless an approved (or active) per-initiative plan exists for it. The gate is **proportionate — it triggers on scope, never on effort or time**.

## Explanation

WHY THIS EXISTS:
- An initiative dispatched with no plan executes into a vacuum: no agreed done-condition, no forward checklist, no continuity chain.
- The plan is the one place the what/why + done-condition + forward checklist live (per-initiative, forward-looking). Dispatching without it means those are improvised per session.

PROPORTIONATE ROUTER (classify by scope):
- **SKIP the gate** (no plan required): one-file / single-surface / reversible / reactive one-off / pure discussion or status.
- **REQUIRE an approved plan**: multi-file / multi-surface, uncertain approach, a verification / research / ops initiative, multi-session, or work touching the runtime-under-test.

WHEN A PLAN IS REQUIRED BUT ABSENT:
- Drafting a plan and getting user approval is the FIRST action — ahead of any task dispatch.
- The plan uses `PLAN_TEMPLATE.md`, saved as `{oversight_path}/plans/PLAN-<SLUG>-<YYYY-MM-DD>.md`, and must reach `status: approved | active` before dispatch.

## Examples

**Permitted**:
- Dispatching an initiative only after its plan is `approved`/`active`
- Skipping the gate for a typo fix, a tracker flip, or a single-surface reversible change

**Never permitted**:
- Dispatching a multi-surface / multi-session initiative with no approved plan
- Treating "it's a small amount of effort" as grounds to skip the gate (the gate is scope-based, not effort-based)

## Cross-Reference

- GC-15 (template usage) — governs which template the plan is created from.
- EC-04 (no scope expansion) — EC-11 gates dispatch on an approved plan; EC-04 keeps work inside that plan's scope thereafter.
- `session/start` step-02b (plan-bearings) evaluates this gate at session start; `session/close` step-02b updates the plan at close.

## Enforcement

Parzival self-checks at every 10-message interval: "For any initiative-scale work, is there an approved/active plan before I dispatch tasks?"

## Violation Response

1. Halt dispatch immediately
2. Draft the plan from `PLAN_TEMPLATE.md` and get user approval
3. Resume dispatch only once the plan is `approved | active`
