---
name: aim-sot
description: Track the source-of-truth for each part of the user's own project — registry schema, templates, and engine (consult / detect-propose / verify).
allowed-tools: Bash, Read
---

# aim-sot — Source-of-Truth Subsystem

Manages a user-committed `.sot/registry.yaml` that declares where the canonical truth lives for each boundary of the user's project. Every entry is a pointer + provenance record — no copied source content ever.

## Overview

The registry lives in **the user's own repository** at `.sot/registry.yaml`, committed alongside code and diff-reviewable by the team. The skill ships the schema, templates, and engine. No project-specific data is baked into the skill.

## Modes

Three engine modes are implemented in subsequent build steps (Wave-1, Items 2–4):

- **consult** — read-only; answers "where does the truth live for X / who owns it / how is it drift-checked." Served from the derived memory cache (Part 5b), falling back to the committed registry.
- **detect-propose** — hybrid auto-discover → propose: scans for candidate components, computes actual state, compares to the registry, and emits a proposed patch on drift or new candidates. Never writes the registry directly.
- **verify** — 16-check gate (Schema · Referential · Completeness · Content). Mandatory before any apply; human approval (HITL) required. CI/pre-commit hook is opt-in only, never auto-installed.

## Registry contract

- `.sot/registry.yaml` is fully human-owned and committed; the schema and templates live in `_ai-memory/skills/aim-sot/`.
- **No-copy invariant**: every field is a pointer or provenance annotation — no copied source content.
- **No machine-auto-bumped fields**: content hashes, drift status, and machine timestamps belong in the per-install drift cache (`~/.ai-memory/drift-state/sot_drift_{project_id}.json`), never in the committed registry.

See `schema/registry.schema.json` and `templates/` for the machine-readable schema and user-facing starter templates.
