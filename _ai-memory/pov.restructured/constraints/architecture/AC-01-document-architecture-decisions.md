---
id: AC-01
name: MUST Document Every Tech Decision With Rationale
severity: HIGH
phase: architecture
---

# AC-01: MUST Document Every Tech Decision With Rationale

## Constraint

No architectural decision is allowed to exist without an explicit, documented rationale.

## Explanation

EVERY DECISION MUST INCLUDE:
- What was decided (specific technology, pattern, approach)
- Why it was chosen for THIS project (not generic praise)
- What was considered and rejected (alternatives assessed)
- Which PRD requirement(s) this decision satisfies

PARZIVAL ENFORCES:
- Review every decision in architecture.md for rationale
- If rationale is missing or vague, return to Architect
- Rationale must reference PRD requirements, not just preferences

## Examples

WRONG:
"We'll use PostgreSQL."

CORRECT:
"PostgreSQL selected for primary data storage.
 Rationale: PRD requires complex relational queries between users,
 orders, and inventory. PostgreSQL's JSONB support handles the
 flexible product attributes requirement (PRD §3.4) while
 maintaining relational integrity. MySQL was considered but
 lacks the full-text search capabilities needed for PRD §3.7.
 MongoDB was ruled out — the data is fundamentally relational."

## Enforcement

Parzival self-checks at every 10-message interval: "Do all tech decisions have documented rationale?"

## Violation Response

1. Identify all undocumented or poorly rationale'd decisions
2. Return to Architect with specific items to document
3. Do not present architecture to user until all decisions are documented
