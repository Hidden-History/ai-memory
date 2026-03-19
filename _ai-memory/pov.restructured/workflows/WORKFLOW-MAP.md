# WORKFLOW-MAP.md -- Master Router

> **Purpose**: Parzival reads this file at every session start to determine project state and route to the correct workflow
> **Loaded**: Immediately after parzival.md and global constraints at activation
> **Authority**: This is the single source of truth for workflow routing decisions
> **Reference**: parzival-master-plan.md Section 6

---

## How to Use This File

This file is not a workflow itself. It is the routing engine. Every session starts here. Parzival reads the project state, follows the decision tree, loads the correct workflow and constraint files, and then operates within that workflow.

**Session start sequence -- always in this order**:
```
1. parzival.md              -> identity and constraints active
2. {constraints_path}/global/constraints.md -> GC-1 through GC-20 active
3. {workflows_path}/WORKFLOW-MAP.md         -> this file -- determine routing
4. project-status.md        -> read current project state
5. [phase workflow]          -> load correct workflow file
6. [phase constraints]       -> load correct constraint file
7. [context slice]           -> load only the files needed for this phase
8. Confirm state to user     -> ready to work
```

---

## Master Decision Tree

### Step 1 -- Does a Project Exist?

```
READ: project-status.md

Does project-status.md exist?
  |-- NO  -> Route to: {workflows_path}/init/new/workflow.md
  |         Load: {constraints_path}/init/constraints.md
  |         Context: none yet -- file creation is the first task
  |
  +-- YES -> Does it have a completed baseline?
              |-- NO  -> Route to: {workflows_path}/init/existing/workflow.md
              |         Load: {constraints_path}/init/constraints.md
              |         Context: project-status.md + any existing docs
              |
              +-- YES -> Proceed to Step 2
```

---

### Step 2 -- Which Phase Is Active?

```
READ: project-status.md -> field: current_phase

current_phase = "discovery"     -> Route to: {workflows_path}/phases/discovery/workflow.md
current_phase = "architecture"  -> Route to: {workflows_path}/phases/architecture/workflow.md
current_phase = "planning"      -> Route to: {workflows_path}/phases/planning/workflow.md
current_phase = "execution"     -> Route to: {workflows_path}/phases/execution/workflow.md
current_phase = "integration"   -> Route to: {workflows_path}/phases/integration/workflow.md
current_phase = "release"       -> Route to: {workflows_path}/phases/release/workflow.md
current_phase = "maintenance"   -> Route to: {workflows_path}/phases/maintenance/workflow.md
current_phase = "complete"      -> Confirm with user: new feature, bug, or new project?
current_phase = [missing/null]  -> Flag: project-status.md is incomplete
                                   Run: {workflows_path}/init/existing/workflow.md (branch: legacy)
```

---

### Step 3 -- Load Workflow + Constraints + Context Slice

Once the correct workflow is identified, load exactly these files -- no more:

| Phase | Workflow File | Constraint File | Context Slice |
|---|---|---|---|
| Init (New) | `{workflows_path}/init/new/workflow.md` | `{constraints_path}/init/constraints.md` | None -- creation is step one |
| Init (Existing) | `{workflows_path}/init/existing/workflow.md` | `{constraints_path}/init/constraints.md` | `project-status.md` + available docs |
| Discovery | `{workflows_path}/phases/discovery/workflow.md` | `{constraints_path}/discovery/constraints.md` | `goals.md` + PRD draft (if exists) |
| Architecture | `{workflows_path}/phases/architecture/workflow.md` | `{constraints_path}/architecture/constraints.md` | `PRD.md` + `architecture.md` |
| Planning | `{workflows_path}/phases/planning/workflow.md` | `{constraints_path}/planning/constraints.md` | `architecture.md` + backlog/epics |
| Execution | `{workflows_path}/phases/execution/workflow.md` | `{constraints_path}/execution/constraints.md` | `current-task.md` + `standards.md` + `project-context.md` |
| Integration | `{workflows_path}/phases/integration/workflow.md` | `{constraints_path}/integration/constraints.md` | feature spec + test plan |
| Release | `{workflows_path}/phases/release/workflow.md` | `{constraints_path}/release/constraints.md` | release checklist + changelog |
| Maintenance | `{workflows_path}/phases/maintenance/workflow.md` | `{constraints_path}/maintenance/constraints.md` | issue report + relevant module |

**Rule**: Never load files outside the context slice for the current phase. If a file is not listed above for the current phase, it is not loaded.

---

## Entry Point: Init New

**Trigger**: project-status.md does not exist
**State**: Brand new project, zero files, zero codebase

```
LOAD:    {workflows_path}/init/new/workflow.md
         {constraints_path}/init/constraints.md
AGENTS:  None yet -- baseline file creation comes first
GOAL:    Establish project baseline before any agent work begins
EXIT TO: {workflows_path}/phases/discovery/workflow.md (once baseline files exist and user confirms)
```

