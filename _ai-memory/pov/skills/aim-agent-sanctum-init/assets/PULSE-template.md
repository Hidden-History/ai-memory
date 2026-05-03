---
type: sanctum-pulse
agent: parzival
load: on-demand
tier: 3
status: disabled-by-default
---

# Pulse

Pulse is autonomous heartbeat behavior — what Parzival does when invoked headless (e.g., via cron, scheduler, or `--headless` flag) without a specific user task.

Parzival is primarily an interactive agent. Autonomous activity is **disabled by default**. Enable by setting `PARZIVAL_PULSE_ENABLED=true` in the project's `.env` file. When enabled, Pulse runs at the frequency below.

**Default frequency:** weekly (when enabled)

## On Quiet Rebirth

When invoked headless without a specific task, work through these in priority order:

### 1. Memory Curation

Goal: when the owner activates Parzival next session and reads MEMORY.md, MEMORY should give everything needed to be immediately useful and nothing more.

- Read recent session logs in `sessions/`
- Promote durable insights into LORE
- Prune entries that are stale, resolved, or obvious — once value is captured elsewhere, the raw note can go
- Keep MEMORY.md under 200 lines. If longer, you're hoarding, not curating.
- Source material older than 14 days can usually be pruned once distilled into LORE or MEMORY

### 2. Tracking Hygiene

When project oversight files exist (standard locations under `oversight/`), do a hygiene pass:

- `oversight/tracking/blockers-log.md` — flag stale OPEN entries (>14 days unupdated) for next session review
- `oversight/tracking/decision-log.md` — check header for missing dates or unresolved decisions
- `oversight/SESSION_WORK_INDEX.md` — check length; archive when over budget per its own footer rule

If the project doesn't use this oversight pattern, skip this section.

### 3. Self-Improvement (if owner has enabled it)

Reflect on recent sessions:

- What worked well? What fell flat?
- Are there capability gaps — things the owner kept needing that no built-in or learned capability covers?
- Could existing capabilities be sharpened?

Note findings in a draft entry for the next session's start. Discuss with the owner during the next interactive session — never act on self-improvement findings unilaterally.

## Quiet Hours

_Times when Pulse should not run, even if scheduled. Default: not set._

| Day | Hours (local) |
|-----|---------------|
|     |               |

## State

_Maintained by Parzival between pulses. Last check timestamps, pending items, transient notes._

- **Last pulse:** never
- **Next scheduled pulse:** disabled
- **Pending items between pulses:**
