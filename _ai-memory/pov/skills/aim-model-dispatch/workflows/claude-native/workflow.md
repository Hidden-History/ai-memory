---
name: claude-native
description: 'Claude Code Agent Teams — create teams, spawn teammates, coordinate via shared tasks'
---

# Claude-Native Workflow — Agent Teams

How to create and manage Claude Code Agent Teams for all Claude-provider dispatches.

---

## Prerequisites

- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` = `1` in settings.json
- tmux installed and available in PATH
- `teammateMode`: `auto` (default) — uses tmux split panes when available
- Claude Code v2.1.32 or later

---

## Applicable Constraints

Do not duplicate — reference only. See source files for full definitions.

**Global (always active):**
GC-01, GC-04, GC-09, GC-10, GC-19, GC-20, GC-21

**Execution phase (when active):**
EC-01, EC-04, EC-05, EC-06, EC-09, EC-10

**Process Rules (project-status.md):**
- Rule 3: Fresh agents for EVERY role — never reuse across tasks
- Rule 4: CWD must be project root (document_pipeline/) before spawn — NEVER DocIntel/
- Rule 5: /bmad-bmm-code-review for reviews, /bmad-agent-bmm-dev for implementation only
- Rule 6: Dual review mandatory (Sonnet + Opus)
- Rule 7: One story per SM dispatch — shutdown after each
- Rule 8: Don't rush-nudge idle agents
- Rule 9: Two-phase BMAD activation (activate → wait for idle → send instruction)
- Rule 11: ALWAYS include explicit story ID + file list in instruction
- Rule 13: mode: bypassPermissions for ALL agent spawns
- Rule 14: Send workflow command + instruction in same message after activation menu
- Rule 15: Claude models MUST use Agent Teams
- Rule 16: Team-builder is the mandatory entry point

---

## MANDATORY: Verify Working Directory

**Before ANY TeamCreate or Agent spawn, verify CWD is the project root.**

Teammates inherit the lead's working directory. If CWD is wrong, teammates
cannot find BMAD skills, story files, or project context.

```
# Run this check EVERY TIME before creating a team:
Bash: pwd
# MUST output the project root containing _ai-memory/ directory
# e.g., /mnt/e/projects/dev-rag-stack/document_pipeline
# If CWD is DocIntel/ or any subdirectory: cd to project root FIRST

Bash: ls _ai-memory/ > /dev/null 2>&1 && echo "OK: project root" || echo "FAIL: wrong directory"
# MUST output "OK: project root"
# If "FAIL": stop, cd to project root, re-verify
```

**DO NOT PROCEED if this check fails.** This is Rule 4 enforcement.

---

## Create a Team

TeamCreate establishes the team and shared task list. Parzival becomes team lead.

```
TeamCreate:
  team_name: "sprint-2-story-4.1"
  description: "Story 4.1: Base Stage Class and Pipeline Message Schemas"
```

One team per session. Clean up previous team before creating new.

---

## Create Tasks

TaskCreate defines work items. Teammates claim and complete tasks from the shared list.

```
TaskCreate:
  subject: "Implement Story 4.1: Base Stage Class"
  description: "[full instruction]"
```

Use addBlockedBy for dependencies between tasks. The system unblocks automatically when dependencies complete.

---

## Spawn Teammates

Agent tool with team_name spawns a visible teammate in its own tmux pane.

```
Agent:
  name: "dev-pipeline"
  team_name: "sprint-2-story-4.1"
  model: sonnet
  mode: bypassPermissions
  run_in_background: true
  prompt: "[activation command or full instruction]"
```

Spawn multiple teammates in parallel by including multiple Agent calls in the same message.

---

## Communicate with Teammates

SendMessage delivers messages to teammates. Idle teammates wake up on message receipt.

```
SendMessage:
  to: "dev-pipeline"
  summary: "DS Story 4.1 implementation"
  message: "[workflow command + instruction]"
```

Messages from teammates are delivered automatically — no polling needed.

---

## Assign Tasks

TaskUpdate assigns tasks to teammates. Teammates can also self-claim unassigned, unblocked tasks.

```
TaskUpdate:
  taskId: "1"
  owner: "dev-pipeline"
  status: "in_progress"
