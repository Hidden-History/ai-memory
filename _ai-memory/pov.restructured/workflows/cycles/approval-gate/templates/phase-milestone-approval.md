---
name: 'phase-milestone-approval'
description: 'Phase milestone approval format used at the end of a phase (PRD approval, architecture approval, release sign-off)'
---

# Phase Milestone Approval Template

Use this format when presenting phase completion for sign-off in step-02.

```
PARZIVAL -- PHASE COMPLETE | Sign-off Required

PHASE:    [Phase name -- e.g., Discovery, Architecture, Integration]
OUTPUT:   [Primary deliverable -- e.g., PRD.md, architecture.md]
STATUS:   Complete and verified -- ready for sign-off

PHASE SUMMARY

[What was accomplished in this phase.
Key decisions made. Key outputs produced.
3-6 sentences -- enough for informed sign-off.]

DELIVERABLES

[List all files produced or updated in this phase]
  - [file path]: [one-line description of contents]
  - [file path]: [one-line description]

KEY DECISIONS MADE

[Decisions made during this phase that lock in direction.
User should be aware these are now the foundation for next phase.]
  1. [Decision]: [brief rationale]
  2. [Decision]: [brief rationale]

ASSUMPTIONS AND OPEN QUESTIONS (if any)

[Any assumptions made that the user should validate.
Any questions that were deferred and will need addressing later.
Skip this section if none.]

NEXT PHASE

On approval, Parzival will begin: [next phase name]
First action: [what Parzival will do immediately after approval]
Agents to activate: [which agents will be used next]

Do you sign off on this phase?
  [A] Approve -- begin next phase
  [R] Reject -- provide specific feedback
  [H] Hold -- I need to review the deliverables first
```
