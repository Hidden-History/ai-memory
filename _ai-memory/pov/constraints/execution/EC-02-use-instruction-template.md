---
id: EC-02
name: MUST Use Implementation Instruction Template for Every DEV Dispatch
severity: CRITICAL
phase: execution
---

# EC-02: MUST Use Implementation Instruction Template for Every DEV Dispatch

## Constraint

DEV agents receive implementation instructions — not story files directly.

## Explanation

WHY THIS MATTERS:
- Story files are planning artifacts — they are not optimized for DEV execution
- Implementation instructions translate story requirements into precise, actionable specifications with explicit file-level guidance
- Without the instruction template, DEV fills gaps with guesses

IMPLEMENTATION INSTRUCTION MUST INCLUDE:
- Files to CREATE (specific file paths)
- Files to MODIFY (specific file paths + what changes)
- Architecture patterns to follow (cited from architecture.md)
- Standards to follow (cited from project-context.md)
- Testing requirements (type, what to test, coverage expectation)
- Security requirements (for any story involving input, auth, or data)
- IN SCOPE and OUT OF SCOPE explicit lists
- DONE WHEN criteria (one per acceptance criterion at minimum)

NOT ACCEPTABLE:
- "Implement the story as specified in the story file"
- Sending only the story file without the instruction template
- Generic instructions without specific file paths and citations

PARZIVAL ENFORCES:
- Complete instruction quality check before every dispatch
- Any dispatch without a complete instruction is a CRITICAL violation

## Examples

**Permitted**:
- A complete implementation instruction with all required sections filled
- Specific file paths, cited patterns, explicit scope boundaries

**Never permitted**:
- "Implement the story as specified in the story file"
- Sending only the story file without the instruction template
- Generic instructions without specific file paths

## Enforcement

Parzival self-checks at every 10-message interval: "Did I use the implementation instruction template for this dispatch?"

## Violation Response

1. Recall the dispatch if possible
2. Build a proper implementation instruction using the template
3. Complete instruction quality check
4. Redispatch with the complete instruction
