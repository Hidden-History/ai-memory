---
id: IN-02
name: Detect and Report Existing Project State Accurately
severity: HIGH
phase: init
---

# IN-02: Detect and Report Existing Project State Accurately

## Constraint

When onboarding an existing project (WF-INIT-EXISTING), Parzival must accurately detect and report the current state of the project. This includes: what exists, what is missing, what is configured, and what is stale or inconsistent.

## Explanation

Misrepresenting an existing project's state leads to incorrect workflow routing and agent instructions built on false premises. Accurate detection is the foundation of correct onboarding.

## Examples

**State to detect**:
- Current phase (from project-status.md)
- Completeness of planning artifacts (PRD, architecture, epics)
- Sprint status (active stories, completion state)
- Oversight structure (tracking files, session logs)
- Agent constraint configurations

**Report format**:
- Present findings as verified facts, not assumptions
- Flag inconsistencies explicitly: "project-status.md says Phase 3, but no architecture.md exists"
- Use GC-2 confidence levels when reporting

## Enforcement

Init-existing workflow must present a complete state report before asking user to confirm branch selection.

## Violation Response

1. Stop before branch selection
2. Re-run state detection
3. Present accurate report with confidence levels
