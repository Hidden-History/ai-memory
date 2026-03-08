---
id: DC-04
name: Requirements Must Be Implementation-Free
severity: HIGH
phase: discovery
---

# DC-04: Requirements Must Be Implementation-Free

## Constraint

The PRD defines WHAT the system does — not HOW it does it.

## Explanation

NOT ALLOWED IN PRD:
- Technology choices ("use PostgreSQL for...")
- Architecture patterns ("implement using REST API...")
- Code structure decisions ("create a UserService class...")
- Algorithm specifications ("use bcrypt with 12 rounds...")
- Database schema decisions

ALLOWED IN PRD:
- "Users can log in with email and password"
- "The system must support 1000 concurrent users"
- "Data must be encrypted at rest"
- "Response time must be under 200ms for core actions"

WHY THIS MATTERS:
Implementation details belong in Architecture. Putting them in the PRD locks decisions before the Architect has assessed trade-offs. This creates constraint conflicts later.

PARZIVAL ENFORCES:
- Review PRD for implementation details
- Remove them and flag for Architecture phase
- Note in decisions.md: "Implementation of [X] deferred to Architecture"

## Examples

**Permitted**:
- "Users can log in with email and password"
- "The system must support 1000 concurrent users"
- "Data must be encrypted at rest"
- "Response time must be under 200ms for core actions"

**Never permitted**:
- "Use PostgreSQL for the database"
- "Implement using REST API"
- "Create a UserService class"
- "Use bcrypt with 12 rounds for password hashing"
- Any database schema decisions

## Enforcement

Parzival self-checks at every 10-message interval: "Are there implementation details in the PRD?"

## Violation Response

1. Identify the implementation detail in the PRD
2. Remove it from the PRD
3. Flag it for Architecture phase
4. Note in decisions.md: "Implementation of [X] deferred to Architecture"
