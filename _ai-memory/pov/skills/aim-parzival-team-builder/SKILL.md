---
name: aim-parzival-team-builder
description: Design agent team structure for parallel work execution
context: fork
---

# Team Builder

**Purpose**: Analyze work to be parallelized, design the appropriate team structure (single agent, 2-tier, or 3-tier), and produce a team design document ready for execution via the agent-dispatch cycle.

**Note**: This skill is the entry point for team design. Parzival designs teams here, then executes them via the agent-dispatch workflow. Parzival activates agents himself -- the user does not run agents.

---

## Single Agent Fast Path

When the work is a single task that does not benefit from parallelization:
1. Collect provider and model preferences (Step 1b)
2. Assign agent role and AI_MEMORY_AGENT_ID (Step 2.3)
3. Prepare the context block (Step 4 format)
4. Present compact output for approval
5. Route to /aim-bmad-dispatch or /aim-agent-dispatch

**Criteria for single agent path:**
- One task, one agent, one review cycle
- No file ownership conflicts (only one agent working)
- No parallel coordination needed

**Compact output**: When the fast path is selected, skip ceremony. Produce only:
```
Fast Path: Single agent
Provider: [claude | openrouter | ollama | ...]
Agent: [role] (AI_MEMORY_AGENT_ID: [id], Model: [model tier])
Mode: [execution | planning]
Task: [one-line description]
Files: [list]
Route: [aim-bmad-dispatch or aim-agent-dispatch]
Approve?
```
Do not produce a full activation greeting, menu display, or multi-step analysis for a single-task dispatch. The fast path should be fast.

---

## Team Presets

Before running the full 6-step design process, check if the work matches a preset. Presets are pre-validated team configurations for common patterns — they skip Steps 1-5 and go straight to confirmation.

**How to use**: Match the user's request against the presets below. If it matches, present the preset with customizations (file paths, story IDs, model overrides). User approves → route directly to dispatch. If no preset matches, fall through to the full Team Design Process.

### Preset: Sprint Development (`sprint-dev`)
**When**: 2-3 stories need parallel implementation with code review
**Structure**: 2-tier — SM Lead (Opus) → 2 DEV workers (Sonnet) + 1 DEV reviewer (Opus)
**Workflow commands**: Workers run `/bmad-bmm-dev-story`, reviewer runs `/bmad-bmm-code-review`
**Requires**: sprint-status.yaml, architecture doc
**Customize**: story assignments, file ownership per story

### Preset: Story Preparation (`story-prep`)
**When**: Multiple stories need to be created from epics in bulk
**Structure**: 2-tier — PM Lead (Opus) → 2-3 SM story creators (Sonnet)
**Workflow commands**: Workers run `/bmad-bmm-create-story`
**Requires**: epics doc, sprint-status.yaml
**Customize**: which stories to create, epic references

### Preset: Test Automation (`test-automation`)
**When**: Completed stories need automated test coverage
**Structure**: 2-tier — TEA Lead (Opus) → 2 QA workers (Sonnet)
**Workflow commands**: Workers run `/bmad-bmm-qa-automate`
**Requires**: sprint-status.yaml, TEA module installed
**Customize**: which stories to test, test framework

### Preset: Architecture Review (`architecture-review`)
**When**: Pre-sprint architecture work with parallel research
**Structure**: 2-tier — Architect Lead (Opus) → Analyst worker (Sonnet) + UX Designer worker (Sonnet)
**Workflow commands**: Analyst runs `/bmad-bmm-technical-research`, UX runs `/bmad-bmm-create-ux-design`
**Requires**: PRD
**Customize**: research focus areas, UX scope

### Preset: Research (`research`)
**When**: Phase 1 parallel research across market, domain, and technical
**Structure**: 2-tier — Analyst Lead (Opus) → 3 Analyst workers (Sonnet)
**Workflow commands**: `/bmad-bmm-market-research`, `/bmad-bmm-domain-research`, `/bmad-bmm-technical-research`
**Requires**: Nothing (recommended: project-context.md)
**Customize**: research focus, industry, technology areas

### Preset Output Format

When a preset matches, produce:
```
Preset Match: [preset name]
Provider: [claude | openrouter | ollama | ...]
Structure: [tier] — [lead] → [workers]
Models: [role defaults or overrides]
Stories/Tasks: [customized assignments]
File Ownership: [per-worker paths]
Workflow Commands: [per-worker commands]
Requires: [prerequisites — verify they exist]
Approve?
```

Skip Steps 1-5. After user approval, route to dispatch.

---

## Team Design Process

Use this full process when NO preset matches — custom team requirements, unusual agent combinations, or file ownership conflicts that presets don't handle.

### Step 1: Preflight Analysis

1. Read the work to be parallelized (plan, spec, or user description)
2. Identify independent work units that can run concurrently
3. Check for file ownership conflicts between units
4. Determine tier selection:

| Scenario | Tier | Reasoning |
|----------|------|-----------|
| Single task | Single agent (fast path) | Overhead not justified |
| 2-6 parallel tasks, single review | 2-Tier | Simple coordination |
| 3+ domains, multi-task per domain, domain-level review | 3-Tier | Complex coordination |

