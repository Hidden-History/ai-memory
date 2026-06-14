# The drift classification rule (BP-173 §3)

The load-bearing decision in content drift. It distinguishes **stale** (the reference
moved on; the operator should update) from **customized** (the operator's own content;
must never be clobbered). "Bytes differ from the template = drift" is the explicit
**anti-pattern** — it would recommend deleting every operator customization. The
classifier anchors on the reference's fingerprintable units, not on byte difference.

## The rule

For each **reference-owned unit** (a `##` section in the sidecar):

| Condition | Class | Action |
|-----------|-------|--------|
| Operator file lacks the unit's heading (current unit) | **MISSING** | recommend ADD + rationale |
| Operator section still contains the **current** reference framing | **MATCH** | none |
| Operator section contains a **prior** reference framing (not the current) | **SUPERSEDED** | recommend UPDATE (diff + why) |
| Operator section replaced the reference framing with its own content | **CUSTOMIZED** | **none — never recommend removal** |
| Unit removed from the reference (`orphan`); operator section is a pristine, uncustomized remnant | **ORPHAN** | recommend REMOVE + rationale |
| Unit removed from the reference (`orphan`); operator added any content | **CUSTOMIZED** | **none — never recommend removal** |

## The anti-clobber guarantee (the cardinal rule)

**CUSTOMIZED operator content is never recommended for removal.** This is enforced
*structurally*, not by a heuristic:

- Classification iterates **reference-owned unit ids only**. A section the operator
  authored (a heading not in the sidecar) is never in the iteration, so it can never
  be surfaced for removal.
- An **ORPHAN → REMOVE** is recommended only when the operator's section is a
  *pristine scaffold remnant* — its content `fullmatch`es the orphaned reference
  guidance with nothing added. The moment the operator has added any content, the
  section is CUSTOMIZED and is kept. Keep-when-uncertain: any ambiguity falls to
  CUSTOMIZED (no action), never to a remove recommendation.

## Acknowledgement (BP-173 §4 — ESLint bulk-suppressions model)

A recommendation the operator has seen and intentionally kept is acknowledged in a
committed, per-project ack sidecar, keyed by `FILE::unit-id` and stamped with the
**reference fingerprint at ack time**:

- An ack **suppresses** the recommendation while the reference unit's current
  fingerprint equals the acked fingerprint.
- It **re-surfaces only when the reference unit changes** (the current fingerprint no
  longer matches the acked one) — the conservative "any reference change re-surfaces"
  rule.
- `--prune-ack` drops entries whose unit no longer drifts, keeping the ack file honest.

The ack sidecar carries the resolved `project_id`; an ack file scoped to a different
project is ignored (no cross-project leak) and never overwritten.

## Severity ranking (BP-173 §5)

Recommendations are batched and ranked HIGH-first. Defaults by class (a sidecar unit
may override its own `severity`):

| Class | Default severity | Why |
|-------|------------------|-----|
| SUPERSEDED | HIGH | the operator is acting on stale framing — most misleading |
| MISSING | MEDIUM | a gap in coverage |
| ORPHAN | LOW | cosmetic; the content is merely no longer owned |
