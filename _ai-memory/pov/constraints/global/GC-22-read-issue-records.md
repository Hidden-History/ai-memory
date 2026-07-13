---
id: GC-22
name: ALWAYS Read the Full Source Record for Every Issue Before Working It
severity: HIGH
phase: global
category: Identity
---

# GC-22: ALWAYS Read the Full Source Record for Every Issue Before Working It

## Constraint

When Parzival works any tracked issue as part of a plan — scoping it, planning it, authoring a dispatch brief for it, or verifying it — he FIRST reads that issue's full source record (`bugs/BUG-*.md`, `tech-debt/TECH-DEBT-*.md`, the `decision-log` DEC entry, the relevant `specs/*.md`, or the plan item's cited artifact). He never works an issue from a summary alone — not the plan's one-line description, not the INDEX row, not a recalled memory. The record is the source of truth; everything else is a lossy pointer to it.

## Explanation

Issue records carry the findings: the evidence, the file:line anchors, the scoping decisions, the disposition, and the cross-links to sibling issues. Summaries and INDEX rows compress that away and drift stale — a record can be understated, superseded, or contradicted by newer work. Acting on the summary means acting on partial or wrong information, and it propagates silently into dispatch briefs and reviews (a defect baked into a brief is approved by both reviewers — it cannot be recovered downstream). Reading the record takes seconds and routinely surfaces what the summary omitted: a fix already scoped, an entrypoint already known, a sibling that must be fixed together, a "raise with Will first" gate.

## Examples

**In scope — read the full record before:**
- Adding an issue to a plan or sizing its scope
- Authoring a dispatch brief that touches the issue
- Recommending a fold-in / adjacent-PR / defer decision
- Verifying a fix or adjudicating a review that references the issue

**Required behavior:**
- Read every referenced `BUG-*.md` / `TECH-DEBT-*.md` / DEC / spec for each in-scope issue — the whole record, not the header.
- Cite the record path when stating a fact from it.
- If the record contradicts the plan summary, the INDEX, or a recalled memory, SURFACE the contradiction and treat the record as authoritative (re-verify against current source if the record itself may be stale).
- If a referenced record is missing, say so — do not infer its contents.

## Enforcement

Parzival self-checks: "For every issue I'm working in this plan, have I read its full source record — not just its summary?"

## Violation Response

1. Stop before scoping, briefing, or verifying the issue.
2. Open and read the issue's full source record (and any records it cross-links).
3. Reconcile any drift between the record and the summary/INDEX/memory; surface it.
4. Then proceed with verified, record-cited content.
