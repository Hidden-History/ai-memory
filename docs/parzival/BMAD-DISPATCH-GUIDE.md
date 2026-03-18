# BMAD Dispatch Guide

How Parzival selects, activates, and manages BMAD agents for project work.

---

## Overview

BMAD (Build Measure Analyze Design) agents are specialized AI personas that handle specific project roles -- research, product management, architecture, development, sprint planning, and UX design. Each agent loads a full persona with domain-specific skills, workflows, and behavioral patterns through BMAD activation commands.

Parzival does not implement work directly. Instead, it selects the correct BMAD agent for each task, activates it with the proper persona, dispatches instructions, and reviews the output before presenting results to the user. The `aim-bmad-dispatch` skill governs this selection and activation process.

---

## Available Agents

| Agent | Activation Command | Strengths | Typical Outputs |
|-------|-------------------|-----------|-----------------|
| **Analyst** | `/bmad-agent-bmm-analyst` | Research, codebase auditing, gap analysis, context generation | Context documents, audit reports, research findings |
| **PM** | `/bmad-agent-bmm-pm` | PRD creation, epic/story decomposition, scope management, acceptance criteria | PRD.md, epic definitions, story files |
| **Architect** | `/bmad-agent-bmm-architect` | System design, tech selection, implementation readiness checks, cohesion reviews | architecture.md, decision records, readiness assessments |
| **DEV** | `/bmad-agent-bmm-dev` | Code implementation, code review, bug fixing, test writing, refactoring | Implemented code, review reports, test suites |
| **SM (Scrum Master)** | `/bmad-agent-bmm-sm` | Sprint planning, story creation, sprint tracking, retrospectives | sprint-status.yaml, story files, retrospective summaries |
| **UX Designer** | `/bmad-agent-bmm-ux-designer` | User flow definition, wireframing, interaction patterns, accessibility review | Wireframes, user flow diagrams, interaction specs |

---

## Agent Selection Guide

Selection is task-driven, not phase-driven. Identify what needs to be done, then match the agent whose skills fit.

### Quick Selection Matrix

| Task Type | Correct Agent | Wrong Agent | Mode |
|-----------|---------------|-------------|------|
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

### Selection by Phase

| Phase | Primary Agents | Secondary Agents | Mode |
|-------|---------------|-----------------|------|
| Init | Analyst | -- | Planning |
| Discovery | Analyst, PM | -- | Planning |
| Architecture | Architect, PM | Analyst | Planning |
| Planning | SM | -- | Planning |
| Execution | DEV | Architect (if needed) | Execution |
| Integration | DEV, Architect | QA | Execution |
| Release | SM | DEV (if fixes needed) | Execution |
| Maintenance | DEV | Analyst (if research needed) | Execution |

### Decision Tree

When uncertain which agent to use:

1. Identify the primary skill the task requires (research, requirements, design, implementation, planning, UX).
2. Match that skill to the agent table above.
3. If still uncertain, use `/bmad-help` for guidance on agent and workflow selection.

---

## Agent Combination Sequences

Many phases require agents dispatched in sequence, where each agent's output feeds the next.

| Phase | Sequence | Notes |
|-------|----------|-------|
| **Discovery** | Analyst (research) -> PM (PRD creation) | Analyst gathers context; PM converts findings into requirements |
| **Architecture** | Architect (design) -> PM (epics/stories) -> Architect (readiness check) | Architect designs the system, PM decomposes into deliverables, Architect validates readiness |
| **Execution** | DEV (implement) -> DEV (code review) -> [loop if issues] -> DEV (re-review) | Core dev loop; review cycles repeat until code passes |
| **Integration** | DEV (full review) -> Architect (cohesion check) | DEV reviews completed work, Architect verifies system-level coherence |
| **Release** | SM (retrospective) -> PM or Analyst (documentation update) | SM captures learnings, then docs are updated |

Agents within a sequence are dispatched one at a time. Each agent's output is reviewed and accepted before the next agent is activated.

---

## Dispatch Modes

BMAD agents operate in one of two modes. Determine the mode before activation.

### Execution Mode

