# Parsing Contract & Status Classification

Reference detail for `aim-tracking-freshness`. The `**Status**` header in each
record file is authoritative; status is never inferred from filename or INDEX
section placement.

## Contract — Source of Truth

Filename and status-token conventions are grounded on the POV template
contract, not on any single project's live tree:

- **`_ai-memory/pov/templates/bug-report.template.md`** — specifies the
  `BUG-NNN` ID convention. **No filename slug is mandated.** Status workflow:
  `New → In Progress → Fixed → Verified → Closed`, plus `Reopened`.
- **`_ai-memory/pov/templates/tech-debt-report.template.md`** — same slug-
  optional convention for `TECH-DEBT-NNN` files.

### Filename convention (slug-optional)

Both `BUG-NNN.md` and `BUG-NNN-<slug>.md` are accepted as valid record
filenames (and the analogous `TECH-DEBT-NNN.md` / `TECH-DEBT-NNN-<slug>.md`
forms). The slug portion `[a-z0-9-]+` is matched case-insensitively
(`re.IGNORECASE`), so a slug using uppercase or mixed-case letters (e.g.
`BUG-005-BADSLUG.md`) is **accepted** as a normal record.

Files that start with `BUG-` or `TECH-DEBT-` but fail the full pattern are
reported as **skipped** and count toward `--check` failure. A file is skipped
when its slug contains characters outside `[a-z0-9-]` (most commonly an
underscore, e.g. `BUG-005-BAD_SLUG.md`), or when it has the wrong file
extension (e.g. `.txt`).

### Closed-class tokens

**Bug records** — canonical tokens (from template status workflow):
`FIXED`, `VERIFIED`, `CLOSED`

Tolerated legacy / extended forms:
`RESOLVED`, `NOT A BUG`, `NOT-A-BUG`, `DUPLICATE`, `RECLASSIFIED`,
`FIX APPLIED`, `FIX-APPLIED`

**Tech-debt records** — canonical tokens:
`RESOLVED`, `CLOSED`, `WONT FIX`, `WON'T FIX`

Tolerated legacy forms:
`IMPLEMENTED`, `FIXED`

All matching uses **leading-token** logic: a closed-class token only closes a
record when it appears at the very start of the normalized status string
(stripped of emoji and bold markers), followed by a word boundary. This
prevents false-closed classification when a closed token appears in a trailing
historical context clause (e.g. `REOPENED (PM #295) — Previously: FIXED`).

> Note: the INDEX displays a *summary* of the status (bounded to 8 words / 64
> characters). Classification always reads the full raw status, so display
> truncation never affects open/closed placement.

## Status Header Parsing

The script handles three formats found in the live oversight tree:

| Format | Example |
|--------|---------|
| Colon outside bold | `**Status**: FIXED` |
| Colon inside bold | `**Status:** FIXED` |
| Table row | `\| **Status** \| FIXED \|` |

Both colon formats are matched by a single regex with two optional-colon slots.
The table-row format is tried as a fallback.

`LIKELY FIXED` remains open: `LIKELY` is not a closed-class token, so
`classify_status` finds no leading closed-class match and treats the record as
open. No explicit guard is needed beyond the leading-token rule.

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
excluded by the filename pattern filter (`BUG-\d+-*.md` / `TECH-DEBT-\d+-*.md`).

## Failure & Degradation Modes (core scan)

| Condition | Behaviour |
|-----------|-----------|
| `oversight/` root missing | Hard error → `sys.exit(1)` |
| `bugs/` or `tech-debt/` dir absent | Graceful degradation: logged to stderr as `NOTE: … absent — not scaffolded`; scan proceeds with 0 records for that tracker |
| `INDEX.md` missing when records exist | Surfaced as `MISSING INDEX FILES` section; counted in `--check` failure; `--write` creates it |
| 0 records scanned (both dirs empty or absent) | Prints `0 records scanned — empty/absent tracking tree`; never prints `✓ in sync` |
| Record-shaped file fails full filename pattern | Logged in `SKIPPED` report section; counted in `--check` failure |
| Record file has no `**Status**` header | Logged in `WARNING — NO STATUS HEADER`; counted in `--check` failure |
| Record file is unreadable (OS error) | Emitted as a `Record` with `numeric_id="???"` and `is_closed=False`; surfaced via no-status warning |
