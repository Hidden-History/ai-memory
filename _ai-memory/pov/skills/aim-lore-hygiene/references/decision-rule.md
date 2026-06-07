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
