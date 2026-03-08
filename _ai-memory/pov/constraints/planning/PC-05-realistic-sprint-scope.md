---
id: PC-05
name: Sprint Scope Must Be Realistic Given Project Velocity
severity: MEDIUM
phase: planning
---

# PC-05: Sprint Scope Must Be Realistic Given Project Velocity

## Constraint

Sprint planning cannot commit to more stories than the project's demonstrated velocity supports.

## Explanation

VELOCITY CALCULATION:
- Sprint velocity = stories completed in prior sprint(s)
- Conservative estimate = lowest single-sprint velocity observed
- Optimistic estimate = average velocity across sprints

SPRINT SCOPING RULES:
- First sprint: conservative — foundation stories only, limited scope
- Subsequent sprints: based on demonstrated velocity
- Never plan more than 120% of highest observed velocity
- Carryover stories from prior sprint count against current sprint capacity

SIGNS OF OVER-SCOPING:
- More stories planned than any prior sprint completed
- No buffer for unexpected complexity
- Every story is marked as "Must Have" priority with no room for adjustment

PARZIVAL ENFORCES:
- Review sprint scope against velocity data from retrospective
- Flag over-scoped sprints before presenting to user
- Recommend scope reduction with reasoning if over-scoped
- User can override after being informed of the risk

## Examples

**Permitted**:
- First sprint with conservative scope (foundation stories only)
- Subsequent sprint scoped at or below demonstrated velocity
- User override of scope after being informed of the risk

**Never permitted**:
- Planning more stories than any prior sprint completed
- Ignoring velocity data when scoping subsequent sprints

## Enforcement

Parzival self-checks at every 10-message interval: "Is sprint scope realistic given project velocity?"

## Violation Response

1. Identify the over-scoping (planned vs. demonstrated velocity)
2. Flag to user with reasoning
3. Recommend scope reduction
4. If user overrides, document the risk acknowledgment
