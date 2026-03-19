---
id: IN-04
name: Validate AI-Memory Installation Completeness
severity: HIGH
phase: init
---

# IN-04: Validate AI-Memory Installation Completeness

## Constraint

Before declaring init complete, Parzival must validate that the `_ai-memory/` installation is complete and functional. This includes verifying all required directories exist, all config files are valid, and all manifest files are populated.

## Explanation

An incomplete installation causes workflow failures when Parzival attempts to load step files, constraints, or config that doesn't exist. Validation during init catches these gaps before they become runtime errors.

## Examples

**Validation checklist**:
- `_ai-memory/_config/manifest.yaml` exists and parses as valid YAML
- `_ai-memory/pov/config.yaml` exists with all required fields
- `_ai-memory/pov/agents/parzival.md` exists
- `_ai-memory/pov/constraints/global/constraints.md` exists
- `_ai-memory/pov/workflows/WORKFLOW-MAP.md` exists
- All workflow directories referenced in WORKFLOW-MAP have `workflow.md` entry points
- All `workflow.md` files have valid `firstStep:` references to existing step files

**If validation fails**:
- Report exactly what is missing
- Do NOT proceed to phase workflow
- Offer to re-run installation or repair

## Enforcement

Init workflow final step must run the validation checklist before handing off to the first phase workflow.

## Violation Response

1. Report validation failures
2. Block transition to phase workflow
3. Present repair options to user
