---
type: sanctum-index
agent: parzival
load: activation
tier: 3
---

# Index

The map of Parzival's sanctum. Update this file when organic files appear.

## Standard Files

These ship in every Parzival sanctum:

- **CREED.md** — Mission, Core Values, Standing Orders, Boundaries, Anti-Patterns. The philosophical anchor. Loaded at activation.
- **PERSONA.md** — Identity (name, icon, title, vibe), Communication Style, Principles, Traits & Quirks. How Parzival shows up. Loaded at activation.
- **BOND.md** — The owner relationship. Filled during First Breath, evolves through ongoing sessions. Loaded at activation.
- **LORE.md** — Project knowledge earned through sessions. Architecture, key decisions, patterns, things learned the hard way. Loaded at session start.
- **MEMORY.md** — Working memory. Recent sessions, pending items, insights to carry forward. Loaded at activation.
- **CAPABILITIES.md** — Built-in workflows + learned capabilities the owner has added over time + tools available. Loaded at activation.
- **PULSE.md** — Autonomous heartbeat behavior. What Parzival does when invoked headless without a specific task. Loaded on-demand. Disabled by default; opt-in via env var.

## Session Logs

Located in `sessions/`. One file per session, named `YYYY-MM-DD-<topic>.md` (where `<topic>` is a short descriptor of the session's focus). Source material for MEMORY curation — raw notes get distilled into durable insights, then pruned.

## Capabilities Library

Located in `capabilities/`. Each learned capability is a markdown prompt file. Registered in CAPABILITIES.md.

## References Library

Located in `references/`. Supporting documents for capabilities (frameworks, guides, patterns).

## My Files

_This section grows as Parzival creates organic files alongside the standard set. Update it when adding new files so future-Parzival can find them._
