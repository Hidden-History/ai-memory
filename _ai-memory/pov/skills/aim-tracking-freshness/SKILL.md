---
name: aim-tracking-freshness
description: Scan oversight tracking files, regenerate bug/TD INDEX views, and report staleness divergences between file Status headers and current INDEX placement.
allowed-tools: Bash
---

# Tracking Freshness — Oversight INDEX Rebuild and Staleness Report

**Purpose**: Prevent tracking-system drift (PLAN-028 P0-4c, RC-1/RC-2). Scans
every `oversight/bugs/BUG-*.md` and `oversight/tech-debt/TECH-DEBT-*.md`,
classifies each record as open or closed from its authoritative `**Status**`
header, compares against current INDEX placement, and reports divergences.
With `--write`, regenerates both INDEX files from scratch.

---

## Usage

```bash
# Read-only staleness report (no writes):
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py \
  --check \
  --oversight-root /path/to/oversight

# Regenerate both INDEX.md files + print report:
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py \
  --write \
  --oversight-root /path/to/oversight

# Oversight root can also be set via env var:
AI_MEMORY_OVERSIGHT_ROOT=/path/to/oversight \
  python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py \
  --check
```

If `--oversight-root` and `AI_MEMORY_OVERSIGHT_ROOT` are both absent, the script
defaults to `./oversight` relative to the current working directory. Run from
the workspace root (the directory that contains `oversight/`).

---

## Modes

### `--check` (read-only)

Reads all record files; reads the current INDEX files; compares. Prints a
staleness report covering:

1. **Companions excluded** — files sharing a numeric ID with a primary record,
   listed explicitly with their exclusion reason. Silent exclusion is never
   acceptable.
2. **No-status warnings** — files with no parseable `**Status**` header.
   Records with no status header are treated as data-quality issues and
   contribute to the non-zero exit code.
3. **Divergences** — records whose open/closed classification (from the file's
   `**Status**` header) disagrees with their current INDEX section (open vs
   closed). The BUG-301 class of issue: REOPENED but in the Closed section.
   These are surfaced prominently, not buried.
4. **Orphan INDEX rows** — IDs present in the INDEX with no corresponding file.
5. **Missing from INDEX** — files present on disk but absent from both INDEX
   sections.

Exits non-zero if any divergence, orphan, missing record, or no-status record
is found. Exits 0 only when INDEX files are fully in sync with all record
files.

### `--write`

Runs the same analysis as `--check`, then regenerates both INDEX files before
printing the report. **Exit code 0** indicates a successful write (drift
found-and-corrected is a successful outcome; the INDEX is now correct). Use
`--check` as the gating command in CI — not `--write`. Structure preserved:

- Title heading + `**Last Updated**` / `**Authority for status**` / `**Method**` lines
- `## Quick Stats` table (total count, open/closed split, severity breakdown)
- `## Open` section: table grouped by severity (CRITICAL → HIGH → MEDIUM → LOW → other)
- `## Closed` section: table of closed records
- Footer with rebuild timestamp

Does NOT touch `oversight/tracking/TD-BUG-TRIAGE-PM295.md` or any other file
outside the two INDEX files.

---

## Status Header Parsing

The script handles three formats found in the live oversight tree:

| Format | Example |
|--------|---------|
| Colon outside bold | `**Status**: FIXED` |
| Colon inside bold | `**Status:** FIXED` |
| Table row | `\| **Status** \| FIXED \|` |

Both colon formats are matched by a single regex with two optional-colon slots.
The table-row format is tried as a fallback.

Closed-class tokens (bugs): `FIXED`, `RESOLVED`, `NOT A BUG`, `NOT-A-BUG`,
`DUPLICATE`, `RECLASSIFIED`, `FIX APPLIED`, `FIX-APPLIED`.

Closed-class tokens (tech-debt): `IMPLEMENTED`, `RESOLVED`, `FIXED`.

`LIKELY FIXED` remains open: `LIKELY` is not a closed-class token, so
`classify_status` finds no leading closed-class match and treats the record as
open. No explicit guard is needed beyond the leading-token rule.

---

## Companion-File Exclusion

A companion file is any file that shares its numeric ID with another file in
the same directory. Among files with the same ID, the script selects the
primary record as follows:

1. If exactly one file in the group carries a parseable `**Status**` header,
   that file is the primary regardless of alphabetical order.
2. If multiple files (or none) have a parseable `**Status**` header, the
   alphabetically-first filename is the primary.

All non-primary files in the group are companions and are excluded from INDEX
regeneration. Every companion is named explicitly in the report output.

Example: `BUG-020-duplicate-sessionstart.md` and
`BUG-020-investigation-report.md` share ID 020. If only
`BUG-020-investigation-report.md` carries a `**Status**` header, it is
promoted to primary even though it sorts later alphabetically.

Non-record files (`INDEX.md`, `BUG_TEMPLATE.md`, `ROOT_CAUSE_TEMPLATE.md`) are
excluded by the filename pattern filter (`BUG-\d+-*.md` /
`TECH-DEBT-\d+-*.md`).

---

## Notes

- The `**Status**` header in each record file is authoritative. Status is
  never inferred from filename or section placement in the INDEX.
- The TD glob is `TECH-DEBT-\d+-*.md`. Files matching the pattern `TD-*.md`
  do not exist in the live tree.
- No `.claude/skills/` shim is needed. The installer auto-generates POV skill
  shims at install time.
