---
name: aim-bmad-dispatch
description: DEPRECATED — use /aim-agent-dispatch
---

# aim-bmad-dispatch (DEPRECATED)

This skill was removed per DEC-253-10 / PLAN-025. BMAD and generic agent dispatch are now unified under `/aim-agent-dispatch`.

**What to do**:

- Invoke `/aim-agent-dispatch` instead — it handles both BMAD and generic agent activation via unified routing.
- If your `settings.json` references `aim-bmad-dispatch`, the installer Option 1 migration updates it automatically. If not, edit manually.

This shim will be removed in a future release. See `CHANGELOG.md` → Removed for details.
