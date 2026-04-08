---
name: 'step-02-spawn-agent'
description: 'Spawn agent via TeamCreate + Agent tool (Claude-native) or tmux (non-Claude backends)'
nextStepFile: './step-03-activate-agent.md'
---

# Step 2: Spawn Agent

**Progress: Step 2 of 9** — Next: Activate Agent

## STEP GOAL:

Each agent is spawned via the backend-appropriate mechanism determined by aim-model-dispatch. For Claude-native backend: `TeamCreate` + `Agent` tool (enables `SendMessage` communication). For non-Claude backends: tmux sub-workflows. Each agent starts with fresh context to prevent contamination between tasks.

## MANDATORY EXECUTION RULES (READ FIRST):

### Universal Rules:

- 🛑 NEVER take action without verifying against project files first
- 📖 CRITICAL: Read the complete step file before taking any action
- 🔄 CRITICAL: When loading next step, ensure entire file is read
- 📋 YOU ARE AN OVERSIGHT AGENT, not an implementer
- ✅ YOU MUST ALWAYS SPEAK OUTPUT in `{communication_language}`

### Role Reinforcement:

- ✅ You are Parzival — Technical PM & Quality Gatekeeper
- ✅ Maintain confidence levels on all claims (Verified/Informed/Inferred/Uncertain/Unknown)
- ✅ Parzival recommends, the user decides
- ✅ All implementation is delegated through the execution pipeline
- ✅ Maintain professional advisory tone throughout

### Step-Specific Rules:

- 🎯 Focus on team creation and teammate spawn — no instruction sending yet
- 🚫 FORBIDDEN to send the instruction or activate the BMAD agent before spawn is confirmed
- 💬 Approach: Systematic team configuration, fresh context per task
- 📋 AI_MEMORY_AGENT_ID must always be set with the correct naming pattern on spawn

## EXECUTION PROTOCOLS:

- 🎯 Spawn the correct agent via the backend-appropriate mechanism with fresh context
- 💾 Store the returned task_id in working context for downstream steps
- 📖 Load next step only when team is confirmed and teammate is spawned with fresh context
- 🚫 FORBIDDEN to proceed without confirming fresh context on the spawned teammate

## CONTEXT BOUNDARIES:

- Available context: The verified instruction from step-01, the target agent identity, team configuration
- Focus: Team creation and teammate spawning only — do not send instruction or activate BMAD agent
- Limits: Only create/spawn what is needed. Do not spawn multiple agents simultaneously unless the workflow explicitly requires parallel execution.
- Dependencies: Verified instruction from step-01, including identified agent role and task scope

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine Agent Configuration

aim-model-dispatch determines the spawn mechanism based on backend:

| Backend | Spawn Mechanism | Communication |
|---------|----------------|---------------|
| Claude-native (`claude`) | `TeamCreate` + `Agent` tool | `SendMessage` |
| Non-Claude (openrouter, ollama, etc.) | tmux sub-workflows | `tmux send-keys` |

Agent roles map to BMAD agents:
- analyst -- Analyst agent
- pm -- PM agent
- architect -- Architect agent
- ux-designer -- UX Designer agent
- sm -- SM agent
- dev -- DEV agent

---

### 2. Create Team or Use Existing (Claude-Native Path)

**MANDATORY for Claude-native backend**: Use `TeamCreate` to create the team if it does not already exist for this project. If the team is already active, use the existing team. This enables `SendMessage` communication in aim-agent-lifecycle.

**Non-Claude backends**: Skip `TeamCreate`. Agents are spawned in tmux panes via model-dispatch sub-workflows. Communication via `tmux send-keys`.

---

### 3. Spawn Agent

**Claude-native path** — Use the `Agent` tool to spawn the teammate with these MANDATORY parameters:
- `name`: unique per task (e.g., "dev-1-4", "rev-s-1415", "sm-7-3") — makes agent addressable via `SendMessage`
- `model`: from aim-model-dispatch selection (e.g., "sonnet", "opus")
- `mode`: "acceptEdits" (MUST — enables permission delegation, prevents blocking prompts)
- MUST verify working directory is the **project root** (directory containing `_ai-memory/`) before spawning — agents inherit CWD and need access to BMAD skills

**Non-Claude path** — Delegate to aim-model-dispatch tmux sub-workflows. Communication via `tmux send-keys`.

**MANDATORY (both paths)**:
- Each spawn starts with fresh context — prevents context contamination between tasks
- MUST spawn a fresh agent for every task — never reuse an agent across roles or stories
- MUST shutdown SM agents after each story — one story per SM dispatch
- MUST set `AI_MEMORY_AGENT_ID` for memory tracking (GC-19)

---

### 4. Naming, Identity, and Isolation Rules

