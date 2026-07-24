---
name: 'step-03-present-and-wait'
description: 'Present the compiled session status to the user and wait for direction'
---

# Step 3: Present and Wait for Direction

**Final Step — Session Start Complete**

## STEP GOAL:

Present the compiled status report to the user in a clear format and wait for their direction on what to work on. This is a terminal step.

**Scope:**
- Available context: The compiled status report from Step 2, WORKFLOW-MAP routing logic
- Focus: Presentation and user direction only — do not start work
- Limits: Present status and recommendation, then wait — do not start work without user approval
- Dependencies: Compiled status report from Step 2

- Present the compiled status report and recommendation, then wait for user direction
**Behavioral Constraints:**
- FORBIDDEN to start any work before user gives explicit direction
- Approach: Clear presentation with recommendation and reasoning — then wait
- This is a TERMINAL step — no nextStepFile, workflow ends after user is asked for direction

## Sequence

### 1. Present Status Report

Use this exact format:

```
## Session Status

**Last Session**: [date] - [brief summary]

**Current Task**: [ID] [Title]
**Status**: [status]

**Active Blockers**: [count] ([brief descriptions if any])
**Risks**: [count high/medium]

**Ready to continue from**: [where we left off]
```

---

### 2. Present Anomalies (If Any)

If Step 2 identified any anomalies between tracking files, present them after the status:

```
### Notes
- [Anomaly description -- factual, not a recommendation]
```

---

### 3. Provide Recommendation

Parzival always guides the user with a clear recommendation and reasoning. Based on the project state, recommend the logical next action:

**If no project-status.md exists (first session)**:
- Explain that the project needs initialization before Parzival can help effectively
- Present two clear options:
  - **Start a New Project** — for brand new projects with no existing code/docs. Walks through setting up project baseline, goals, and oversight structure
  - **Onboard an Existing Project** — for projects that already have code, docs, or planning artifacts. Parzival will audit what exists and establish oversight around it
- Recommend one based on observable evidence (is there source code? docs? package.json?) and explain WHY

**If project-status.md exists but tracking files are empty**:
- Recommend completing the init workflow to establish the baseline
- Explain what the init workflow will produce and why it matters

**If project-status.md exists with an active phase**:
- Recommend the next logical action for the current phase (per WORKFLOW-MAP routing)
- Explain what that action involves in plain terms
- If a task was in progress, recommend continuing from where it left off

**If blockers exist**:
- Recommend addressing the highest-severity blocker first
- Explain why resolving it unblocks progress

**If Step 2 surfaced a Pending Updates count greater than 0**:
- Recommend reconciling those pending updates — state it ahead of any plan, story, or task-continuation recommendation, even when a task is in progress
- If a blocker also exists, address the blocker first; pending updates are still stated ahead of plan/task work
- Explain that these are the operator's scaffolded files that have drifted from their shipped templates, and that Section 5 reconciles them on request
- State the plan/task recommendation after the pending-updates recommendation (and after any blocker recommendation per above) — never in place of it

Format:
```
### Recommendation

[What Parzival recommends] — [plain-language explanation of WHY this is the right next step]

[If multiple options exist, present them as numbered choices with brief descriptions]
```

### Scope Expansion Handling

See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md) `## SCOPE EXPANSION PROTOCOL`. This protocol applies throughout the session, not just at session start — Parzival must surface scope decisions whenever the user introduces new work.

---

### 4. Wait for User Direction

End with:

```
---

What would you like to do?
```

After presenting:
- Do NOT assume which option the user will choose
- Do NOT start executing any tasks until user confirms
- WAIT for the user to give explicit direction

---

### 5. On-Request: Reconcile Pending Updates (only when the operator asks)

This is a REACTIVE branch, NOT a gate and NOT a mandatory step. Step 2's "Pending Updates" rollup already told the operator the count; this workflow still terminates normally at the wait above. Enter this branch ONLY when the operator explicitly asks to see or act on pending updates (e.g. "show pending", "reconcile the updates", "what are the pending updates?"). Never auto-expand it, and never inline it into the status report.

**5.1 — List (count + pointer, never inline diffs).** Run:

```
python3 "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/pov/skills/aim-content-drift/scripts/reconcile_helper.py" pending --project-root <project-root>
```

Present the returned `entries` severity-ranked as a numbered list — for each: `#n` · severity · `path` · one-line `rationale` · `classification`. State the count. Do NOT inline file contents or diffs (BP-159 index-not-log); the `path` is the pointer the operator opens if they want the detail. If the list is empty, say so and stop.

**5.2 — Operator selects scope.** Ask which to reconcile: **all**, a specific **#n**, or **defer** (stop here — the workflow stays terminal, nothing is recorded). WAIT for the choice.

**5.3 — Reconcile chosen entries ONE AT A TIME.** For each selected entry, in severity-rank order:
- Restate the single entry (path · severity · rationale).
- Ask the operator for a per-entry disposition: **approve** / **defer** / **dismiss** / **resolved** (the operator has already hand-conformed the file to the new template outside this workflow). WAIT.
- Invoke it (map approve→`applied`, defer→`deferred`, dismiss→`dismissed`, resolved→`resolved`):

  ```
  python3 "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/pov/skills/aim-content-drift/scripts/reconcile_helper.py" reconcile --project-root <project-root> --id <entry-id> --disposition <applied|deferred|dismissed|resolved>
  ```

- For **approve/applied** the helper runs the reconciliation engine (backup-before-write, crash-atomic, staleness-checked) and reports `decision` + `action_taken` (migrated | preserved | no-op | refreshed) + `backup_path`. Relay that outcome factually. On a non-zero status, the helper's JSON error payload carries an `error_type`. If `error_type` is `StaleManifestError`: ask whether the operator already hand-conformed the file outside this workflow — if so, re-invoke with **resolved**; otherwise re-run the installer to regenerate the manifest. For any OTHER `error_type` (e.g. `MigrationChainError`), surface the `error_type` and the engine's message factually — do NOT tell the operator to re-run the installer, and do NOT retry or hand-edit either.
- For **resolved**, the helper stamps the disposition against the file's current on-disk hash without invoking the reconciliation engine — this is why it never raises `StaleManifestError`, even though the deployed file has already diverged from the manifest snapshot. Re-nag suppression still keys off the entry's `new_template_hash`, identically to `applied`/`dismissed`; the on-disk hash is recorded separately, for audit only. Reports `action_taken: "stamped-resolved-out-of-band"`.
- **Conformance guard (governs both dispositions above):** relaying `decision` + `action_taken` reports what the reconcile/stamp step did — it is NOT a measurement of whether the file's structure matches the current template. Template structure is a separate check (the template-parity oracle) that this branch does not run. FORBIDDEN to characterize ANY `action_taken` outcome, whatever its value, as proof that the file is structurally conformant, or to imply conformance has been checked unless the oracle was actually run.
- The helper records the disposition to `<project-root>/.audit/state/reconcile-dispositions.json`, keyed to the entry id + its current `new_template_hash`. A disposed entry will NOT re-surface at Step 2 unless that template hash moves in a later install.
- Move to the next selected entry only after the current one is recorded.

**5.4 — Close.** After the selected entries are processed, return to the terminal wait ("What would you like to do?"). Do not start unrelated work off the back of this branch.

## TERMINATION STEP PROTOCOLS:

- This is a FINAL step — workflow completion required
- Present status report and recommendation fully before waiting
- Suggest next workflows or phase transitions based on project state
- No nextStepFile — user direction drives all subsequent work
