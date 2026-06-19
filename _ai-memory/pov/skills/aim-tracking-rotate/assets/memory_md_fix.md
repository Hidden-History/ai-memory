# MEMORY.md Fix Guide — Lossless Relocation

Read this file only when a `--fix-memory-md` or a log-shape WARN for `MEMORY.md`
requires hands-on resolution. The `--fix-memory-md` script action handles the
common case automatically; this guide covers edge cases and the design rationale.

---

## What problem are we fixing

Claude Code's auto-memory system loads `MEMORY.md` into context at session start.
The load window is **200 lines OR 25 KB — whichever comes first**. Content past
that boundary is silently truncated: the agent begins the session without the
oldest remembered facts.

The fix is structural, not lossy. Detail moves to sibling topic files
(`feedback_*.md`, `project_*.md`, etc.) in the same `memory/` directory; a
one-line pointer replaces each bulky entry in `MEMORY.md`. Siblings are
loaded on demand, so no information is lost — it is just re-homed.

---

## When the script handles it automatically

Run:

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --fix-memory-md
```

The script:
0. Checks if MEMORY.md is over cap OR has log-shape violations (entries > 2 non-blank
   lines / > 200 chars). If neither condition holds, prints "already within cap — no
   action needed" and exits.
1. Reads `MEMORY.md` and all sibling `memory/*.md` files (conservation baseline).
2. Backs up `MEMORY.md` to `MEMORY.md.<timestamp>.bak`.
3. Parses the file into section blocks.
4. For each block that is **over-length** (> 200 chars OR > 2 non-blank lines) and
   NOT already a one-line pointer:
   - Derives a deterministic sibling filename from the section header + entry text.
   - Appends the block to the sibling (creating it if needed).
   - Replaces the block in `MEMORY.md` with a `- [Title](sibling.md) — hook` pointer.
5. Proves conservation: `union(after) ⊇ union(before)` — zero lines lost.

---

## Manual relocation procedure

Use this when the automated fix hits a **sibling collision** (a slug conflict
where the derived sibling name already exists with incompatible content).

### Step 1 — Identify the over-long entries

```bash
wc -l ~/.claude/projects/<slug>/memory/MEMORY.md
```

Any entry body that is more than ~2 lines or ~200 characters is a candidate.

### Step 2 — Choose a sibling filename

| Section | Sibling convention |
|---|---|
| `## Feedback` | `feedback_<slug>.md` |
| `## Active Project` / `## Build` | `project_<slug>.md` |
| `## Next Steps` | `next_steps.md` |
| Other | `<section-slug>_<entry-slug>.md` |

Pick a name that is **unique to this entry's topic** and does not conflict with
an existing sibling that covers a different topic.

### Step 3 — Move the entry body

Copy the full entry text verbatim to the sibling file. Do **not** summarise or
lossy-compact it — the sibling is the live, searchable home of this detail.

### Step 4 — Leave a pointer in MEMORY.md

Replace the relocated body with exactly one line:

```
- [Short Title](sibling.md) — one-line hook describing the detail
```

The title and hook should give the agent enough context to know whether to read
the sibling file for a given session topic.

### Step 5 — Verify conservation

```bash
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py \
  --check --oversight-root <path>
```

Pass `--oversight-root <path>` or set `$AI_MEMORY_OVERSIGHT_ROOT` first; without a
configured oversight root the command errors before checking MEMORY.md.

The MEMORY.md check is a WARN gate (non-blocking). After a successful fix, it
should print no WARN lines for MEMORY.md.

---

## Collision resolution

A **sibling collision** means a target filename already exists with content that
does not match the entry being relocated. Options:

1. **Different topic, same slug** — rename the sibling (`feedback_task_notes.md`
   vs `feedback_task_tracker.md`). Re-run the script.
2. **Same topic, stale sibling content** — the entry was previously relocated and
   the sibling was manually edited. Merge the two bodies by hand, then re-run.
3. **Duplicate entry in MEMORY.md** — the entry body appears twice. Remove the
   duplicate, then re-run.

---

## Index-not-log constraint

`MEMORY.md` is an **index**, not a session log. Each entry should be at most a
one-line pointer or a two-line summary. If you find yourself writing three or
more lines of session notes directly in `MEMORY.md`, write them in a sibling
file instead and leave only a pointer. This keeps the load window useful for the
breadth of all remembered topics, not monopolised by the depth of one session.
