---
id: IN-03
name: Confirm User Intent Before Creating or Modifying Project Files
severity: CRITICAL
phase: init
---

# IN-03: Confirm User Intent Before Creating or Modifying Project Files

## Constraint

During init, Parzival must confirm user intent before creating new files, modifying existing files, or changing project configuration. Init workflows create foundational project state — mistakes here are expensive to undo.

## Explanation

Init is a one-time operation that establishes project structure. Unlike phase workflows where changes are incremental and reversible, init changes define the entire project baseline. Explicit user confirmation prevents costly misalignments.

## Examples

**Requires explicit user confirmation**:
- Creating project-status.md (establishes project as "managed by Parzival")
- Creating or modifying oversight directory structure
- Setting initial phase
- Enabling Claude Code teams in settings.json
- Any file creation outside of `_ai-memory/` directory

**Does NOT require confirmation** (read-only operations):
- Reading project files to detect state
- Listing directory contents
- Checking configuration values

## Enforcement

All init workflow steps that create or modify files must include a user confirmation checkpoint before executing.

## Violation Response

1. Stop immediately
2. Revert any unauthorized changes
3. Present what was about to change and ask for user confirmation
