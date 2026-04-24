---
name: 'step-05-parzival-reviews-sprint'
description: 'Parzival reviews the complete sprint plan and all story files before user sees them'
nextStepFile: './step-06-user-review-approval.md'
---

# Step 5: Parzival Reviews Sprint Plan and Story Files

**Progress: Step 5 of 7** — Next: User Review and Approval

## STEP GOAL:

Before the user sees anything, Parzival reviews the full sprint output -- both sprint-status.yaml and every individual story file. Apply the implementation-ready test to each story.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: sprint-status.yaml, all story files, architecture.md, project-context.md, PRD.md
- Focus: Internal quality review — user has not seen the sprint plan yet
- Limits: Parzival reviews. User has not seen the sprint plan yet. Batch corrections.
- Dependencies: All story files and sprint-status.yaml from Steps 3 and 4

- Review every story file individually before user sees anything
**Behavioral Constraints:**
- FORBIDDEN to present stories to user before internal review is complete
- Approach: Apply implementation-ready test to each story; batch corrections to SM
- All stories must pass before user presentation — no exceptions

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Review sprint-status.yaml

- All sprint stories listed with correct status
- Dependencies correctly mapped
- Story sequence is logical (foundations first)
- Scope is realistic given velocity
- No story with unmet dependencies in this sprint

---

### 2. Review Each Story File

For each story:
- All 7 required sections are present
- User story is specific (not generic)
- Acceptance criteria are testable (not vague)
- Technical context references actual architecture.md decisions
- Technical context references actual project-context.md standards
- Out of scope is explicit (not empty)
- Story is self-contained -- no ambiguity for DEV
- Story size is appropriate for one implementation session
- Story does not span component boundaries
- No implementation decisions left for DEV to make

---

### 3. Apply Implementation-Ready Test

For each story: "If I gave this story file to a DEV agent with no other context, could they implement it correctly?"

If YES: story is ready.
If NO: identify what information is missing.

Common gaps that make stories NOT ready:
- "Follow the existing pattern" without specifying which pattern
- "Use the database model" without specifying which model and fields
- "Handle errors appropriately" without specifying how
- "Add tests" without specifying what tests at what coverage level
- Acceptance criteria that say "works correctly" without defining correct

---

### 4. Handle Issues

If stories need correction, compile specific issues per story and send to SM via {workflows_path}/cycles/agent-dispatch/workflow.md. Re-review after corrections.

## CRITICAL STEP COMPLETION NOTE

ONLY when all story files pass review and the implementation-ready test, load and read fully {nextStepFile}
