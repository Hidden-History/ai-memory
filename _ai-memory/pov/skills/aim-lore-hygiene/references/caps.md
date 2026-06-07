# Per-file caps, the compaction trigger, and the LORE section schema

Source of truth: BP-159 (per-operator lore-file hygiene) and BP-165 (this skill's
architecture). This file is loaded on demand — keep SKILL.md lean.

## Caps

| File | Cap | Rationale |
|------|-----|-----------|
| `LORE.md` | 200 lines | BP-159 §2 — always-injected; models follow ~150–200 distinct instructions; the harness consumes ~50 slots. |
| `MEMORY.md` | 200 lines | BP-159 §2 + Claude Code's undocumented 200-line hard limit (claude-code #25006): content past line 200 is silently truncated and never loaded. |
| `CLAUDE.md` | 300 lines | BP-165 DELTA-2 — companion cap for project-root rules. Lives at the project root, not the sanctum, so it is **not** scanned by default; pass it explicitly with `--cap 300`. |

The cap counts the **whole file**, frontmatter included — the harness loads the
first N lines regardless of what they contain.

## Compaction trigger — ~80% of cap

Compaction is triggered at **80% of the cap** (160/200 lines), set by the
`COMPACT_AT = 0.80` constant. BP-165 DELTA-1: 2026 sources put Claude Code's
auto-compaction at 83.5% with proactive `/compact` recommended in the 70–90% band
and context rot observable from ~70%; 0.80 sits safely inside that band.

A file is **actionable** when it is at/over the trigger **or** contains any
prune/archive marker or duplicate — so a small file with a `[contradicted]` entry
is still cleaned (correctness), while a clean under-trigger file is left untouched
(idempotent no-op).

## Anchored summarization — the section schema

Compaction is *anchored* on the shipped `LORE-template.md` section schema, so the
document's shape is preserved while entries within each section are pruned,
archived, or deduped:

- **System Architecture**
- **Key Design Decisions**
- **Patterns & Conventions**
- **Things Learned the Hard Way**

`MEMORY.md` is anchored on its own schema (Recent Sessions / Pending Items /
Insights to Carry). The script never moves an entry across sections and never
rewrites prose — genuinely semantic summarization (saying the same thing in fewer
words) is surfaced as a residual-over-cap flag for a human/LLM pass, never
auto-truncated (the "memory blindness" guard, BP-159 §6).

## Treat the hot file as a curated index, not a log

The hot file should hold identity, durable preferences, and **one-line index
entries** that point to detail living in the cold tier (`references/lore-archive/`
or Qdrant). This is the same index-not-log discipline `MEMORY.md` already follows.