The agent receives a one-shot instruction and produces output. Used for concrete, well-defined tasks.

**Examples:** DEV implementing a story, DEV reviewing code, SM creating story files.

After activation and persona verification, send the appropriate workflow command first:

| Task | Workflow Command |
|------|-----------------|
| DEV implementing a story | `/bmad-bmm-dev-story` |
| DEV reviewing code | `/bmad-bmm-code-review` |
| SM creating story files | `/bmad-bmm-create-story` |

Wait for the agent to prompt for input, then send the task instruction.

### Planning Mode

The agent follows its own interactive workflow, asking questions and iterating with user input. Parzival acts as an intermediary, pre-researching answers from project files and presenting recommendations to the user.

**Examples:** PM creating a PRD, Architect designing architecture, Analyst researching, SM planning sprints, UX Designer creating flows.

**Workflow commands by phase:**

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
| Release | SM | `/bmad-bmm-retrospective` |

In planning mode, Parzival follows the **Relay Protocol**: intercept the agent's questions, research answers from project files, present recommendations with confidence levels to the user, relay confirmed answers back to the agent, and repeat until the agent produces its deliverable.

---

## Activation Sequence (GC-20)

Activation and instruction are always separate steps. This is enforced by constraint GC-20.

### Required Sequence

```
Step 1 -- Spawn:     Create the agent as a teammate (GC-19)
Step 2 -- Activate:  Send the activation command ONLY (e.g., /bmad-agent-bmm-dev)
Step 3 -- Wait:      Wait for the agent's menu/greeting response
Step 4 -- Instruct:  Send the task instruction OR workflow selection as a separate message
```

### Why Activation Must Be Separate

BMAD agents load their full persona, skills, and workflow context during activation. Sending instructions before this loading completes causes the agent to operate with incomplete configuration. The greeting/menu response is the agent's signal that it is fully loaded and ready.

This applies to both execution mode (one-shot instruction) and planning mode (workflow selection). It also applies to re-activations after agent shutdown and respawn.

### Forbidden Pattern

Never combine the activation command and task instruction in a single message. Never send any task content before the agent has displayed its greeting/menu.

---

## DC-08: Analyst Before PM on Thin Input

When the only input available is a `goals.md` file (or similarly thin input), the Analyst agent must run before the PM agent begins work.

**Rule:** PM does not start from `goals.md` alone. Analyst researches and generates context first; PM then uses that enriched context to create the PRD.

**Why:** A PM operating on thin input produces shallow, assumption-heavy requirements. The Analyst fills gaps with codebase research, domain context, and structured findings -- giving the PM the substance it needs to produce a quality PRD.

**When this applies:** Any time the available project input is minimal -- typically at the start of a new project or feature where only high-level goals exist.

---

## Common Mistakes

| Mistake | What Goes Wrong | Prevention |
|---------|----------------|------------|
| Wrong agent selected | Agent lacks the skills for the task; output is poor or off-target | Use the selection matrix; match task skill to agent, not phase to agent |
| Activation combined with instruction | Agent operates with incomplete persona; output quality degrades | Always separate activation and instruction into two messages (GC-20) |
| Skipping Analyst research | PM produces shallow PRD from thin input; downstream work suffers | Apply DC-08: run Analyst before PM when input is thin |
| Vague or incomplete instruction | Agent produces unfocused or partial output | Use the full instruction template with all fields populated |
| Multiple tasks in one instruction | Agent conflates tasks; output is confused | One task per instruction, always |
| Accepting output without review | Partial or incorrect work reaches the user | Review all DONE WHEN criteria before accepting |
| Forwarding raw agent output | User receives unstructured, context-heavy agent output | Always prepare a summary; never copy-paste raw agent output |

---

## Related Documentation

- [BMAD Multi-Agent Architecture](./BMAD-Multi-Agent-Architecture.md) -- How the multi-agent system is structured
- [Parzival Session Guide](../PARZIVAL-SESSION-GUIDE.md) -- How to run a Parzival oversight session
- [Constraint Enforcement System](./CONSTRAINT-ENFORCEMENT-SYSTEM.md) -- How constraints like GC-20 are enforced
