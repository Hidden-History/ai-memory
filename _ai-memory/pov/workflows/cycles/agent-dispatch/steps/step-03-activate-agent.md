---
name: 'step-03-activate-agent'
description: 'Activate the correct BMAD agent within the spawned teammate'
nextStepFile: './step-04-send-instruction.md'
---

# Step 3: Activate Agent

## STEP GOAL
Once the teammate is spawned with fresh context, activate the correct BMAD agent using the appropriate activation command. Verify the agent is active and ready to receive instructions.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The spawned teammate from step-02, the target agent identity
- Limits: Only activate one agent per teammate. Verify activation before sending any instruction.

## MANDATORY SEQUENCE

### 1. Activate the BMAD Agent
Use the appropriate agent activation command within the teammate context:
- Analyst: /bmad-agent-bmm-analyst
- PM: /bmad-agent-bmm-pm
- Architect: /bmad-agent-bmm-architect
- UX Designer: /bmad-agent-bmm-ux-designer
- SM: /bmad-agent-bmm-sm
- DEV: /bmad-agent-bmm-dev

### 2. Verify Activation
Confirm the agent is active and ready:
- Agent responds with its identity/role confirmation
- Agent is in a clean state (no prior task context)
- Agent is ready to receive instruction

### 3. Do Not Proceed Until Verified
If activation fails or agent does not respond correctly:
- Retry the activation command
- If repeated failure, check team configuration
- Do not send instruction to an unverified agent

## CRITICAL STEP COMPLETION NOTE
ONLY when the agent is activated and verified ready, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Correct agent activated for the task
- Agent verified as active and ready
- Clean state confirmed (no prior context)

### FAILURE:
- Activating wrong agent
- Sending instruction before verifying activation
- Agent in unclean state from prior task