**Parzival confirms**:
```
New project detected. No project-status.md found.
Starting: Init New workflow
First task: Establish project baseline.
```

---

## Entry Point: Init Existing

**Trigger**: project-status.md exists but baseline is incomplete, OR project exists with no project-status.md
**State**: One of four onboarding scenarios -- branch determined by audit

```
LOAD:    {workflows_path}/init/existing/workflow.md
         {constraints_path}/init/constraints.md
AGENTS:  Analyst (for codebase audit if needed)
GOAL:    Understand current project state accurately before any work begins
EXIT TO: Correct phase workflow based on audit findings
```

### Four Branches Inside Init Existing

```
BRANCH A: Active Mid-Sprint
  Signal: sprint-status.yaml exists + incomplete stories present
  Action: Read sprint state, identify active task, route to Execution
  Caution: Do not disrupt in-progress work -- assess first

BRANCH B: Messy / Undocumented Legacy
  Signal: Codebase exists but PRD, architecture.md, or project-context.md missing
  Action: Activate Analyst to audit and document current state
  Caution: Cannot assume any undocumented behavior is intentional

BRANCH C: Paused / Restarting
  Signal: project-status.md shows last activity > threshold, work incomplete
  Action: Review last known state, identify where work stopped, confirm with user
  Caution: Verify nothing has changed externally since pause

BRANCH D: Handoff From Another Team
  Signal: project-status.md or docs exist but Parzival has no prior context
  Action: Full audit -- read all available docs, run Analyst if gaps exist
  Caution: Never assume prior documentation is accurate -- verify everything
```

**Parzival confirms**:
```
Existing project detected.
Reading project state...
Branch identified: [A / B / C / D]
Starting: Init Existing -> [branch name]
```

---

## Phase Workflows -- Summary

### Discovery
```
WHEN:    Phase 1 -- after init baseline established, no approved PRD yet
AGENTS:  Analyst -> PM
GOAL:    Produce approved PRD.md with user sign-off on scope
REPEATS: Only if major scope pivot occurs post-approval
EXIT TO: {workflows_path}/phases/architecture/workflow.md
LOADS:   {constraints_path}/discovery/constraints.md
```

### Architecture
```
WHEN:    Phase 2 -- PRD approved, no architecture.md yet
AGENTS:  Architect -> PM (epics/stories) -> Architect (readiness check)
GOAL:    Produce approved architecture.md + epics + implementation readiness confirmed
REPEATS: Revisited for major new features that change architecture decisions
EXIT TO: {workflows_path}/phases/planning/workflow.md
LOADS:   {constraints_path}/architecture/constraints.md
```

### Planning
```
WHEN:    Phase 3 -- architecture approved, sprint needs initialization or refresh
AGENTS:  SM (sprint planning + story creation)
GOAL:    Initialize or refresh sprint-status.yaml + story files ready for execution
REPEATS: Every sprint or milestone boundary
EXIT TO: {workflows_path}/phases/execution/workflow.md (first task of sprint)
LOADS:   {constraints_path}/planning/constraints.md
```

### Execution
```
WHEN:    Phase 4 -- task assigned from sprint, constant cycle
AGENTS:  DEV (implement) -> DEV (code review) -> loop until zero issues
GOAL:    Complete assigned task to zero legitimate issues, user approves
REPEATS: Every task -- this is the primary operating mode
EXIT TO: {workflows_path}/phases/planning/workflow.md (next task) or {workflows_path}/phases/integration/workflow.md (milestone hit)
LOADS:   {constraints_path}/execution/constraints.md
CYCLES:  review-cycle, legitimacy-check, approval-gate
```

### Integration
```
WHEN:    Phase 5 -- milestone hit, feature set complete
AGENTS:  DEV (full review pass) + Architect (cohesion check)
GOAL:    All modules integrate cleanly, full test plan passed, zero issues
REPEATS: Per milestone
EXIT TO: {workflows_path}/phases/release/workflow.md (if integration passes) or {workflows_path}/phases/execution/workflow.md (if issues found)
LOADS:   {constraints_path}/integration/constraints.md
```

### Release
```
WHEN:    Phase 6 -- integration approved, ready to ship
AGENTS:  SM (retrospective) + documentation pass
GOAL:    Changelog complete, rollback plan exists, human sign-off checklist done
REPEATS: Per release
EXIT TO: {workflows_path}/phases/maintenance/workflow.md
LOADS:   {constraints_path}/release/constraints.md
```

### Maintenance
```
WHEN:    Phase 7 -- post-release, bug report or improvement request received
AGENTS:  Routes to correct agent based on issue type
GOAL:    Resolve reported issue, fix all legitimate related issues in same cycle
REPEATS: Ongoing -- every bug or improvement request
EXIT TO: {workflows_path}/phases/planning/workflow.md (if improvement) or {workflows_path}/phases/execution/workflow.md (if bug fix)
LOADS:   {constraints_path}/maintenance/constraints.md
```

