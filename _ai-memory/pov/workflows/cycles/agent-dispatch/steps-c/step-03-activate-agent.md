---
name: 'step-03-activate-agent'
description: 'Activate the correct agent within the spawned teammate (BMAD or generic)'
nextStepFile: './step-04-send-instruction.md'
---

# Step 3: Activate Agent

**Progress: Step 3 of 9** — Next: Send Instruction

## STEP GOAL:

Once the teammate is spawned with fresh context, activate the correct agent. For BMAD agents, use the appropriate activation command and verify readiness. For generic (non-BMAD) agents, no activation command is needed — proceed directly with instruction delivery.

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

- 🎯 Focus on activating the correct agent and verifying readiness — no instruction sending yet
- 🚫 FORBIDDEN to send instruction before agent activation is verified (BMAD agents)
- 💬 Approach: BMAD — activate, verify, then proceed. Generic — spawn and proceed to step-04. One agent per teammate only.
- 📋 If BMAD activation fails, retry before proceeding — never send to unverified BMAD agent

## EXECUTION PROTOCOLS:

- 🎯 Issue the activation command for the correct agent within the spawned teammate
- 💾 Confirm agent identity and clean state before proceeding
- 📖 Load next step only when agent is verified active and ready
- 🚫 FORBIDDEN to send instruction to an agent that has not confirmed ready state

## CONTEXT BOUNDARIES:

- Available context: The spawned teammate from step-02, the target agent identity
- Focus: Agent activation and verification only — do not send instruction
- Limits: Only activate one agent per teammate. Verify activation before sending any instruction.
- Dependencies: Spawned teammate from step-02 with confirmed fresh context

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Activate the BMAD Agent

Use the appropriate agent activation command within the teammate context:
- Analyst: /bmad-agent-bmm-analyst
- PM: /bmad-agent-bmm-pm
- Architect: /bmad-agent-bmm-architect
- UX Designer: /bmad-agent-bmm-ux-designer
- SM: /bmad-agent-bmm-sm
- DEV: /bmad-agent-bmm-dev

---

### 1b. Generic Agent Activation (Non-BMAD)

For agents that are NOT BMAD agents (e.g., code-reviewer, verify-implementation, skill-creator):

1. Spawn the agent with fresh context using the Agent tool
2. No activation command is needed — generic agents do not require BMAD activation
3. Pass the prepared instruction from step-01 directly as the agent's prompt
4. Proceed to step-04 (Monitor and Collect)

Generic agents include any agent defined in `{project-root}/_ai-memory/agents/` or built-in Claude Code agents (Explore, Plan, general-purpose).

> **Skip to step-04**: Since generic agents do not require an activation/verification handshake, steps 2 and 3 below (Verify Activation, Do Not Proceed Until Verified) apply only to BMAD agents. For generic agents, proceed directly to {nextStepFile} after spawning.

---

### 2. Verify Activation (BMAD Agents Only)

Confirm the agent is active and ready:
- Agent responds with its identity/role confirmation
- Agent is in a clean state (no prior task context)
- Agent is ready to receive instruction

---

### 3. Do Not Proceed Until Verified (BMAD Agents Only)

If activation fails or agent does not respond correctly:
- Retry the activation command
- If repeated failure, check team configuration
- Do not send instruction to an unverified agent

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the agent is activated and verified ready, load and read fully {nextStepFile}

---

## 🚨 SYSTEM SUCCESS/FAILURE METRICS

### ✅ SUCCESS:

- Correct agent activated for the task
- Agent verified as active and ready
- Clean state confirmed (no prior context)

### ❌ SYSTEM FAILURE:

- Activating wrong agent
- Sending instruction before verifying activation
- Agent in unclean state from prior task

**Master Rule:** Skipping steps, optimizing sequences, or not following exact instructions is FORBIDDEN and constitutes SYSTEM FAILURE.
