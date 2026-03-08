---
id: EC-04
name: Story Scope Cannot Expand During Execution Without User Approval
severity: HIGH
phase: execution
---

# EC-04: Story Scope Cannot Expand During Execution Without User Approval

## Constraint

Once execution begins, the story scope is fixed. Additional work requires a new story or explicit user approval.

## Explanation

SCOPE EXPANSION INDICATORS:
- DEV identifies "related" work and implements it beyond story scope
- Parzival adds requirements to the implementation instruction not present in the story file
- Review finds issues in adjacent code — adding them expands scope (pre-existing legitimate issues are different — they are fixed in cycle)
- User casually mentions additional requirements during execution

SCOPE BOUNDARY:
- Story files define scope
- Out of scope section is enforced
- Pre-existing legitimate issues in surrounding code ARE fixed (GC-7, GC-8) but these are quality fixes, not feature additions

IF SCOPE EXPANSION IS NEEDED:
- Stop — do not implement the additional scope
- Identify it as a scope change
- Create a new story for the additional work
- Complete current story within original scope
- New story enters sprint backlog for planning

PARZIVAL ENFORCES:
- Monitor DEV output for out-of-scope changes during review
- Any out-of-scope implementation, instruct revert before continuing
- User requests during execution, acknowledge, create new story, do not add to current story without formal scope change

## Examples

**Permitted**:
- Fixing pre-existing legitimate issues found in the fix area (GC-7, GC-8)
- Creating a new story for additional work identified during execution

**Never permitted**:
- DEV implementing "related" work beyond story scope
- Adding requirements not in the story file to the implementation instruction
- Implementing user requests during execution without formal scope change

## Enforcement

Parzival self-checks at every 10-message interval: "Has story scope stayed within defined boundaries?"

## Violation Response

1. Identify the scope expansion
2. Instruct revert of out-of-scope implementation
3. Create a new story for the additional work
4. Complete current story within original scope
