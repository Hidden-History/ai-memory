---
name: 'cycles-agent-dispatch-checklist'
description: 'Quality gate rubric for cycles-agent-dispatch'
---
> **Note**: This file is a BMAD module quality gate summary. The authoritative execution path is `workflow.md` → step files. If this checklist conflicts with step file content, the step files are canonical.

# Cycles Agent Dispatch — Validation Checklist

## Pre-Execution Checks

- [ ] Task or story requiring agent execution is clearly identified
- [ ] Relevant project files (PRD, architecture, story) are accessible

## Step Completion Checks

### Step 1: Prepare Instruction (step-01-prepare-instruction)
- [ ] Instruction checklist is fully completed
- [ ] Every requirement cites a specific project file and section
- [ ] Scope is explicitly defined (IN and OUT)
- [ ] DONE WHEN criteria are specific and measurable
- [ ] Instruction is unambiguous

### Step 2: Spawn Agent (step-02-spawn-agent)
- [ ] Team is created or confirmed active
- [ ] Correct teammate is spawned for the task
- [ ] Teammate has fresh context (no contamination from prior tasks)
- [ ] Naming convention followed
- [ ] AI_MEMORY_AGENT_ID set with correct naming pattern
- [ ] task_id stored in working context for downstream steps
- [ ] TaskCreate skipped gracefully when CLAUDE_CODE_TASK_LIST_ID not set (task_id = null)

### Step 3: Activate Agent (step-03-activate-agent)
- [ ] Correct agent activated for the task
- [ ] Agent verified as active and ready
- [ ] Clean state confirmed (no prior context)

### Step 4: Send Instruction (step-04-send-instruction)
- [ ] **Generic agents:** Complete instruction sent without modification; no preamble; once only; agent acknowledged receipt
- [ ] **BMAD skill-driven agents:** First SendMessage is recommendation request (TASK + minimal context + "what do you recommend and why?"); recommendation received before proceeding
- [ ] Clarification requests handled with citations, never guessed

### Step 5: Monitor Progress (step-05-monitor-progress)
- [ ] Progress tracked via idle notifications and TaskList
- [ ] Out-of-scope work detected and stopped immediately
- [ ] Blockers assessed and resolved (or escalated) promptly
- [ ] Normal progress not interrupted

### Step 6: Receive Output (step-06-receive-output)
- [ ] Every DONE WHEN criterion checked individually
- [ ] Output type correctly identified and routed
- [ ] Implementation output always routed to WF-REVIEW-CYCLE
- [ ] Incomplete output identified and not accepted

### Step 7: Accept or Loop (step-07-accept-or-loop)
- [ ] Output accepted only when all criteria are met
- [ ] Corrections are specific with locations and requirements
- [ ] Correction loops are tracked
- [ ] No partial acceptance

### Step 8: Shutdown Teammate (step-08-shutdown-teammate)
- [ ] Teammate shut down gracefully after task completion
- [ ] No pending work left with the teammate
- [ ] Dispatch log updated
- [ ] No orphaned teammates

### Step 9: Prepare Summary (step-09-prepare-summary)
- [ ] Summary written in Parzival's own words
- [ ] All five summary sections addressed (skip any marked N/A)
- [ ] Dispatch log updated with final status
- [ ] Routed to appropriate next workflow

## Workflow-Level Checks

- [ ] Agent completed task without scope drift
- [ ] Dispatch log updated
- [ ] No orphaned teammates remain
- [ ] No SYSTEM FAILURE conditions triggered in any step

## Anti-Pattern Checks

- [ ] Did NOT proceed to agent activation with incomplete instruction
- [ ] Did NOT have missing project file citations in instruction
- [ ] Did NOT: Vague or missing scope definition
- [ ] Did NOT: Unmeasurable completion criteria
- [ ] Did NOT: Ambiguous task description
- [ ] Did NOT spawn wrong teammate for the task
- [ ] Did NOT carry over context from prior tasks
- [ ] Did NOT: Running same agent as multiple simultaneous teammates
- [ ] Did NOT: Not setting AI_MEMORY_AGENT_ID on agent spawn
- [ ] Did NOT: Calling TaskCreate without storing returned task_id
- [ ] Did NOT: Failing to handle missing CLAUDE_CODE_TASK_LIST_ID gracefully
- [ ] Did NOT activate wrong agent
- [ ] Did NOT send instruction before verifying activation
- [ ] Did NOT send full template instruction to a BMAD skill-driven agent (use lightweight recommendation-request form)
- [ ] Did NOT ask BMAD agent to "state your planned approach" (ask "what do you recommend and why?" instead)
- [ ] Did NOT abbreviate or modify the full instruction for generic agents
- [ ] Did NOT add casual preamble to the instruction (generic agents)
- [ ] Did NOT re-send instruction while agent was working
- [ ] Did NOT pre-read the dispatched agent's skill or workflow files
- [ ] Did NOT: Guessing clarifications instead of checking project files
- [ ] Did NOT: Not waiting for agent acknowledgment or recommendation (per agent type)
- [ ] Did NOT miss out-of-scope work
- [ ] Did NOT interrupt normal agent progress
- [ ] Did NOT: Not monitoring agent progress
- [ ] Did NOT: Ignoring reported blockers
- [ ] Did NOT: Not escalating unresolvable blockers to user
- [ ] Did NOT accept output without checking all DONE WHEN criteria
- [ ] Did NOT accept implementation output without WF-REVIEW-CYCLE
- [ ] Did NOT accept output with failed checks
- [ ] Did NOT: Presenting incomplete output to user
- [ ] Did NOT: Not identifying scope violations in output
- [ ] Did NOT send vague corrections without specific issues
- [ ] Did NOT: Not tracking correction loops
- [ ] Did NOT: Accepting partial output
- [ ] Did NOT shut down teammate mid-task
- [ ] Did NOT: Leaving teammate active with pending failed task
- [ ] Did NOT: Not cleaning up teammates at session end
- [ ] Did NOT copy agent output into summary
- [ ] Did NOT fail to route to appropriate next workflow

_Validated by: Parzival Quality Gate on {date}_
