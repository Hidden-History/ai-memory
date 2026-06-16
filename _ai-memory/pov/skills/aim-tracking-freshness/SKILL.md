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

Oversight root may also be set via `AI_MEMORY_OVERSIGHT_ROOT`. If both that and
`--oversight-root` are absent, the script defaults to `./oversight` relative to
the CWD — run from the workspace root (the directory containing `oversight/`).

## Modes

### `--check` (read-only)

Reads all record files and the current INDEX files, then compares. Reports:
companions excluded, no-status warnings, divergences (file Status vs INDEX
section — the BUG-301 class), orphan INDEX rows, and records missing from the
INDEX. The id-parse spans `INDEX.md` **and** `CLOSED.md`, so sharded closed
records are not falsely reported as missing.

Exits non-zero if any divergence, orphan, missing record, or no-status record
is found. Exits 0 only when INDEX files are fully in sync with all record files.

### `--write`

Runs the same analysis as `--check`, then regenerates both INDEX files. **Exit
code 0** means a successful write. Use `--check` as the CI gate. Each INDEX:

- Opens with the D2 contract front-matter (`class: register`,
  `read_path: section-anchored`, `cap_lines`/`cap_kb`, `archive_target: CLOSED.md`).
- `## Open` cells **summarize** the status (≤ 8 words / 64 chars); the linked
  file holds the full text. Classification uses the full raw status, so display
  truncation never changes open/closed placement.
- `## Closed` lists only the most recent 10 plus a
  `[Full closed history → ./CLOSED.md] (N)` pointer; the complete history is
  written to `bugs/CLOSED.md` / `tech-debt/CLOSED.md` (idempotent overwrite).
- The written INDEX size is asserted against its cap (bugs ≤ 100 lines / 12 KB,
  TD ≤ 150 lines / 18 KB); over-cap emits a loud stderr `WARNING` (a sensor, not
  a crash — open records cannot be shed).

Touches nothing outside the two INDEX files and their `CLOSED.md` shards.

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
