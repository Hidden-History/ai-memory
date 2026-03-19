---
id: EC-01
name: MUST Verify Story Requirements Against Current Project Files Before Proceeding
severity: CRITICAL
phase: execution
---

# EC-01: MUST Verify Story Requirements Against Current Project Files Before Proceeding

## Constraint

The story file must be verified against current architecture.md and project-context.md before any implementation work begins.

## Explanation

VERIFICATION IS REQUIRED BECAUSE:
- Architecture and standards evolve over the project
- A story written in Sprint 1 may reference outdated patterns by Sprint 3
- Following outdated technical context produces architecture drift

WHAT TO VERIFY:
- Architecture patterns referenced still exist and are current
- File paths and module names referenced still match actual codebase
- Standards referenced in project-context.md are still current
- PRD acceptance criteria have not been updated since story was written
- Dependencies listed are confirmed complete

IF STORY IS OUTDATED:
- Update story file before proceeding -- never proceed with outdated technical context
- Document what was updated and why in decisions.md

PARZIVAL ENFORCES:
- Phase 1 of WF-EXECUTION runs before every implementation -- no exceptions
- An outdated story that proceeds without verification is a CRITICAL violation

## Examples

**Permitted**:
- Verifying the story file against current project files before every implementation
- Updating the story file when outdated patterns or file paths are found

**Never permitted**:
- Proceeding with a story without verification
- Proceeding with a story with known outdated technical context

## Enforcement

Parzival self-checks at every 10-message interval: "Did I verify story requirements against current project files?"

## Violation Response

1. Stop execution immediately
2. Verify the story against current architecture.md and project-context.md
3. Update the story file if outdated
4. Document updates in decisions.md
5. Resume only after verification is complete
