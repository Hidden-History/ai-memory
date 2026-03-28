---
name: aim-bmad-dispatch
description: BMAD agent selection, activation commands, and persona loading -- Layer 3b
---

# BMAD Dispatch -- BMAD Agent Activation (Layer 3b)

**Purpose**: Activate BMAD-specific agents with persona loading, BMAD activation commands, and role-specific behavior. For generic agents without BMAD personas, use aim-agent-dispatch instead.

---

## Embedded Constraints (Layer 3)

- **DC-08 (moved from Discovery phase)**: Analyst research MUST precede PM when input is thin. When goals.md is the only input, Analyst must run before PM begins. PM does NOT begin from goals.md alone when input is thin.
- **Agent activation verification**: Never send an instruction to an unverified agent. Verify activation before proceeding.
- **One task per instruction**: Never combine multiple tasks in a single dispatch.

---

## When to Use This Skill

Use aim-bmad-dispatch when:
- The task requires ANY BMAD agent role (see full activation table below)
- The agent requires persona activation via `/bmad-agent-*` commands

Use aim-agent-dispatch instead when:
- The agent does NOT need a BMAD persona
- Examples: code-reviewer, verify-implementation, skill-creator

---

## Agent Selection Guide

See [agent-selection-guide.md](data/agent-selection-guide.md) for detailed role descriptions, selection criteria, and dispatch decision tree.

### Quick Selection Matrix

| Task Type | Correct Agent | Wrong Agent | Mode |
|---|---|---|---|
| Research current codebase state | Analyst | Architect | Planning |
| Create, validate, or update PRD | PM | Analyst | Planning |
| Break down features into stories | PM | SM | Planning |
| Design system architecture | Architect | PM | Planning |
| Check if implementation is ready | Architect | DEV | Planning |
| Plan and initialize a sprint | SM | PM | Planning |
| Create individual story files | SM | PM | Execution |
| Write code / implement a story | DEV | Any other | Execution |
| Review implemented code | DEV | Architect | Execution |
| Design user flows and screens | UX Designer | PM | Planning |
| Write or review documentation | Tech Writer | PM | Execution |
| Write and run tests | QA Engineer | DEV | Execution |
| Design test architecture/strategy | Test Architect (TEA) | QA Engineer | Planning |
| Small feature, solo workflow | Quick Flow Solo Dev | DEV | Execution |
| Build new BMAD agents | Agent Builder | DEV | Execution |
| Build new BMAD modules | Module Builder | DEV | Execution |
| Build new BMAD workflows | Workflow Builder | DEV | Execution |
| BMAD framework guidance | BMAD Master | PM | Planning |
| Brainstorming / ideation session | Brainstorming Coach | Analyst | Planning |
| Creative problem solving | Creative Problem Solver | Analyst | Planning |
| Design thinking facilitation | Design Thinking Coach | UX Designer | Planning |
| Innovation strategy | Innovation Strategist | PM | Planning |
| Presentation creation/coaching | Presentation Master | Tech Writer | Execution |
| Narrative and storytelling | Storyteller | Tech Writer | Execution |

### Agent Combination Sequences

Some phases require agents in sequence:

- **Discovery phase:** Analyst (research) -> PM (PRD creation)
- **Architecture phase:** Architect (design) -> PM (epics/stories) -> Architect (readiness check)
- **Execution cycle:** DEV (implement) -> DEV (code review) -> [loop if issues] -> DEV (re-review)
- **Integration phase:** DEV (full review) -> Architect (cohesion check)
- **Release phase:** SM (retrospective) -> PM or Analyst (documentation update)

---

## BMAD Activation Process

### Dispatch Modes

BMAD agents operate in two modes. Determine the mode BEFORE activation:

**Execution mode** — agent receives a one-shot instruction and produces output:
- DEV implementing a story, DEV reviewing code, SM creating story files
- After BMAD activation (step 4 above), send the workflow command FIRST:
  - DEV implementing: send `/bmad-bmm-dev-story`, wait for story prompt, THEN send instruction
  - DEV reviewing: send `/bmad-bmm-code-review`, wait for review prompt, THEN send instruction
  - SM creating stories: send `/bmad-bmm-create-story`, wait for prompt, THEN send instruction
- Use the standard instruction template from aim-agent-dispatch for the instruction content
- Hand off to aim-agent-lifecycle Steps 4-9

**Planning mode** — agent follows its own interactive workflow with questions:
- PM creating PRD, Architect designing architecture, Analyst researching, SM planning sprints, UX designing flows
- Use the Relay Protocol below instead of a one-shot instruction
- The agent drives the workflow; Parzival acts as intermediary between agent and user

When uncertain about mode, use `/bmad-help` to get guidance on which agent and workflow to use.

