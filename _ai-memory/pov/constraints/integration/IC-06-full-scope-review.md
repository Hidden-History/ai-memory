---
id: IC-06
name: DEV Integration Review Covers All Files in Milestone Scope
severity: HIGH
phase: integration
---

# IC-06: DEV Integration Review Covers All Files in Milestone Scope

## Constraint

The integration code review is not scoped to new code only — it covers all files touched across the milestone.

## Explanation

FULL SCOPE MEANS:
- All files created during milestone stories
- All files modified during milestone stories
- All integration points between new and existing code
- All external API interaction points
- All data models and migrations in scope

NOT SUFFICIENT:
- "The new files look good"
- Reviewing only the files changed in the last story
- Reviewing only the "main" files and skipping utilities/helpers

WHY FULL SCOPE:
- Cross-story consistency can only be verified by looking at all stories
- Issues at integration boundaries span multiple files
- A file that passed its story review may conflict with another story's implementation in ways only visible when reviewed together

PARZIVAL ENFORCES:
- Phase 3 instruction explicitly lists all files in scope
- DEV instruction includes the full file list from Phase 1
- Any indication DEV is scoping the review narrowly, send correction instruction to expand to full milestone scope

## Examples

**Permitted**:
- Integration review covering all files created and modified across all milestone stories
- Explicitly listing all files in scope in the DEV instruction

**Never permitted**:
- Reviewing only files from the last story
- Reviewing only "main" files and skipping utilities/helpers
- Allowing DEV to scope the review narrowly

## Enforcement

Parzival self-checks at every 10-message interval: "Does the DEV review cover all files in full milestone scope?"

## Violation Response

1. Identify that the review scope is too narrow
2. Send correction instruction to expand to full milestone scope
3. Provide the complete file list from Phase 1
