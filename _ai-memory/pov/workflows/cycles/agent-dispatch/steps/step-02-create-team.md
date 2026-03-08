---
name: 'step-02-create-team'
description: 'Create a Claude Code team and spawn the appropriate agent as a teammate'
nextStepFile: './step-03-activate-agent.md'
---

# Step 2: Create Team and Spawn Teammate

## STEP GOAL
Each agent runs as a teammate within a Claude Code team. Parzival creates the team (if not already created) and spawns the appropriate agent teammate. Each teammate starts with fresh context to prevent contamination between tasks.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The verified instruction from step-01, the target agent identity, team configuration
- Limits: Only create/spawn what is needed. Do not spawn multiple agents simultaneously unless the workflow explicitly requires parallel execution.

## MANDATORY SEQUENCE

### 1. Determine Team Configuration
Use TeamCreate to create teams and the Agent tool to spawn teammates.

Teammate roles map to BMAD agents:
- analyst -- Analyst agent
- pm -- PM agent
- architect -- Architect agent
- ux-designer -- UX Designer agent
- sm -- SM agent
- dev -- DEV agent

### 2. Create Team or Use Existing
Use TeamCreate to create the team if it does not already exist for this project. If the team is already active, use the existing team.

### 3. Spawn Teammate via Agent Tool
Use the Agent tool to spawn the appropriate teammate:
- Each teammate spawn starts with fresh context
- This prevents context contamination between tasks

### 4. Naming and Isolation Rules
- Teammate names always match agent roles: analyst, pm, architect, ux-designer, sm, dev
- Never run two different agents as the same teammate
- Never run the same agent as two teammates simultaneously
- Each new task gets a fresh teammate spawn

### 5. Fresh Context Rule
ALWAYS start fresh for:
- Every new task assigned to DEV
- Every new workflow phase
- Every time a different agent is activated for the same role

NEVER carry over context from:
- Previous tasks with the same teammate
- Other teammates
- Prior sessions

## CRITICAL STEP COMPLETION NOTE
ONLY when the team is created/confirmed and the teammate is spawned with fresh context, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Team is created or confirmed active
- Correct teammate is spawned for the task
- Teammate has fresh context (no contamination)
- Naming convention followed

### FAILURE:
- Spawning wrong teammate for the task
- Carrying over context from prior tasks
- Running same agent as multiple simultaneous teammates
- Not using fresh context for new tasks
