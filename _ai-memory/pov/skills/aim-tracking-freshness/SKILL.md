---
name: aim-tracking-freshness
description: Scan oversight tracking files, regenerate bug/TD INDEX views, report STATUS divergences, verify phantom-open bug candidates against git history, and check decision-log body coverage.
allowed-tools: Bash
---

# Tracking Freshness — Oversight INDEX Rebuild and Staleness Report

**Purpose**: Prevent tracking-system drift (PLAN-028 P0-4c, RC-1/RC-2). Scans
every `oversight/bugs/BUG-*.md` and `oversight/tech-debt/TECH-DEBT-*.md`,
classifies each record as open or closed from its authoritative `**Status**`
header, compares against current INDEX placement, and reports divergences.
With `--write`, regenerates both INDEX files (and their `CLOSED.md` shards).

## Usage

```bash
SCRIPT=~/.ai-memory/_ai-memory/pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py

# Read-only staleness report (no writes; the CI gate):
python "$SCRIPT" --check --oversight-root /path/to/oversight

# Regenerate both INDEX.md files (+ CLOSED.md shards) and print the report:
python "$SCRIPT" --write --oversight-root /path/to/oversight

# Add phantom-open code-state verification (cross-checks open records vs git):
python "$SCRIPT" --check --oversight-root /path/to/oversight \
  --verify-code-state --source-repo /path/to/source-git-repo
```

Oversight root also reads `AI_MEMORY_OVERSIGHT_ROOT`; with neither it nor
`--oversight-root` set, it defaults to `./oversight` under the CWD (run from the
workspace root containing `oversight/`).

## Modes

**`--check`** (read-only) — reads every record file and the current INDEX files
and compares. Reports companions excluded, no-status warnings, divergences (file
Status vs INDEX section — the BUG-301 class), orphan INDEX rows, and missing
records. Id-parsing spans `INDEX.md` **and** `CLOSED.md`, so sharded closed
records are not falsely flagged as missing. Exits non-zero on any divergence,
orphan, missing, or no-status record; exits 0 only when fully in sync.

**`--write`** — same analysis, then regenerates both INDEX files (**exit 0** is a
successful write; gate CI on `--check`). Each INDEX opens with the D2 register
front-matter (`class`, `read_path`, `owns`, `cap_lines`/`cap_kb`,
`rotation_trigger: none`, `archive_target: ./CLOSED.md`); `## Open` cells
summarize the status (≤ 8 words / 64 chars) while classification uses the full
raw status; `## Closed` lists the most recent 10 plus a
`[Full closed history → ./CLOSED.md] (N)` pointer, with the full history in
`bugs/CLOSED.md` / `tech-debt/CLOSED.md` (idempotent overwrite). Written size is
asserted against the cap (bugs ≤ 100 lines / 12 KB, TD ≤ 150 / 18); over-cap
emits a loud stderr `WARNING` (a sensor — open records cannot be shed). Nothing
outside the two INDEX files and their `CLOSED.md` shards is touched.

## Extended checks

- **`--verify-code-state`** — advisory phantom-open sweep (file says OPEN, git
  says FIXED); does not affect the `--check` exit code.
- **Decision-log body coverage** — folded into `--check`; flags header DEC IDs
  with no `### DEC-…` body entry (`DRIFT-DEC-MISSING` → exit 1).

## References

- [`references/parsing-and-contract.md`](references/parsing-and-contract.md) —
  status-token contract, filename convention, status-header formats,
  companion-file exclusion, core-scan degradation modes.
- [`references/extended-checks.md`](references/extended-checks.md) —
  `--verify-code-state` and decision-log coverage: flags, algorithm, output,
  degradation modes.

## Notes

- The `**Status**` header in each record file is authoritative. Status is never
  inferred from filename or INDEX section placement.
- The TD pattern is `TECH-DEBT-\d+(?:-[a-z0-9-]+)?\.md` (slug optional); files
  matching `TD-*.md` are not matched (wrong prefix).
- No `.claude/skills/` shim is needed — the installer auto-generates POV skill
  shims at install time.
