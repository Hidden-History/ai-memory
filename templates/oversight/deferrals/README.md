# Deferrals Register

One view of everything postponed and its revisit-trigger, so deferred work resurfaces at the right time instead of rotting across TD-DEFERRED status flags, decision-log footnotes, or plan margin notes.

## What a deferral is

A deferral is **a decision to not do work now, plus a revisit-trigger** — nothing more. It **points to** the real detail (a TD, a DEC, a plan item) rather than copying it. If you're duplicating a TD's summary or a plan's rationale into a DEFER file, stop — that belongs on the record `Points-To` names, not here. The one field that matters is `Revisit-Trigger`: without a checkable trigger, a deferral is indistinguishable from something that was simply forgotten.

## When to file one

File a `DEFER-NNN.md` when you consciously postpone something AND can name a condition under which it should come back — a phase, a date, or a stated condition. If you can't name a trigger, you don't have a deferral yet; you have an open question. Pick a fallback date rather than leaving it untriggered (see the template's Revisit-Trigger Convention).

Don't file one for: work you're simply not going to do (that's a TD marked `Won't Fix`, not a deferral); or detail that only exists here (deferrals point to detail, they aren't a substitute for filing the TD/DEC/plan item in the first place — unless the deferred item is genuinely small enough to need no separate record, in which case set `Points-To: self`).

## How

1. Check `oversight/deferrals/` for the highest existing `DEFER-NNN`.
2. Copy `DEFERRAL_TEMPLATE.md`, fill the identity block + three body sections.
3. Save as `DEFER-NNN.md` (slug optional).

Full field reference, the Revisit-Trigger value convention, and the Status Workflow are in `DEFERRAL_TEMPLATE.md`.

## Surfacing

Open deferrals (`Status: Deferred` / `Revisiting`) are surfaced at session-start, with anything whose `Revisit-Trigger` has fired flagged for attention. Resolved/Dropped deferrals archive out of the live view the same way closed bugs and tech-debt do — the file itself is never deleted, only moved out of the active index.
