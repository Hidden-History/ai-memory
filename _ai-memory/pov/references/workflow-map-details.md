---
type: reference
load: on-demand
description: Lazy-loaded reference detail for WORKFLOW-MAP.md (phase summaries, transition rules, schema, header standard, end-of-session prose). Consulted only when authoring/auditing workflows or writing project-status.md.
---

# workflow-map-details.md -- Lazy-Loaded Reference

This file holds the reference-only sections extracted from WORKFLOW-MAP.md to keep the eager routing surface compact. Load on-demand only when authoring/auditing workflows or writing `project-status.md`.

---

## Phase Summaries

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
AGENTS:  Architect -> PM (epics/stories) -> Architect (readiness check via [IR] bmad-check-implementation-readiness)
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

## Phase Transition Rules

Parzival never advances to the next phase without completing the current phase exit condition. These gates are non-negotiable.

| From | To | Exit Condition Required |
|---|---|---|
| Init New | Discovery | project-status.md + goals.md created, user confirms |
| Init Existing | Correct phase | Audit complete, current state documented, user confirms |
| Discovery | Architecture | PRD.md approved by user with explicit sign-off |
| Architecture | Planning | architecture.md approved + epics created + readiness check passed (dispatch [IR] bmad-check-implementation-readiness) |
| Planning | Execution | sprint-status.yaml initialized + at least one story file ready + test design reviewed ([TA] bmad-testarch-test-design) |
| Execution | Planning | Task complete, zero legitimate issues, user approved |
| Execution | Integration | Milestone hit + all milestone tasks complete to zero issues |
| Integration | Release | Full test plan passed, cohesion check passed, zero issues |
| Release | Maintenance | Changelog complete, rollback plan exists, user sign-off complete |
| Maintenance | Planning or Execution | Issue resolved to zero legitimate issues, user approved |

**If an exit condition is not met -- the phase does not advance. No exceptions.**

---

## project-status.md Schema

`project-status.md` is what Parzival reads at every session start. It must always be kept current. This is the project's heartbeat file.

The heartbeat carries its own maintenance contract as front-matter (the cap the
Step 4 gate reads), above the routing body. This schema is the single source of
truth shared by the `project-status.md` template seed and session-close step-02:

```yaml
---
class: heartbeat
read_path: whole-file
owns: "routing-machine state + live_record pointer"
cap_lines: 60
cap_kb: 6
rotation_trigger: none
archive_target: N/A
index_file: N/A
reconciliation: "overwrite-in-place every close; narrative lives in SESSION_WORK_INDEX + handoff, NEVER here"
---
# project-status.md

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

live_record: oversight/SESSION_WORK_INDEX.md
last_session_summary: "[≤200 chars — date + PM# + what shipped/blocked/next. Full narrative lives in session-logs + SESSION_WORK_INDEX, NOT here.]"
open_issues: [count of known legitimate open issues]
```

**Field caps (enforced — the Step 4 gate reads `cap_lines`/`cap_kb`):**
- Whole file: ≤60 lines / ≤6 KB.
- `last_session_summary`: ≤200 chars, one line.

### DO ✓

```yaml
last_session_summary: "2026-05-13 PM#268: shipped EDIT-G (CREED/PERSONA slim −2,141 chars); blocked on F (scaffold cycle); next: re-plan EDIT-F as smaller atomic edits."
```

### DO NOT ✗

```yaml
last_session_summary: |
  In this session we began by reviewing the verification report from session 25 which had flagged 39 FAIL results across 24 agents and 702 tests, then we determined that all 5 of the "genuine defects" identified as D-1 through D-5 were in fact false positives caused by stale installed code in the live `_ai-memory/` directory differing from the current source on branch `feature/parzival-2.1` at commit 41496fd, after which we updated the MEMORY.md feedback file to add the `reinstall-before-verify` feedback entry pointing at feedback_reinstall_before_verify.md and then we discussed the 25 stale test specs identified as technical debt with priority ordering (Agent 18 full rewrite first, then 6, 14, 17, 7, 12, 22) before moving on to plan the next verification round which will require reinstalling from the current source HEAD before re-running the 4-batch Sonnet sub-agent verification protocol against the updated TESTING-SOURCE-OF-TRUTH.md...
```

(The DO NOT example is a real anti-pattern from the testV2 project — a 200+ word narrative crammed into `last_session_summary` instead of the proper session-logs file.)

Long-form session narrative belongs in `oversight/session-logs/SESSION_HANDOFF_<DATE>.md`, not in `project-status.md`. The status file is a pointer, not a journal.

The `project-status.md` heartbeat is overwritten in place by session-close
step-02 (one datum, one home); see `session/close/steps-c/step-02-update-tracking.md`.

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

## End of Session Protocol

*Note: end-of-session protocol is implemented by `session/close/workflow.md`; this section is reference prose only.*

Before every session ends, Parzival must:

```
1. project-status.md heartbeat — written by session-close step-02
   (session/close/steps-c/step-02-update-tracking.md), which overwrites it in
   place from the 60/6 schema. Do NOT write it from here: one datum, one home.

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

*Reference: lazy-loaded detail companion to WORKFLOW-MAP.md.*
