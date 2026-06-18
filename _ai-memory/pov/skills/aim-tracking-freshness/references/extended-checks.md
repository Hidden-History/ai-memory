# Extended Checks

Reference detail for the two opt-in/folded checks in `aim-tracking-freshness`:
phantom-open code-state verification and decision-log body coverage.

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
   bulleted lines. Version tokens are captured for completeness; the current
   Step C scoring does not consume them.
2. **Resolve default branch** (spec §4.7 row 3): the script reads
   `git symbolic-ref --short refs/remotes/origin/HEAD` to learn the source
   repo's default-branch name (so `master` / `trunk` / `develop` repos
   classify the same as `main` repos). When that fails (no origin remote,
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
| Source repo default branch is not `main` (e.g. `master`, `trunk`) | `git symbolic-ref refs/remotes/origin/HEAD` resolves the real default-branch name; reachability checks use that branch. No NOTE emitted (the resolved name is the silent happy path). |
| `origin/HEAD` unresolvable (bare repo, missing origin, …) | Fall back to literal `HEAD`; emit `NOTE: --verify-code-state: default branch not resolvable …` once per sweep to stderr; exit code unchanged |
| Detached HEAD in source repo | Fall back to literal `HEAD` plus a second `NOTE: --verify-code-state: source repo in detached HEAD state …` to stderr; reachability is checked against HEAD only |
| Per-record `git log` exceeds the 5 s timeout | Record is routed into the `EVIDENCE-TIMEOUT` bucket (spec §4.7 row 4); reported as an informational table in stdout + sidecar; does NOT contribute to `--check` exit code |
| `--write --verify-code-state` | Phantom-open sweep runs and the sidecar is written; the sweep does NOT contribute to the `--write` exit-code contract (existing behaviour preserved) |

The check is intentionally a *signal*, not a *gate*: false positives are
acceptable because human triage confirms each candidate before any Status
change. The exit code is reserved for the deterministic INDEX-vs-Status
divergence checks.

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
4. Extract body DEC IDs from `^### (DEC-PM\d+-D\d+)` headings (`re.MULTILINE`).
5. Diff:
   - **DRIFT-DEC-MISSING** — DEC ID in header block but no body heading.
     Emits `✗`. **Contributes to `--check` exit 1.**
   - **DRIFT-DEC-ORPHAN** — body heading with no header reference. Emits `ℹ`.
     **Informational only — does not affect exit code.**

### Output

A `DECISION-LOG COVERAGE` section is appended to the staleness report, printed
after the phantom-open section (when enabled). When the missing count is zero,
the section ends with `✓ Decision-log body coverage is complete.`.

### Failure & Degradation Modes

| Condition | Behaviour |
|-----------|-----------|
| `oversight/tracking/decision-log.md` absent | Section prints with zero counts; `NOTE: decision-log.md not found at <path> — decision-log coverage check skipped.` to stderr; exit unchanged by this check |
| `tracking/decision-log.md` present but unreadable (OS error) | Same graceful skip as above with the OS-error message in the NOTE |
| No `^---$` separator anywhere in the file | The entire file is treated as the header block; `NOTE: decision-log.md has no '---' separator — treating entire file as header block.` to stderr |
| Header references a range that overlaps the body partially (e.g. header `D1..D3`, body only `D2`) | D1 and D3 emitted as DRIFT-DEC-MISSING; exit 1 |
| Body heading present without header reference | DRIFT-DEC-ORPHAN emitted (ℹ); exit unchanged |
