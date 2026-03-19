---
id: GC-17
name: Complex Bug Unified Spec Requirement
severity: HIGH
phase: global
category: Quality
---

# GC-17: Complex Bug Unified Spec Requirement

## Constraint

For complex bugs (>2 sub-issues OR >2 files OR previous fix attempt failed), the following rules apply:

1. MUST create a unified fix spec using `{oversight_path}/specs/FIX_SPEC_TEMPLATE.md` before any fix work begins
2. NEVER allow piecemeal fixes to complex bugs
3. MUST follow the fix order specified in the unified spec
4. MUST get user approval if deviating from the spec

## Explanation

Piecemeal fixes to complex bugs compound the problem. Each partial fix risks introducing new issues while only addressing one symptom, leading to a cascade of follow-up bugs. This was the pattern behind BUG-003, where 6 separate fix attempts introduced new issues at each step.

A unified fix spec forces holistic analysis before any code changes. It identifies all affected components, establishes a safe fix order, and creates a shared contract between Parzival and the user. Deviations require explicit approval so the user remains in control of scope changes.

This constraint complements GC-05 (verify fixes against requirements) and GC-12 (loop until zero issues) — GC-17 adds the requirement for a unified spec BEFORE any fix work begins on complex bugs.

## Examples

**Complex Bug Indicators** — a bug is complex if it exhibits ANY of the following:

1. Multiple symptoms / >2 sub-issues (e.g., wrong field + truncation + timing issue)
2. Multiple files need changes (>2 files)
3. A previous fix attempt failed or introduced a new issue
4. Architectural understanding is required to resolve correctly

**Correct workflow**:
1. Detect complexity indicators
2. Create a new fix spec at `{oversight_path}/specs/BUG-XXX-fix-spec.md` using FIX_SPEC_TEMPLATE.md
3. Get user review/approval of the spec
4. Execute fixes in the order specified
5. Any deviation → stop and get user approval before continuing

**Incorrect workflow** (violation):
- File the bug, immediately dispatch a dev agent with "fix it"
- Let the agent patch one symptom at a time across multiple passes
- Accept "mostly fixed" and move on

## Enforcement

Parzival self-checks at every 10-message interval: "GC-17: Is this bug complex (>2 sub-issues, >2 files, prior fix failed, or architectural understanding required)? If yes, have I created a unified fix spec?"

## Violation Response

1. Stop all fix work immediately
2. Assess the full scope of the bug using all complexity indicators
3. Create a new fix spec at `{oversight_path}/specs/BUG-XXX-fix-spec.md` using FIX_SPEC_TEMPLATE.md
4. Present the spec to the user for approval
5. Resume fix work only after approval, following the spec's fix order
