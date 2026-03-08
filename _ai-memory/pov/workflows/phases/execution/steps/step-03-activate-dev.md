---
name: 'step-03-activate-dev'
description: 'Activate DEV agent via agent-dispatch workflow with the prepared implementation instruction'
nextStepFile: './step-04-review-cycle.md'
---

# Step 3: Activate DEV Agent

## STEP GOAL
Route to {workflows_path}/cycles/agent-dispatch/workflow.md with the prepared implementation instruction. Monitor DEV for clarification questions, blocker reports, scope drift, and undocumented decisions.

## MANDATORY EXECUTION RULES
- Read the complete step file before taking any action
- Follow the sequence exactly as written
- Do not skip or reorder steps

## CONTEXT BOUNDARIES
- Available context: Prepared implementation instruction from Step 2
- Limits: DEV implements. Parzival monitors. All agent interaction goes through the agent-dispatch workflow.

## MANDATORY SEQUENCE

### 1. Dispatch DEV via Agent Dispatch
Invoke {workflows_path}/cycles/agent-dispatch/workflow.md with:
- The complete implementation instruction from Step 2
- Agent to activate: DEV
- Start fresh session for this story

### 2. Monitor DEV Progress
While DEV is implementing, monitor for:

**Clarification questions:** Answer with citations to project files (architecture.md, project-context.md, PRD.md). Do not give vague answers.

**Blocker reports:** Assess and resolve:
- Is the answer in project files? If yes, provide with citation.
- If not in project files, trigger research protocol.
- If research does not resolve, escalate to user per agent-dispatch blocker protocol.
- Document resolution in decisions.md.

**Out-of-scope drift:** Correct immediately:
- Stop DEV
- Instruct DEV to revert out-of-scope changes
- Clarify scope boundary explicitly
- If out-of-scope work was needed, create a new story

**Undocumented implementation decisions:** If DEV proceeds on an assumption without flagging, catch it during review (Step 4).

### 3. Receive Implementation Completion Report
DEV signals implementation complete with:
- List of files created or modified
- Implementation approach description
- Any decisions made during implementation
- Any blockers encountered

### 4. Update Story State
Update sprint-status.yaml: story status changes from IN-PROGRESS to IN-REVIEW.

## CRITICAL STEP COMPLETION NOTE
ONLY when DEV reports implementation complete, load and read fully {nextStepFile}

## SYSTEM SUCCESS/FAILURE METRICS

### SUCCESS:
- DEV dispatched through {workflows_path}/cycles/agent-dispatch/workflow.md
- Clarification questions answered with citations
- Scope drift caught and corrected
- Blockers resolved or escalated properly
- Implementation completion report received

### FAILURE:
- DEV activated directly instead of through agent-dispatch workflow
- Vague answers to clarification questions
- Scope drift not caught during monitoring
- Blockers ignored or left unresolved
