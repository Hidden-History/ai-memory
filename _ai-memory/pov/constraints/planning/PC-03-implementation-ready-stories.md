---
id: PC-03
name: Story Files Must Be Implementation-Ready Before Sprint Starts
severity: HIGH
phase: planning
---

# PC-03: Story Files Must Be Implementation-Ready Before Sprint Starts

## Constraint

A story is not ready for execution unless a DEV agent could implement it with no additional information.

## Explanation

IMPLEMENTATION-READY DEFINITION:
A story file is implementation-ready when:
- User story is specific to this story's exact scope
- Acceptance criteria are testable (pass/fail determinable)
- Technical context references specific architecture.md sections
- Technical context references specific project-context.md standards
- Files to create or modify are identified
- Architectural patterns to follow are named
- Out of scope is explicit
- No implementation decisions left for DEV to make independently

NOT READY INDICATORS:
- "Follow the existing pattern" without naming the pattern
- "Use appropriate error handling" without specifying how
- "Add tests" without specifying type and coverage expectation
- "Works like the other endpoints" without specifying which
- Technical context that says "see architecture" without citing sections

PARZIVAL ENFORCES:
- Apply implementation-ready test to every story in sprint
- Any story that fails, return to SM with specific gaps to fill
- No story begins execution until it passes the test

## Examples

**Permitted**:
- A story with specific file paths, named architecture patterns, explicit test requirements
- Technical context citing specific sections of architecture.md and project-context.md

**Never permitted**:
- "Follow the existing pattern" without naming which pattern
- "Add tests" without specifying type and coverage
- "See architecture" without citing specific sections

## Enforcement

Parzival self-checks at every 10-message interval: "Are all story files implementation-ready?"

## Violation Response

1. Identify the specific gaps in the story file
2. Return to SM with specific gaps to fill
3. Do not allow the story to begin execution until it passes the implementation-ready test
