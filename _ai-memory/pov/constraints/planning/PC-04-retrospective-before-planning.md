---
id: PC-04
name: Retrospective Must Run Before Subsequent Sprint Planning
severity: MEDIUM
phase: planning
---

# PC-04: Retrospective Must Run Before Subsequent Sprint Planning

## Constraint

For every sprint after the first, retrospective output must inform the next sprint plan.

## Explanation

WHY THIS IS REQUIRED:
- Sprint velocity (stories completed vs. planned) is the primary input for realistic next sprint scoping
- Recurring issues identified in retrospective inform story sizing
- Carryover stories need explanation before being replanned
- Patterns in review cycle length indicate story complexity problems

RETROSPECTIVE BEFORE PLANNING MEANS:
- SM runs /bmad-retrospective before /bmad-sprint-planning
- Retrospective output is given to SM as input for next sprint
- Sprint [N+1] scope is based on Sprint [N] velocity — not optimism

EXCEPTION:
- User explicitly requests to skip retrospective — allowed once
- Note the skip in project-status.md
- Default behavior: retrospective always runs

PARZIVAL ENFORCES:
- Do not activate SM for sprint planning (subsequent sprints) until retrospective is complete
- Sprint plan that ignores velocity data is flagged and corrected

## Examples

**Permitted**:
- Running retrospective before subsequent sprint planning
- Using retrospective output to inform next sprint scope

**Never permitted**:
- Planning a subsequent sprint without running retrospective first
- Ignoring velocity data from retrospective in sprint planning

## Enforcement

Parzival self-checks at every 10-message interval: "Did retrospective run before this sprint planning (if not first sprint)?"

## Violation Response

1. Pause sprint planning
2. Run retrospective first
3. Use retrospective output to inform the sprint plan
4. Resume planning with velocity data available
