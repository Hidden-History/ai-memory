# Agent Dispatch Guide

How Parzival activates, instructs, monitors, and closes agents -- the operational backbone of every agent interaction.

---

## Table of Contents

- [Overview](#overview)
- [The Dispatch Cycle](#the-dispatch-cycle)
- [Instruction Template](#instruction-template)
- [Instruction Quality Checklist](#instruction-quality-checklist)
- [Agent Lifecycle](#agent-lifecycle)
- [Correction Template](#correction-template)
- [Common Dispatch Errors](#common-dispatch-errors)
- [Constraints](#constraints)

---

## Overview

Agent dispatch is the process by which Parzival delegates implementation work to specialized agents. Parzival does not write code or produce deliverables directly. Instead, Parzival prepares precise instructions, spawns agents as teammates, sends those instructions, monitors progress, reviews output, and either accepts or loops corrections until the work meets project requirements.

There are two dispatch paths:

| Path | When to Use |
|------|-------------|
| **Generic dispatch** (`aim-agent-dispatch`) | The agent does not need a BMAD persona. Examples: code-reviewer, verify-implementation, skill-creator. |
| **BMAD dispatch** (`aim-bmad-dispatch`) | The agent is a BMAD role (Analyst, PM, Architect, DEV, SM, UX Designer) and requires persona activation. |

Both paths converge on the same lifecycle (steps 4--9) managed by `aim-agent-lifecycle`.

---

## The Dispatch Cycle

The full dispatch cycle consists of nine steps, divided between dispatch (steps 1--3) and lifecycle (steps 4--9).

| Step | Name | Owner | Description |
|------|------|-------|-------------|
| 1 | Prepare Instruction | `aim-agent-dispatch` or `aim-bmad-dispatch` | Build the full instruction using the template. Every requirement cites a project file. |
| 2 | Verify Instruction | `aim-agent-dispatch` or `aim-bmad-dispatch` | Run the quality checklist. Fix any failures before proceeding. |
| 3 | Spawn Agent | `aim-agent-dispatch` or `aim-bmad-dispatch` | Spawn the agent as a teammate using the Agent tool with `team_name`. Select model via `aim-model-dispatch`. |
| 4 | Send Instruction | `aim-agent-lifecycle` | Send the complete instruction via `SendMessage`. Do not abbreviate or add preamble. Wait for acknowledgment. |
| 5 | Monitor Progress | `aim-agent-lifecycle` | Track progress. Intervene on scope breaches or unreported blockers. Relay clarifications with citations. |
| 6 | Review Output | `aim-agent-lifecycle` | Evaluate output against DONE WHEN criteria, OUTPUT EXPECTED, cited requirements, and standards. |
| 7 | Accept or Loop | `aim-agent-lifecycle` | Accept if all checks pass. Otherwise, send a correction and loop back to step 5. Maximum 3 loops before escalation. |
| 8 | Shutdown | `aim-agent-lifecycle` | Shut down the agent cleanly. Verify no pending work remains. |
| 9 | Summary | `aim-agent-lifecycle` | Prepare a user-facing summary in Parzival's own words. Never copy-paste raw agent output. |

### Execution Flow

```
Prepare Instruction --> Verify --> Spawn Agent --> Send Instruction
                                                        |
                                                        v
                                                   Monitor Progress
                                                        |
                                                        v
                                                   Review Output
                                                      / \
                                            Pass    /     \   Fail
                                                  v         v
                                              Accept     Correction
                                                |           |
                                                v      (back to Monitor)
                                             Shutdown
                                                |
                                                v
                                             Summary
```

---

## Instruction Template

Every instruction sent to an agent must follow this format. No exceptions.

```
PARZIVAL -> [AGENT NAME] INSTRUCTION

TASK:
[Single, specific, unambiguous description of what to do.
One task per instruction. Never combine multiple tasks.]

CONTEXT:
[Relevant background the agent needs -- only what is necessary.
Do not dump the entire project history. Be precise.]

REQUIREMENTS:
[Cite specific files and sections:]
- PRD.md [section]: [requirement]
- architecture.md [section]: [constraint]
- project-context.md [section]: [standard]
- [story file]: [acceptance criteria]

SCOPE:
  IN SCOPE:
  - [exactly what the agent should work on]
  - [specific files, functions, modules]

  OUT OF SCOPE:
  - [explicitly what the agent must not touch]
  - [adjacent areas to avoid]

OUTPUT EXPECTED:
[Exactly what the agent should produce -- file names, formats, contents]

DONE WHEN:
[Measurable, specific criteria. Agent must be able to self-assess completion.]
- [ ] [criterion 1]
- [ ] [criterion 2]
- [ ] [criterion 3]

STANDARDS TO FOLLOW:
[Specific coding standards, patterns, naming conventions from project-context.md]

IF YOU ENCOUNTER A BLOCKER:
For ambiguities or minor questions: proceed with your best interpretation and note
what you assumed. Do not stop for trivial clarifications.
For true blockers (missing files, conflicting requirements, scope confusion):
stop and report immediately. State: what the blocker is, what you tried, what you
need to continue.
```

### Field Reference

| Field | Purpose | Key Rule |
|-------|---------|----------|
| TASK | What the agent must do | One task per instruction. Never combine multiple tasks. |
| CONTEXT | Background the agent needs | Only what is necessary. No project history dumps. |
| REQUIREMENTS | Cited project files and sections | Every requirement must reference a specific file and section. |
| SCOPE | Boundaries of the work | Explicit IN SCOPE and OUT OF SCOPE lists. |
| OUTPUT EXPECTED | What the agent produces | File names, formats, and contents specified exactly. |
| DONE WHEN | Completion criteria | Measurable and objectively verifiable. Agent self-assesses against these. |
| STANDARDS TO FOLLOW | Coding conventions | Patterns, naming conventions, and standards from project files. |
| BLOCKER HANDLING | What to do when stuck | Minor ambiguities: proceed and note assumptions. True blockers: stop and report. |

---

## Instruction Quality Checklist

Before dispatching any instruction, verify all five checks pass. If any check fails, fix the instruction before proceeding.

| Check | Criteria |
|-------|----------|
| **Complete** | All template sections are filled. No placeholders or TODOs remain. |
| **Unambiguous** | The instruction cannot be interpreted multiple ways. |
| **Scoped** | Clear IN SCOPE and OUT OF SCOPE boundaries are defined. |
| **Cited** | Every requirement references a specific project file and section. |
| **Measurable** | Every DONE WHEN criterion is objectively verifiable by the agent. |

---

## Agent Lifecycle

Once an agent is spawned and the instruction is sent, the lifecycle skill (`aim-agent-lifecycle`) manages the remaining steps.

### Monitoring (Step 5)

**Intervene immediately if:**
- Agent is working outside defined scope
- Agent is making assumptions it should be flagging
- Output is heading in a direction that contradicts project files
- Agent appears stuck without reporting a blocker

**Do not interrupt if:**
- Agent is progressing normally within scope
- Agent is asking clarifying questions (respond, do not redirect)

**Scope breach response:**
1. Send: "Stop -- that is outside scope for this task. Scope is limited to [IN SCOPE items]. Please complete only what was specified."
2. Log the scope breach.
3. If caused by ambiguous instruction, revise and re-send.

**Blocker escalation:**
1. Assess if project files or research can resolve it.
2. If resolvable: provide resolution with citation.
3. If not resolvable: pause agent, prepare escalation summary for user (task, agent, blocker, options, recommendation).

### Review (Step 6)

Run the output review checklist:

- Did the agent complete everything in DONE WHEN?
- Does output match OUTPUT EXPECTED?
- Does output comply with all cited requirements?
- Does output follow specified standards?
- Did the agent stay within scope?
- Is the output complete (no partial implementations)?

**Routing rules:**
- Implementation output (code, configuration): always trigger a full review cycle. Never accept without review.
- Planning/documentation output: review against project requirements manually for completeness, accuracy, and internal consistency.

### Accept or Loop (Step 7)

**Accept when all of the following are true:**
- All DONE WHEN criteria are met
- All review checks pass
- Zero legitimate issues remain
- Output is complete, not partial

**Send correction when any check fails.** Use the correction template (see below). Then return to monitoring while the agent applies fixes, and re-review when done.

**Correction loop limit:** Maximum 3 correction loops per dispatch. If 3 loops do not resolve the issues, escalate to the user.

### Shutdown (Step 8)

**Shut down when:**
- Agent task is fully complete and accepted
- Agent is no longer needed for the current phase
- Session is ending

**Keep active when:**
- Agent will be needed again within the same session
- Agent is in a review-fix loop and will be called back

**Rules:**
- Never leave an agent active with a pending failed task.
- Never run a new task with an agent that has unresolved prior output.
- Never shut down an agent while a task is still in progress.

### Summary (Step 9)

Write the summary in Parzival's own words. Never copy-paste agent output.

**Summary format:**

| Section | Content |
|---------|---------|
| COMPLETED | What was accomplished |
| FOUND | Issues discovered during the work |
| FIXED | What was resolved and the verified basis for each fix |
| DECISION NEEDED | Anything requiring user input |
| NEXT STEP | Recommended next action with options if applicable |

---

## Correction Template

When agent output fails review, send a correction using this format:

```
PARZIVAL -> [AGENT NAME] CORRECTION

REVIEW RESULT: Issues found -- do not proceed

ISSUE 1: [specific description]
  Location: [file, function, line if applicable]
  Problem:  [what is wrong]
  Required: [what it should be -- cite source if possible]

ISSUE 2: [specific description]
  Location: [file, function, line if applicable]
  Problem:  [what is wrong]
  Required: [what it should be -- cite source if possible]

[Continue for all legitimate issues]

ACTION REQUIRED:
Fix all issues listed above. Re-review your work after fixing.
Report back when complete with zero issues remaining.

DO NOT:
- Fix only some issues and report back
- Introduce new changes outside the scope of these fixes
- Proceed to other tasks
```

Each issue must include a specific location, a clear description of the problem, and the required fix with a citation where possible. Do not send vague corrections.

---

## Common Dispatch Errors

These are the most frequent anti-patterns observed during agent dispatch. Each has a direct prevention measure.

| Error | Prevention |
|-------|------------|
| Sending vague instruction | Always complete the full instruction template before dispatching. |
| Combining multiple tasks in one instruction | One task per instruction -- always. |
| Activating wrong agent | Consult `aim-bmad-dispatch` for agent role selection. |
| Accepting partial output | Review all DONE WHEN criteria before accepting. |
| Passing raw agent output to user | Always prepare a summary in Parzival's words. Never copy-paste. |
| Running agents without project file verification | Complete the instruction quality checklist before every dispatch. |
| Starting new task before prior one is fully accepted | One active task per agent at a time. |

---

## Constraints

Three global constraints govern agent dispatch behavior.

### GC-11: Precise Instructions

Every agent dispatch must use the instruction template. Every requirement must cite a project file. Every DONE WHEN criterion must be objectively measurable.

This constraint is enforced at Layer 3 (embedded in the dispatch skills) and verified during the instruction quality checklist.

### GC-19: Spawn Agents as Teammates

**Rule:** When dispatching any agent, Parzival must spawn the agent as a teammate using the Agent tool with the `team_name` parameter.

**Required pattern:**
```
Agent tool:
  team_name: [descriptive name for the team/task]
  model: [appropriate model for the role]
```

**Forbidden:** Agent tool called without `team_name` (standalone subagent). Standalone dispatches lack the Edit and Write tool permissions required for implementation work, and prevent Parzival from sending follow-up instructions or managing the agent lifecycle.

**Self-check:** Am I about to spawn an agent without a `team_name`? If yes -- stop and add `team_name`.

### GC-20: Activation and Instruction Are Separate

**Rule:** The activation command and the task instruction must be sent as separate messages. The activation message contains only the activation command. The instruction is sent only after the agent has responded with its menu/greeting confirming it has fully loaded its persona.

**Required sequence:**

| Step | Action | Content |
|------|--------|---------|
| 1 | Spawn | Agent tool with `team_name` (GC-19) |
| 2 | Activate | Send activation command only (e.g., `/bmad-agent-bmm-dev`) |
| 3 | Wait | Wait for agent menu/greeting -- do not send anything yet |
| 4 | Instruct | Send task instruction as a separate message |

**Forbidden:** Combining activation command and task instruction in a single message. Sending any task content before the agent has displayed its greeting/menu.

**Why:** BMAD agents must load their full persona, skills, and workflow context during the activation step. Sending instructions before this loading completes causes the agent to operate with incomplete configuration.

**Self-check:** Am I about to send an activation command that also contains task instructions? If yes -- split into two messages: activate first, wait for menu, then instruct.

**Note:** GC-20 applies specifically to BMAD agents that require persona activation. Generic agents dispatched through `aim-agent-dispatch` do not have an activation step and receive their instruction directly after spawning.
