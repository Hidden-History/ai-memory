---
name: aim-parzival-team-builder
description: Design agent team structure for parallel work execution
allowed-tools: Read
context: fork
---

# Team Builder

**Purpose**: Analyze work to be parallelized, design the appropriate team structure (single agent, 2-tier, or 3-tier), and produce a team design document ready for execution via the agent-dispatch cycle.

**Note**: This skill is the entry point for team design. Parzival designs teams here, then executes them via the agent-dispatch workflow. Parzival activates agents himself -- the user does not run agents.

> **HARD PROHIBITION**: This skill (aim-parzival-team-builder) MUST NEVER spawn or activate agents itself -- **including when it runs as `context: fork`**. It emits the dispatch plan ONLY. Parzival performs all dispatch via the agent-dispatch workflow. Even as a fork, this skill must not launch agents -- spawning from within this skill bypasses the agent-dispatch workflow and is forbidden.

---

## Fast Path: Single Agent

The fast path trims the 6-step design for a single uncoordinated agent — it still emits a structured dispatch plan and routes through the full pipeline.

### Trigger Criteria (ALL must hold)

- **Single agent**: exactly one executor, no lead/worker split
- **No parallelization**: no peer agents, no file-ownership partitioning
- **Clear file ownership**: every file the agent will touch is already known at
  dispatch time (no "will discover what to modify")
- **Single review cycle**: at most one reviewer planned (dual review still
  permitted — see `reviewer_plan.mode`)
- **No cross-cutting concerns**: the task does not force interface contracts
  with other in-flight work

If any criterion fails, fall through to the full Team Design Process.

### Fast Path Execution

1. Collect provider and model preferences (Step 1b)
2. Assign agent role and AI_MEMORY_AGENT_ID (Step 2.3)
3. Prepare the context block (Step 4 format)
4. Emit the compact Dispatch Plan (see `Dispatch Plan Schema` below) for approval
5. On approval, route to `/aim-agent-dispatch` — the plan object is passed
   verbatim to the downstream skill

**No activation greeting, no menu display, no multi-step analysis narration.**
The fast path should read like a form, not a conversation.

### Fast Path Compact Output Example

```yaml
# Dispatch Plan v1
provider: claude
model: claude-sonnet-4-6
agent: dev
agent_id: dev-auth
bmad_agent_type: dev
task_summary: "Implement Story 4.2 password-reset endpoint"
files:
  - /abs/path/src/auth/reset.py
  - /abs/path/tests/test_reset.py
workspace_root: /mnt/e/projects/dev-ai-memory
complexity: moderate
reviewer_plan:
  mode: single
  models: [claude-sonnet-4-6]
route: aim-agent-dispatch
# Approve?
```

---

## Dispatch Plan Schema (v1)

Every team-builder invocation — fast path, preset, or full design — emits a
**Dispatch Plan** object. Downstream skills (`aim-agent-dispatch`,
`aim-model-dispatch`) MUST accept this object as structured data and re-emit it
verbatim to the next skill in the chain.

**Goal**: model IDs like `glm-5.1:cloud` must survive the pipeline without
paraphrase-corruption (no `glm-5`, no "use the latest glm"). File lists must
not collapse to prose.

### Schema

```yaml
# Dispatch Plan v1
provider: claude | openrouter | ollama | gemini | deepseek | groq | cerebras | mistral | openai | vertex-ai | siliconflow
model: <exact-model-id-string>       # verbatim, e.g., "glm-5.1:cloud", "claude-sonnet-4-6"
agent: <role-name>                   # dev | pm | architect | analyst | ux-designer | tech-writer | code-reviewer | <generic>
agent_id: <AI_MEMORY_AGENT_ID>       # e.g., "dev-auth", "review-opus", "architect-design"
bmad_agent_type: <type> | null       # null ONLY for genuine non-BMAD work (code-reviewer, verify). If a BMAD role fits, null is a FAIL — assign the persona.
task_summary: <one-line>
files:
  - <absolute-path-1>
  - <absolute-path-2>
workspace_root: <absolute-path>      # MUST contain _ai-memory/ + _bmad/ + oversight/
complexity: straightforward | moderate | significant | complex
reviewer_plan:
  mode: none | single | dual
  models: [<reviewer-model-1>, <reviewer-model-2>]  # empty list when mode=none
route: aim-agent-dispatch            # which dispatch skill to invoke next
```

### Round-Trip Rules

- **All keys always present.** Emit `null` or empty list for not-applicable
  fields rather than omitting the key — keeps schema stable.
- **No paraphrasing.** When passing the plan to the next skill, copy the object
  as-is. Never reformat model IDs, never summarize file lists to "the auth
  files", never drop `agent_id` or `bmad_agent_type`.
- **Validation gate.** The downstream skill MUST re-emit the plan unchanged in
  its first action. If a field is missing or malformed, STOP and request a
  corrected plan from the caller.
- **Source of truth.** `workspace_root` is verified by the CWD sentinel in
  `aim-model-dispatch`. The plan is the record; the sentinel is the check.

