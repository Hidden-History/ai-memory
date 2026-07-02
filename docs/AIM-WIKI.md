# Project Wiki Generator & Maintainer (aim-wiki)

The `aim-wiki` skill creates and maintains a wiki of **your own project** under a `wiki/` directory, in-session. It answers "what is this repo, how is it organized, and where do I start" for any agent (or person) opening the codebase cold — a quickstart entrypoint plus linked section pages, grounded in source and git evidence rather than invented.

**Claude Code is the doc-gen agent** — there is no separate LLM or provider. A Python engine does only the deterministic work (repo scoping, inventory, scaffolding, run-state, git-diff, pointer injection, verifier manifest) and hands the results to Claude Code, which does the reasoning: authoring and refreshing pages, and dispatching a read-only verifier to cross-check claims against source before acceptance.

## How It Works

| Part | Artifact | Location |
|------|----------|----------|
| **Wiki output** | `quickstart.md` + section pages | `wiki/` (project root, committed like any other doc) |
| **Skill** | `aim-wiki` (`init` · `update` · `status` · `verify` · `finalize`) | `_ai-memory/skills/aim-wiki/` |
| **Engine (deterministic)** | `aim_wiki.py` (+ `wiki_common.py`, `wiki_inventory.py`, `wiki_pointer.py`, `wiki_verify.py`) | `_ai-memory/skills/aim-wiki/scripts/` |
| **Agent-instruction pointer** | Managed `## Project Wiki` section | Top-level `CLAUDE.md` and/or `AGENTS.md` |
| **Run state** | `.last-update.json` (content-hash + `gitHead` + `updatedAt`) | `wiki/.last-update.json` (excluded from the content hash) |

The engine is invoked via `run-with-env.sh` (the AI-memory run-with-env convention). Every subcommand accepts `--root PATH` (override the project root; defaults to the git toplevel, else the current directory) and `--json` (machine-readable output).

## Grounding discipline

Authoring is held to the same standard as the underlying source:

- **Do not invent** files, modules, APIs, business rules, or behavior — ground every important claim in source files, existing docs, or inspected git evidence, with inline source references so a reader can verify.
- **Discover efficiently** — inspect the tree, config/package files, entrypoints, and representative files per domain rather than reading everything; prefer `Grep`/`Glob` and targeted reads.
- **Existing docs are primary source** — treat READMEs, `docs/`, and `SKILL.md` files as material to summarize and link, not duplicate; flag a doc that conflicts with current source rather than trusting it.
- **Subagents are read-only** — a dispatched research/verifier subagent may inspect and summarize but never create, edit, move, or delete files, and never writes under `wiki/`.
- **Security** — never read or document secret values, credentials, keys, tokens, or `.env` files (placeholders in `.env.example` are fine).

Full page-authoring rules (entrypoint, page count, no thin pages, one canonical home per concept) live in `references/page-structure.md` and are read before authoring, not restated here.

## Modes

### `init` — create the wiki

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  init [--force] [--json]
```

Guards an existing wiki — if `wiki/` already has authored content, `init` routes to `update` unless `--force` is passed to rebuild. Otherwise it builds a repo inventory (file counts by bucket: docs, entrypoints, config, tests, schema) and a git summary (branch + recent commits), which Claude Code reads as its grounding before authoring `wiki/_plan.md` (deleted before finishing), then `wiki/quickstart.md` and the linked section pages — at most ~8 pages on a first run unless the repo is clearly tiny.

### `update` — incremental maintenance

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  update [--json]
```

Reads the recorded state and computes the git-diff since the recorded `gitHead` (committed + uncommitted, wiki-managed paths excluded), plus whether the wiki's own content hash has changed since the last record. Claude Code builds a docs-impact plan (changed source → page → edit → why) and edits surgically — replacing a stale sentence rather than adding paragraphs, and never reformatting an accurate page. **A no-op is valid**: if nothing relevant changed, the correct action is to say so and stop. If no state file is found, `update` reports `no_state` (wiki exists, needs a `finalize --command init` baseline) or `not_initialized` (no wiki — run `init`) instead of guessing.

### `status` — freshness only, no writes

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  status [--json]
```

Reports `current`, `drifted`, or `unknown`: the last `updatedAt` and `gitHead`, how many source files have changed since (committed + uncommitted), and whether the wiki content was hand-edited since the last recorded run. `unknown` means the recorded `gitHead` no longer resolves (e.g. rewritten history) — the diff can't be computed, so `status` never reports `current` in that case. Never writes.

### `verify` — correctness gate

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  verify [--json]
```

