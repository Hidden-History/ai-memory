---
name: 'step-06-pm-creates-epics-stories'
description: 'Activate PM to break down PRD into epics and stories informed by architecture decisions'
nextStepFile: './step-07-readiness-check.md'
---

# Step 6: PM Creates Epics and Stories

## STEP GOAL
After architecture is approved by Parzival, activate the PM to break down the PRD into epics and stories. Stories must be informed by architecture decisions -- this is why epics come after architecture, not before.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: PRD.md, architecture.md (approved by Parzival), UX design artifacts (if created)
- Limits: PM creates epics/stories. Parzival reviews them. Architecture decisions determine how work is broken down.

## MANDATORY SEQUENCE

### 1. Prepare PM Epics and Stories Instruction

**Epics requirements:**
- Group stories by feature area or component
- Each epic represents a meaningful, deployable increment
- Epic names map to PRD feature groups

**Stories requirements:**
- Each story is ONE reviewable unit of work
- One story = one DEV agent task = one review cycle
- Stories must NOT span component boundaries
- Stories must NOT require architecture decisions to be made

Each story must include:
- Clear title
- User story format (As a [user], I want [action], so that [value])
- Acceptance criteria (from PRD where possible)
- Technical context (which components, files, patterns to use -- from architecture.md)
- Dependencies (which stories must complete first)
- Out of scope (what this story does NOT include)

Story sizing:
- Completable in a reasonable implementation session
- Produces output reviewable in one review cycle
- If a story cannot be reviewed as a unit -- split it

### 2. Dispatch PM via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the PM. Provide both PRD.md and architecture.md as critical inputs.

### 3. Review Epics and Stories
Parzival reviews for:
- Every Must Have PRD feature is covered
- Stories map to architecture boundaries correctly
- No story is too large
- Dependencies are logical and correctly ordered
- Acceptance criteria match PRD requirements
- Technical context is accurate per architecture.md
- No gaps -- no feature in PRD without a story

### 4. Handle Issues
If stories need correction, send specific issues per story to PM via {workflows_path}/cycles/agent-dispatch/workflow.md. Re-review after corrections.

## CRITICAL STEP COMPLETION NOTE
ONLY when epics and stories pass Parzival's review, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- PM received both PRD and architecture as inputs
- Stories reference architecture decisions for technical context
- Every PRD Must Have feature has a story
- Stories do not span component boundaries
- Parzival reviewed before proceeding

### FAILURE:
- Writing stories without architecture as input
- Stories that span component boundaries
- PRD features without corresponding stories
- PM dispatched without architecture.md
