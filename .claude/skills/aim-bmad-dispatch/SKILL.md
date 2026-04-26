---
name: aim-bmad-dispatch
description: DEPRECATED — use /aim-agent-dispatch
---

# aim-bmad-dispatch (DEPRECATED)

This skill was removed per DEC-253-10 / PLAN-025. BMAD and generic agent dispatch are now unified under `/aim-agent-dispatch`.

**What to do**:

- Invoke `/aim-agent-dispatch` instead — it handles both BMAD and generic agent activation via unified routing.
- If your `settings.json` references `aim-bmad-dispatch`, this redirect stub provides backward compat — invocations land here and are routed to `/aim-agent-dispatch`. The installer does not modify `settings.json`. Update the path manually before this stub is removed in a future release.

This shim will be removed in a future release. See `CHANGELOG.md` → Removed for details.
