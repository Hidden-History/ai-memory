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

# Add phantom-open code-state verification (cross-checks open records against git):
python ~/.ai-memory/_ai-memory/pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py \
  --check \
  --oversight-root /path/to/oversight \
  --verify-code-state \
  --source-repo /path/to/source-git-repo

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
reported as **skipped** and count toward `--check` failure.  A file is skipped
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
- The TD pattern is `TECH-DEBT-\d+(?:-[a-z0-9-]+)?\.md` (slug optional).
  Files matching `TD-*.md` are not matched (wrong prefix).
- No `.claude/skills/` shim is needed. The installer auto-generates POV skill
  shims at install time.

---

## Failure & Degradation Modes

| Condition | Behaviour |
|-----------|-----------|
| `oversight/` root missing | Hard error → `sys.exit(1)` |
| `bugs/` or `tech-debt/` dir absent | Graceful degradation: logged to stderr as `NOTE: … absent — not scaffolded`; scan proceeds with 0 records for that tracker |
| `INDEX.md` missing when records exist | Surfaced as `MISSING INDEX FILES` section; counted in `--check` failure; `--write` creates it |
| 0 records scanned (both dirs empty or absent) | Prints `0 records scanned — empty/absent tracking tree`; never prints `✓ in sync` |
| Record-shaped file fails full filename pattern | Logged in `SKIPPED` report section; counted in `--check` failure |
| Record file has no `**Status**` header | Logged in `WARNING — NO STATUS HEADER`; counted in `--check` failure |
| Record file is unreadable (OS error) | Emitted as a `Record` with `numeric_id="???"` and `is_closed=False`; surfaced via no-status warning |

---

## Phantom-Open Code-State Verification (`--verify-code-state`)

**Purpose**: Detect records whose file `**Status**` says OPEN but whose fix
commits are already reachable from `main` in the source repository. Prevents
the BUG-301 / DEC-PM298-D2 class of waste where a phantom-open record nearly
triggered an unnecessary dispatch. Advisory only — does **not** affect the
`--check` exit code.

### Activation

Pass `--verify-code-state` together with `--check` (or `--write`).

```bash
python tracking_freshness.py --check \
  --oversight-root /path/to/oversight \
  --verify-code-state \
  --source-repo /path/to/source-git-repo
```

### Flags

| Flag | Effect |
|------|--------|
| `--verify-code-state` | Enable the phantom-open sweep. Required to invoke this check. |
| `--source-repo PATH` | Path to the source git repo. Resolution order: this flag → `AI_MEMORY_SOURCE_REPO` env var → `../ai-memory` relative to `--oversight-root`. |
| `--last-n-sessions N` | Limit the sweep to the N most recently modified open records. |
| `--bug-id RECORD-ID` | Run the sweep for a single record (e.g. `BUG-273` or `TECH-DEBT-547`). |

### Algorithm

For each open BUG/TD record:

1. **Extract evidence tokens** from the record body (spec §4.1 Step A):
   commit SHAs (`\b[0-9a-f]{7,40}\b`), PR refs (`#\d{1,4}` on non-heading
   lines), version strings (`v\d+\.\d+\.\d+`), and file paths cited on
   bulleted lines.  Version tokens are captured for completeness; the current
   Step C scoring does not consume them.
2. **Resolve default branch** (spec §4.7 row 3): the script reads
   `git symbolic-ref --short refs/remotes/origin/HEAD` to learn the source
   repo's default-branch name (so `master` / `trunk` / `develop` repos
   classify the same as `main` repos).  When that fails (no origin remote,
   bare repo, detached HEAD, …) the script falls back to the literal `HEAD`
   ref-spec and emits a `NOTE: --verify-code-state: default branch not
   resolvable …` to stderr; a truly detached HEAD emits a second
   detached-state NOTE.
3. **Query git history**: `git log --all --grep=<RECORD-ID>` and
   `git log <branch-ref> --grep=<RECORD-ID>`; `git diff-tree --no-commit-id
   --name-only -r --root <SHA>` for each branch-ref-reachable SHA.
4. **Score confidence**:
   - **HIGH** — at least one commit reachable from `<branch-ref>`, file-path
     overlap with the record body, AND the record file mtime predates the
     latest fix commit timestamp.
   - **MEDIUM** — commit reachable from `<branch-ref>`, no file-path overlap.
   - **LOW** — only inline evidence (PR ref / SHA in body) without a
     branch-ref-reachable commit; OR a matching `Revert "…<RECORD-ID>…"`
     commit is also reachable from `<branch-ref>` (downgrade rule).

Records with no git evidence and no inline evidence tokens are skipped (no
phantom-open finding emitted).

### Output

