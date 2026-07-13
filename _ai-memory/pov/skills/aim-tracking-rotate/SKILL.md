---
name: aim-tracking-rotate
description: Enforce oversight-file caps at session-close, rotate over-cap append-only-logs and registers into dated archive shards, and fix over-cap files non-interactively (including MEMORY.md lossless relocation).
allowed-tools: Bash
---

# Tracking Rotate — Oversight Cap Enforcement and Archival

**Purpose**: Bound oversight-file bloat without breaking the chronological
trail or by-id lookup (PLAN-028 D3 / BP-167 Part C). `--check` is the
session-close enforcement gate; `--apply` is the BP-167 Part C rotation that
fixes an over-cap file. Complements `aim-tracking-freshness` (which *detects*
INDEX drift); rotate *bounds* the append-only-logs and registers.

**Ownership boundary**: rotate owns append-only-log + register archival. It does
NOT touch `bugs/INDEX.md` or `tech-debt/INDEX.md` — those generated files and
their `CLOSED.md` shards are owned by `aim-tracking-freshness`.

**`--apply` support (and the TD-655 limitation)**: `--check` enforces the cap on
**every** governed file, but `--apply` auto-rotation is shipped only for the
id-H3 append-only log it was verified against:

| File | `--apply` | Why |
|------|-----------|-----|
| `tracking/decision-log.md` | ✅ supported | `### DEC-…` id-H3 entries **or** `## S{n}` session-blocks (auto-detected — see note below), newest-first; archives the oldest into a dated shard + manifest |
| `tracking/blockers-log.md` | ⛔ refused → TD-655 | "Active Blockers" table + `### BLK-` detail H3 + "Resolved Blockers" table — archiving the H3 details orphans the matching table rows |
| `tracking/risk-register.md` | ⛔ refused → TD-655 | table rows under `### Critical/High/Medium/Low` severity headers — the H3 boundary is a severity header, not a record |
| `tracking/technical-debt.md` | ⛔ refused → TD-655 | `### TD-NNN` detail H3 entries + `### <Category>` summary tables in "Debt by Category" — archiving the H3 details orphans the table rows referencing those TDs |
| `SESSION_WORK_INDEX.md` | ⛔ refused → TD-655 | four distinct tables (Active Task / Last 5 Sessions / Active Blockers / High Priority Risks); a bare `^\| ` match sheds rows from the wrong table, and the last-5 window is hand-managed |
| `session-index/INDEX.md` | ⛔ refused → TD-655 | `### [Month YYYY]` H3 sections + Current-Year and Archive tables (mixed) |

