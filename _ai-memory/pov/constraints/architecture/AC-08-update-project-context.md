---
id: AC-08
name: project-context.md Must Be Updated With Architecture Decisions
severity: MEDIUM
phase: architecture
---

# AC-08: project-context.md Must Be Updated With Architecture Decisions

## Constraint

When architecture is finalized, project-context.md must reflect the confirmed decisions.

## Explanation

MUST BE UPDATED WITH:
- Confirmed technology stack (specific versions)
- Code organization patterns (directory structure, module approach)
- Naming conventions established in architecture
- Testing approach and frameworks
- Any framework-specific patterns in use

WHY THIS MATTERS:
- DEV agents use project-context.md as their implementation guide
- If project-context.md is outdated or generic, DEV agents will make implementation choices that contradict architecture
- project-context.md is the bridge between architecture decisions and story-level implementation

PARZIVAL ENFORCES:
- Architecture phase does not exit until project-context.md is updated or generated from the finalized architecture
- Use /bmad-generate-project-context to generate or update
- Review generated content for accuracy before accepting

## Examples

**Permitted**:
- Updating project-context.md with all confirmed architecture decisions before exiting
- Generating project-context.md from finalized architecture using /bmad-generate-project-context

**Never permitted**:
- Exiting Architecture without updating project-context.md
- Leaving project-context.md with outdated or generic content after architecture is finalized

## Enforcement

Parzival self-checks at every 10-message interval: "Has project-context.md been updated with architecture decisions?"

## Violation Response

1. Block Architecture exit
2. Update or generate project-context.md from finalized architecture
3. Review generated content for accuracy
4. Proceed only after project-context.md reflects confirmed decisions
