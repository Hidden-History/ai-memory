---
name: claude-native
description: 'Claude Code Agent Teams — create teams, spawn teammates, coordinate via shared tasks'
type: reference
---

# Claude-Native Workflow — Agent Teams

> Reference doc — no executable step chain.

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
- Rule 5: /bmad-code-review for reviews, /bmad-agent-dev for implementation only
- Rule 6: Dual review mandatory (Sonnet + Opus)
- Rule 7: One story per story-creation dispatch — shutdown after each
- Rule 8: Idle is noise — an idle ping means the teammate is working; wait, no nudges, no on-disk checks (see /aim-agent-dispatch Playbook)
- Rule 9: Two-phase BMAD activation (activate → wait for the teammate's greeting/menu SendMessage reply → send instruction)
- Rule 11: ALWAYS include explicit story ID + file list in instruction
- Rule 13: mode: auto for ALL agent spawns
- Rule 14: In planning mode, send the workflow command after the menu; the task/recommendation-request follows as its own message (GC-20) — never bundled with activation
- Rule 15: Claude models MUST use Agent Teams
- Rule 16: Team-builder is the mandatory entry point

---

## MANDATORY: Verify Working Directory (Workspace Root Sentinel)

**Before EVERY TeamCreate or Agent spawn, verify CWD is the workspace root.**

Teammates inherit the lead's working directory. If CWD is wrong, teammates
cannot find BMAD skills, oversight docs, or project context. The workspace root
is distinguished from a nested source repo (e.g., `ai-memory/`) by the
co-presence of all three sentinel directories: `_ai-memory/`, `_bmad/`, and
`oversight/`. Checking only `_ai-memory/` produces a false positive when CWD
has drifted into a source repo clone.

```
# Scope: dev workspace dispatches only. End-user installs (~/.ai-memory/) launch
# via skill installer wrappers and do not require this sentinel.
# Run this check EVERY TIME before creating a team or spawning an agent:
Bash: pwd
# MUST output the workspace root (e.g., /mnt/e/projects/dev-ai-memory)

Bash: bash "${SKILL_DIR:=$(pwd)/_ai-memory/pov/skills/aim-model-dispatch}/scripts/lib/cwd_sentinel.sh" --variant loose
# MUST output "OK: workspace root"
# If "FAIL": stop, cd to workspace root, re-verify.
# A single-marker check (e.g., ls _ai-memory/) is INSUFFICIENT -- a nested
# source repo (ai-memory/) also contains _ai-memory/ and will pass.
```

**DO NOT PROCEED if this check fails.** The sentinel is enforced on every spawn,
not just the first one in a session -- `cd` drifts silently across Bash calls.

---

## MANDATORY: Verify Agent Teams Prerequisites

**Before the first TeamCreate, verify the Agent Teams prerequisites above are live.**

The Prerequisites list is not self-enforcing -- a missing
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` or a `teammateMode` set to a non-team
mode (`in-process`) silently degrades parallel-team dispatch. This preflight is
**fire-only-if-missing**: silent when the prerequisites hold, loud with exact
remediation (and non-zero) when one is missing.

```
Bash: bash "${SKILL_DIR:=$(pwd)/_ai-memory/pov/skills/aim-model-dispatch}/scripts/lib/preflight_agent_teams.sh"
# No output + exit 0 -> prerequisites satisfied, proceed.
# Any output on stderr + exit 1 -> add the flag / fix teammateMode as instructed, then re-run.
```

**DO NOT PROCEED if this check fails.** Tell the user exactly what to add (the
script prints the remediation). Same guard runs in `/aim-agent-lifecycle` Step 1
for tmux dispatch, so both dispatch paths enforce the identical prerequisites.

---

## Create a Team (not required — single implicit team)

A session has a single implicit team; `TeamCreate` is **not required** and the per-spawn team-name
param is deprecated/ignored. Spawning a teammate via the Agent tool (below) is sufficient — the shared task
list exists without an explicit team. Parzival is team lead. If you do call TeamCreate, pass only a
`description`.

```
TeamCreate:
  description: "Story 4.1: Base Stage Class and Pipeline Message Schemas"
```

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

The Agent tool with a unique `name` spawns a visible teammate in its own tmux pane.

```
Agent:
  name: "dev-pipeline"
  model: sonnet
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-agent-dev (the BMAD dev persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."
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
  model: opus
  mode: plan
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-agent-architect (the BMAD architect persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."
```

Teammate sends plan_approval_request when ready. Lead reviews and approves or rejects with feedback.

---

## Monitor Teammates

- Teammates work in their own tmux panes — visible to user
- Idle is noise; teammate finished its turn, waiting for input — do not nudge
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
  description: "Story 4.1: Base Stage Class"

TaskCreate:
  subject: "Implement Story 4.1"
  description: "[full instruction]"

Agent:
  name: "dev-pipeline"
  model: sonnet
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-agent-dev (the BMAD dev persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

# Wait for the greeting/menu SendMessage reply (idle is noise — see /aim-agent-dispatch Playbook)

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
  model: sonnet
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-code-review (the BMAD code-review persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

Agent:
  name: "review-opus"
  model: opus
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-code-review (the BMAD code-review persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

# After both send their greeting/menu reply, send the review instruction directly (review workflow takes it — no CR menu code)
SendMessage:
  to: "review-sonnet"
  message: "[review instruction]"

SendMessage:
  to: "review-opus"
  message: "[review instruction]"
```

### Multi-Track Parallel Sprint

```
TeamCreate:
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
  model: sonnet
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-agent-dev (the BMAD dev persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

Agent:
  name: "dev-services"
  model: sonnet
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-agent-dev (the BMAD dev persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

Agent:
  name: "dev-observability"
  model: sonnet
  mode: auto
  run_in_background: true
  prompt: "Use the Skill tool to load bmad-agent-dev (the BMAD dev persona). You're activated as a teammate under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and anything the agent asks) to team-lead, then wait for my instructions before doing any work."

# After the greeting/menu SendMessage reply, send instructions — each owns different files
```

---

## Limitations

- No session resumption for teammates — spawn new after `/resume`
- Task status can lag — check manually if stuck
- One team per session
- No nested teams — only the lead spawns teammates
- Permissions inherited from lead at spawn time
