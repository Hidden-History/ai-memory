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

Run the `aim-lore-hygiene` curation procedure: promote durable insights to LORE, prune stale/resolved MEMORY entries, hold MEMORY to its cap. (Procedure and thresholds live in the skill — do not restate them here.)

### 2. Tracking Hygiene

When project oversight files exist (standard locations under `oversight/`), do a hygiene pass:

- the project's **issue/blocker log** — flag stale OPEN entries (>14 days unupdated) for next-session review
- the project's **decision log** — check the header for missing dates or unresolved decisions
- the project's **session/work index** — check length; archive when over budget per its own rule

*(In an AI-Memory-style layout these are `oversight/tracking/blockers-log.md`, `oversight/tracking/decision-log.md`, and `oversight/SESSION_WORK_INDEX.md` — adapt to the project's actual paths.)*

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
