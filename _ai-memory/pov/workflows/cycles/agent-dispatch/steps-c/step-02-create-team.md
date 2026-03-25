---
name: 'step-02-create-team'
description: 'Create a Claude Code team and spawn the appropriate agent as a teammate'
nextStepFile: './step-03-activate-agent.md'
---

# Step 2: Create Team and Spawn Teammate

**Progress: Step 2 of 9** — Next: Activate Agent

## STEP GOAL:

Each agent runs as a teammate within a Claude Code team. Parzival creates the team (if not already created) and spawns the appropriate agent teammate. Each teammate starts with fresh context to prevent contamination between tasks.

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

- 🎯 Create or confirm team, then spawn the correct teammate with fresh context
- 💾 Store the returned task_id in working context for downstream steps
- 📖 Load next step only when team is confirmed and teammate is spawned with fresh context
- 🚫 FORBIDDEN to proceed without confirming fresh context on the spawned teammate

## CONTEXT BOUNDARIES:

- Available context: The verified instruction from step-01, the target agent identity, team configuration
- Focus: Team creation and teammate spawning only — do not send instruction or activate BMAD agent
- Limits: Only create/spawn what is needed. Do not spawn multiple agents simultaneously unless the workflow explicitly requires parallel execution.
- Dependencies: Verified instruction from step-01, including identified agent role and task scope

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Determine Team Configuration

Use TeamCreate to create teams and the Agent tool to spawn teammates.

Teammate roles map to BMAD agents:
- analyst -- Analyst agent
- pm -- PM agent
- architect -- Architect agent
- ux-designer -- UX Designer agent
- sm -- SM agent
- dev -- DEV agent

---

### 2. Create Team or Use Existing

Use TeamCreate to create the team if it does not already exist for this project. If the team is already active, use the existing team.

---

### 3. Spawn Teammate via Agent Tool

Use the Agent tool to spawn the appropriate teammate:
- Each teammate spawn starts with fresh context
- This prevents context contamination between tasks

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

- Team is created or confirmed active
- Correct teammate is spawned for the task
- Teammate has fresh context (no contamination)
- Naming convention followed
- AI_MEMORY_AGENT_ID set with correct naming pattern
- task_id stored in working context for downstream steps
- TaskCreate skipped gracefully when CLAUDE_CODE_TASK_LIST_ID not set (task_id = null)

### ❌ SYSTEM FAILURE:

- Spawning wrong teammate for the task
- Carrying over context from prior tasks
- Running same agent as multiple simultaneous teammates
- Not using fresh context for new tasks
- Not setting AI_MEMORY_AGENT_ID on agent spawn
- Calling TaskCreate without storing returned task_id
- Failing to handle missing CLAUDE_CODE_TASK_LIST_ID gracefully

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
