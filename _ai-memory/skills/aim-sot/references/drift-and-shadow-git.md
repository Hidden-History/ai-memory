# Drift strategies, shadow git & doc-drift — reference

Detailed reference for the `[CL]` detect pass (`detect-propose run --shadow`). The
SKILL.md body holds the summary; this file holds the look-up detail. All of it is
engine-side and shared by every CLI — the per-CLI Stop hooks only pass `--shadow`.

## Drift strategy registry

The drift digest for each registry entry is computed by an **enum-selected** strategy
(never a shell command — no arbitrary code execution). The default is chosen by the
artifact shape; override per entry with the schema-validated `drift_strategy` field.

| Strategy | Applies to | Digest | Default for |
|----------|-----------|--------|-------------|
| `content-digest` | a file | `sha256(file)[:8]` | file `sot_location` |
| `tree-digest` | a directory | BP-039 `vN:` sorted-per-file-SHA-256 hash-of-hashes | directory `sot_location` |
| `git-tree-hash` | a directory | same as tree-digest (BP-039 content digest); git-native tree hash reserved for a future version | — (opt-in) |
| `git-ahead-behind` | a ref boundary | reserved — not yet implemented; temporal-only, no content digest | — (opt-in) |
| `temporal` | any | date-only (no content digest) | — (fallback) |

**R-1 re-baseline:** the drift-state records the entry's `drift_strategy` and
`digest_version`. A strategy switch (e.g. `content-digest` → `tree-digest`) or a
digest-version bump (`v1:` → `v2:`) is treated as a **re-baseline**, not a drift
finding — the digest is not comparable across strategies or versions.

