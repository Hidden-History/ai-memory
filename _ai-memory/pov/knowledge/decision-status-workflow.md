---
name: Decision Status Workflow
description: Reference for the decision lifecycle states, transition rules, and cross-references used by Parzival when tracking DEC-XXX items.
---

# Decision Status Workflow

Parzival tracks all architectural and project decisions through a defined lifecycle. Every DEC-XXX item moves through these states. Transitions are gated by user approval — Parzival recommends, the user decides.

## Status Flow

```
Proposed → Under Review → Accepted → Implemented
              ↓               ↓
           Rejected      Superseded (by newer decision)
```

## Status Definitions

| Status | Definition | Who Transitions |
|--------|-----------|----------------|
| **Proposed** | Decision need identified, DEC-XXX assigned, options documented using decision-log template | Parzival |
| **Under Review** | Options presented to user with pros/cons and Parzival's recommendation | Parzival (after documenting options) |
| **Accepted** | User has chosen an option — decision is binding for implementation | User (explicit approval required) |
| **Implemented** | Decision has been applied in code, configuration, or architecture | Parzival (after verifying implementation matches decision) |
| **Rejected** | User rejected all options or deferred the decision | User |
| **Superseded** | A newer decision (DEC-YYY) replaces this one — link to successor | Parzival (with user approval, references new DEC-XXX) |

## Transition Rules

1. **Proposed → Under Review**: Only after context is documented thoroughly — why the decision is needed, what depends on it
2. **Under Review → Accepted**: Only the user can accept — Parzival NEVER accepts decisions on behalf of the user
3. **Under Review → Rejected**: User explicitly rejects. Document the reasoning. Decision may be re-proposed later with new information.
4. **Accepted → Implemented**: Only after the decision is reflected in the appropriate project file (architecture.md for architectural decisions, project-context.md for standards)
5. **Any → Superseded**: When a newer decision replaces an older one. The superseding DEC-XXX MUST reference the superseded one. Both documents are updated.

## What Gets a DEC-XXX

Assign a DEC-XXX when the decision:
- Changes or establishes an architectural pattern
- Sets a precedent that affects future implementation choices
- Resolves a conflict between competing approaches
- Affects multiple components or files
- Was debated — capturing the reasoning prevents re-litigating

Do NOT assign a DEC-XXX for:
- Implementation details within a single story (these go in the story file)
- Obvious choices with no meaningful alternatives
- Temporary workarounds (these are tech debt items, TD-XXX)

## Cross-References

- **GC-15**: Use oversight templates (decision-log template)
- **EC-07**: Implementation decisions must be documented
- **Decision template**: `{project-root}/_ai-memory/pov/templates/decision-log.template.md`
