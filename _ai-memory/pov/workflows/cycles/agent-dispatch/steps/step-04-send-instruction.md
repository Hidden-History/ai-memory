---
name: 'step-04-send-instruction'
description: 'Send the prepared instruction to the activated agent via SendMessage'
nextStepFile: './step-05-monitor-progress.md'
---

# Step 4: Send Instruction

## STEP GOAL
After agent activation, send the prepared instruction in full to the teammate using SendMessage. Do not summarize or abbreviate. The complete instruction from step-01 is delivered as-is.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: The verified instruction from step-01, the activated agent from step-03
- Limits: Send the instruction exactly as prepared. Do not modify, abbreviate, or add conversational preamble.

## MANDATORY SEQUENCE

### 1. Send the Complete Instruction
Use SendMessage with type: "message" to send the full instruction to the teammate:
- Send the complete instruction using the template from step-01
- Do not add conversational preamble ("Hey, can you...")
- Do not modify the instruction format -- agents expect consistency
- Send once -- do not re-send while agent is working
- If instruction needs clarification, wait for agent to flag it

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

### 3. Confirm Instruction Received
Wait for agent acknowledgment that the instruction was received and understood before moving to monitoring.

## CRITICAL STEP COMPLETION NOTE
ONLY when the instruction has been sent and the agent has acknowledged receipt, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- Complete instruction sent without modification
- No conversational preamble added
- Instruction sent exactly once
- Agent acknowledged receipt
- Clarification requests handled with citations

### FAILURE:
- Abbreviating or summarizing the instruction
- Adding casual preamble to the instruction
- Re-sending instruction while agent is working
- Guessing clarifications instead of checking project files
- Not waiting for agent acknowledgment
