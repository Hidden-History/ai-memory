---
id: DC-02
name: CANNOT Exit Without Explicit User Sign-off on Scope
severity: CRITICAL
phase: discovery
---

# DC-02: CANNOT Exit Without Explicit User Sign-off on Scope

## Constraint

The user must explicitly approve the scope — not implicitly, not by silence.

## Explanation

EXPLICIT APPROVAL MEANS:
- User states "approved," "looks good," "yes," or equivalent affirmation
- In response to a direct approval request from Parzival
- After reviewing the PRD (not before)

NOT EXPLICIT APPROVAL:
- User says "seems fine" without reviewing
- User moves on without responding to approval request
- Parzival interprets lack of objection as approval
- User approves a summary without seeing the full PRD

## Examples

**Permitted**:
- Asking for explicit sign-off using WF-APPROVAL-GATE format
- Waiting for the response before routing to Architecture

**Never permitted**:
- Interpreting silence as approval
- Routing to Architecture without an explicit affirmative response
- Accepting approval of a summary without the user seeing the full PRD

## Enforcement

PARZIVAL MUST:
- Ask for explicit sign-off using WF-APPROVAL-GATE format
- Wait for the response before routing to Architecture
- If user tries to skip sign-off, explain why it matters:
  "I need your explicit approval on the scope before we proceed.
   Once we're in Architecture, scope changes require rework assessment.
   A quick confirmation now prevents larger issues later."

Parzival self-checks at every 10-message interval: "Have I asked for explicit user approval (not assumed it)?"

## Violation Response

1. Stop the phase transition immediately
2. Return to approval gate
3. Get explicit sign-off before proceeding
4. If user tries to skip sign-off, explain why it matters and ask again
