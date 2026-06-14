---
name: aim-content-drift
description: Detect content drift of an operator's scaffolded sanctum files (BOND,
  CAPABILITIES, CREED, INDEX, LORE, MEMORY, PERSONA, PULSE) against the evolving
  reference templates, and surface recommended add/remove WITH rationale — never a
  silent overwrite. Use on a session-start drift check, after the reference templates
  change, or when the operator asks whether their sanctum is current.
allowed-tools: Bash, Read
---

# aim-content-drift — Sanctum Content-Drift Detection

When an operator's already-scaffolded sanctum files drift from the evolving reference
templates, the operator must see a recommended add/remove **with rationale** — never a
silent overwrite, never a hard-default to stale content. This generalizes the
`langfuse-guard` version-drift pattern (recorded reference, offline detection,
surface→human-decides, never auto-apply) from *version* drift to *content* drift.

The deterministic mechanics (unit parsing, anchored-fingerprint comparison,
classification, ack bookkeeping) live in `scripts/content_drift.py`, invoked **by
path**. This file decides *when* to run and *how to read the recommendations*.

**v1 is detect + acknowledge, and is READ-ONLY for sanctum content** — it never
writes a sanctum file or a template. Applying a recommendation is the operator's
manual edit (an `--apply` path is deferred). The only files the skill writes are its
own per-project ack sidecar (via `--ack` / `--prune-ack`).

## When to use

- A session-start sanctum drift check, or after the reference templates change.
- The operator asks whether their sanctum is current with the standard.

## Steps

1. Resolve the sanctum path: `{project-root}/_ai-memory/sanctum/{agent_id}/`.

2. **Detect (DEFAULT — read-only):**
   `python3 scripts/content_drift.py <sanctum-path>`
   Reports batched, severity-ranked recommendations (HIGH first), each with its
   class (MISSING / SUPERSEDED / ORPHAN), rationale, and an `--ack` pointer. The
   notify is a cheap count + pointer (index-not-log); add `--show-diff` for the full
   previewable detail.

3. **Read the recommendations.** Each is *explainable* (which reference unit changed
   and why) and *previewable*. **CUSTOMIZED operator content is never recommended for
   removal** — only reference-owned units are ever surfaced. Nothing changes until the
   operator chooses; apply by hand.

4. **Acknowledge intentional divergence (writes the ack sidecar only):**
   `python3 scripts/content_drift.py <sanctum-path> --ack LORE.md::system-architecture`
   An ack suppresses that recommendation until the *reference* unit changes again.
   Drop entries whose unit no longer drifts with `--prune-ack`.

5. **Verify:** re-run detect. Acknowledged units no longer surface; a clean sanctum
   reports no recommendations.

## References

- The section/unit schema for the sanctum family: `references/unit-schema.md`
- The MATCH/MISSING/SUPERSEDED/ORPHAN/CUSTOMIZED decision rule: `references/classification-rule.md`
