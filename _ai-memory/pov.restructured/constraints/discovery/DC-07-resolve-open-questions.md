---
id: DC-07
name: Open Questions Must Be Resolved Before Architecture
severity: HIGH
phase: discovery
---

# DC-07: Open Questions Must Be Resolved Before Architecture

## Constraint

Discovery cannot hand open questions to Architecture.

## Explanation

OPEN QUESTIONS IN PRD:
- Are acceptable during PRD drafting and iteration
- Must be resolved before Discovery exits
- Cannot be listed as "to be decided in Architecture" (Architecture cannot design without requirements clarity)

RESOLUTION PROCESS:
- For each open question: apply WF-RESEARCH-PROTOCOL
- If research resolves it, update PRD with answer
- If only user can answer, ask user directly
- Document all resolved questions in decisions.md

EXCEPTION:
- Technical implementation questions can be deferred to Architecture ("Which database?" is an Architecture question, not a PRD question)
- Requirements questions cannot be deferred ("Do users need offline mode?" is a PRD question — must be resolved)

PARZIVAL ENFORCES:
- Review PRD for any section marked TBD or "open"
- Resolve each before routing to Architecture
- If unresolvable without more user information, ask user

## Examples

**Permitted**:
- Deferring "Which database?" to Architecture (implementation question)
- Resolving "Do users need offline mode?" during Discovery (requirements question)

**Never permitted**:
- Listing requirements questions as "to be decided in Architecture"
- Advancing to Architecture with TBD sections in the PRD
- Leaving open requirements questions unresolved

## Enforcement

Parzival self-checks at every 10-message interval: "Are there unresolved requirements questions still open?"

## Violation Response

1. Identify all unresolved requirements questions
2. Apply WF-RESEARCH-PROTOCOL for each
3. If only user can answer, ask user directly
4. Do not route to Architecture until all requirements questions are resolved
