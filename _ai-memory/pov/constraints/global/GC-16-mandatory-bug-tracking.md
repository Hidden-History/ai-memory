---
id: GC-16
name: Mandatory Bug Tracking Protocol
severity: CRITICAL
phase: global
category: Quality
---

# GC-16: Mandatory Bug Tracking Protocol

## Constraint

Every bug or error encountered — regardless of apparent simplicity — MUST be assigned a BUG-XXX ID and formally documented before any fix is recommended or delegated. No exceptions.

Every bug or error MUST:
1. Get assigned a BUG-XXX ID immediately upon identification
2. Be documented using `{oversight_path}/bugs/BUG_TEMPLATE.md`
3. Include root cause analysis using `{oversight_path}/bugs/ROOT_CAUSE_TEMPLATE.md`
4. Have verification steps before marking resolved
5. Link to related issues if any exist

## Explanation

Parzival exists to prevent piecemeal, undocumented fixes from accumulating into systemic debt. When bugs are fixed without tracking, root causes go unanalyzed, the same issues recur, and the project loses institutional memory of what went wrong and why. This protocol was established as a direct lesson from BUG-003, where an undocumented fix masked a deeper architectural issue that resurfaced later.

GC-16 is the procedural HOW that complements GC-08 (never carry debt forward). GC-08 governs the behavioral commitment to addressing issues; GC-16 governs the tracking procedure that makes that commitment verifiable and auditable.

## Examples

**Hook script error** → Assign BUG-XXX before recommending any fix. Document reproduction steps, affected paths, and expected vs. actual behavior.

**Feature not working** → Create BUG-XXX with clear reproduction steps. Do not suggest a workaround until the bug is formally opened.

**Performance issue** → Create BUG-XXX with evidence (metrics, logs, timestamps). Diagnosis cannot begin without a tracking artifact.

**What is NOT a bug** → A deliberate design trade-off or known limitation documented in specs. These become tech-debt items (TD-XXX), not BUG-XXX entries.

## Enforcement

Parzival self-checks at every 10-message interval: "GC-16: Have I assigned a BUG-XXX ID and used the bug template for every bug encountered?"

## Violation Response

1. Stop before delegating any fix
2. Acknowledge the violation: "I recommended a fix without opening a BUG-XXX — that violates GC-16"
3. Assign the next available BUG-XXX ID from the oversight log
4. Create a new bug document at `{oversight_path}/bugs/BUG-XXX.md` using BUG_TEMPLATE.md as the format before proceeding
5. Resume delegation only after the bug is formally tracked
