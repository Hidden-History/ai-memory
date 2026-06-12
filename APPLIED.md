# P3-3a Applied — Sanctum Template Content-Model Corrections

Source of truth: `oversight/tasks/pm330-p3-3a-sanctum-content-audit/reports/MANIFEST-verified.md`.
Applied the Will-approved subset only: **C-01..C-11 + D-01..D-03 (14 items)**. D-04..D-13 NOT applied.

All template paths relative to `_ai-memory/pov/skills/aim-agent-sanctum-init/`.

| Item | File | Section changed |
|------|------|-----------------|
| C-01 | `assets/CAPABILITIES-template.md` | `## Built-in Workflows` — replaced 19-row table + trailing sentence with the canonical-`<menu>`-pointer paragraph. `## Learned Capabilities` table left byte-unchanged. |
| C-02 | `assets/CREED-template.md` | `## Anti-Patterns` — demoted the 9-entry catalog to `references/anti-patterns.md`; kept the 3 not-stated-elsewhere patterns inline behind a pointer. |
| C-03 | `assets/LORE-template.md` | `## Bootstrapping LORE for a New Project` — demoted read-list + distill paragraph to `references/lore-bootstrapping.md`; replaced in place with one-time pointer. |
| C-04 | `assets/MEMORY-template.md` | `## Curation Rule` 2nd paragraph — replaced procedure sentences with `aim-lore-hygiene` pointer; kept 1st paragraph + contract. |
| C-05 | `assets/PULSE-template.md` | `### 1. Memory Curation` — kept Goal sentence; replaced the 5 procedure bullets with `aim-lore-hygiene` pointer. |
| C-06 | `assets/PERSONA-template.md` | `## Communication Style` — "Write for Future Parzival" now references CREED Standing Order 10 as the rule's home, keeps the voice. |
| C-07 | `assets/LORE-template.md` | `# Lore` header italic — replaced with explicit semantic-memory-type framing. Existing footer left untouched. |
| C-08 | `assets/BOND-template.md` | Framing line inserted under `# Bond`, before intro. |
| C-09 | `assets/CREED-template.md` | Framing line inserted under `# Creed`, before `## Mission`. |
| C-10 | `assets/PERSONA-template.md` | Framing line inserted under `# Persona`, before `## Identity`. |
| C-11 | `assets/MEMORY-template.md` | `# Memory` header line sharpened to episodic/working-memory framing. |
| D-01 | `assets/BOND-template.md` | `## Trust Boundaries` — added CREED-cross-ref drift-insurance note. |
| D-02 | `assets/INDEX-template.md` | `## Standard Files` — MEMORY.md description "Working memory." → "Episodic + working-set memory." |
| D-03 | `assets/PERSONA-template.md` | `## Traits & Quirks` — collapsed "Confidence discipline." entry to a pointer to ## Communication Style. |

## New reference files created (the C-02 / C-03 demote targets)

- `references/anti-patterns.md` — full 9-entry CREED Anti-Patterns catalog, each entry's "Correct action:" guidance preserved verbatim.
- `references/lore-bootstrapping.md` — LORE bootstrapping 8-file read-list + distillation paragraph, preserved verbatim.

## Call-chain verification (`scripts/init-sanctum.py` `copy_references()`)

`copy_references()` copies every file in the skill's `references/` dir into `sanctum/references/`, skipping only `SKILL_ONLY_FILES` — which is an empty set. Both new reference files are therefore copied into the operator sanctum and are NOT excluded by any filter. The pointer path `references/<file>.md` resolves correctly from a sanctum file (`sanctum/CREED.md` → `sanctum/references/anti-patterns.md`). **No dangling pointer — PASS.**

## Addendum applied (Will-approved subset — D-04 / D-05 / D-06 / D-13)

Source of truth: `oversight/tasks/pm330-p3-3a-sanctum-content-audit/reports/MANIFEST-addendum-D.md`. Applied verbatim on top of `4ed0b95`.

| Item | File | Section changed |
|------|------|-----------------|
| D-04 | `assets/PERSONA-template.md` | `## Evolution Log` — inserted scope-guard italic line (identity-level changes only) between heading and table. |
| D-05 | `assets/PERSONA-template.md` | `## Traits & Quirks` — rephrased the 5 named entries (Scope-change radar, Parallel-dispatch instinct, File-citation discipline, Never-implements, Re-verification reflex) as dispositions pointing to their rule's home. "Confidence discipline." entry left unchanged (already D-03). |
| D-06 | `assets/CAPABILITIES-template.md` | `# Capabilities` — inserted procedural-registry framing italic line before the intro sentence. |
| D-13 | `assets/PULSE-template.md` | `### 2. Tracking Hygiene` — replaced 3 hard-coded `oversight/…` bullets with project-agnostic categories + AI-Memory example line; lead-in and self-guard closer unchanged. |

## Not applied (out of scope, deferred by Will)

D-07, D-08, D-09, D-10, D-11, D-12 — confirmed untouched by diff (only the named sections changed).
