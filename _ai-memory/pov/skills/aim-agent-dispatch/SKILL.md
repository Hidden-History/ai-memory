---
name: aim-agent-dispatch
description: Generic and BMAD agent selection, instruction preparation, and activation routing
allowed-tools: Read
---

# Agent Dispatch -- Generic and BMAD Agent Activation

**Purpose**: Prepare instructions for all agents (generic and BMAD). Determines if BMAD persona is needed and routes accordingly. BMAD routing is handled within this skill.

---

## Embedded Constraints (Layer 3)

- **EC-02**: MUST use the instruction template for every agent dispatch. Story files are planning artifacts -- implementation instructions translate requirements into precise, actionable specifications.
- **GC-11 L3**: ALWAYS use the instruction template for every agent dispatch. Every requirement must cite a project file. Every DONE WHEN criterion must be objectively measurable.
- **DC-08**: Analyst research MUST precede PM when input is thin. When goals.md is the only input, Analyst must run before PM begins. PM does NOT begin from goals.md alone when input is thin.
- **Agent activation verification**: Never send an instruction to an unverified agent. Verify activation before proceeding.
- **One task per instruction**: Never combine multiple tasks in a single dispatch.

---

## Step 0: Pre-Spawn Sentinel Gate (MANDATORY -- re-run before EVERY spawn)

Before routing any dispatch, assert the current directory is the workspace root by confirming co-presence of `_ai-memory/`, `_bmad/`, and `oversight/` (CLAUDE.md workspace-root sentinel). Concretely: `test -d _ai-memory && test -d _bmad && test -d oversight`.

- PASS -> proceed to Step 1.
- FAIL -> **ABORT the spawn.** Report: "CWD drift -- not at workspace root; return to root before spawning." Do NOT route to /aim-model-dispatch or /aim-agent-lifecycle.

CWD drifts across Bash calls, so re-run this gate immediately before EACH spawn -- not once per session.

---

## Step 1: Determine Dispatch Type

