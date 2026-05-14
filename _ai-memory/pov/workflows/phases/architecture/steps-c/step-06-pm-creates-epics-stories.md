---
name: 'step-06-pm-creates-epics-stories'
description: 'Define epic/story structure requirements and dispatch PM via agent-dispatch cycle'
nextStepFile: './step-07-readiness-check.md'
---

# Step 6: PM Creates Epics and Stories

**Progress: Step 6 of 9** — Next: Implementation Readiness Check

## STEP GOAL:

After architecture is approved by Parzival, define the epic/story structure requirements and dispatch the PM via the agent-dispatch cycle to break down the PRD into epics and stories. Stories must be informed by architecture decisions -- this is why epics come after architecture, not before.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: PRD.md, architecture.md (approved by Parzival), UX design artifacts (if created)
- Focus: PM epics/stories dispatch and Parzival review — architecture decisions determine work breakdown
- Limits: PM creates epics/stories. Parzival reviews them. Architecture decisions determine how work is broken down.
- Dependencies: Step 5 complete — user has approved architecture with no more changes

- Focus on preparing the PM instruction with both PRD and architecture as mandatory inputs
**Behavioral Constraints:**
- FORBIDDEN to dispatch PM without providing architecture.md as input
- Approach: Stories must reference architecture decisions — never create stories in isolation from architecture
- Parzival reviews epics/stories before proceeding — PM output is not self-approving

## Sequence of Instructions (Do not deviate, skip, or optimize)

### Parzival's Responsibility (Layer 1)

#### 1. Prepare PM Epics and Stories Instruction

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

### Execution (via agent-dispatch cycle)

---

#### 2. Dispatch PM via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md to activate the PM. Provide both PRD.md and architecture.md as critical inputs.

### Parzival's Responsibility (Layer 1)

---

#### 3. Review Epics and Stories

Parzival reviews for:
- Every Must Have PRD feature is covered
- Stories map to architecture boundaries correctly
- No story is too large
- Dependencies are logical and correctly ordered
- Acceptance criteria match PRD requirements
- Technical context is accurate per architecture.md
- No gaps -- no feature in PRD without a story

---

#### 4. Handle Issues

If stories need correction, send specific issues per story via {workflows_path}/cycles/agent-dispatch/workflow.md. Re-review after corrections.

## CRITICAL STEP COMPLETION NOTE

ONLY when epics and stories pass Parzival's review, load and read fully {nextStepFile}
