---
name: 'step-03-activate-agent'
description: 'Activate the correct agent within the spawned teammate (BMAD or generic)'
nextStepFile: './step-04-send-instruction.md'
---

# Step 3: Activate Agent

**Progress: Step 3 of 9** — Next: Send Instruction

## STEP GOAL:

Once the teammate is spawned with fresh context, activate the correct agent. For BMAD agents, use the appropriate activation command and verify readiness. For generic (non-BMAD) agents, no activation command is needed — proceed directly with instruction delivery.

**Scope:**
- Available context: The spawned teammate from step-02, the target agent identity
- Focus: Agent activation and verification only — do not send instruction
- Limits: Only activate one agent per teammate. Verify activation before sending any instruction.
- Dependencies: Spawned teammate from step-02 with confirmed fresh context

- Focus on activating the correct agent and verifying readiness — no instruction sending yet
**Behavioral Constraints:**
- FORBIDDEN to send instruction before agent activation is verified (BMAD agents)
- Approach: BMAD — activate, verify, then proceed. Generic — spawn and proceed to step-04. One agent per teammate only.
- If BMAD activation fails, retry before proceeding — never send to unverified BMAD agent

## Sequence

### 1. Activate the BMAD Agent

BMAD activation is embedded in the spawn prompt as a **Skill-tool-load** (`Use the Skill tool to load bmad-<role>`) — never a bare `/bmad-*` sent to an already-spawned teammate. See `/aim-agent-dispatch` **B4 (Verify Activation)** as the single source for the two-phase Skill-tool-load-in-the-spawn-prompt form. Agent selection — which persona, plus the MUST-use rules (`/bmad-code-review` for ALL reviews, `/bmad-agent-tech-writer` for ALL docs, `/bmad-help` when unsure) — lives in `/aim-agent-dispatch` **B1 / Quick Selection Matrix**.

---

### 1b. Generic Agent Activation (Non-BMAD)

For agents that are NOT BMAD agents (e.g., code-reviewer, verify-implementation, skill-creator):

1. Spawn the agent with fresh context using the Agent tool
2. No activation command is needed — generic agents do not require BMAD activation
3. Use a minimal spawn prompt — agent role identifier and task_id only. Do not embed the prepared instruction in the spawn prompt; step-04 (Send Instruction) delivers the full instruction via SendMessage.
4. Proceed to {nextStepFile}

Generic agents include any agent defined in `{project-root}/_ai-memory/agents/` or built-in Claude Code agents (Explore, Plan, general-purpose).

> **Dispatch Discipline (all agent types):** FORBIDDEN to pre-read or load the dispatched agent's skill or workflow files before sending the instruction. The agent loads its own skill upon activation. Reading ahead to summarize, supplement, or replicate the skill's guidance introduces duplication and undermines the skill's authority. Provide target + context only — the skill handles requirements and approach.

> **Skip to step-04**: Since generic agents do not require an activation/verification handshake, steps 2 and 3 below (Verify Activation, Do Not Proceed Until Verified) apply only to BMAD agents. For generic agents, proceed directly to {nextStepFile} after spawning.

---

### 2. Verify Activation (BMAD Agents Only)

Confirm the agent is active and ready:
- Agent responds with its identity/role confirmation
- Agent is in a clean state (no prior task context)
- Agent is ready to receive instruction

---

### 3. Do Not Proceed Until Verified (BMAD Agents Only)

If activation fails or agent does not respond correctly (state-based, not time-based):
- Idle is noise — a slow load is not a stall; the teammate is working. Do NOT retry the activation command or nudge.
- Inspect first: Claude-native = the spawn's first response / SendMessage reply; tmux = `tmux capture-pane`.
- Only on a genuine stall (no activation output and no loading/work, or output stopped at a crash/error signature with no menu) respawn a FRESH teammate.
- Do not send instruction to an unverified agent

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the agent is activated and verified ready, load and read fully {nextStepFile}