**Entry-format auto-detection (#291):** auto-rotation tries the default id-H3 boundary (`^### [A-Z]{2,4}-`) first; if a governed append-only-log contains zero id-H3 entries, it falls back to the session-block boundary (`^## S\d+ `) before reporting "no entries detected". This prevents a `## S{n}` decision-log from silently no-op'ing at closeout while its file grows past cap.

For a ⛔ file, `--apply` makes **no changes** and exits non-zero with a manual
remedy; run `python $SCRIPT --fix {file} --oversight-root {oversight_path}`
(archive-whole-verbatim + lean index rewrite) or trim by hand. Field-aware safe
auto-rotation for table-under-severity registers and multi-table live-indexes is
deferred to **TD-655**. The refusal is enforced by relative path (the fixed set:
`blockers-log.md`, `risk-register.md`, `technical-debt.md`,
`SESSION_WORK_INDEX.md`, `session-index/INDEX.md`), so a future cap-contract
seed cannot re-enable an unsafe `--apply`.

---

## Usage

```bash
SCRIPT=~/.ai-memory/_ai-memory/pov/skills/aim-tracking-rotate/scripts/tracking_rotate.py

# Enforcement gate (session-close): exit non-zero if any governed file is over cap.
python $SCRIPT --check --oversight-root /path/to/oversight

# Rotate an over-cap file's oldest entries into a dated archive shard:
python $SCRIPT --apply /path/to/oversight/tracking/decision-log.md \
               --oversight-root /path/to/oversight

# Fix a single over-cap file (conformance + cap-fix + conservation proof):
python $SCRIPT --fix /path/to/oversight/tracking/decision-log.md \
               --oversight-root /path/to/oversight

# Fix all governed oversight files (MEMORY.md excluded by default):
python $SCRIPT --fix-all --oversight-root /path/to/oversight

# Fix all governed files AND MEMORY.md:
python $SCRIPT --fix-all --include-memory-md --oversight-root /path/to/oversight

# Fix MEMORY.md only (lossless relocation to sibling topic files):
python $SCRIPT --fix-memory-md
```

Optional flags (all modes): `--period YYYY-MM` (archive period override for
deterministic runs). `--apply` additionally accepts `--entry-pattern '<regex>'`
and `--keep <N>`. `--include-memory-md` (with `--fix-all` only): also fix the
auto-memory `MEMORY.md`; skipped by default with a NOTICE. Oversight root can
also come from `$AI_MEMORY_OVERSIGHT_ROOT`.

**MEMORY.md fix details**: when you need the full step-by-step procedure for
MEMORY.md relocation or collision resolution, read:

```bash
cat "$(dirname "$SCRIPT")/../assets/memory_md_fix.md"
```

---

## How it works

- **`--check`** — for every governed file, read its cap from the file's own
  front-matter contract (`cap_lines`/`cap_kb`, D2) and fall back to a built-in
  `filename → cap` registry when the front-matter is absent (the D2 no-clobber
  carry-over case). Measure `wc -l` / `wc -c`. On any breach emit a SYSTEM
  FAILURE block (file, size, cap, remedy command) and **exit non-zero** so
  closeout cannot complete while a governed file is over cap.

- **`--apply <file>`** — move the **oldest contiguous block of whole entries**
  (never splitting an entry) into a dated shard, then update the manifest
  (`decision-log-INDEX.md`, append-only-log), write a thin live pointer, and
  verify counts. An archived entry whose id already exists in the shard with **identical** content is treated as a safe replay and skipped (so an interrupted `--apply` can be re-run idempotently); if the id matches with **different** content, `--apply` refuses — exiting non-zero with the colliding id(s), leaving the live file and shard untouched — so a body is never silently overwritten or dropped. Heartbeat / thin-register files (`rotation_trigger: none`) are
  check-only, and the table-under-severity registers / multi-table live-indexes
  are deferred to TD-655 (see the support table above) — `--apply` refuses both
  non-destructively. For `append-only-log` files, `--apply` also fences any
  unfenced `## Entry Format` example before parsing, preventing scaffold-strip
  (additive-only; no change to archived content).

- **`--fix <file>` / `--fix-all`** — non-interactive fix: (1) add D2 front-matter
  if missing (template-sourced), (2) cap-fix by class (`--apply` for
  append-only-log / rotatable registers; archive-whole-verbatim + lean index
  rewrite for table-row registers and multi-table live-indexes (`blockers-log.md`,
  `risk-register.md`, `technical-debt.md`, `SESSION_WORK_INDEX.md`,
  `session-index/INDEX.md`); template
  front-matter refresh for heartbeats), (3) prove conservation (`lost == 0`).
  Always backup-first; emits a plan + conservation report. `--fix-all` iterates
  over all governed oversight files; pass `--include-memory-md` to also fix
  MEMORY.md (default: NOTICE + skip).

- **`--fix-memory-md`** — lossless relocation for the Claude Code auto-memory
  `MEMORY.md` (class `auto-memory-index`, cap 200 lines / 25 KB
  whichever-comes-first). Triggers when MEMORY.md is over cap OR contains
  log-shape violations (any entry > 2 non-blank lines or > 200 chars); a
  compliant MEMORY.md triggers no changes. Moves over-long entries to sibling
  topic files in the same `memory/` directory, leaves one-line
  `- [Title](sibling.md) — hook` pointers. Proves conservation across the full union (`MEMORY.md ∪ memory/*.md`).
  Does **not** use cold dated shards — sibling files stay hot and on-demand.
  For the full procedure and collision resolution steps, read `assets/memory_md_fix.md`.

- **`--check` MEMORY.md** — the cap check for `auto-memory-index` is a **WARN,
  not a gate failure**. If MEMORY.md is over cap or has log-shape violations, the
  check emits `WARN:` lines to stderr but still exits 0.

Contract source of truth: `PARZIVAL-OVERSIGHT-SOT.md` §14 (caps) and BP-167
Part C (rotation lifecycle). **Caps are byte and line — either breach triggers a
violation** (the oversight classes; for `auto-memory-index` whichever-comes-first).

---

## When to use

Invoked by the session-close workflow (`session/close/steps-c/`): step-02
rotates at write (append, then `--apply` if over cap); the enforce-caps gate
step runs `--check` before save so a bloated handoff is never pushed.
