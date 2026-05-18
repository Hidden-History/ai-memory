---
name: 'step-04-send-instruction'
description: 'Send the prepared instruction to the activated agent via SendMessage'
nextStepFile: './step-05-monitor-progress.md'
---

# Step 4: Send Instruction

**Progress: Step 4 of 9** — Next: Monitor Progress

## STEP GOAL:

After agent activation, send the prepared instruction to the teammate using SendMessage. The form depends on agent type: generic agents receive the complete instruction; BMAD skill-driven agents receive a recommendation request (target + minimal context) — not a full work order.

**Scope:**
- Available context: The verified instruction from step-01, the activated agent from step-03
- Focus: Instruction delivery only — do not begin monitoring or interpret agent responses as output
- Limits: Deliver per the agent-type conditional. Do not modify generic instructions; do not over-instruct skill-driven agents.
- Dependencies: Verified instruction from step-01 and activated, verified agent from step-03

**Behavioral Constraints:**
- For generic agents: FORBIDDEN to abbreviate, summarize, or add conversational preamble to the instruction
- For BMAD skill-driven agents: FORBIDDEN to send a full work plan; FORBIDDEN to ask "state your planned approach"
- Clarification requests must be resolved from project files, never guessed

## Sequence

### 1. Send the Instruction (Agent-Type Conditional)

The form of the first SendMessage depends on agent type.

#### For GENERIC agents (Explore, general-purpose, built-in non-BMAD agents):

Send the complete instruction from step-01 using SendMessage:
- Send the complete instruction exactly as prepared — do not add conversational preamble
- Do not modify the instruction format — agents expect consistency
- Send once — do not re-send while agent is working
- If instruction needs clarification, wait for agent to flag it

#### For BMAD skill-driven agents (activated via `/bmad-agent-{type}`):

First SendMessage asks for recommendation — do NOT send the full work plan:
- Send: TASK (target) + CONTEXT (minimal) + DONE WHEN (from step-01 section 2b) + "What do you recommend and why?"
- FORBIDDEN to ask "state your planned approach" — that steers away from the skill's guidance
- FORBIDDEN to send the full instruction template — the skill drives the approach, not Parzival's prescription
- Wait for the agent's recommendation before proceeding

#### 1b. Receive Recommendation (BMAD skill-driven agents only)

After the recommendation request:
- Wait for the agent to respond with their recommendation and reasoning
- Review: does the recommendation address the task correctly?
  - YES → respond "proceed" or with brief directional input; move to monitoring (step-05)
  - MISALIGNED → provide a specific, minimal redirect; ask for revised recommendation; do not over-correct
  - BLOCKER → apply research-protocol or escalate to user
- Do not over-instruct after receiving recommendation — the skill drives execution from here

---

### 2. Handle Agent Clarification Requests

**Agent asks for clarification BEFORE starting:**
- Provide the clarification with a citation if possible
- If you cannot clarify without checking project files: check files first
- Never guess the clarification

**Agent asks for clarification DURING work (blocker):**
- Assess: can you resolve this from project files?
  - YES: provide resolution with citation via SendMessage
  - NO: apply WF-RESEARCH-PROTOCOL
  - If still unresolved: escalate to user

---

### 3. Confirm Ready for Monitoring

- **Generic agents:** Wait for acknowledgment that the instruction was received and understood before moving to monitoring.
- **BMAD skill-driven agents:** The recommendation exchange in section 1b completes this step — agent is already working after "proceed" is sent.

---

## CRITICAL STEP COMPLETION NOTE

ONLY when the instruction or recommendation request has been sent and the agent is confirmed ready to work (generic: acknowledged receipt; BMAD: recommendation exchanged and "proceed" sent), load and read fully {nextStepFile}
