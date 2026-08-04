# C4 Wiring — Design & Reconciliation (PLAN-035 P2 Phase B, Lane C)

**Author:** Winston (architect, teammate `arch-wiring`) · **Branch:** `plan035-p2b-wiring`
**Inputs:** frozen registry `oversight/tasks/pm408-p2-phasea/oversight-templates.frozen.yaml`;
existing wiring SoT `_ai-memory/_memory/parzival-sidecar/oversight-schema.yaml` (extended);
POV tree `_ai-memory/pov/`; PLAN-035 §3a (C4), §5 (Done-When).
**Gate:** schema edit is a source-repo shipping artifact → Parzival proposed-diff review at reconcile.

C4 is CI-blocking, source-repo only (users never see it). It has **two directions**:

- **(a) consumer resolution** — every registry `consumed_by:` value names a real shipped consumer.
- **(b) reference resolution** — every POV reference to an `oversight/` target that AI-Memory
  ships resolves; a reference to an oversight area AI-Memory does **not** ship a template for is
  **UNBACKED** (wiring direction only, per DEC-PM409-D2).

The registry→disk direction (a declared `target`/`glob` missing on disk) is a **separate token,
`MISSING_TARGET`, owned by the oracle — out of scope here** (DEC-PM409-D2).

---

## Deliverable 1 — schema extension (DONE, committed)

`consumed_by` needs a resolvable target. The existing wiring SoT
(`oversight-schema.yaml`) had **no consumer concept** — only a directory→files listing.
DEC-PM406-D3 forbids a second parallel system, so the fix is **additive, in that same file**:

Added one top-level `consumers:` block (sibling to `directories:`) — the single vocabulary of
valid consumer identifiers:

```yaml
consumers:
  aim-tracking-rotate:      { kind: skill, path: pov/skills/aim-tracking-rotate,      reads: "…" }
  aim-tracking-freshness:   { kind: skill, path: pov/skills/aim-tracking-freshness,   reads: "…" }
```

**Node/edge split (this is what makes it ONE SoT, not two):**
- **Nodes** (the set of legal consumers) live in `oversight-schema.yaml → consumers:`.
- **Edges** (which file is consumed by which consumer) live in the registry as per-template
  `consumed_by:` lists.
- C4(a) = every edge's value resolves to a node. No consumer list is duplicated across the two
  files; they compose.

**`consumer` definition (documented in the schema):** a shipped POV skill/workflow that
programmatically **reads or rewrites an oversight file's structure or lifecycle** (caps/rotates,
scans, regenerates an index) — **not** a skill that merely displays a file's text for context.
Rationale + the open question this definition settles: see **§ Decision needed** below.

**Vocabulary is exactly the two lifecycle skills** because those are the only values the frozen
registry's `consumed_by` lists reference today — so schema and registry reconcile with **zero
dangling edges**. Both are real shipped skills (`pov/skills/aim-tracking-{rotate,freshness}/`).

> **Companion change required (not done — flagged):** `oversight-schema.yaml` is a build-hashed
> reference artifact. Editing it stales its sha256 in `_ai-memory/_config/files-manifest.csv:12`.
> - old hash `3dce831567c2d18eec402970a1c25e6e6f4db6ae93a35199a4b2c3cccf5580e7`
> - new hash `50fc6edd7c0d2120c9ec2b10f9e9fed7f761460bb49c2e6152db46fa66f210aa`
> No in-repo generator/verifier references `files-manifest.csv` by name (install.sh's manifest
> logic is the separate BP-188 template-drift manifest), so it appears **build-generated**.
> At reconcile: regenerate `files-manifest.csv`, or hand-patch line 12 to the new hash.

---

## Deliverable 2 — `consumed_by` patch spec

Reconciled every registry `consumed_by` value against (1) the extended schema vocabulary and
(2) the **verified** consumption behavior of each skill. Ground truth for behavior:
- rotate → its own `FALLBACK_REGISTRY` Contract table (`tracking_rotate.py:26-71`) + `FRESHNESS_OWNED` exclusion set (`:79`).
- freshness → its `FRESHNESS_OWNED` set + literal scan targets (`bugs/INDEX.md`, `tech-debt/INDEX.md`, `decision-log.md`, phantom sidecar).

### 2.1 — C4(a) resolvability: **0 blocking corrections**

Every value currently in the registry (`aim-tracking-rotate`, `aim-tracking-freshness`) names a
valid node in the extended schema. **C4(a) passes as-is.** No rename/unknown-consumer corrections.

### 2.2 — Edge-accuracy corrections (map fidelity — recommended, non-blocking)

The registry's declared edges are **incomplete and carry one false edge** vs. what the skills
actually do. These are quality corrections for Parzival to apply at reconcile; they do not block
C4(a) (a resolvable-but-incomplete map still passes resolution).

