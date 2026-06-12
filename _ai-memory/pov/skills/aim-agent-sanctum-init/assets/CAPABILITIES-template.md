---
type: sanctum-capabilities
agent: parzival
load: on-demand
tier: 3
---

# Capabilities

*Procedural registry — the catalog of what Parzival can do and how. Voice and identity live in PERSONA; this file is the "what," not the "how he sounds." Loaded on-demand.*

The complete catalog of what Parzival can do. Built-in workflows ship with every install. Learned capabilities accumulate over time as the owner teaches new ones.

## Built-in Workflows

These are the workflows Parzival can route to from the activation menu; every install ships all of them. The canonical catalog — codes, names, descriptions, and order — is the `<menu>` block in `_ai-memory/pov/agents/parzival.md`. Read it from there. Do **not** keep a second copy here: a hand-maintained table silently drifts from the live menu (it already has).

## Learned Capabilities

_Capabilities the owner has added over time. Each one's prompt lives in `capabilities/`. Register new capabilities here when added._

| Code | Name | Description | Source | Added |
|------|------|-------------|--------|-------|

## How to Add a Capability

Tell Parzival "I want you to be able to do X" and he'll create it together with you. The new capability prompt gets saved to `capabilities/`, registered in this table, and is available in the next session. The owner's authority over capabilities is unilateral — Parzival ships extensible.

For the full creation framework, load `references/capability-authoring.md` if present.

## Tools

Parzival prefers crafting his own tools over depending on external ones. A script written, saved, and tested is more reliable than an unfamiliar external API. The file system is the primary working surface — files are durable, observable, and version-controllable.

Standard tools always available:
- File system read/write within authorized dominion (per CREED Boundaries)
- Subagent dispatch via the orchestration pipeline (per CREED Standing Orders + GC-21)
- Web fetch and web search (for best-practices research per [BR])
- Shell execution within sandbox limits

### User-Provided Tools

_MCP servers, APIs, or services the owner has made available. Document them here as they're added._
