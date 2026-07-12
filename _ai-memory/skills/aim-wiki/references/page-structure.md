# Wiki page structure & quality rules

Authoring discipline for the pages `aim-wiki` produces under `wiki/`. Concepts
adapted from OpenWiki's system prompt (`prompt.ts:98-127`, MIT — paraphrased).
The engine scaffolds and records; **you** (the in-session agent) author
to these rules.

## Entrypoint

- `wiki/quickstart.md` is the required entrypoint and must exist.
- It carries a high-level repository overview and links to **every** major section
  page. A reader with zero knowledge of the repo starts here and learns what the
  project is, how it is organized, what it does, and where to go next.

## Page count & scope

- **init**: at most ~8 pages on the first run unless the repo is clearly tiny.
  Keep the initial set focused — quickstart plus the smallest set of section pages
  that explains the repo clearly. A strong first pass, then stop; later `update`
  runs refine.
- **Small repos** (~10 or fewer primary source files): prefer `quickstart.md`
  plus at most 1–2 supporting pages. Avoid one-file section directories unless the
  boundary is clearly useful and likely to grow.

## Section directories

- Create a directory only when it represents a real documentation area.
- A section directory should usually hold multiple substantive pages. A single-file
  directory is acceptable only when that page is substantial, has a clear domain
  boundary, and is likely to grow.
- Prefer headings inside a broader page before creating many small directories.
- Typical names when the repo is large enough to need them: `architecture/`,
  `workflows/`, `domain/`, `api/`, `data-models/`, `operations/`, `integrations/`,
  `testing/` — or names that fit the repo.

## No thin pages

- Avoid stub pages. If a page would mostly be a stub, source map, or short note,
  merge it into `quickstart.md` or a broader section page instead.
- Every page must give real explanatory value: what the area does, why it exists,
  where to start, what to watch out for, and key source references.
- Before finishing a run, review the `wiki/` tree and merge, move, or remove
  low-value single-file directories and stub pages.

## One canonical home per concept

- Give each concept a single canonical page; link to it from elsewhere rather than
  repeating the explanation. Keeps the wiki concise enough to maintain.

## Grounding (correctness)

- **Do not invent** files, modules, APIs, business rules, or behavior. Ground every
  important claim in source, existing docs, or git evidence you have inspected.
- Include inline source references (e.g. `` `src/app.py` `` or a link to the file)
  where they help a reader verify or continue exploring. These citations are what
  the `verify` manifest and the read-only verifier subagent check.
- **Citations must be full paths** — repo-root-relative (`` `src/app.py` ``) or a
  valid page-relative link (`` [readme](../README.md) ``) — **never a bare
  filename** (`` `app.py` ``). The verifier only resolves those two forms; a bare
  basename cannot be matched to a real file and will show as a dead citation even
  when the file exists elsewhere in the repo.
- Prefer current source over stale docs. If existing docs conflict with the code or
  git history, flag the likely-stale doc and prefer the source evidence.
- Explain **why** important code exists, not only what files contain. Use git
  history for the "why"; do not paste persistent commit-hash lists into pages
  unless a specific historical decision matters.

## Security & privacy

- Never read or document secret values, credentials, keys, tokens, or `.env` files.
  `.env.example` / sample config may be read only if it holds placeholders.
- Document only that such configuration exists and where non-sensitive setup lives.

## Scope of writes

- Keep all documentation under `wiki/`.
- The only files outside `wiki/` the flow ever touches are the top-level `CLAUDE.md`
  / `AGENTS.md` pointer section — and the engine's `finalize` step owns that write,
  not free-hand editing.

## Temporary plan file

- After discovery and before authoring, write `wiki/_plan.md`: intended pages,
  source evidence per page, and open questions.
- **Delete `wiki/_plan.md` before finishing.** It is excluded from the content hash
  but must not ship in the final wiki.