### When Full Design Is Required

The full 6-step Team Design Process emits one Dispatch Plan per team member
plus a Team Document describing the overall structure. The fast path emits a
single plan. Presets emit a preset-specific fan-out of plans. In all cases the
schema above applies per-agent.

---

## Team Presets

Before running the full 6-step design process, check if the work matches a preset. Presets are pre-validated team configurations for common patterns — they skip Steps 1-5 and go straight to confirmation.

**How to use**: Match the user's request against the presets below. If it matches, present the preset with customizations (file paths, story IDs, model overrides). User approves → route directly to dispatch. If no preset matches, fall through to the full Team Design Process.

### Preset: Sprint Development (`sprint-dev`)
**When**: 2-3 stories need parallel implementation with code review
**Structure**: 2-tier — PM Lead (Opus) → 2 DEV workers (Sonnet) + 1 DEV reviewer (Opus)
**Workflow commands**: Workers run `/bmad-dev-story`, reviewer runs `/bmad-code-review`
**Requires**: sprint-status.yaml, architecture doc
**Customize**: story assignments, file ownership per story

### Preset: Story Preparation (`story-prep`)
**When**: Multiple stories need to be created from epics in bulk
**Structure**: 2-tier — PM Lead (Opus) → 2-3 story-creation workers (Sonnet, run `/bmad-create-story`)
**Workflow commands**: Workers run `/bmad-create-story`
**Requires**: epics doc, sprint-status.yaml
**Customize**: which stories to create, epic references

### Preset: Test Automation (`test-automation`)
**When**: Completed stories need automated test coverage
**Structure**: 2-tier — Architect Lead (Opus) → 2 test workers (Sonnet, run `/bmad-qa-generate-e2e-tests`)
**Workflow commands**: Workers run `/bmad-qa-generate-e2e-tests` — generates automated API and E2E tests for completed story implementations
**Requires**: sprint-status.yaml, bmm + tea modules installed
**Customize**: which stories to test, test framework

### Preset: Architecture Review (`architecture-review`)
**When**: Pre-sprint architecture work with parallel research
**Structure**: 2-tier — Architect Lead (Opus) → Analyst worker (Sonnet) + UX Designer worker (Sonnet)
**Workflow commands**: Analyst runs `/bmad-technical-research`, UX runs `/bmad-ux`
**Requires**: PRD
**Customize**: research focus areas, UX scope

### Preset: Research (`research`)
**When**: Phase 1 parallel research across market, domain, and technical
**Structure**: 2-tier — Analyst Lead (Opus) → 3 Analyst workers (Sonnet)
**Workflow commands**: `/bmad-market-research`, `/bmad-domain-research`, `/bmad-technical-research`
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
BMAD Agent Types: [per-worker bmad_agent_type, e.g. dev, pm; null for generic]
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

1. Assign agent roles from available BMAD agents (analyst, pm, architect, dev, ux-designer, tech-writer)
2. Size teams: 3-5 teammates recommended, 5-6 tasks per teammate for productive sizing
3. **Assign agent identity**: Each agent MUST have a unique `AI_MEMORY_AGENT_ID`:
   - **Domain-named** (recommended): `dev-auth`, `dev-api`, `review-auth` -- same agent always works on same domain
   - **Numbered** (for generic work): `dev-1`, `dev-2`, `review-1` -- interchangeable agents
   - **Single-instance**: `pm`, `architect` -- use role name directly
   - Same `AI_MEMORY_AGENT_ID` across sessions enables cross-session memory accumulation
4. Select models per agent role:
   - Planning agents (Analyst, PM, Architect): Opus
   - Execution agents (DEV, review): Sonnet
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
- BMAD AGENT TYPE: Intended BMAD agent type (`bmad_agent_type`), e.g. dev; null for generic, non-BMAD agents
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
- Never spawn/activate agents from within this skill (even as a `context: fork`) -- emit the dispatch plan only; Parzival dispatches

---

## Output

The team design document (Steps 1-6) is the deliverable. It feeds into the agent-dispatch cycle.

**Do NOT assemble a copy-paste team prompt in the output.** The design document contains the context blocks (Step 4) and the templates are reference formats for dispatch. Prompt assembly happens at dispatch time — not here.

**Templates:**
- [`templates/team-prompt-2tier.template.md`](templates/team-prompt-2tier.template.md) — 2-tier team prompt format (lead + workers)
- [`templates/team-prompt-3tier.template.md`](templates/team-prompt-3tier.template.md) — 3-tier team prompt format (lead + managers + workers)

Parzival activates all agents himself — the user does not run agents.

**MANDATORY NEXT STEP**: After user approves the dispatch plan:
- All agents (BMAD and generic) → /aim-agent-dispatch

Pass the full Dispatch Plan object verbatim — including exact model ID, full file list, `agent_id`, and `bmad_agent_type` (see `Dispatch Plan Schema`). Downstream skills re-emit the plan for round-trip verification. (`bmad_agent_type` identifies the intended BMAD agent type, e.g. dev; null for generic agents.)