| # | Action | Template `target` | Edge | Evidence |
|---|--------|-------------------|------|----------|
| 1 | **REMOVE** | `oversight/project-status.md` | `aim-tracking-freshness` | freshness has **no** reference to project-status (any casing) anywhere in its skill dir; it scans only bugs/INDEX, tech-debt/INDEX, decision-log, phantom sidecar. rotate keeps it (heartbeat Contract, `tracking_rotate.py:27`). |
| 2 | **ADD** | `oversight/SESSION_WORK_INDEX.md` | `aim-tracking-rotate` | rotate Contract `SESSION_WORK_INDEX.md` (rotatable, `:28`). |
| 3 | **ADD** | `oversight/tracking/task-tracker.md` | `aim-tracking-rotate` | rotate Contract `tracking/task-tracker.md` (`:36`). |
| 4 | **ADD** | `oversight/tracking/blockers-log.md` | `aim-tracking-rotate` | rotate Contract `tracking/blockers-log.md` (`:37`). |
| 5 | **ADD** | `oversight/tracking/risk-register.md` | `aim-tracking-rotate` | rotate Contract `tracking/risk-register.md` (`:44`). |
| 6 | **ADD** | `oversight/tracking/technical-debt.md` | `aim-tracking-rotate` | rotate Contract `tracking/technical-debt.md` (`:59`). |
| 7 | **ADD** | `oversight/session-index/INDEX.md` | `aim-tracking-rotate` | rotate Contract `session-index/INDEX.md` (`:66`). |

Edges that are **already correct** (no change): `decision-log.md → [rotate, freshness]`;
`tech-debt/INDEX.md → [freshness]` (rotate correctly excluded — it is `FRESHNESS_OWNED`).

> Corrections 2–7 depend on the `consumer` definition below. Under the recommended
> **lifecycle-processor** definition they are correct and complete. Under a **broad any-reader**
> definition, many more edges (loader, model-dispatch) would also be required — see § Decision.

### 2.3 — Registry-completeness gap surfaced (NOT a consumed_by edit — for oracle/registry owner)

`aim-tracking-freshness` **regenerates `oversight/bugs/INDEX.md`** (`FRESHNESS_OWNED`,
`tracking_freshness.py`), but **the registry ships no template for `oversight/bugs/INDEX.md`**
(`bugs/` ships only the `BUG-*.md` family). There is no template to attach a `consumed_by` to.
This is a registry-completeness finding (a real shipped generated singleton with no template),
owned by the oracle's `MISSING_TARGET`/`ORPHAN` logic or a new template — **not** Lane C's to fix.
(Note: it is **not** UNBACKED under the rule in D3, because `oversight/bugs/` is a backed dir.)

---

## Deliverable 3 — C4 design (for Lane D / Wave 2 to implement)

### 3.1 — Direction (a): consumer resolution

```
for each registry template T with a consumed_by list:
    for each value v in T.consumed_by:
        if v not in oversight-schema.yaml::consumers:  -> C4 FAIL "unknown consumer: {v} (in {T.target})"
```
Empty/absent `consumed_by` is legal (most templates). Today: **PASS** (both values resolve).

### 3.2 — Direction (b): reference resolution + `UNBACKED`

**Reference surface = the ENTIRE `_ai-memory/pov/` tree** (skills, references, workflows,
scripts, knowledge, constraints, assets) — **not** `pov/workflows/` alone.

> **This is the single most important design decision, and it contradicts the literal wording of
> §5 / the brief** ("POV *workflows* reference…"). The 5 anchor gaps do **not** appear in
> `pov/workflows/` at all — they live in `pov/skills/` and `pov/references/`. Scoping the surface
> to `workflows/` would flag **zero** of the 5 required gaps and C4 would be vacuously green.
> Verified: a full-tree grep places tasks-refs in `aim-parzival-loader`, reports-refs in
> `aim-tracking-freshness` + `auto-memory-best-practices.md`. **The surface must be the whole POV
> tree.** (Flagged to Parzival — see Frictions.)

**Extraction (per source file under `pov/`):**
1. Regex every path token matching `oversight/[A-Za-z0-9_.*/-]+`.
2. Normalize each to its **resolution key** at **top-level-subdirectory granularity**:
   - root-level singleton form `oversight/<file>` (e.g. `oversight/project-status.md`) → key = that exact path;
   - any deeper path `oversight/<dir>/…` → key = `oversight/<dir>/` (first segment only).
3. Dedup to **(source_file, key)** edges (multiple hits of the same key in one file = one edge).

**Resolution against the registry:**
```
BACKED(key) :=
    key is `oversight/<file>`  and  some registry template has target == key           (root singleton)
 OR key is `oversight/<dir>/`  and  some registry template's target|glob starts with key (dir has ≥1 shipped template)
UNBACKED edge  <=>  not BACKED(key)
```

**Why top-level-subdirectory granularity (not per-file):** it is the granularity that reproduces
the §5 acceptance anchor *exactly*. `tasks/` and `reports/` are whole unshipped directories; the
anchor names them at directory level and is silent on `bugs/INDEX.md` (a per-file gap that
file-granularity *would* flag). Directory granularity keeps backed dirs (`bugs/`, `plans/`,
`tracking/`, `verification/`, `knowledge/`, `session-logs/`, `tech-debt/`) green while flagging
only areas AI-Memory ships nothing into. It also matches the native granularity of the wiring SoT
(`oversight-schema.yaml` lists directories).