**Tree-digest (BP-039)** is deterministic across walk-order, machine, and
clone/restore: regular files only, content-only hashing, POSIX relpaths byte-sorted,
symlinks skipped and recorded, a `vN:` version prefix. Excludes are applied to the
relpath before the file set is frozen (defaults plus the registry's `exclude:` list).

**Budget truncation is a partial sentinel (F-SOT-3).** A directory tree digest is
bounded by `AI_MEMORY_SOT_DIGEST_MAX_SECONDS` / `AI_MEMORY_SOT_DIGEST_MAX_FILES`
(see [`docs/AIM-SOT.md`](../../../../docs/AIM-SOT.md)). When a boundary's walk hits
that budget it stops early and returns a **partial** digest flagged `truncated`. A
truncated digest is never a valid drift signal, so the engine:

- **never compares it as drift** — the content-hash and declaration checks are skipped
  for that boundary this run (a partial digest would otherwise mismatch and report
  false drift);
- **never stores it as a baseline** — the prior `last_verified_sha` is carried forward
  unchanged; a cold-start boundary (no prior baseline) is left `unverified` with no
  baseline, so the next complete walk establishes the real digest;
- **surfaces the truncation** — a `FRICTION` finding naming the boundary is emitted and
  the run's `budget_truncated` flag is set, so an incomplete scan is never silent.

The per-file hash cache (BP-048) is the mitigation: it warms across sessions so a
large boundary that truncated on a cold run completes on a later warm run.

## Shadow git (BP-040)

A machine-local **bare** repository at `~/.ai-memory/sot-git/<project_id>/` tracks the
project tree without touching the user's VCS.

- **Two-pointer** — every git op runs with `GIT_DIR=<shadow>` and
  `GIT_WORK_TREE=<project>`. `--separate-git-dir` is rejected (it would write a `.git`
  pointer into the user's tree). Zero footprint in the project: no `.git`, no
  `.gitignore`, no hooks.
- **Config at setup** — `core.worktree`, `status.showUntrackedFiles=no`, `gc.auto=256`,
  `gc.pruneExpire=30.days.ago`, `gc.autoPackLimit=10`, `core.symlinks=false`.
- **Excludes** — written to `<shadow>/info/exclude` (never a `.gitignore` in the
  user's tree): the project's `.git`, caches, build output, secrets, and `.sot/`.
- **Cadence** — one commit at Stop; the commit is skipped when the `git diff --cached`
  index is clean (no staged changes after `git add -A`). This index check is the gate
  and is digest-equivalent on the shared file set once exclude semantics are aligned
  (F-M1). The `detect-propose run --shadow` path also stores per-component
  `drift_strategy`/`digest_version` + `drift_rollup` in the 5a cache and emits
  content-drift findings for directory SOTs. `git gc --prune=30.days.ago` runs after
  the commit.
- **Cap-and-rotate** — at ≥500 commits or ≥100 MB packed, a one-shot
  `gc --aggressive --prune=now` runs.
- **Teardown** — `rm -rf ~/.ai-memory/sot-git/<project_id>` (or `aim_sot_shadow.py
  teardown`); no user-project residue.

## Setup sentinel (BP-041)

Setup runs once, then skips fast (~0.35 ms) on every later session.

- **Sentinel** — `~/.ai-memory/sot-setup/sot_setup_<project_id>.json` (machine-local,
  never committed). Written **last**, after the shadow git is created and verified, so
  a partial failure leaves no sentinel and the next session retries.
- **Skip gate** — sentinel exists → `json.load` → `schema_version` + `setup_version`
  match → skip.
- **Invalidation, cheapest-first** — absent → corrupt → `schema_version` mismatch →
  `setup_version` mismatch → `AIM_SOT_RECONFIGURE=1` (or `--reconfigure`).
- **Idempotent** — every action is check-then-create; `git init --bare` is re-run-safe.

Explicit CLI (the separate setup workflow):

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-sot/scripts/aim_sot_shadow.py" \
  setup [--project-dir PATH] [--reconfigure]      # also: teardown | status
```

## Doc-drift (BP-042)

On a shadow commit, `git diff --name-status <last_verified_sha> HEAD` yields a typed
change set; each changed code path is correlated to the docs that own it.

**`.sot/DOCOWNERS`** (Pattern A) lives with the registry in the single committed SOT
home, `.sot/` — not repo root. Format: `<doc-glob>  <watched-code-glob...>`.

```
# .sot/DOCOWNERS — consumed only by the aim-sot engine
docs/api/*.md           src/api/**
docs/auth.md            src/auth/**
docs/architecture/*.md  src/core/** src/infra/**
```

**False-positive guards** — a finding is suppressed when the whole commit is
test-only, doc-only, or internal-only; and per-path test/doc/internal changes never
trigger a doc. Severity: a deleted or renamed code path → `HIGH`; otherwise `MEDIUM`.
No doc-drift findings are emitted on the first session Stop — the shadow git needs at
least two commits (a before and an after) to produce a diff.

A **reformat-only guard is deferred**: `git diff --name-status` cannot distinguish a
formatter-only pass from a substantive modification (no line-content visibility), so
an all-`M` commit cannot be reliably classified as reformat-only. Doc-drift findings
are advisory/propose-only, so a reviewer can dismiss a formatter false-positive at low
cost.

## Findings pipe

One structured emitter carries every finding class — drift, doc-staleness, and tool
`ERROR` / `FRICTION` — so nothing is silently dropped. The engine **emits**; only the
oversight agent (Parzival) writes the register.

```json
{
  "bp_id": "BP-042",
  "finding_type": "DOC_DRIFT",          // DOC_DRIFT | SOT_ANOMALY | ERROR | FRICTION
  "severity": "MEDIUM",                  // HIGH | MEDIUM | LOW | INFO
  "detected_at": "2026-06-21T12:00:00Z",
  "doc_file": "docs/api/users.md",
  "trigger_path": "src/api/users.py (Modified)",
  "trigger_commit": {},
  "anchor_type": "DOCOWNERS_MAP",
  "recommended_action": "Review docs/api/users.md against the change to src/api/users.py."
}
```

Findings appear under `findings` in the `detect-propose run --shadow --json` output;
the live `drift_rollup` (`clean` / `changed` / `docs_stale`) is surfaced by
`consult digest` as the `[ST]` ambient channel.
