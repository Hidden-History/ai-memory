---
name: aim-lore-hygiene
description: Enforce hygiene on per-operator sanctum LORE/MEMORY files — line-cap
  enforcement, anchored-summarization compaction at ~80% of cap, and the
  prune-vs-archive decision. Use when a sanctum file approaches its size cap, on a
  scheduled hygiene pass, or when the operator asks to compact or prune lore.
allowed-tools: Bash, Read
---

# aim-lore-hygiene — Per-Operator Lore File Hygiene

Compacts always-injected sanctum files (LORE.md, MEMORY.md) under the BP-159
~200-line cap so rules don't "get lost in the noise" and adherence stays high.
**FILE-content compaction only** — NOT Qdrant-point purging by age (that is
`aim-purge`, a different domain — PLAN-028 P0-3).

The deterministic mechanics (line-counting, marker classification, structural
compaction, archiving) live in `scripts/lore_hygiene.py`, invoked **by path**.
This file decides *when* to run, *which* files, and *how to read the plan*.

## When to use

- A sanctum file crosses ~80% of its cap (160/200 lines — the compaction trigger).
- A scheduled hygiene pass (session-stop hook or cron).
- The operator asks to prune or compact lore, or flags a stale/wrong entry.

## Steps

1. Resolve the sanctum path: `{project-root}/_ai-memory/sanctum/{agent_id}/`.
   Confirm it contains `LORE.md` and/or `MEMORY.md`.

2. **Dry-run audit (DEFAULT — never mutates):**
   `python3 scripts/lore_hygiene.py <sanctum-path>`
   Reports per file: line count, % of cap, and the proposed prune / archive /
   dedup actions with a projected post-compaction line count.

3. **Review the plan** — the verifiable intermediate output. Confirm prunes are
   genuinely superseded/contradicted, archives are stale-but-meaningful, and the
   projected count lands at or under cap. If the plan reports a residual over-cap,
   a manual/LLM semantic-summarization pass is needed (the script will not
   auto-truncate recall-value content).

4. **Apply only after review:**
   `python3 scripts/lore_hygiene.py <sanctum-path> --apply`
   Each mutated file gets a timestamped `.bak` sidecar first; archived entries
   move to `references/lore-archive/<FILE>.archive.md` with a one-line pointer
   left in the hot file. Add `--qdrant --group-id <project>` to also push archived
   entries to the Qdrant cold tier (best-effort, opt-in).

5. **Verify:** re-run the dry-run audit. Every file should be ≤ cap (or carry an
   explicit residual flag), and each archived entry should have a one-line pointer
   in the hot file. A second `--apply` on an already-clean file is a no-op.

## How entries are classified

The script is marker-driven (it never guesses an entry is low-utility):

- **Prune (delete):** `[superseded]`, `[contradicted]`, `[wrong]`, `[obsolete]`,
  `[prune]`, a `[expired:YYYY-MM-DD]` TTL that has passed, or strikethrough
  (`~~...~~`).
- **Archive (cold tier + pointer):** `[stale]`, `[archive]`.
- **Dedup:** exact-duplicate entries are collapsed, keeping the first.
- **Keep:** everything else.

Tag entries with these markers (during a Pulse, or when the operator says "that's
not right anymore") so the next hygiene pass acts on them safely.

## References

- Per-file caps, the ~80% trigger, and the LORE section schema: `references/caps.md`
- The prune-vs-archive decision rule (BP-159 §6): `references/decision-rule.md`
