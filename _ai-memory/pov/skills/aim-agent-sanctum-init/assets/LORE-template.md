---
type: sanctum-lore
agent: {agent_id}
scope: {project_root}
created: {birth_date}
tier: 3
load: session-start
---

# Lore

*Project knowledge earned through sessions. Architecture internalized, decisions absorbed, patterns recognized. Updated as {agent_id} learns this codebase.*

---

## Bootstrapping LORE for a New Project

When this file is empty (first sessions in a new project), spend time reading these if they exist:

- `README.md` — what is this project, who uses it, how is it run
- `CHANGELOG.md` — what's been delivered, what's in flight, version history
- `oversight/tracking/decision-log.md` — major decisions and their reasoning
- `oversight/plans/` — active and historical plans
- `oversight/bugs/` — known issue patterns and recurring failure modes
- `docs/` — architecture and design documentation
- `package.json` / `pyproject.toml` / equivalent — language, framework, key dependencies
- `.github/workflows/` — CI/CD posture, what gates merges

Capture what matters into the sections below. Don't paste — distill. Prune ruthlessly: not everything you read needs to live in LORE. The goal is signal, not coverage.

---

## System Architecture

_What does this project do? How are its pieces connected? Write what you learn as you work._

## Key Design Decisions

_Major architectural or product decisions that shape ongoing work. Reference the decision-log for full context — copy the WHY, not the WHAT._

## Patterns & Conventions

_Coding conventions, workflow patterns, naming rules, file layout. The conventions the owner cares about enough to correct when missed._

## Things Learned the Hard Way

_Gotchas, debugging lessons, and "don't do this" notes earned through actual sessions. Specific failures with specific causes — not generic advice._

---

*Prune ruthlessly. LORE is for what you USE, not what you've SEEN. Stale knowledge is worse than no knowledge.*
