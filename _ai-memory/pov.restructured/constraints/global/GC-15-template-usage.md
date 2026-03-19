---
id: GC-15
name: Template Usage for Oversight Documentation
severity: MEDIUM
category: Quality
phase: global
---

# GC-15: ALWAYS Use Oversight Templates When Creating Structured Documents

## Rule

When directing the creation of any oversight document, Parzival MUST reference the appropriate
template from `{oversight_path}/`. Ad-hoc structures are not acceptable for documents that will
be referenced across sessions.

## Template Map

| Document Type | Template |
|---|---|
| Bug report | `{oversight_path}/bugs/BUG_TEMPLATE.md` |
| Root cause analysis | `{oversight_path}/bugs/ROOT_CAUSE_TEMPLATE.md` |
| Complex fix spec (>2 sub-issues or >2 files) | `{oversight_path}/specs/FIX_SPEC_TEMPLATE.md` |
| Architectural decision record | `{oversight_path}/decisions/DECISION_TEMPLATE.md` |
| Plan (major initiative) | `{oversight_path}/plans/PLAN_TEMPLATE.md` |
| System audit | `{oversight_path}/audits/AUDIT_TEMPLATE.md` |
| Validation report | `{oversight_path}/validation/VALIDATION_TEMPLATE.md` |
| Verification report | `{oversight_path}/verification/checklists/` (story/code/production) |
| Fix verification | `{project-root}/_ai-memory/pov/templates/verification-fix.template.md` |

## Applies To

- Parzival's own session handoffs (use `{project-root}/_ai-memory/pov/templates/session-handoff.template.md`)
- Decision logging (use entry format from `{project-root}/templates/oversight/tracking/decision-log.md`)
- Any structured document that will be referenced across sessions

## What This Does NOT Apply To

- In-session working notes (these are ephemeral, not persisted)
- PROJECT_STANDARDS.yaml and other config files (these have their own schema)
- Free-form notes appended to existing structured files

## Rationale

Consistent structure enables cross-session pattern recognition and searchability. Templates
capture the right fields for each document type. Derived from V1 C5: without enforcement,
oversight documents diverge in structure and become harder for Future Parzival to parse.

## Self-Check

- GC-15: Am I creating an oversight document without referencing the appropriate template?

## Violation Response

1. Identify the correct template from the table above
2. Use that template for the document
3. Review the output against the template structure before accepting
