---
id: PC-06
name: Architecture.md Must Be Used as Technical Context for All Stories
severity: HIGH
phase: planning
---

# PC-06: Architecture.md Must Be Used as Technical Context for All Stories

## Constraint

Every story's technical context section must reference architecture.md — not generic guidance.

## Explanation

REQUIRED IN EVERY STORY'S TECHNICAL CONTEXT:
- Specific architectural pattern to follow (named, cited from architecture.md)
- Specific components involved (named in architecture)
- Data models relevant to this story (from architecture)
- API patterns to follow (from architecture)

NOT ACCEPTABLE:
- "Follow REST conventions" without citing which conventions apply here
- "Use the database" without specifying which model and relationships
- "Match the existing code style" without citing project-context.md

WHY THIS MATTERS:
- DEV agents do not have memory between sessions
- A story without specific technical context forces DEV to guess
- Guessed implementation choices create architecture drift
- Architecture drift accumulates into significant tech debt

PARZIVAL ENFORCES:
- Review technical context section of every story
- Vague technical context, return to SM with specific sections to cite
- "See architecture.md" alone is not sufficient — specific sections required

## Examples

**Permitted**:
- Technical context citing "architecture.md S4.2 REST API patterns" with specific details
- Naming specific components, data models, and patterns from architecture

**Never permitted**:
- "Follow REST conventions" without citing which ones
- "See architecture.md" without citing specific sections
- "Match the existing code style" without citing project-context.md

## Enforcement

Parzival self-checks at every 10-message interval: "Does every story's technical context cite architecture.md specifically?"

## Violation Response

1. Identify the story with vague or missing technical context
2. Return to SM with specific architecture.md sections to cite
3. Do not allow the story to enter the sprint until technical context is specific
