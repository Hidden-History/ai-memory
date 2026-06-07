# Prune vs. archive — the decision rule (BP-159 §6)

The load-bearing distinction in lore hygiene. Two failure modes bound it:

- **Over-archiving → "memory blindness":** the agent doesn't know a critical fact
  exists in cold storage, so it never retrieves it.
- **Over-retention → context bloat:** degraded adherence and token cost.

## The rule

| Condition | Action | Marker the script reads |
|-----------|--------|-------------------------|
| Superseded, contradicted, or proven wrong | **Delete** | `[superseded]`, `[contradicted]`, `[wrong]`, `[obsolete]`, or `~~strikethrough~~` |
| Low utility: declared no-longer-useful, ephemeral | **Delete** | `[prune]` |
| Time-bound and expired | **Delete** (it was a TTL entry) | `[expired:YYYY-MM-DD]` past today |
| Stale-but-historically-meaningful; detail behind an index line | **Archive** to cold tier, keep a one-line pointer | `[stale]`, `[archive]` |
| Exact duplicate of an earlier entry | **Dedup** (keep the first) | (detected automatically) |
| High retrieval frequency + still accurate | **Keep** | (no marker) |

## Markers are matched only in the LEADING position

A marker classifies an entry **only** when it sits in the single dedicated **leading**
tag position, so that an entry which merely *talks about* a marker — or merely *ends*
in one — is never self-destructively pruned:

- **Leading tag**: immediately after the bullet/number prefix, or in the first cell
  of a table row — `- [superseded] Old belief…`, `| [superseded] row | … |`.

A marker appearing **anywhere else** — mid-prose ("Tag an entry `[superseded]` when it
is no longer accurate") or at the **trailing** end of a line ("A fact retired at end of
life `[obsolete]`") — is **not** in the leading zone and is therefore **kept**.
(Strikethrough `~~…~~` is anchored by definition only when a *single* span covers the
entire entry content; an entry with live un-struck text between spans is kept.
`[expired:YYYY-MM-DD]` follows the same leading-only rule.)

> **Leading-only (cycle-2).** Earlier drafts also honored a *trailing* tag. That was
> dropped: it pruned prose that happened to end in a marker token, silently missed a
> trailing tag on a multi-line entry's first line, and missed trailing punctuation.
> A single leading convention is unambiguous and data-safe. Place every classification
> tag at the start of the entry.

**Table structural rows are never deduped.** Header and separator (`|---|`) rows are
preserved, so a second table sharing a column schema keeps its own header and
separator instead of having them collapsed away as "duplicates".

**Archiving a tagged table row.** A `[stale]`/`[archive]` (or `[prune]`) tag in a
table content row drops that row **in place** so the table stays well-formed; for
archive, the full row content still moves to the cold tier. No inline pointer bullet
is injected into a table body (that would corrupt the table and leak the row's pipes).

Two invariants from BP-159 §6:

- **Never silently delete anything with recall value** — archive it. Archive moves
  the full entry to `references/lore-archive/<FILE>.archive.md` (the cold tier) and
  leaves a dated one-line pointer in the hot file.
- **Never keep anything contradicted** — deleting wrong memory is more valuable than
  keeping it, because confidently-wrong high-relevance memory is the worst failure
  mode.

## Why marker-driven, not heuristic

BP-159 §5 prescribes utility = f(recency, retrieval frequency, operator priority)
with LRU + temporal decay. Those signals require retrieval telemetry this skill
cannot see. Rather than **guess** that an entry is low-utility (which risks
memory-blindness), the script acts only on **explicit markers**: the operator, a
Pulse pass, or an upstream LLM tags entries, and this deterministic core executes
the tagged decisions safely. The agent-invokable "forget" path (BP-165 DELTA-3) is
the manual trigger that adds a `[superseded]`/`[stale]` marker when the operator
says "that's not right anymore."

## The cold tier

BP-159 §3 allows the cold tier to be **a vector DB OR sharded files**. This skill
uses local archive files as the always-available, testable cold tier. The optional
`--qdrant --group-id <project>` flag additionally pushes archived blocks to the
Qdrant `discussions` collection via the runtime `memory.storage.store_agent_memory`
import path (the same path bootstrap/sanctum-init use), degrading gracefully to the
local-file-only behavior when the runtime or Qdrant is unavailable.
