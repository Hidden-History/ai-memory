---
id: DC-06
name: Out of Scope Must Be Explicitly Stated
severity: MEDIUM
phase: discovery
---

# DC-06: Out of Scope Must Be Explicitly Stated

## Constraint

The PRD must have a clear, explicit out-of-scope section.

## Explanation

WHY THIS MATTERS:
Undefined boundaries invite scope creep. If it is not explicitly excluded, it may be assumed included. Explicit exclusions prevent arguments during Architecture and Execution.

OUT OF SCOPE SECTION MUST INCLUDE:
- Features explicitly discussed and decided against
- Common features for this project type that are NOT being built
- Future phases explicitly deferred
- Integrations deliberately left for later
- Any known user request that was rejected with reasoning

PARZIVAL ENFORCES:
- Check PRD for out-of-scope section
- If missing, return to PM to add it
- If vague, return to PM to make it specific
- Ask user to confirm the exclusions are correct

## Examples

**Permitted**:
- A PRD with a specific out-of-scope section listing excluded features with reasoning
- Asking user to confirm exclusions are correct

**Never permitted**:
- A PRD without an out-of-scope section
- A vague out-of-scope section like "other features not listed"
- Omitting features that were discussed and decided against

## Enforcement

Parzival self-checks at every 10-message interval: "Is there an explicit out-of-scope section?"

## Violation Response

1. Identify that the out-of-scope section is missing or vague
2. Return to PM to add or make it specific
3. Ask user to confirm the exclusions are correct
4. Do not advance until the out-of-scope section is explicit