### 3.3 — Deterministic `UNBACKED` output on TODAY's tree

Running the rule over the current worktree yields **exactly these edges**:

| key | UNBACKED? | referencing files (deduped) | count |
|-----|-----------|------------------------------|-------|
| `oversight/tasks/`   | **YES** | `pov/skills/aim-parzival-loader/SKILL.md`, `pov/skills/aim-parzival-loader/loader_common.py` | **2** |
| `oversight/reports/` | **YES** | `pov/references/auto-memory-best-practices.md`, `pov/skills/aim-tracking-freshness/references/extended-checks.md`, `pov/skills/aim-tracking-freshness/scripts/tracking_freshness.py` | **3** |
| `oversight/archive/` | **YES** | `pov/knowledge/document-maintenance.md` (line 121, an `Example:` in prose) | 1 |

- **`tasks/`×2 + `reports/`×3 = the 5 anchor gaps (§5) — flagged. Acceptance MET.**
- **`archive/`×1 is a 6th gap the same rule surfaces** (see § Boundary case).

All other POV `oversight/` references resolve to backed keys and are **not** flagged
(`SESSION_WORK_INDEX.md`, `project-status.md`, `tracking/`, `bugs/`, `plans/`, `knowledge/`,
`verification/`, `tech-debt/`, `session-logs/`).

### 3.4 — Acceptance fixture (recommended for Lane D)

Assert the UNBACKED set **⊇ {`oversight/tasks/`, `oversight/reports/`}** with the reference
multiplicities **tasks = 2, reports = 3** (§5 anchor). Use **subset (`⊇`), not exact-set**, so the
legitimately-surfaced `archive/` finding does not fail the fixture. Pin the three referencing
files per key (above) so a future refactor that moves/removes a reference is caught.

### 3.5 — Boundary case: `oversight/archive/` (decision for Parzival/Lane D)

The same extraction that produces the 5 anchor gaps also produces `oversight/archive/` from an
`Example:` line in `document-maintenance.md`. Suppressing it would require special-casing prose
lines — but the anchor's own `reports/` set **includes** a prose bullet
(`auto-memory-best-practices.md:21` "lives in oversight/reports/"), so prose references are
in-scope by the anchor's own construction. **Recommendation: keep `archive/` as a true UNBACKED
finding.** Triage (Parzival): either correct the stale doc example, or ship an archive
convention/template. Do **not** silently drop it — that reintroduces exactly the "rule the system
states and cannot check" failure this plan exists to eliminate.

### 3.6 — Scope guards (so C4 stays source-repo only + noise-free)

- **Source-repo only.** C4 runs against the shipped `pov/` + registry in the AI-Memory source
  tree; it never runs against a user project (users never see it). No user-tree paths enter the
  surface. (This is why `oversight/tasks/**` — the maintainer's scratch dir — must never be in a
  shipped artifact: PLAN-035 §3a.)
- **Ignore `oversight/.` and bare `oversight/`** — punctuation/regex artifacts, not references
  (e.g. `tracking_freshness.py:1970` "…that contains oversight/.").
- **Binary/asset files** (`*.json` fingerprints) contribute references only if they contain
  literal `oversight/…` path tokens; today one asset references `SESSION_WORK_INDEX.md` (backed) —
  harmless. No special handling needed.

---

## § Decision needed (Parzival owns — registry/wiring semantics)

**What counts as a `consumer`?** Verified: `project-status.md` and `SESSION_WORK_INDEX.md` are
referenced not only by the two lifecycle skills but also by **`aim-parzival-loader`**
(reads them for session-start context) and **`aim-model-dispatch`**. Two defensible definitions:

- **(Recommended) Lifecycle-processor** — a consumer programmatically caps/rotates/scans/indexes
  the file's *structure*. Vocabulary = `{rotate, freshness}`. Matches Phase A's de-facto choice,
  keeps C4 focused on **hard structural dependencies** (what breaks if a template's contract
  changes), and keeps the wiring graph small. Patch spec §2.2 is complete under this reading.
- **Broad any-reader** — any shipped skill/workflow that reads or writes the file. Vocabulary must
  then add `aim-parzival-loader` (+ likely `aim-model-dispatch`), and many ADD edges follow. More
  complete, but larger, and each edge needs per-skill verification.

I recommend **lifecycle-processor**. This changes only the *definition* documented in the schema
(already written that way) and the size of §2.2 — not the C4 mechanism. Flagging because it is a
semantic boundary that changes the gate's strictness; it is Parzival's call, not mine to fix by fiat.

---

## Done-When (this lane)

- [x] Schema carries consumers without a parallel system (node/edge split; additive `consumers:` block).
- [x] `consumed_by` patch spec complete: 0 C4(a)-blocking corrections; 7 edge-accuracy corrections (1 REMOVE, 6 ADD), all evidence-cited; 1 registry-completeness gap surfaced.
- [x] C4 design implementable by Lane D, including the exact `UNBACKED` rule that flags the 5 known live gaps (tasks/ ×2 + reports/ ×3), with deterministic today-tree output and an acceptance fixture.
