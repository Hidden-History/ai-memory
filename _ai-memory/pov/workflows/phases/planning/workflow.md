---
name: planning
description: 'Sprint Planning phase. Transforms approved epics and stories into an executable sprint with implementation-ready story files.'
firstStep: './steps/step-01-review-project-state.md'
---

# Sprint Planning Phase

**Goal:** Transform approved epics and stories into an executable sprint. Answer three questions: what gets built next, in what order, and what does each unit of work look like in enough detail that a DEV agent can implement it without guessing. Planning is not done when a sprint is created. It is done when every story in the sprint is implementation-ready and the user has approved the plan.

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Step Processing Rules
1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute numbered sections in order
3. **WAIT FOR INPUT**: Halt at decision points and wait for user direction
4. **LOAD NEXT**: When directed, load and execute the next step file

### Critical Rules
- NEVER load multiple step files simultaneously
- ALWAYS read entire step file before execution
- NEVER skip steps unless explicitly optional
- ALWAYS follow exact instructions in step files

### Step Chain Overview
1. **step-01** -- Review current project state
2. **step-02** -- Retrospective (subsequent sprints only -- skip for first sprint)
3. **step-03** -- SM initializes or updates sprint planning
4. **step-04** -- SM creates story files for sprint stories
5. **step-05** -- Parzival reviews sprint plan and story files
6. **step-06** -- User review and approval
7. **step-07** -- Approval gate and route to Execution

### Planning Anti-Patterns
These apply across ALL steps in this workflow:
- Never create stories without architecture as input
- Never let stories leave implementation decisions to DEV
- Never accept oversized stories that cannot be reviewed in one cycle
- Never skip retrospective for subsequent sprints (without user approval)
- Never plan more stories than velocity supports
- Never assign stories with unmet dependencies
- Never accept vague acceptance criteria
- Never present sprint to user without reviewing story files first
- Never start execution before sprint is approved

### Constraints
- Load with: CONSTRAINTS-GLOBAL + CONSTRAINTS-PLANNING
- Drop on exit: CONSTRAINTS-PLANNING
- Exit to: WF-EXECUTION

---

## MID-SPRINT REPLANNING PROTOCOL

If scope changes require replanning during a sprint:

**Triggers:**
- User requests scope change
- Architecture change invalidates stories
- Blocker makes current sprint plan invalid
- User invokes correct-course workflow

**Replanning Steps:**
1. Pause current task (complete current review cycle if in progress)
2. Document why replanning is triggered
3. Activate SM with correct-course assessment
4. SM assesses impact on current sprint and remaining stories
5. Parzival reviews SM's impact assessment
6. Present impact assessment to user:
   - In-progress work: [affected/not affected]
   - Current sprint stories affected: [N]
   - Stories needing update: [list]
   - Estimated rework: [assessment]
   - "Do you want to proceed with this change?"
7. If confirmed: update affected stories, update sprint-status
8. Resume execution with updated plan

**NEVER:**
- Change story scope without user confirmation
- Continue implementing a story known to be invalidated
- Replan without documenting why

---

## INITIALIZATION SEQUENCE

Load and follow: {firstStep}