### Planning Mode: Relay Protocol

When dispatching a BMAD agent in planning mode, Parzival acts as the intelligent intermediary between the agent and the user. The agent's own BMAD workflow drives the process — Parzival does not send a one-shot instruction.

**Activation sequence** (replaces Steps 2-6 for planning mode):

1. **Spawn agent** as teammate (GC-19). Set AI_MEMORY_AGENT_ID.
2. **Activate** with the BMAD command (e.g., `/bmad-agent-bmm-pm`).
3. **Wait for agent menu** — do NOT send anything until the agent displays its greeting/menu. The agent needs to fully load its persona and workflow options.
4. **Select the workflow** — send the appropriate menu selection based on the task (e.g., "create PRD", "create architecture"). If unsure which workflow, use `/bmad-help` for guidance.
5. **Agent begins asking questions** — the BMAD agent follows its own workflow and asks discovery/design questions.

**Relay cycle** (repeats until agent produces deliverable):

6. **Intercept agent questions** — read the questions the agent is asking.
7. **Research answers** — check project files (goals.md, PRD, architecture, existing code, oversight docs) for information that answers the questions. Assess confidence level for each answer.
8. **Present to user** — show the user:
   - The agent's original questions
   - Parzival's recommended answers with evidence and confidence levels
   - Citations from project files that support each recommendation
   - Any questions Parzival cannot answer (flag as "needs user input")
9. **User confirms/modifies** — user approves, edits, or provides answers Parzival couldn't find.
10. **Relay confirmed answers** — send the confirmed answers to the agent via SendMessage.
11. **Repeat from step 6** — agent processes answers and either asks more questions or produces output.

**Deliverable review**:

12. **Agent produces deliverable** (PRD, architecture doc, etc.) — apply the standard review cycle from aim-agent-lifecycle.
13. **Present summary to user** — never raw agent output (GC-10).

**Key principles**:
- Parzival ALWAYS pre-researches before presenting questions to the user. Never forward raw agent questions without adding recommendations.
- Parzival uses confidence levels on every recommendation (Verified/Informed/Inferred/Uncertain/Unknown).
- If Parzival can answer a question with high confidence from project files, say so — but still present it to the user for confirmation. Parzival recommends, user decides.
- Agent questions that require NEW decisions (not derivable from existing project files) should be clearly flagged as "user decision needed."

### 1. Select the Correct Agent
Use the selection guide and matrix above. When uncertain, assess the primary skill required by the task, not the phase you are in.

If still uncertain, use `/bmad-help` — it can answer questions about which agent and workflow to use for a given task.

### 2. Prepare BMAD-Specific Instruction
Extends the generic instruction template (from aim-agent-dispatch) with:
- Persona confirmation requirement
- BMAD activation command reference

### 3. Select Model
Consult aim-model-dispatch for the appropriate model based on task complexity and agent role.

### 4. Spawn and Activate Agent
Spawn the BMAD agent as a teammate in parallel using the Agent tool with MANDATORY parameters: `team_name`, `mode: "acceptEdits"`, unique `name` per task. MUST verify working directory is the **project root** (directory containing `_ai-memory/`) before spawning. Then activate the BMAD persona. All BMAD agents are teammates. MUST spawn fresh agent for every task -- never reuse across roles or stories (GC-21).

**Non-Claude provider**: When the user specifies a non-Claude provider (e.g., "use openrouter"), delegate the terminal launch to the model-dispatch skill. It handles tmux panes, wrapper scripts, and two-phase activation for that provider. Parzival still manages the agent as a teammate.

> **DEC-123**: aim-bmad-dispatch is the single entry point for all BMAD agent dispatch. aim-model-dispatch/bmad-dispatch provides implementation-level routing (backend selection, model selection, tmux launch) after initial dispatch.

#### Core Project Agents (bmm-)

| Agent | Activation Command | Description |
|-------|-------------------|-------------|
| Analyst | `/bmad-agent-bmm-analyst` | Research, codebase analysis, domain investigation |
| PM (Product Manager) | `/bmad-agent-bmm-pm` | PRD creation/validation, epics and stories |
| Architect | `/bmad-agent-bmm-architect` | System architecture design, readiness checks |
| Developer (DEV) | `/bmad-agent-bmm-dev` | Code implementation ONLY |
| Developer (review) | `/bmad-bmm-code-review` | Code review ONLY -- MUST use this for ALL review agents, never /bmad-agent-bmm-dev |
| Scrum Master (SM) | `/bmad-agent-bmm-sm` | Sprint planning, story creation, retrospectives |
| QA Engineer | `/bmad-agent-bmm-qa` | Test planning, test execution, quality validation |
| UX Designer | `/bmad-agent-bmm-ux-designer` | User flows, screen design, UX research |
| Tech Writer | `/bmad-agent-bmm-tech-writer` | Documentation writing and validation |
| Quick Flow Solo Dev | `/bmad-agent-bmm-quick-flow-solo-dev` | Lightweight single-dev flow (analysis through implementation) |

