# Proposal — Master/Session Plan System with Stage-Gate Ordering + Installer Template Sync

**Origin:** downstream use (DocIntel). Validated by **BP-062** (research verdict: SUPPORTED-WITH-ADJUSTMENTS — master step-spine + session child-plans + stage-gate ordering composes stage-gate/phase-gate + RTM + definition-of-done + docs-as-code SSoT). Reference implementation shipped as `MASTER_PLAN_TEMPLATE.md` + `SESSION_STEP_PLAN_TEMPLATE.md` in this PR.

**Problem this fixes (3 linked defects):**
1. **Template drift, no installer migration** — the shipped `PLAN_TEMPLATE.md` was leaned to front-matter form, but existing projects keep their old copy forever (the installer never syncs it). Plans get authored from the wrong shape.
2. **No master/session hierarchy or per-step traceability** — the lean template supports only linear `previous_plan` chaining; there is no master step-spine, no parent link, and no per-step Built?/Live-verified?/Status traceability. Nothing structurally prevents building a downstream step before an upstream one is verified.
3. **POV plan-workflows are single-plan only** — `session/start` plan-bearings and `session/close` update-plan handle "the active plan" with no master-first reading and no stage-gate ordering.

---

## Part A — Templates (in this PR, installer-propagated)

- **NEW** `templates/oversight/plans/MASTER_PLAN_TEMPLATE.md` — step-ordered spine, 11-field RTM row schema, R1 gate rule, derived evidence-linked RAG status, SSoT discipline.
- **NEW** `templates/oversight/plans/SESSION_STEP_PLAN_TEMPLATE.md` — scoped child plan with `plan_role`/`master_plan`/`step_id` front-matter and a mandatory close-back section.
- **EDIT** `templates/oversight/plans/PLAN_TEMPLATE.md` front-matter — add three OPTIONAL fields so a plan can declare its role/parent:

```diff
 ---
 plan_id: PLAN-<SLUG>-<YYYY-MM-DD>
 type: build | ops | maintenance | verification | research
 status: draft | approved | active | done | superseded | abandoned
+plan_role: standalone | master | session   # optional; default standalone
+master_plan: <path to MASTER plan | none>  # required when plan_role: session
+step_id: <ST-NN | none>                     # required when plan_role: session
 previous_plan: <PLAN-… filename | none>
 previous_completed: yes | no | n/a
 approved_by: <user> | pending
 approved_date: <YYYY-MM-DD> | pending
 ---
```

## Part B — POV workflow changes (spec; maintainer applies to the code)

### B1 — `_ai-memory/pov/workflows/session/start/steps-c/step-02b-plan-bearings.md`
Add a **master-first + stage-gate** reading ahead of the existing "locate the active plan" logic:
1. If a `plan_role: master` plan exists under `{oversight_path}/plans/`, read it FIRST. Compute the **current step** = the first spine row whose Status is not GREEN.
2. The recommended resume point is that step's open **session child** (its `master_plan`+`step_id` link), not just "the most recent active plan."
3. **Stage-gate guard (F-09 — refusal mechanism):** if the user/next-action targets a step *downstream* of the current step while an upstream row is RED/YELLOW/`—`, **surface a WARN and require explicit override** ("upstream ST-NN is not GREEN; downstream BUILD is gated — proceed read-only, or override with reason"). Read-only design/research look-ahead is allowed; BUILD/verify-claims are gated. (Warn+override, not a hard block — matches the no-hard-gates-in-development posture.)
4. **Front-matter validation (F-10):** if a `plan_role: session` plan is missing `master_plan` or `step_id`, flag it as a plan-integrity anomaly (an orphan child — the #1 SSoT-killer).

### B2 — `_ai-memory/pov/workflows/session/close/steps-c/step-02b-update-plan.md`
Add a **master-row roll-up** to the close sequence:
1. When a `plan_role: session` child closes, **update its master row** (Built?/Verified?/Live-verified?/derived Status) using **git + live evidence as truth** — a step cannot be marked Live-verified without an evidence link + date (anti-watermelon).
2. Enforce the close-back: a session child MUST roll up into its master row the same session (orphan children flagged).

## Part C — Installer template sync (spec; fixes defect 1 — F-08 tightened)

In `update.sh` / `scripts/` template-deploy step:
1. Stamp each shipped template with a `template_version` (or hash) and record the deployed hash per project.
2. On update, for each template: **if the project copy is unmodified vs the last-deployed hash → auto-sync** to the new shipped version; **if the project copy was locally modified → do NOT clobber; emit a loud WARN** ("template drifted + upstream changed; review + merge") and leave it.
3. Add `--check` (CI-gateable) that reports every template whose project copy differs from the shipped version and whether it's an unmodified-stale (safe to sync) or locally-modified (needs merge).
4. This must handle **new** template files (e.g. `MASTER_PLAN_TEMPLATE.md`) — deploy them into existing projects, not only pre-existing ones.

---

## Reference implementation (worked example, from the DocIntel project)

- Master spine: a 14-row pipeline `MASTER-PIPELINE-PLAN.md` (`plan_role: master`) with the 11-field schema, R1 gate rule, derived RAG status, all rows `pending audit` until a verification child populates them.
- Session child: `S255-pipeline-state-audit-session.md` (`plan_role: session`, `step_id: ALL`, spine-wide verification exception) with a mandatory close-back that populates every master row from audit evidence.

These are available on request as concrete examples of the templates in use.

## Related issues
Files under the S255 AI-Memory friction batch (umbrella tracks them). This proposal closes the plan-system issue; the dispatch/tracking/best-practices issues in the batch are independent.