**BMAD dispatch** (use the [BMAD Agent Dispatch](#bmad-agent-dispatch) section below) when:
- The task requires ANY BMAD agent role (Analyst, PM, Architect, DEV, UX Designer, Tech Writer)
- The agent requires persona activation via `/bmad-agent-<name>` commands

**Generic dispatch** (use the [Generic Agent Dispatch](#generic-agent-dispatch) section below) when:
- The agent does NOT need a BMAD persona
- The agent is a generic worker spawned for a specific task
- Examples: code-reviewer agent, verify-implementation agent, skill-creator agent

**Mandatory (BMAD-or-fail):** if the task maps to any BMAD role/skill above, you MUST dispatch that
BMAD persona. A generic/no-persona agent on BMAD-shaped work is a FAILED dispatch — shut it down and
respawn via the correct `/bmad-*`. Generic dispatch is only for work with no BMAD role.

---

## Generic Agent Dispatch

### 2. Prepare Instruction Using Template

Build the instruction using the instruction template (`templates/agent-instruction.template.md`):

- **TASK**: Single, specific, unambiguous description. One task per instruction.
- **CONTEXT**: Relevant background -- only what is necessary.
- **REQUIREMENTS**: Cited project files and sections (PRD, architecture, standards, story criteria)
- **SCOPE**: Explicit IN SCOPE and OUT OF SCOPE lists
- **OUTPUT EXPECTED**: Exactly what the agent should produce (file names, formats, contents)
- **DONE WHEN**: Measurable, specific criteria the agent can self-assess
- **STANDARDS TO FOLLOW**: Specific coding standards, patterns, naming conventions
- **IF YOU ENCOUNTER A BLOCKER**: Stop and report immediately. Do not guess.

### 3. Verify Instruction Quality

Before dispatching, verify the instruction is:
- Complete (all template sections filled)
- Unambiguous (could not be interpreted multiple ways)
- Scoped (clear IN and OUT boundaries)
- Cited (every requirement references a project file)
- Measurable (DONE WHEN criteria are objectively verifiable)

IF ANY CHECK FAILS: fix the instruction before proceeding.

### 4. Route Based on Provider

Check provider from the dispatch plan:

**Claude provider:**
→ /aim-model-dispatch (MANDATORY next step)
Pass: instruction, AI_MEMORY_AGENT_ID, model from dispatch plan.

**Non-Claude provider:**
→ /aim-agent-lifecycle (MANDATORY next step)
Pass: instruction, AI_MEMORY_AGENT_ID, provider, model from dispatch plan.

MUST spawn fresh agent for every task -- never reuse across roles or stories.

### 5. Dispatch Complete

Agent instruction prepared and routed. Downstream skill handles spawn and activation.

---

## BMAD Agent Dispatch

### Agent Selection Guide

See [agent-selection-guide.md](data/agent-selection-guide.md) for detailed role descriptions, selection criteria, and dispatch decision tree.

### Quick Selection Matrix

| Task Type | Correct Agent | Wrong Agent | Mode |
|---|---|---|---|
| Research current codebase state | Analyst | Architect | Planning |
| Create, validate, or update PRD | PM | Analyst | Planning |
| Break down features into stories | PM | Analyst | Planning |
| Design system architecture | Architect | PM | Planning |
| Check if implementation is ready | Architect | DEV | Planning |
| Plan and initialize a sprint | `/bmad-sprint-planning` (direct skill) | PM | Planning |
| Create individual story files | `/bmad-create-story` (direct skill) | PM | Execution |
| Write code / implement a story | DEV | Any other | Execution |
| Review implemented code | DEV | Architect | Execution |
| Design user flows and screens | UX Designer | PM | Planning |
| Write or review documentation | Tech Writer | PM | Execution |
| Write and run tests | `/bmad-qa-generate-e2e-tests` (direct skill) | DEV | Execution |
| Design test architecture/strategy | `/bmad-tea` (direct skill) | DEV | Planning |
| Small feature, solo workflow | `/bmad-quick-dev` (direct skill) | DEV | Execution |

### Agent Combination Sequences

Some phases require agents in sequence:

- **Discovery phase:** Analyst (research) -> PM (PRD creation)
- **Architecture phase:** Architect (design) -> PM (epics/stories) -> Architect (readiness check)
- **Execution cycle:** DEV (implement) -> DEV (code review) -> [loop if issues] -> DEV (re-review)
- **Integration phase:** DEV (full review) -> Architect (cohesion check)
- **Release phase:** `/bmad-retrospective` (direct skill) -> PM or Analyst (documentation update)

---

### Steps

#### B1. Select the Correct Agent

Use the selection guide and matrix above. When uncertain, assess the primary skill required by the task, not the phase you are in.

If still uncertain, use `/bmad-help` -- it can answer questions about which agent and workflow to use for a given task.

#### B2. Prepare BMAD-Specific Instruction

Extends the generic instruction template (from the Generic Agent Dispatch section above) with:
- Persona confirmation requirement
- BMAD activation command reference

#### B3. Route Based on Provider

Check provider from the dispatch plan:

**Claude provider:**
→ /aim-model-dispatch (MANDATORY next step)
Pass: BMAD activation command, instruction, AI_MEMORY_AGENT_ID, model from dispatch plan.

**Non-Claude provider:**
→ /aim-agent-lifecycle (MANDATORY next step)
Pass: BMAD activation command, instruction, AI_MEMORY_AGENT_ID, provider, model from dispatch plan.

MUST spawn fresh agent for every task -- never reuse across roles or stories.

#### Core Project Agents

| Agent | Activation Command | Description |
|-------|-------------------|-------------|
| Analyst | `/bmad-agent-analyst` | Research, codebase analysis, domain investigation |
| PM (Product Manager) | `/bmad-agent-pm` | PRD creation/validation, epics and stories |
| Architect | `/bmad-agent-architect` | System architecture design, readiness checks |
| Developer (DEV) | `/bmad-agent-dev` | Code implementation ONLY |
| Developer (review) | `/bmad-code-review` | Code review ONLY -- MUST use this for ALL review agents, never /bmad-agent-dev |
| UX Designer | `/bmad-agent-ux-designer` | User flows, screen design, UX research |
| Tech Writer | `/bmad-agent-tech-writer` | Documentation writing and validation |

MUST use `/bmad-agent-tech-writer` for ALL documentation tasks (writing, updating, reviewing docs). MUST use `/bmad-code-review` for ALL review agents (never `/bmad-agent-dev`). MUST use `/bmad-help` whenever unsure which agent or workflow to use -- the tables above are NOT exhaustive.

**Workflow commands by phase** (sent AFTER activation, when in planning mode):

| Phase | Agent | Workflow Command |
|-------|-------|-----------------|
| Research | Analyst | `/bmad-market-research`, `/bmad-domain-research`, `/bmad-technical-research` |
| Discovery | Analyst | `/bmad-product-brief` |
| Discovery (or any phase) | PM | `/bmad-create-prd`, `/bmad-validate-prd`, `/bmad-edit-prd` |
| Architecture | Architect | `/bmad-create-architecture` |
| Architecture | PM | `/bmad-create-epics-and-stories` |
| Architecture | Architect | `/bmad-check-implementation-readiness` |
| Architecture | UX Designer | `/bmad-ux` |
| Planning | (direct skill) | `/bmad-sprint-planning`, `/bmad-create-story` |
| Execution | DEV | `/bmad-dev-story` |
| Execution | DEV | `/bmad-code-review` |
| Release | (direct skill) | `/bmad-retrospective` |

Set `AI_MEMORY_AGENT_ID` environment variable when spawning.

> **Maintenance check:** `scripts/check_bmad_commands.sh` verifies every `/bmad-*` command in the tables above resolves to an installed skill under `.claude/skills/` (fire-only-if-missing: silent when all resolve, non-zero listing any that don't; degrades gracefully when BMAD is not installed). Run it after editing these tables or updating the BMAD module.

#### B4. Verify Activation (MANDATORY — two-phase)

**Sentinel (GC-19):** before every spawn, as its own Bash step, assert workspace root:
`test -d _ai-memory && test -d _bmad && test -d oversight`. FAIL → ABORT.

**Spawn (two-phase, GC-20):** the spawn prompt loads the BMAD persona via the Skill tool (e.g.
`Use the Skill tool to load bmad-agent-dev` — likewise `bmad-create-story`, `bmad-code-review`; a bare
`/bmad-*` at spawn activates the lead, not the persona) + one line — "You're activated as a teammate
under Parzival (team-lead). Once activated, SendMessage your activation reply (greeting + menu, and
anything the agent asks) to team-lead, then wait for my instructions before doing any work." Never the
task. `mode: auto`.

**Wait:** idle pings (`idle_notification "available"`) are NOISE — no reaction, no on-disk checks, no
nudges; the teammate sends a real message when it has one.

**Instruct:** read the menu, then SendMessage the task — one task per message, never bundled (GC-20).

#### B5. Dispatch Complete

Agent selection and instruction complete. Downstream skill handles spawn and activation.

---

## Dispatch & Coordination Playbook (life of the teammate)

- **Reporting address (mandatory-for-function):** a teammate reaches the lead only by name —
  `team-lead`. `to:"main"` is background-subagents-only; a teammate using it is rejected and the lead
  receives nothing (plain text is invisible between agents). Every report/answer → `team-lead`.
- **One message, then wait:** send ONE message, then wait for the reply. A teammate gets a new message
  only after it stops and replies; another before then just re-triggers its work. Never multiple in a row.
- **Acceptance:** accept ONLY against Parzival's own cold on-disk verification (re-read the files) —
  never a "done"/idle signal.
- **Reviewer disagreement:** adjudicate via `review-cycle/workflow.md` (## Reviewer Disagreement).
- **Stall (state-based, not time-based):** respawn FRESH only on a genuine stall — no activation output
  and no loading/work, or output stopped at a crash/error signature with no menu. A slow load ≠ stall.

---

## Common Dispatch Errors

| Error | Prevention |
|---|---|
| Sending vague instruction | Always complete the full instruction template |
| Combining multiple tasks | One task per instruction -- always |
| Activating wrong agent | Use the BMAD selection matrix above |
| Accepting partial output | Review all DONE WHEN criteria |
| Passing raw agent output to user | Always prepare summary |
| Running agents without verification | Complete instruction checklist first |
| Starting new task before prior accepted | One active task per agent at a time |
| PM activated with thin input | Run Analyst first (DC-08) |

---

## Instruction Template Reference

> **Convention**: All POV skill templates use the `.template.md` extension to distinguish them from step files and other markdown documents.

The full instruction template is at: `templates/agent-instruction.template.md`
