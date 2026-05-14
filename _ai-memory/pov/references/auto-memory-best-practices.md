---
type: reference
load: on-demand
description: Best-practice principles for ~/.claude/projects/<project>/memory/ auto-memory directory.
---

# Auto-Memory Best Practices

Claude Code maintains a per-project auto-memory directory at `~/.claude/projects/<project-slug>/memory/` containing `MEMORY.md` (an index loaded into every prompt) and individual `feedback_*.md` / `user_*.md` / `project_*.md` / `reference_*.md` files (lazy).

## Per-prompt cost
`MEMORY.md` loads on **every user message**, not just session start. A 1,500-word index over a 30-turn session = ~67K cumulative tokens just for the index. Treat this as the most expensive surface to bloat.

## What belongs in MEMORY.md
- A list of feedback/user/project/reference memories
- One-liner descriptions per entry, ≤100 chars
- A short ## Active Project section if needed (≤80 words; no multi-thousand-word session journals)

## What does NOT belong
- Session-by-session project status (lives in oversight/SESSION_WORK_INDEX.md or session-logs/)
- Build histories, sprint metrics, verification reports (lives in oversight/reports/)
- Decisions (lives in oversight/tracking/decision-log.md)
- Per-task narratives (lives in oversight/tracking/task-tracker.md)
- Stale feedback entries (e.g., references to obsolete tooling, resolved bugs, deprecated workflows)

## Maintenance cadence
- After every session: re-read MEMORY.md; prune any entry that's been overtaken by current state.
- Audit quarterly: validate every entry's relevance; archive stale ones to a separate `archive/` subdirectory.
- Cap MEMORY.md at ~150 words index + ~50 words active-project pointer = ~200 words total.

## Anti-patterns to avoid
- Index entries naming specific session numbers, PM IDs, or BUG IDs (these date instantly)
- Essay-length feedback files when a 2-line rule would suffice
- Contradictory memories left unresolved (newer evidence wins)
- Orphan files on disk not indexed in MEMORY.md (silent dead weight)
