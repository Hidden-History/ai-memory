---
name: 'step-03-activate-dev'
description: 'Activate DEV agent via agent-dispatch workflow with the prepared implementation instruction'
nextStepFile: './step-04-review-cycle.md'
---

# Step 3: Activate DEV Agent

**Progress: Step 3 of 7** — Next: Review Cycle

## STEP GOAL:

Route to {workflows_path}/cycles/agent-dispatch/workflow.md with the prepared implementation instruction. Monitor DEV for clarification questions, blocker reports, scope drift, and undocumented decisions.

> **Preamble**: All universal rules, role reinforcement, execution protocols apply. See [STEP-PREAMBLE.md]({workflows_path}/STEP-PREAMBLE.md).

**Scope:**
- Available context: Prepared implementation instruction from Step 2
- Focus: Routing and monitoring only — DEV implements, Parzival monitors
- Limits: DEV implements. Parzival monitors. All agent interaction goes through the agent-dispatch workflow.
- Dependencies: Prepared implementation instruction from Step 2

- Focus only on routing through agent-dispatch and monitoring — no direct implementation
**Behavioral Constraints:**
- FORBIDDEN to activate DEV directly without going through agent-dispatch workflow
- Approach: Structured monitoring with clear escalation paths
- Update sprint-status.yaml when DEV completion report is received

## Sequence of Instructions (Do not deviate, skip, or optimize)

### 1. Dispatch DEV via Agent Dispatch

Invoke {workflows_path}/cycles/agent-dispatch/workflow.md with:
- The complete implementation instruction from Step 2
- Agent to activate: DEV
- Start fresh session for this story

---

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

---

### 3. Receive Implementation Completion Report

DEV signals implementation complete with:
- List of files created or modified
- Implementation approach description
- Any decisions made during implementation
- Any blockers encountered

---

### 4. Update Story State

Update sprint-status.yaml: story status changes from IN-PROGRESS to IN-REVIEW.

## CRITICAL STEP COMPLETION NOTE

ONLY WHEN DEV reports implementation complete, will you then read fully and follow: `{nextStepFile}` to begin the review cycle.