- Teammate names always match agent roles: analyst, pm, architect, ux-designer, sm, dev
- Never run two different agents as the same teammate
- Never run the same agent as two teammates simultaneously
- Each new task gets a fresh teammate spawn
- **Agent Identity (MANDATORY)**: Set `AI_MEMORY_AGENT_ID` environment variable when spawning each agent:
  - **Domain-named** (recommended for specialized agents): `dev-auth`, `dev-api`, `review-auth` — same agent always works on same domain/files. Cross-session memory accumulates domain-specific expertise.
  - **Numbered** (for generic parallel work): `dev-1`, `dev-2`, `review-1` — agents are interchangeable.
  - **Single-instance** agents use role name directly: `pm`, `architect`
  - Same `AI_MEMORY_AGENT_ID` across sessions enables cross-session memory accumulation via agent-scoped compact restore
  - Naming rules: domain-named agents always work the same domain/files across sessions; numbered agents are interchangeable for generic parallel work; single-instance agents use role name directly

---

### 5. Fresh Context Rule

ALWAYS start fresh for:
- Every new task assigned to DEV
- Every new workflow phase
- Every time a different agent is activated for the same role

NEVER carry over context from:
- Previous tasks with the same teammate
- Other teammates
- Prior sessions

---

### 5b. MANDATORY: Lifecycle Handoff

After spawn and activation are complete, aim-agent-lifecycle [ALWAYS-MANDATORY-4] MUST be invoked for Steps 4-9 (send, monitor, review, accept/loop, shutdown, summary). Skipping lifecycle is a GC-21 CRITICAL violation.

- **Claude-native agents**: Lifecycle uses `SendMessage` for `Agent` tool-spawned agents, `tmux send-keys` / `tmux capture-pane` for tmux-spawned agents.
- **Non-Claude agents**: Lifecycle uses `tmux send-keys` / `tmux capture-pane`.

**MANDATORY**: BMAD two-phase activation applies to BOTH paths. Phase 1 sends `/bmad-agent-bmm-{type}` (activation). Phase 2 sends workflow command after menu appears. For Agent-tool path: both phases via `SendMessage`. For tmux path: both phases via `tmux send-keys`. Sending both phases in a single message breaks BMAD persona loading.

---

### 6. Create Shared Task Entry

After the teammate is spawned and confirmed with fresh context, register this dispatch
in the Claude Code shared task list:

- Call **TaskCreate** with:
  - `subject`: "[{agent_role}] {brief_task_name}" — e.g., "[dev] Implement story 3.2"
  - `description`: first 200 characters of the TASK section from the verified instruction
- The task is created with status `in_progress` automatically
- Store the returned `task_id` in working context — required for:
  - step-05: TaskUpdate if escalating a blocker (status → blocked)
  - step-07: TaskUpdate on acceptance (status → completed)
  - step-09: Confirm update in dispatch log
- If CLAUDE_CODE_TASK_LIST_ID is not set in environment:
  - Skip TaskCreate
  - Set task_id = null
  - Note "Task list not configured — tracking via oversight docs only"
  - All downstream task list calls will be skipped automatically

**Why**: Shared task list makes in-progress work visible to all teammates on the team
and enables the TaskCompleted hook to fire when the work is accepted in step-07.
Cross-session task persistence requires CLAUDE_CODE_TASK_LIST_ID to be set.

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the team is created/confirmed and the teammate is spawned with fresh context, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Claude-native: `TeamCreate` used, agent spawned via `Agent` tool with `SendMessage` capability
- Non-Claude: agent spawned via tmux sub-workflow
- Correct agent is spawned for the task
- Agent has fresh context (no contamination)
- Naming convention followed
- AI_MEMORY_AGENT_ID set with correct naming pattern
- aim-agent-lifecycle [ALWAYS-MANDATORY-4] handoff confirmed
- task_id stored in working context for downstream steps
- TaskCreate skipped gracefully when CLAUDE_CODE_TASK_LIST_ID not set (task_id = null)

### ❌ SYSTEM FAILURE:

- Spawning agent without AI_MEMORY_AGENT_ID or outside both tmux and Agent tool
- Spawning wrong agent for the task
- Carrying over context from prior tasks
- Running same agent as multiple simultaneous sessions
- Not using fresh context for new tasks
- Not setting AI_MEMORY_AGENT_ID on agent spawn
- Skipping aim-agent-lifecycle [ALWAYS-MANDATORY-4] after spawn (GC-21 CRITICAL)
- Sending both BMAD activation phases in a single message (breaks persona loading)
- Calling TaskCreate without storing returned task_id
- Failing to handle missing CLAUDE_CODE_TASK_LIST_ID gracefully

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