Two layers, run after authoring or refreshing:

1. **Deterministic dead-citation precheck** — the engine extracts every inline source citation from the wiki pages (markdown links and backtick-wrapped paths with a recognized source extension) and checks each resolves to a real file. A dead citation is immediate, unambiguous drift.
2. **Read-only verifier subagent** — dispatched (via the `Task` tool) with the manifest, it cross-checks that each page's *claims* match its cited source — a citation can point at a real file yet still misdescribe it. It inspects and reports only, one pass, never edits.

All discrepancies (dead citations + ungrounded/drifted claims) are surfaced in the review gate before acceptance — the in-session equivalent of a PR review.

### `finalize --command init|update` — post-acceptance writes

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  finalize --command init [--json]
```

Runs only after the human accepts the authored/refreshed wiki and the verify pass. It upserts the `## Project Wiki` pointer (below) and writes the run-state (`updatedAt`, `command`, `gitHead`, content hash) to `wiki/.last-update.json`. If `wiki/` has no authored pages yet, `finalize` refuses and writes nothing.

## The `## Project Wiki` pointer

`finalize` is the only step that touches files outside `wiki/`, and it touches exactly one thing: a pointer section telling any coding agent the wiki exists.

- **Placement**: upserted into the top-level `CLAUDE.md` and/or `AGENTS.md`, whichever already exist. If neither exists, a new `AGENTS.md` is created containing only the section. Only ever the top-level files — never a nested `CLAUDE.md`/`AGENTS.md`.
- **Idempotency**: the section is delivered inside a managed marker pair, `<!-- BEGIN AI-MEMORY (managed aim-wiki) -->` … `<!-- END AI-MEMORY (managed aim-wiki) -->`. Idempotency keys on the marker pair, **never** on the human-readable `## Project Wiki` heading — so a user's own hand-written section with that same heading is never clobbered.
- **Legacy migration**: a markerless `## Project Wiki` section is migrated to the marked form exactly once, and only when its body matches aim-wiki's own template verbatim — anything else is treated as user content and left untouched.
- **Malformed markers**: any other marker state (stray, duplicate, or out-of-order BEGIN/END) is left unchanged; the engine prints a warning to stderr and writes nothing rather than risk clobbering content on an ambiguous state.
- **Write safety**: on an actual content change, the existing file is copied to a timestamped `.backup.<timestamp>` first, then the new content is written via a temp file (`tempfile.mkstemp`) and `os.replace` (atomic) — a crash mid-write cannot truncate the original. When the managed block is already present and identical, nothing is written and no backup is made.

## Staleness model

Freshness is tracked two ways, both recorded in `wiki/.last-update.json` at `finalize` time:

- **Source drift** — files changed (committed since the recorded `gitHead`, or currently uncommitted) that aren't part of the wiki's own managed paths. The wiki directory itself and the top-level `CLAUDE.md`/`AGENTS.md` pointer files are excluded from this signal, since editing the docs isn't the source changing out from under them.
- **Wiki-edited-since-record** — a SHA-256 over every authored file under `wiki/` (sorted relative path + bytes; the state file and the temporary `_plan.md` are excluded) compared against the hash stamped at the last `finalize`. A mismatch means someone hand-edited the wiki without going through `finalize`.

`status` combines both into `current` / `drifted` / `unknown`.

## Limits (v1)

- **Standalone, no Qdrant** — the wiki lives entirely in `wiki/` on disk; there is no memory-store integration in v1.
- **Whole-file drift exclusion** — source-drift detection excludes the *entire* top-level `CLAUDE.md`/`AGENTS.md`, not just the injected pointer section. A substantive unrelated hand-edit elsewhere in one of those files will not register as drift. Pointer-section-scoped drift is a deferred v2 refinement.
- **In-session only** — there is no headless or CI mode / GitHub Action in v1.
- **No `aim-sot` composition** — doc-drift signals are not yet composed with the `aim-sot` skill's own drift tracking (see [`docs/AIM-SOT.md`](AIM-SOT.md)); these are separate systems today.
- **Multi-project scoping** is guaranteed by the resolved project root: the wiki is written only under that project's `wiki/`, never across projects.
