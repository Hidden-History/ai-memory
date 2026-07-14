# 🔍 Sanctum Content-Drift Detection

Detect when your operator-scaffolded sanctum files have drifted from the evolving reference templates — and surface recommended additions, updates, or removals with rationale. Your content is never automatically changed.

---

## Overview

When you first initialise a sanctum for a Claude Code agent, the `aim-agent-sanctum-init` skill scaffolds eight files from reference templates:

| File | Purpose |
|------|---------|
| `BOND.md` | Relationship framing and working agreements |
| `CAPABILITIES.md` | Declared agent capabilities |
| `CREED.md` | Operating principles and values |
| `INDEX.md` | Directory of sanctum contents |
| `LORE.md` | Project knowledge and architecture |
| `MEMORY.md` | Persistent notes and learnings |
| `PERSONA.md` | Agent identity and communication style |
| `PULSE.md` | Health signals and operational status |

Over time the reference templates evolve — new guidance sections are added, outdated framing is revised, and obsolete sections are retired. Your scaffolded files stay as you left them. **Content drift** is the gap between what your sanctum files say and what the current templates recommend.

The `aim-content-drift` skill detects this gap deterministically (anchored fingerprints, unit-by-unit comparison) and surfaces batched, severity-ranked recommendations with rationale. It is **read-only for sanctum content** in v1 — nothing changes until you choose.

For the precise mechanics (unit parsing, fingerprint comparison, classification, ack bookkeeping), see the skill's own reference: `_ai-memory/pov/skills/aim-content-drift/SKILL.md`.

---

## When to Run

Run `/aim-content-drift` when:

- **Session start** — quick drift check before beginning significant work in a new session.
- **After template updates** — the reference templates ship with the module; after installing an update, check whether your sanctum has fallen behind.
- **On operator request** — whenever you want to know if your sanctum is current with the standard.

---

## Drift Classes

Every recommendation belongs to one of three actionable classes. Two classification results — **MATCH** (current, no action) and **CUSTOMIZED** (operator-authored, protected) — produce no finding.

### MISSING · severity MEDIUM

**What it means:** A section that exists in the current reference template is absent from your sanctum file. This is a gap — you are not getting the guidance that section provides.

**Operator action:** Review the reference framing (shown with `--show-diff`) and add the section to your sanctum file if it applies to your use case.

---

### SUPERSEDED · severity HIGH

**What it means:** Your sanctum file contains a section whose framing matches an *older* version of the reference. The template has since updated it with new or corrected guidance, but your file still reflects the prior framing.

This is the highest-severity class because you may be relying on stale guidance — following advice the template has since revised.

**Operator action:** Review the current reference framing alongside your existing section. Update your file to incorporate the new guidance, keeping any operator-added content you wish to preserve.

---

### ORPHAN · severity LOW

**What it means:** A section that was once in the reference template has since been removed from it. Your sanctum file still contains this section, and it looks like the original unmodified scaffold text — suggesting you may not have added your own content to it.

