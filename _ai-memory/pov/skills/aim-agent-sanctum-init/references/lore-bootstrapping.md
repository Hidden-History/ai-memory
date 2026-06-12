# Bootstrapping LORE for a New Project

One-time guidance for the first sessions in a new project, demoted here from LORE so it does not load every session. Once LORE is populated, this is no longer needed.

When LORE is empty (first sessions in a new project), spend time reading these if they exist:

- `README.md` — what is this project, who uses it, how is it run
- `CHANGELOG.md` — what's been delivered, what's in flight, version history
- `oversight/tracking/decision-log.md` — major decisions and their reasoning
- `oversight/plans/` — active and historical plans
- `oversight/bugs/` — known issue patterns and recurring failure modes
- `docs/` — architecture and design documentation
- `package.json` / `pyproject.toml` / equivalent — language, framework, key dependencies
- `.github/workflows/` — CI/CD posture, what gates merges

Capture what matters into the LORE sections. Don't paste — distill. Prune ruthlessly: not everything you read needs to live in LORE. The goal is signal, not coverage.
