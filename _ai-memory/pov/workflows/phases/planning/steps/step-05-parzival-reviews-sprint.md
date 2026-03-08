---
name: 'step-05-parzival-reviews-sprint'
description: 'Parzival reviews the complete sprint plan and all story files before user sees them'
nextStepFile: './step-06-user-review-approval.md'
---

# Step 5: Parzival Reviews Sprint Plan and Story Files

## STEP GOAL
Before the user sees anything, Parzival reviews the full sprint output -- both sprint-status.yaml and every individual story file. Apply the implementation-ready test to each story.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: sprint-status.yaml, all story files, architecture.md, project-context.md, PRD.md
- Limits: Parzival reviews. User has not seen the sprint plan yet. Batch corrections.

## MANDATORY SEQUENCE

### 1. Review sprint-status.yaml
- All sprint stories listed with correct status
- Dependencies correctly mapped
- Story sequence is logical (foundations first)
- Scope is realistic given velocity
- No story with unmet dependencies in this sprint

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

### 4. Handle Issues
If stories need correction, compile specific issues per story and send to SM via {workflows_path}/cycles/agent-dispatch/workflow.md. Re-review after corrections.

## CRITICAL STEP COMPLETION NOTE
ONLY when all story files pass review and the implementation-ready test, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Sprint-status.yaml reviewed for coherence
- Every story file reviewed individually
- Implementation-ready test applied to each story
- Issues batched and corrected
- All stories pass before user presentation

### FAILURE:
- Presenting stories with known issues to user
- Not applying implementation-ready test
- Accepting vague acceptance criteria
- Not reviewing sprint-status.yaml