```

---

## Plan Approval Mode

Use `mode: plan` when teammates should plan before implementing. Teammate works read-only until lead approves.

```
Agent:
  name: "architect"
  team_name: "architecture-review"
  model: opus
  mode: plan
  run_in_background: true
  prompt: "/bmad-agent-bmm-architect"
```

Teammate sends plan_approval_request when ready. Lead reviews and approves or rejects with feedback.

---

## Monitor Teammates

- Teammates work in their own tmux panes — visible to user
- Idle notifications are normal — teammate finished its turn, waiting for input
- TaskList shows progress across all tasks
- Shift+Down cycles through teammates; click tmux pane for direct interaction
- SendMessage for status checks or intervention

---

## Shutdown and Cleanup

Shutdown each teammate when their work is complete and accepted:

```
SendMessage:
  to: "dev-pipeline"
  message: {type: "shutdown_request", reason: "Task complete"}
```

After ALL teammates shut down, clean up:

```
TeamDelete
```

TeamDelete fails if active teammates remain. Always shutdown all teammates first.
Always clean up from the lead session, not from a teammate.

---

## Examples

### Single DEV Story Implementation

```
TeamCreate:
  team_name: "sprint-2-story-4.1"
  description: "Story 4.1: Base Stage Class"

TaskCreate:
  subject: "Implement Story 4.1"
  description: "[full instruction]"

Agent:
  name: "dev-pipeline"
  team_name: "sprint-2-story-4.1"
  model: sonnet
  mode: bypassPermissions
  run_in_background: true
  prompt: "/bmad-agent-bmm-dev"

# Wait for idle (persona loaded, menu shown)

SendMessage:
  to: "dev-pipeline"
  message: "DS\n[full instruction with story ID, files, ACs, scope, DONE WHEN]"

TaskUpdate:
  taskId: "1"
  owner: "dev-pipeline"
  status: "in_progress"
```

### Parallel Dual Review

```
TeamCreate:
  team_name: "sprint-2-review-4.1"
  description: "Story 4.1 dual review"

TaskCreate:
  subject: "Review Story 4.1 (Sonnet)"
  description: "[review instruction]"

TaskCreate:
  subject: "Review Story 4.1 (Opus)"
  description: "[review instruction]"

# Spawn both in same message for parallel launch
Agent:
  name: "review-sonnet"
  team_name: "sprint-2-review-4.1"
  model: sonnet
  mode: bypassPermissions
  run_in_background: true
  prompt: "/bmad-agent-bmm-dev"

Agent:
  name: "review-opus"
  team_name: "sprint-2-review-4.1"
  model: opus
  mode: bypassPermissions
  run_in_background: true
  prompt: "/bmad-agent-bmm-dev"

# After both idle, send review instructions
SendMessage:
  to: "review-sonnet"
  message: "CR\n[review instruction]"

SendMessage:
  to: "review-opus"
  message: "CR\n[review instruction]"
```

### Multi-Track Parallel Sprint

```
TeamCreate:
  team_name: "sprint-2-parallel"
  description: "Parallel: Track A (4.2) + Track B (11.1) + Track C (14.2)"

TaskCreate:
  subject: "Implement Story 4.2"
  description: "[instruction]"

TaskCreate:
  subject: "Implement Story 11.1"
  description: "[instruction]"

TaskCreate:
  subject: "Implement Story 14.2"
  description: "[instruction]"

# Spawn 3 teammates in parallel
Agent:
  name: "dev-pipeline"
  team_name: "sprint-2-parallel"
  model: sonnet
  mode: bypassPermissions
  run_in_background: true
  prompt: "/bmad-agent-bmm-dev"

Agent:
  name: "dev-services"
  team_name: "sprint-2-parallel"
  model: sonnet
  mode: bypassPermissions
  run_in_background: true
  prompt: "/bmad-agent-bmm-dev"

Agent:
  name: "dev-observability"
  team_name: "sprint-2-parallel"
  model: sonnet
  mode: bypassPermissions
  run_in_background: true
  prompt: "/bmad-agent-bmm-dev"

# After idle, send instructions — each owns different files
```

---

## Limitations

- No session resumption for teammates — spawn new after `/resume`
- Task status can lag — check manually if stuck
- One team per session
- No nested teams — only the lead spawns teammates
- Permissions inherited from lead at spawn time