### Step 1b: Provider and Model Preferences

Ask the user:

1. **Provider**: Which LLM provider for this team?
   - claude, openrouter, ollama, gemini, deepseek, groq, cerebras, mistral, openai, vertex-ai, siliconflow

2. **Model tier**: Present role-based defaults (Opus for planning, Sonnet for execution).
   Ask if user wants to override any.

Store provider and model selections in the dispatch plan.

### Step 2: Team Composition

1. Assign agent roles from available BMAD agents (analyst, pm, architect, dev, sm, ux-designer)
2. Size teams: 3-5 teammates recommended, 5-6 tasks per teammate for productive sizing
3. **Assign agent identity**: Each agent MUST have a unique `AI_MEMORY_AGENT_ID`:
   - **Domain-named** (recommended): `dev-auth`, `dev-api`, `review-auth` -- same agent always works on same domain
   - **Numbered** (for generic work): `dev-1`, `dev-2`, `review-1` -- interchangeable agents
   - **Single-instance**: `pm`, `architect` -- use role name directly
   - Same `AI_MEMORY_AGENT_ID` across sessions enables cross-session memory accumulation
   - Naming rules: domain-named agents always work the same domain/files across sessions; numbered agents are interchangeable for generic parallel work; single-instance agents use role name directly
4. Select models per agent role:
   - Planning agents (Analyst, PM, Architect): Opus
   - Execution agents (DEV, SM, QA, review): Sonnet
   - Simple/high-volume tasks: Haiku
   Present defaults to user. Apply overrides if user requests.

### Step 3: File Ownership Map

1. Map every file that will be modified to exactly one agent
2. NO file ownership overlap between agents at any level
3. Cross-cutting concerns use interface contracts
4. Verify ownership map has zero conflicts before proceeding

**Format**: Use a compact assignment list, not a matrix:
```
agent-name -> path/to/owned/files/**
agent-name -> path/to/other/files/**
Conflicts: NONE (or list conflicts found)
```
A sparse NxN matrix wastes tokens on columns of "—" entries. The assignment list conveys the same information.

### Step 4: Context Block Assembly

For each agent, prepare:
- ROLE: Agent type and assigned identity (AI_MEMORY_AGENT_ID)
- TASK: Specific work items with acceptance criteria
- FILES: Owned files (absolute paths)
- CONSTRAINTS: "DO NOT modify any files outside your SCOPE list." — do not enumerate every other agent's files; the ownership map in Step 3 is the source of truth
- DONE WHEN: Explicit completion criteria

### Step 5: Conflict Avoidance Strategy

Select from ranked strategies (highest effectiveness first):
1. **Git Worktree Isolation** -- Each worker gets independent filesystem copy
2. **Exclusive File Ownership** -- Enforced by Step 3 ownership map
3. **Directory Partitioning** -- Workers own directories, not individual files
4. **Interface Contracts** -- For workers producing compatible code
5. **Merge-on-Green** -- Code merges to main only when all tests pass

**NEVER use file locking** -- collapsed 20 agents to throughput of 2-3 in production testing.

**WSL2 note**: In-process mode recommended for WSL2 environments. tmux works best on macOS.

### Step 6: Pre-Delivery Review

Before executing, verify:
- [ ] All work units assigned to exactly one agent
- [ ] No file ownership conflicts
- [ ] Each agent has clear DONE WHEN criteria
- [ ] Each agent has a unique AI_MEMORY_AGENT_ID assigned
- [ ] Team size is 3-5 (split if larger)
- [ ] Conflict avoidance strategy selected and documented
- [ ] Context blocks are complete (no placeholders or TBDs)

---

## Anti-Patterns

- Never force 3-tier hierarchy when 2-tier suffices
- Never allow file ownership overlap between agents
- Never create teams without reading the codebase to verify boundaries
- Never skip the pre-delivery review
- Never let managers implement anything -- they orchestrate workers only
- Never embed more than 4 worker prompts in a single manager context
- Never allow unbounded review loops -- hard cap at 3 cycles, then escalate

---

## Output

The team design document (Steps 1-6) is the deliverable. It feeds into the agent-dispatch cycle.

**Do NOT assemble a copy-paste team prompt in the output.** The design document contains the context blocks (Step 4) and the templates are reference formats for dispatch. Prompt assembly happens at dispatch time — not here.

**Templates:**
- [`templates/team-prompt-2tier.template.md`](templates/team-prompt-2tier.template.md) — 2-tier team prompt format (lead + workers)
- [`templates/team-prompt-3tier.template.md`](templates/team-prompt-3tier.template.md) — 3-tier team prompt format (lead + managers + workers)

Parzival activates all agents himself — the user does not run agents.

**MANDATORY NEXT STEP**: After user approves the dispatch plan:
- BMAD agents → /aim-bmad-dispatch
- Generic agents → /aim-agent-dispatch

Pass the full dispatch plan (provider, model, agent role, task, files, mode) to the next skill.
