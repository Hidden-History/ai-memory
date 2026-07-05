# WORKFLOW-MAP.md -- Master Router

> **Purpose**: Parzival reads this file at every session start to determine project state and route to the correct workflow
> **Loaded**: Immediately after parzival.md and global constraints at activation
> **Authority**: This is the single source of truth for workflow routing decisions
> **Reference**: the Parzival master-plan design history

---

## How to Use This File

This file is not a workflow itself. It is the routing engine. Every session starts here. Parzival reads the project state, follows the decision tree, loads the correct workflow and constraint files, and then operates within that workflow.

**Session start sequence -- always in this order**:
```
1. parzival.md              -> identity and constraints active
2. {constraints_path}/global/constraints.md -> GC-1 through GC-21 active
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

For per-phase WHEN/AGENTS/GOAL/REPEATS/EXIT details, see each phase's workflow.md header or `{project-root}/_ai-memory/pov/references/workflow-map-details.md` ## Phase Summaries.

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

## User-Invoked Commands

The decision tree above routes Parzival automatically by project state. In addition, the user can invoke session commands at any time — these are **user-driven**, not state-driven, and do not appear in the Master Decision Tree.

Authoritative registry: `pov/module-help.csv` (rows where `phase = 0-session`).

| Command | Code | Workflow File | Purpose |
|---|---|---|---|
| `pov_session_start` | ST | `{workflows_path}/session/start/workflow.md` | Full session initialization: load context, compile status, present recommendation, wait for direction |
| `pov_session_status` | SU | `{workflows_path}/session/status/workflow.md` | Quick read-only status snapshot — does not initialize a session |
| `pov_session_blocker` | BL | `{workflows_path}/session/blocker/workflow.md` | Analyze and resolve a reported blocker |
| `pov_session_decision` | DC | `{workflows_path}/session/decision/workflow.md` | Structure a decision with options and record it |
| `pov_session_verify` | VE | `{workflows_path}/session/verify/workflow.md` | Run verification protocol (story / code / production types) |
| `pov_session_handoff` | HO | `{workflows_path}/session/handoff/workflow.md` | Create mid-session state snapshot for handoff |
| `pov_session_close` | CL | `{workflows_path}/session/close/workflow.md` | Full closeout: summary + handoff + session ends |

**Routing distinction:**
- Phase/init workflows (sections above): loaded automatically by the Master Decision Tree based on `project-status.md` state
- Session commands (this section): loaded on explicit user invocation, independent of current phase

**Overlap with phase verification:** `session/verify` is the on-demand audit runner. It is distinct from (a) `cycles/legitimacy-check` — atomic issue classification, invoked by review cycles and maintenance — and (b) `phases/execution/steps-c/step-05-verify-fixes.md` — the four-source fix gate inside the execution review loop. See [Verification Hierarchy](#verification-hierarchy) below.

## Verification Hierarchy

Parzival distinguishes three verification surfaces. They are not interchangeable — each has a defined trigger, scope, and output. Use this table to identify which surface applies before invoking any "verify" work.

| Surface | File | Trigger | Scope | Output | Composes With |
|---|---|---|---|---|---|
| **Legitimacy Check** | `{workflows_path}/cycles/legitimacy-check/workflow.md` | Any issue surfaced during review, audit, or maintenance | One issue at a time | LEGITIMATE / NON-ISSUE / UNCERTAIN classification with project file citations | Called from Review Cycle (per-issue) and Maintenance (per bug report) |
| **Fix Verification (In-Cycle)** | `{workflows_path}/phases/execution/steps-c/step-05-verify-fixes.md` | Review cycle exits with zero legitimate issues; before summary preparation | All fixes applied during the current review cycle | Four-source pass (PRD / architecture / standards / best-practices) — PASS or re-enter review cycle | Runs inside Execution phase; gates Step 6 (summary) |
| **Verification Protocol (On-Demand)** | `{workflows_path}/session/verify/workflow.md` | User explicitly invokes `pov_session_verify` | One of three verification types: Story / Code / Production | Verification report for the specified type | Invoked by user, independent of current phase |

**How they compose:**
- A **review cycle** loops: implement → review → classify (→ legitimacy-check per issue) → fix → repeat until zero legitimate issues.
- When review exits clean, **fix-verification** (step-05) runs as a gate against four authoritative sources before the user sees any summary.
- **session/verify** is a separate, user-driven audit — not part of any review loop. It produces a verification report against the chosen type's template (story / code / production).

**Decision rule — which surface to use:**
- An issue arose during review or maintenance → **legitimacy-check**
- Review cycle just exited clean; need to confirm fixes before presenting → **fix-verification** (automatic per phases/execution)
- User says "verify [X]" outside any active cycle → **session/verify**; pick the type based on what X is (completed story → Story; code diff → Code; deployment → Production)

**Never:** run fix-verification as a substitute for legitimacy-check; run legitimacy-check on already-classified issues; combine verification types in a single session/verify run.

---

For phase exit conditions, see each phase's workflow.md or `{project-root}/_ai-memory/pov/references/workflow-map-details.md` ## Phase Transition Rules.

---

For project-status.md YAML schema, see `{project-root}/_ai-memory/pov/references/workflow-map-details.md` ## project-status.md Schema. **ENFORCE: each YAML field is short-form; long prose belongs in session-logs/SESSION_HANDOFF_*.md.**

---

Workflow file header standard: see `{project-root}/_ai-memory/pov/references/workflow-map-details.md`.

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

End-of-session protocol is implemented by `session/close/workflow.md`. For the prose narrative, see `{project-root}/_ai-memory/pov/references/workflow-map-details.md`.

---

*Reference: the Parzival master-plan design history*
