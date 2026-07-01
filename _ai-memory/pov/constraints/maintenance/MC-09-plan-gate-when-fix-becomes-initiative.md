---
id: MC-09
name: Maintenance Work That Grows Into an Initiative Requires an Approved Plan
severity: HIGH
phase: maintenance
---

# MC-09: Maintenance Work That Grows Into an Initiative Requires an Approved Plan

## Constraint

A reactive maintenance fix does not need a plan. But the moment maintenance work crosses into **initiative scope**, no further task dispatch may occur without an approved (or active) per-initiative plan. The gate is **proportionate — it triggers on scope, never on effort or time**.

## Explanation

WHY THIS EXISTS:
- Maintenance is the most scope-unstable phase: fixes look simple, then sprawl across surfaces and sessions. Once that happens the work is an initiative, and an initiative dispatched with no plan executes into a vacuum.

PROPORTIONATE ROUTER (classify by scope):
- **SKIP the gate** (no plan required): a reactive one-off — single-surface, reversible fix scoped to one issue.
- **REQUIRE an approved plan**: the fix turns multi-file / multi-surface, the approach is uncertain, it spans multiple sessions, or it touches the runtime-under-test.

WHEN A PLAN IS REQUIRED BUT ABSENT:
- Stop dispatching. Draft a plan and get user approval first — this pairs with MC-03 (new feature requests route to Planning): initiative-scale maintenance routes through a plan, not deeper into ad-hoc maintenance.
- The plan uses `PLAN_TEMPLATE.md`, saved as `{oversight_path}/plans/PLAN-<SLUG>-<YYYY-MM-DD>.md`, and must reach `status: approved | active` before dispatch.

## Examples

**Permitted**:
- Fixing a single-surface reactive bug with no plan
- Pausing an expanding fix to draft and approve a plan before continuing

**Never permitted**:
- Letting a fix grow into a multi-surface, multi-session effort with no approved plan
- Justifying skipping the gate because the remaining effort "feels small" (the gate is scope-based, not effort-based)

## Cross-Reference

- MC-03 (new features route to Planning) — the routing companion: initiative-scale work leaves ad-hoc maintenance.
- MC-02 (strict fix scope) — MC-02 keeps a fix inside its issue; MC-09 fires when the work is no longer a single fix.
- EC-11 — the execution-phase counterpart of this gate.
- `session/start` step-02b evaluates the gate at session start.

## Enforcement

Parzival self-checks at every 10-message interval: "Has any maintenance fix grown into an initiative? If so, is there an approved/active plan before I dispatch further?"

## Violation Response

1. Halt further dispatch immediately
2. Draft the plan from `PLAN_TEMPLATE.md` and get user approval
3. Resume only once the plan is `approved | active`