- **Stdout section**: `PHANTOM-OPEN CANDIDATES (file says OPEN, git says FIXED)`
  with one markdown table per confidence bucket (HIGH / MEDIUM / LOW) and
  an `EVIDENCE-TIMEOUT` table when per-record git queries timed out.
- **Sidecar file**: `oversight/reports/PHANTOM-OPEN-CANDIDATES.md`. The
  `oversight/reports/` directory is created with `mkdir -p` if absent. The
  sidecar is overwritten on every run (no append, no rotation).
- **Zero candidates**: stdout prints `✓ No phantom-open candidates detected.`

### Failure & Degradation Modes

| Condition | Behaviour |
|-----------|-----------|
| `--source-repo` not provided, env var unset, and `../ai-memory` not a directory | Section skipped; `NOTE: --verify-code-state requested but source repo not resolved …` to stderr; exit code unchanged |
| `git` binary missing from `PATH` | Section skipped; `NOTE: --verify-code-state requested but 'git' binary not found in PATH.` to stderr; exit code unchanged |
| Source repo default branch is not `main` (e.g. `master`, `trunk`) | `git symbolic-ref refs/remotes/origin/HEAD` resolves the real default-branch name; reachability checks use that branch.  No NOTE emitted (the resolved name is the silent happy path). |
| `origin/HEAD` unresolvable (bare repo, missing origin, …) | Fall back to literal `HEAD`; emit `NOTE: --verify-code-state: default branch not resolvable …` once per sweep to stderr; exit code unchanged |
| Detached HEAD in source repo | Fall back to literal `HEAD` plus a second `NOTE: --verify-code-state: source repo in detached HEAD state …` to stderr; reachability is checked against HEAD only |
| Per-record `git log` exceeds the 5 s timeout | Record is routed into the `EVIDENCE-TIMEOUT` bucket (spec §4.7 row 4); reported as an informational table in stdout + sidecar; does NOT contribute to `--check` exit code |
| `--write --verify-code-state` | Phantom-open sweep runs and the sidecar is written; the sweep does NOT contribute to the `--write` exit-code contract (existing behaviour preserved) |

The check is intentionally a *signal*, not a *gate*: false positives are
acceptable because human triage confirms each candidate before any Status
change. The exit code is reserved for the deterministic INDEX-vs-Status
divergence checks above.

---

## Decision-Log Body Coverage (`--check` default)

**Purpose**: Catch the PM #299 closeout failure mode where the decision-log
header summary references DEC IDs (e.g. `DEC-PM299-D1..D8`) without
corresponding `### DEC-PM299-Dn` body entries. Folded into `--check` default;
no opt-in flag required. Graceful skip when `tracking/decision-log.md` is
absent.

### Algorithm

1. Read `oversight/tracking/decision-log.md`.
2. Split on the first `^---$` separator; everything before it is the **header
   block**.
3. Extract DEC IDs from the header block using two patterns:
   - **Range** — `DEC-PM(\d+)-D(\d+)\.\.D(\d+)` expanded to all IDs in the
     range. Example: `DEC-PM299-D1..D8` → eight individual IDs.
   - **Individual** — `DEC-PM(\d+)-D(\d+)` applied to text not already
     consumed by a range match (dedup by position).
4. Extract body DEC IDs from `^### (DEC-PM\d+-D\d+)` headings
   (`re.MULTILINE`).
5. Diff:
   - **DRIFT-DEC-MISSING** — DEC ID in header block but no body heading.
     Emits `✗`. **Contributes to `--check` exit 1.**
   - **DRIFT-DEC-ORPHAN** — body heading with no header reference. Emits `ℹ`.
     **Informational only — does not affect exit code.**

### Output

A `DECISION-LOG COVERAGE` section is appended to the staleness report,
printed after the phantom-open section (when enabled). When the missing count
is zero, the section ends with `✓ Decision-log body coverage is complete.`.

### Failure & Degradation Modes

| Condition | Behaviour |
|-----------|-----------|
| `oversight/tracking/decision-log.md` absent | Section prints with zero counts; `NOTE: decision-log.md not found at <path> — decision-log coverage check skipped.` to stderr; exit unchanged by this check |
| `tracking/decision-log.md` present but unreadable (OS error) | Same graceful skip as above with the OS-error message in the NOTE |
| No `^---$` separator anywhere in the file | The entire file is treated as the header block; `NOTE: decision-log.md has no '---' separator — treating entire file as header block.` to stderr |
| Header references a range that overlaps the body partially (e.g. header `D1..D3`, body only `D2`) | D1 and D3 emitted as DRIFT-DEC-MISSING; exit 1 |
| Body heading present without header reference | DRIFT-DEC-ORPHAN emitted (ℹ); exit unchanged |
