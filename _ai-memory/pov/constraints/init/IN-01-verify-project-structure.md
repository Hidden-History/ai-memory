---
id: IN-01
name: Verify Project Structure Before Proceeding
severity: HIGH
phase: init
---

# IN-01: Verify Project Structure Before Proceeding

## Constraint

Before performing any init actions, Parzival must verify the project's file structure by reading the filesystem directly. Never assume a directory exists, a file is present, or a configuration is in place without checking.

## Explanation

Init is the first interaction with a project. Assumptions about project structure at this stage propagate through every subsequent workflow. A missed directory or misconfigured file during init causes cascading failures in phase workflows.

## Examples

**Required checks**:
- Does `_ai-memory/` directory exist?
- Does `_ai-memory/pov/config.yaml` exist and contain required fields?
- Does `{oversight_path}/` directory exist?
- Does `{oversight_path}/SESSION_WORK_INDEX.md` exist?
- Does `project-status.md` exist? (determines new vs existing path)

**Never**:
- Assume a directory exists because it "should" be there
- Skip structure verification to save time

## Enforcement

Init workflow step 1 must complete all structure checks before proceeding to step 2.

## Violation Response

1. Stop init workflow
2. Report exactly what is missing or misconfigured
3. Present options to the user: create missing structure, or abort init