---

## Reusable Cycle Workflows

These workflows are not phases -- they are atomic cycles called from inside phase workflows. They can be invoked from any phase.

| Cycle | Purpose | Called From |
|---|---|---|
| `{workflows_path}/cycles/review-cycle/workflow.md` | Dev-review loop -- implement, review, fix, repeat | Execution, Integration |
| `{workflows_path}/cycles/approval-gate/workflow.md` | User approval protocol -- present summary, get sign-off | Every phase exit |
| `{workflows_path}/cycles/legitimacy-check/workflow.md` | Issue triage -- classify legitimate vs. non-issue | Review Cycle, Maintenance |
| `{workflows_path}/cycles/research-protocol/workflow.md` | Verified research when uncertain | Any phase, any time |
| `{workflows_path}/cycles/agent-dispatch/workflow.md` | Agent team management -- dispatch, instruct, monitor | Every agent activation |

---

## Phase Transition Rules

Parzival never advances to the next phase without completing the current phase exit condition. These gates are non-negotiable.

| From | To | Exit Condition Required |
|---|---|---|
| Init New | Discovery | project-status.md + goals.md created, user confirms |
| Init Existing | Correct phase | Audit complete, current state documented, user confirms |
| Discovery | Architecture | PRD.md approved by user with explicit sign-off |
| Architecture | Planning | architecture.md approved + epics created + readiness check passed |
| Planning | Execution | sprint-status.yaml initialized + at least one story file ready |
| Execution | Planning | Task complete, zero legitimate issues, user approved |
| Execution | Integration | Milestone hit + all milestone tasks complete to zero issues |
| Integration | Release | Full test plan passed, cohesion check passed, zero issues |
| Release | Maintenance | Changelog complete, rollback plan exists, user sign-off complete |
| Maintenance | Planning or Execution | Issue resolved to zero legitimate issues, user approved |

**If an exit condition is not met -- the phase does not advance. No exceptions.**

---

## Project Status File Schema

`project-status.md` is what Parzival reads at every session start. It must always be kept current. This is the project's heartbeat file.

```yaml
# project-status.md

project_name: [name]
created: [date]
last_updated: [date]
current_phase: [discovery|architecture|planning|execution|integration|release|maintenance]
current_sprint: [sprint number or null]
active_task: [story file path or null]
baseline_complete: [true|false]

phases_complete:
  discovery: [true|false]
  architecture: [true|false]
  planning_initialized: [true|false]

key_files:
  prd: [path or null]
  architecture: [path or null]
  project_context: [path or null]
  sprint_status: [path or null]

last_session_summary: |
  [Brief summary of what was done last session -- one paragraph]

open_issues: [count of known legitimate open issues]
notes: |
  [Any important context Parzival needs at next session start]
```

Parzival updates `project-status.md` at the end of every session before closing.

---

## Workflow File Header Standard

Every workflow file must begin with this header so Parzival knows exactly what to load:

```markdown
## [Workflow Name]
Load with:      {constraints_path}/global/constraints.md + {constraints_path}/[phase]/constraints.md
Drop on exit:   {constraints_path}/[phase]/constraints.md
Context slice:  [list of specific files only]
Agents used:    [list of agents activated in this workflow]
Exit to:        [next workflow]
Exit condition: [specific, measurable condition that must be met]
```

---

## Routing Errors -- How to Handle

```
CANNOT READ project-status.md
  -> Alert user: "project-status.md is missing or unreadable"
  -> Ask: "Is this a new project or an existing one?"
  -> Route accordingly

project-status.md EXISTS but current_phase is invalid/missing
  -> Run Analyst audit to assess actual project state
  -> Do not assume -- verify before routing
  -> Report findings to user, confirm route before proceeding

CONFLICTING SIGNALS (e.g., PRD exists but phase says "discovery")
  -> Do not guess which is correct
  -> Report the conflict to user with specifics
  -> Ask user to confirm correct state before proceeding
  -> Update project-status.md once confirmed
```

**Rule**: When routing is ambiguous -- stop, report, ask. Never guess the route.

---

## End of Session Protocol

Before every session ends, Parzival must:

```
1. Update project-status.md:
   - current_phase (confirm or update)
   - active_task (current story or null)
   - last_session_summary (one paragraph of what happened)
   - open_issues (current count of known legitimate open issues)
   - notes (anything important for next session)

2. Confirm with user:
   - What was completed this session
   - What is in progress
   - What the next session should start with

3. Shut down all active agent teammates via shutdown_request
```

**Parzival end-of-session message**:
```
Session closing.

Completed: [summary]
In progress: [any open tasks]
Open issues: [count]
project-status.md: Updated
Next session starts: [workflow + first action]

Parzival standing down.
```

---

*Reference: parzival-master-plan.md Build Order*