MUST use `/bmad-agent-bmm-tech-writer` for ALL documentation tasks (writing, updating, reviewing docs). MUST use `/bmad-bmm-code-review` for ALL review agents (never `/bmad-agent-bmm-dev`). MUST use `/bmad-help` whenever unsure which agent or workflow to use -- the tables above are NOT exhaustive.

#### BMAD Framework Agents

| Agent | Activation Command | Description |
|-------|-------------------|-------------|
| BMAD Master | `/bmad-agent-bmad-master` | BMAD framework orchestration and guidance |

#### Builder Agents (bmb-)

| Agent | Activation Command | Description |
|-------|-------------------|-------------|
| Agent Builder | `/bmad-agent-bmb-agent-builder` | Build new BMAD agent definitions |
| Module Builder | `/bmad-agent-bmb-module-builder` | Build new BMAD modules |
| Workflow Builder | `/bmad-agent-bmb-workflow-builder` | Build new BMAD workflows |

#### CIS Coaches (cis-)

| Agent | Activation Command | Description |
|-------|-------------------|-------------|
| Brainstorming Coach | `/bmad-agent-cis-brainstorming-coach` | Facilitated brainstorming sessions |
| Creative Problem Solver | `/bmad-agent-cis-creative-problem-solver` | Creative approaches to complex problems |
| Design Thinking Coach | `/bmad-agent-cis-design-thinking-coach` | Design thinking methodology facilitation |
| Innovation Strategist | `/bmad-agent-cis-innovation-strategist` | Innovation strategy and ideation |
| Presentation Master | `/bmad-agent-cis-presentation-master` | Presentation creation and coaching |
| Storyteller | `/bmad-agent-cis-storyteller` | Narrative crafting and storytelling |

#### Test Agents (tea-)

| Agent | Activation Command | Description |
|-------|-------------------|-------------|
| Test Architect (TEA) | `/bmad-agent-tea-tea` | Test architecture and strategy design |

**Workflow commands by phase** (sent AFTER activation, when in planning mode):

| Phase | Agent | Workflow Command |
|-------|-------|-----------------|
| Research | Analyst | `/bmad-bmm-market-research`, `/bmad-bmm-domain-research`, `/bmad-bmm-technical-research` |
| Discovery | Analyst | `/bmad-bmm-create-product-brief` |
| Discovery (or any phase) | PM | `/bmad-bmm-create-prd`, `/bmad-bmm-validate-prd`, `/bmad-bmm-edit-prd` |
| Architecture | Architect | `/bmad-bmm-create-architecture` |
| Architecture | PM | `/bmad-bmm-create-epics-and-stories` |
| Architecture | Architect | `/bmad-bmm-check-implementation-readiness` |
| Architecture | UX Designer | `/bmad-bmm-create-ux-design` |
| Planning | SM | `/bmad-bmm-sprint-planning`, `/bmad-bmm-create-story` |
| Execution | DEV | `/bmad-bmm-dev-story` |
| Execution | DEV | `/bmad-bmm-code-review` |
| Release | SM | `/bmad-bmm-retrospective` |

Set `AI_MEMORY_AGENT_ID` environment variable when spawning.

### 5. Verify Activation
Confirm the agent is active and ready:
- Agent responds with its identity/role confirmation
- Agent is in a clean state (no prior task context)
- Agent is ready to receive instruction

If activation fails:
- Retry the activation command
- If repeated failure, check configuration
- Do not send instruction to an unverified agent

### 6. Hand Off

**Execution mode**: Proceed with aim-agent-lifecycle Steps 4-9 (send instruction, monitor, review, accept/loop, shutdown, summary).

**Planning mode**: Follow the Relay Protocol above. The agent drives the workflow — Parzival relays questions and answers between agent and user until the agent produces its deliverable, then apply aim-agent-lifecycle review steps.

---

## Common Dispatch Errors

| Error | Prevention |
|---|---|
| Sending vague instruction | Always complete the full instruction template |
| Combining multiple tasks | One task per instruction -- always |
| Activating wrong agent | Use the selection matrix above |
| Accepting partial output | Review all DONE WHEN criteria |
| Passing raw agent output to user | Always prepare summary |
| Running agents without verification | Complete instruction checklist first |
| Starting new task before prior accepted | One active task per agent at a time |
| PM activated with thin input | Run Analyst first (DC-08) |
