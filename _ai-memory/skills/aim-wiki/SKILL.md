---
name: aim-wiki
description: Creates and maintains an up-to-date wiki of the user's current project, in-session, while you work — a dedicated wiki/ directory with a quickstart entrypoint plus section pages, grounded in source and git evidence. Claude Code itself authors the pages; a Python engine does the deterministic work (repo inventory, wiki scaffold, content-hash/gitHead state, git-diff-since-last-run, CLAUDE.md/AGENTS.md pointer, verifier manifest). Modes init | update | status, plus verify and finalize. Use when asked to create, refresh, or check the freshness of the project wiki/docs. Do NOT use for AI Memory search/save/health (use aim-search, aim-save, aim-status) or SOT drift (use aim-sot).
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task
---

# aim-wiki — Project Wiki Generator & Maintainer

Creates and maintains a wiki of the current project under `wiki/`, **in-session**.
Works on any project (new or existing) under AI Memory.

**You (Claude Code) are the doc-gen agent.** The Python engine
(`scripts/aim_wiki.py`) does only deterministic work and hands you structured
context; you do the reasoning — analyze the code and author/refresh the pages,
grounding every claim in source. There is no separate LLM or provider — you are
the model.

## Split of responsibilities

- **Engine (Python) → deterministic**: project scoping, repo inventory, wiki
  scaffold, run-state (content-hash + gitHead + updatedAt), git-diff since last
  run, pointer injection, and the verifier manifest.
- **You (Claude Code) → reasoning**: author `wiki/quickstart.md` + section pages,
  refresh them surgically, and dispatch the read-only verifier.
- **Correctness → a read-only verifier subagent**: after authoring,
  cross-check page claims against source before acceptance.

The engine is invoked via `run-with-env.sh` (the AI-memory run-with-env convention). All modes accept
`--root PATH` (override the project root; default = git toplevel, else cwd) and
`--json`.

## Grounding discipline (read before authoring)

Concepts adapted from OpenWiki's system prompt (MIT — paraphrased, not lifted).

- **Do not invent** files, modules, APIs, business rules, or behavior. Ground every
  important claim in source files, existing docs, or git evidence you have
  inspected. Include inline source references so a reader can verify.
- **Discover efficiently.** Do not read every file. Inspect the tree, package/config
  files, README-style docs, entrypoints, routing, schema/data files, and
  representative files per domain. Prefer `Grep`/`Glob` and short targeted reads
  over full-file reads. Do not glob `**/*` from the repo root; exclude `.git`,
  `node_modules`, `dist`, `build`, caches, and the `wiki/` output itself.
- **Use git for the "why".** Use recent history and targeted `git log`/`show`/`blame`
  on high-signal files to explain why code exists, not just what it is. Do not
  over-index on ancient history or paste commit-hash lists into pages.
- **Existing docs are primary source.** Treat READMEs, `docs/`, runbooks, and
  `SKILL.md` files as source material — summarize and link rather than duplicate.
  If existing docs conflict with the code, flag the likely-stale doc and prefer
  current source.
- **Subagents are read-only.** You may dispatch read-only research/verifier
  subagents that only inspect and summarize with source paths; they must not
  create, edit, move, or delete files, and must not write under `wiki/`. You
  synthesize and own all writes.
- **Security.** Never read or document secret values, credentials, keys, tokens, or
  `.env` files. `.env.example`/samples only if they hold placeholders. Keep all
  docs under `wiki/`.
- **Plan file.** After discovery, before authoring, write `wiki/_plan.md` (intended
  pages, evidence per page, open questions). **Delete it before finishing.**

Full page-structure, page-count, thin-page, and canonical-home rules:
[`references/page-structure.md`](references/page-structure.md) — read before authoring.

## Flows

### `init` — create the wiki from the current project

1. **Engine (prep):**
   ```bash
   bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
     "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
     init [--force] [--json]
   ```
   Resolves the project root, guards an existing wiki (routes you to `update`
   unless `--force`), builds the repo inventory + git summary, and scaffolds
   `wiki/`. Read the emitted `inventory` and `git_summary` — that is your grounding.
2. **You (author):** write a `wiki/_plan.md` (evidence-linked), then author
   `wiki/quickstart.md` first and the linked section pages. ≤8 pages on the first
   run unless tiny; no thin pages; one canonical home per concept; ground every
   claim. Delete `wiki/_plan.md` when done.
3. **Verify** (below).
4. **Review gate:** present the wiki diff + the verifier's report; the user accepts
   or requests fixes (the in-session equivalent of OpenWiki's PR gate).
5. **Engine (finalize)** on acceptance — injects the pointer and records state:
   ```bash
   bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
     "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
     finalize --command init [--json]
   ```
   `finalize` exits **2** if a target `CLAUDE.md`/`AGENTS.md` has malformed
   AI-memory markers — it refuses that file's pointer write (writing nothing to
   it) but still records run-state. Detect a refusal via the `pointer_files_refused`
   field in `--json`, not the exit code alone (argparse also uses 2).

### `update` — incremental maintenance

1. **Engine (prep):** `aim_wiki.py update [--json]` — reads state, computes the
   git-diff since the recorded `gitHead` (+ uncommitted), and flags whether the
   wiki was edited since the last record.
2. **You (author):** build a docs-impact plan (changed source → page → edit → why).
   **Edit surgically** — prefer replacing one stale sentence over adding
   paragraphs; do not reformat or refresh accurate pages. A **no-op is valid**: if
   nothing relevant changed, say the wiki is already current and stop. Soft budget:
   <5 changed source files → touch ≤1–2 pages. Also refresh the `## Project Wiki`
   pointer only if it is missing or stale.
3. **Verify** → **review gate** → `finalize --command update`.

### `status` — freshness only (no writes)

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  status [--json]
```
Reports last `updatedAt`, recorded `gitHead`, source changes since last run, and
whether the wiki was edited since the last record. Never writes.

## Verify — correctness

After authoring/refreshing, run the verifier manifest:
```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-wiki/scripts/aim_wiki.py" \
  verify [--json]
```
The engine extracts every inline source citation from the wiki pages and checks
each cited path exists (a deterministic dead-citation precheck — dead paths are
immediate drift; fix them). Then **dispatch a read-only verifier subagent** (via
the `Task` tool, read-only) with the manifest: it cross-checks that each page's
**claims** match the cited source — a claim can cite a real file yet misdescribe
it. It inspects and reports only; it does not edit. One pass, not a multi-round
loop. Surface all discrepancies (dead citations + ungrounded/drifted claims) in
the review gate before acceptance.

## Scope & invariants

- **In-session only** (v1). Multi-project: the wiki is written **only** under the
  resolved project's `wiki/` — no cross-project bleed.
- **Deterministic work stays in the engine**; authoring/reasoning stays with you.
  No provider config, no keys, no deepagents.
- **Writes** are confined to `wiki/` plus the top-level `CLAUDE.md`/`AGENTS.md`
  pointer section (owned by `finalize`). Never edit source outside these.
- **Known v1 limitation**: source-drift excludes the *whole* top-level
  `CLAUDE.md`/`AGENTS.md`, not just the injected pointer section — unrelated edits
  to those files don't register as drift. Pointer-section-scoped drift is a v2 refinement.
- **Deferred seams** (designed-for, not built in v1): memory-store integration of
  wiki pages, headless/CI mode + GitHub Action, and `aim-sot` doc-drift
  composition. Do not build these here.