**Operator action:** Consider removing the section if it was never customised. If you have come to rely on it for your own purposes, keep it — that is a valid choice and the skill will respect it (see [The Anti-Clobber Guarantee](#the-anti-clobber-guarantee) and [Known Limitation](#known-v1-limitation-orphan-heuristic) below).

---

## The Anti-Clobber Guarantee

**Operator content is never recommended for removal.**

The classification logic iterates over *reference-owned unit IDs only*. Content you have authored — sections you added yourself, or sections where you replaced the reference framing with your own writing — is structurally invisible to the remove path. The guarantee is enforced by design, not by a runtime check.

Specifically:

- **MISSING** and **SUPERSEDED** only fire for sections the *reference* owns and tracks. If you have replaced the reference framing entirely, the section is classified **CUSTOMIZED** (kept, no finding).
- **ORPHAN** fires only when your section's content is a *pristine scaffold remnant* — the reference framing with each `{placeholder}` resolved to a short value such as a name or date, and nothing else added. If you have added any operator prose, the section is **CUSTOMIZED** (kept, no finding).
- The only files the skill writes are its own per-project ack sidecar (see [Acknowledging Intentional Divergence](#acknowledging-intentional-divergence)). Sanctum files and templates are never touched.

---

## Acknowledging Intentional Divergence

Sometimes a recommendation is correct — the reference changed — but the divergence is intentional. You want to keep your sanctum as-is and stop being reminded about it. That is what `--ack` is for.

### How acks work

An ack entry suppresses a specific recommendation until the *reference unit itself changes again*. It is keyed to the current reference fingerprint, so if the template is later updated and the unit drifts again, the recommendation re-surfaces automatically.

Ack entries are stored in a per-project sidecar file `content-drift-ack.json` located alongside the sanctum dir under your project's `_ai-memory/` directory. The file is designed to be committed and reviewed in diffs (the ESLint bulk-suppressions model).

### The ack workflow

**Step 1 — Detect drift:**

```bash
# Default: severity-ranked count + pointer (index-not-log)
python3 scripts/content_drift.py <sanctum-path>

# Add --show-diff to preview the full recommended change for each finding
python3 scripts/content_drift.py <sanctum-path> --show-diff
```

Output looks like:

```
content drift: 2 recommendation(s) (HIGH 1 · MEDIUM 1 · LOW 0)

  [HIGH] SUPERSEDED  LORE.md → ## System Architecture
    Your 'System Architecture' section matches an earlier version of the reference
    framing; the template has since updated it. Review the change.
    ack with: --ack LORE.md::system-architecture

  [MEDIUM] MISSING  CREED.md → ## Conflict Resolution
    The reference template added the 'Conflict Resolution' section; your CREED.md
    does not have it. Consider adding it.
    ack with: --ack CREED.md::conflict-resolution

  (re-run with --show-diff to preview each change)

  Nothing changes until you choose. v1 is detect + acknowledge only.
```

**Step 2 — Acknowledge a unit you are intentionally keeping as-is:**

```bash
python3 scripts/content_drift.py <sanctum-path> --ack LORE.md::system-architecture
```

The ack key format is `<filename>::<unit-slug>` — the skill prints the exact key in each recommendation's output.

Multiple units can be acked in one command by repeating the flag:

```bash
python3 scripts/content_drift.py <sanctum-path> \
  --ack LORE.md::system-architecture \
  --ack CREED.md::conflict-resolution
```

**Step 3 — Verify:**

```bash
python3 scripts/content_drift.py <sanctum-path>
```

Acknowledged units no longer appear. A sanctum with no outstanding recommendations reports:

```
content drift: 0 recommendation(s) (HIGH 0 · MEDIUM 0 · LOW 0)
  no action recommended — your sanctum is current.
```

### Pruning stale acks

When a reference unit no longer drifts (because you updated your sanctum to match), its ack entry is no longer needed. Run `--prune-ack` to drop these stale entries and keep the ack file clean:

```bash
python3 scripts/content_drift.py <sanctum-path> --prune-ack
```

---

## Known v1 Limitation: ORPHAN Heuristic

The **ORPHAN** class — the only one that recommends *removing* a section — relies on a bounded heuristic to determine whether a section is a "pristine scaffold remnant".

The test checks whether your section's content is exactly the original reference framing, with each `{placeholder}` resolved to a short, value-shaped fill (a name, a date, a language — up to five sub-tokens). If the fill fits this pattern and nothing else was added, the section is treated as pristine and the ORPHAN recommendation fires.

**The known edge case:** A short fill that happens to look like a simple value (e.g. a one-word entry where a name was expected) can make a section read as pristine even if you intended that fill as operator content. When this happens the skill will suggest you consider removing the section.

This is safe by design:
- Detection is read-only — no automatic edit can result from a false ORPHAN.
- The recommendation is phrased as a suggestion ("if that is right, you may remove it"), not a directive.
- If you have genuinely customised the section — added your own prose, used a longer fill, or used punctuation-joined phrasing — the section classifies as **CUSTOMIZED** (kept, no finding). The heuristic's bias is always toward *keeping* content when ambiguous.

A confirming `--apply` path, which would carry a stricter pre-apply check, is deferred to v1.1.

---

## `--apply` Deferred to v1.1

v1 of `aim-content-drift` is **detect + acknowledge only**. There is no `--apply` flag.

Applying a recommendation is always an operator-performed manual edit to the sanctum file. This is intentional — the operator reviews the proposed change, decides what to keep from their own content, and applies it by hand. An automated apply path is planned for v1.1 with an explicit pre-apply gate.

---

## CLI Reference

All flags verified against `scripts/content_drift.py`:

| Flag | Description |
|------|-------------|
| `<sanctum-path>` | Path to the sanctum directory (required) |
| `--show-diff` | Show the full previewable diff for each recommendation (default: count + pointer) |
| `--ack FILE::unit-id` | Acknowledge an intentional divergence; writes the per-project ack sidecar. Repeatable. |
| `--prune-ack` | Drop ack entries whose unit no longer drifts; writes the ack sidecar. |
| `--group-id ID` | Explicit project scope (group\_id). Resolved automatically when omitted. |
| `--fingerprints-dir PATH` | Override the reference fingerprint sidecars location (default: runtime sanctum-init assets dir). |
| `--ack-file PATH` | Override the ack sidecar path (default: `<project-root>/_ai-memory/content-drift-ack.json`). |
| `--emit-fingerprints` | **Maintenance only.** Regenerate `*.fingerprints.json` sidecars from `*-template.md` files in `<path>`. Reads templates; never modifies them. |

---

## See Also

- [`_ai-memory/pov/skills/aim-content-drift/SKILL.md`](../_ai-memory/pov/skills/aim-content-drift/SKILL.md) — deterministic mechanics: unit parsing, fingerprint schema, classification rule, ack bookkeeping
- [AI_MEMORY_ARCHITECTURE.md](AI_MEMORY_ARCHITECTURE.md) — overall system architecture
