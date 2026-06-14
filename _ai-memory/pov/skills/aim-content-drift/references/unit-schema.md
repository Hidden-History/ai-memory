# The sanctum unit schema + the fingerprint sidecar

Source of truth: BP-173 (content-drift detect/recommend-with-rationale) and the
sanctum templates shipped by `aim-agent-sanctum-init`. Loaded on demand — keep
SKILL.md lean.

## Reference-owned units

The reference owns a set of **anchored, fingerprintable units** (BP-173 §3). For the
sanctum family a **unit is a `##` section** of a template: its id is the slug of the
heading text (`## System Architecture` → `system-architecture`), and its content is
every line after the heading up to the next `##`/`#` heading. `###` subsections and
their prose belong to the parent `##` unit. The lone `#` title, frontmatter, blank
lines, and thematic breaks (`---`) are structural — not units, not content.

The 8 sanctum files and their templates (DEC-PM333-D7 #2 — v1 covers these only):

| Operator file | Reference template | Reference-owned `##` units |
|---|---|---|
| `BOND.md` | `BOND-template.md` | Owner · Working Style · Things They've Asked Me to Remember · Things to Avoid · Trust Boundaries |
| `CAPABILITIES.md` | `CAPABILITIES-template.md` | Built-in Workflows · Learned Capabilities · How to Add a Capability · Tools |
| `CREED.md` | `CREED-template.md` | Mission · Core Values · Standing Orders · Boundaries · Anti-Patterns |
| `INDEX.md` | `INDEX-template.md` | Standard Files · Session Logs · Capabilities Library · References Library · My Files |
| `LORE.md` | `LORE-template.md` | Bootstrapping … · System Architecture · Key Design Decisions · Patterns & Conventions · Things Learned the Hard Way |
| `MEMORY.md` | `MEMORY-template.md` | Curation Rule · Recent Sessions · Pending Items · Insights to Carry |
| `PERSONA.md` | `PERSONA-template.md` | Identity · Communication Style · Traits & Quirks · Evolution Log |
| `PULSE.md` | `PULSE-template.md` | On Quiet Rebirth · Quiet Hours · State |

## The fingerprint sidecar

DEC-PM333-D3: fingerprints ship as a **sidecar** beside each template,
`<NAME>-template.fingerprints.json`. It is generated from the template (never edited
by hand) and versions with it:

```
python3 scripts/content_drift.py <assets-dir> --emit-fingerprints
```

Shape (one entry per `##` unit):

```json
{
  "template": "LORE-template.md",
  "reference_version": "sha256:…",        // hash of the whole template (file-level change signal)
  "units": [
    {
      "id": "system-architecture",
      "heading": "## System Architecture",
      "guidance": "…canonical reference content for the unit…",
      "fingerprint": "sha256:…",          // hash of the canonical guidance (ack re-surface key)
      "prior": { "sha256:…": "…older guidance text…" },   // for SUPERSEDED detection
      "status": "current",                // or "orphan" once removed from the template
      "severity": null                    // null → per-class default (see classification-rule.md)
    }
  ]
}
```

On first generation every unit is `status: "current"` with no `prior` and no orphans
— drift only appears as the templates evolve. When a template changes, re-running
`--emit-fingerprints` rolls the previous `fingerprint` into `prior` (and flags a
removed unit `orphan`) so the older operator content becomes detectable as SUPERSEDED
/ ORPHAN.

## Canonicalization

A unit's content is whitespace-normalized (blank lines and thematic breaks dropped,
internal whitespace collapsed) so cosmetic reflow is not drift. A template
`{placeholder}` (e.g. `{user_name}`) matches any resolved value: the reference owns
the framing *around* the placeholder, not the operator's value inside it.
