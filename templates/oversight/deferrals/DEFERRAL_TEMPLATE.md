## DEFER-{number}: {title}

| Field | Value |
|-------|-------|
| **Deferral ID** | DEFER-{number} |
| **Date** | {date deferred} |
| **Status** | {status: Deferred / Revisiting / Resolved / Dropped} |
| **Revisit-Trigger** | {`Phase: <P#>` / `Date: <YYYY-MM-DD>` / `Condition: <text>` — see Revisit-Trigger Convention below} |
| **Deferred-By** | {who/what made the call — DEC-PM###-D# or PM#} |
| **Points-To** | {the detail record — TD-### / DEC-### / PLAN-### item / self (if this deferral has no separate detail record)} |

### What was deferred
{one paragraph — what work or decision was postponed}

### Why
{the reason it was postponed now rather than done — do not duplicate detail already on the Points-To record; only the deferral-specific rationale}

### Revisit criteria
{what "trigger met" looks like in practice — expand on the Revisit-Trigger field if the condition needs more than one line}

---

### Deferral ID Convention
Assign sequential IDs: DEFER-001, DEFER-002, etc. Check `{oversight_path}/deferrals/` for the highest existing ID before assigning.

**Filename**: save the record as `DEFER-NNN.md` or, optionally, `DEFER-NNN-<short-slug>.md` (a few kebab-case words). The slug is optional — both forms are valid. The `**Status**` header inside the file is authoritative for tracking, never the filename.

### Points-To — this register never duplicates detail
A deferral is a *decision to not do work now + a revisit-trigger*. It points to where the real detail lives (a TD, a DEC, a plan item) — it never copies that detail in. If there is no separate detail record (the deferred item is small enough that this file *is* the detail), set **Points-To** to `self`.

### Revisit-Trigger Convention
Use a type-tagged value so the trigger is mechanically checkable, not free text a human has to interpret every session:
- `Phase: P3` — revisit when the project reaches phase P3
- `Date: 2026-09-01` — revisit on or after this date
- `Condition: <text>` — revisit when a stated condition becomes true (no mechanical check; listed for manual review each session)

When the real trigger is fuzzy (no clean phase or date), still pick a periodic fallback date (e.g. next quarterly review) rather than leaving Revisit-Trigger open-ended — an un-checkable trigger defeats the register's purpose.

### Status Workflow
```
Deferred → Revisiting → Resolved
              ↓
           Dropped (revisited, decided not to do it after all)

Deferred → Dropped (decided not to do it without ever revisiting)
```
Open-class: Deferred, Revisiting. Closed-class: Resolved, Dropped.
