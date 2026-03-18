# Team Builder Guide

**Skill**: `aim-parzival-team-builder` | **Menu Code**: TP | **Version**: 2.1

---

## Overview

The Team Builder is Parzival's skill for designing agent teams that execute work in parallel. When a task can be decomposed into independent units -- multiple stories to implement, research across domains, test coverage for several modules -- the Team Builder analyzes the work, selects the right team structure, assigns file ownership, and produces a team design document ready for dispatch.

Parzival designs teams and activates agents. The user does not run agents directly. After the team design is approved, Parzival routes it to the dispatch layer (`aim-agent-dispatch` or `aim-bmad-dispatch`) for execution.

---

## How It Works

The Team Builder follows a structured process from analysis through to dispatch-ready output.

### Process Flow

```
Work request
  --> Preset check (skip to dispatch if matched)
  --> Preflight analysis (identify parallelizable units)
  --> Tier selection (single / 2-tier / 3-tier)
  --> Team composition (roles, models, agent IDs)
  --> File ownership map (zero overlap enforced)
  --> Context block assembly (per-agent instructions)
  --> Conflict avoidance strategy
  --> Pre-delivery review checklist
  --> User approval
  --> Route to dispatch
```

### Step-by-Step

| Step | Action | Output |
|------|--------|--------|
| 0 | **Preset Check** | Match against common patterns; skip to confirmation if found |
| 1 | **Preflight Analysis** | List of independent work units, dependency map, tier recommendation |
| 2 | **Team Composition** | Agent roles, models, unique agent IDs, team size (3-5) |
| 3 | **File Ownership Map** | Every modified file assigned to exactly one agent; zero conflicts |
| 4 | **Context Blocks** | Per-agent: ROLE, TASK, FILES, CONSTRAINTS, DONE WHEN |
| 5 | **Conflict Avoidance** | Strategy selection (worktree isolation, exclusive ownership, etc.) |
| 6 | **Pre-Delivery Review** | Checklist verification before presenting to user |

---

## Team Presets

Before running the full design process, the Team Builder checks if the work matches a known pattern. Presets are pre-validated team configurations that skip Steps 1-5.

| Preset | When to Use | Structure |
|--------|-------------|-----------|
| `sprint-dev` | 2-3 stories need parallel implementation with code review | 2-tier: SM Lead (Opus) -> 2 DEV workers (Sonnet) + 1 reviewer (Opus) |
| `story-prep` | Multiple stories need to be created from epics | 2-tier: PM Lead (Opus) -> 2-3 SM story creators (Sonnet) |
| `test-automation` | Completed stories need automated test coverage | 2-tier: TEA Lead (Opus) -> 2 QA workers (Sonnet) |
| `architecture-review` | Pre-sprint architecture with parallel research | 2-tier: Architect Lead (Opus) -> Analyst + UX Designer (Sonnet) |
| `research` | Phase 1 parallel research (market, domain, technical) | 2-tier: Analyst Lead (Opus) -> 3 Analyst workers (Sonnet) |

If no preset matches, the full 6-step design process runs.

---

## When to Use Each Tier

### Single Agent (Fast Path)

Use when the work is a single task that does not benefit from parallelization.

**Criteria:**
- One task, one agent, one review cycle
- No file ownership conflicts
- No parallel coordination needed

The fast path skips the full design process and produces a compact output for immediate dispatch.

### 2-Tier (Flat)

Use for simple parallel work where a lead coordinates workers directly.

**Structure:** Lead -> Workers (teammates)

```
Lead (coordinates via TaskCreate, SendMessage)
  ├── Worker 1 (teammate)
  ├── Worker 2 (teammate)
  └── Worker 3 (teammate)
```

**When appropriate:**
- 2-6 parallel tasks
- Single domain or loosely coupled domains
- One review cycle covers all work
- Workers report directly to lead

**Worker prompt structure** (8 elements): ROLE, OBJECTIVE, SCOPE, CONSTRAINTS, BACKGROUND, DELIVERABLE, COORDINATION, SELF-VALIDATION.

### 3-Tier (Hierarchical)

Use for complex multi-domain work where managers own domain-level coordination.

**Structure:** Lead -> Managers (teammates) -> Workers (subagents)

```
Lead (coordinates managers via SendMessage)
  ├── Manager 1 — Domain A (teammate)
  │     ├── Worker 1a (subagent)
  │     ├── Worker 1b (subagent)
  │     └── Review agent (subagent)
  └── Manager 2 — Domain B (teammate)
        ├── Worker 2a (subagent)
        ├── Worker 2b (subagent)
        └── Review agent (subagent)
```

**When appropriate:**
- 3+ distinct domains (e.g., backend API, frontend UI, database)
- Multiple tasks per domain
- Domain-level review required before cross-domain integration
- Lead should not manage individual workers

**Key distinction:** Managers spawn workers as subagents (Agent tool without `team_name`), not as teammates. Workers return results to their manager; the lead never communicates directly with workers.

**Manager prompt structure** (10 elements): ROLE, OBJECTIVE, SCOPE, WORKER ROSTER, REVIEW PROTOCOL, TASK CHECKLIST, QUALITY GATES, CONSTRAINTS, CONTEXT FOR WORKERS, REPORTING.

---

## Team Sizing

| Guideline | Recommendation |
|-----------|---------------|
| Teammates per team | 3-5 (split into multiple teams if larger) |
| Tasks per teammate | 5-6 for productive sizing |
| Workers per manager (3-tier) | 2-4 workers + 1 review agent |
| Max worker prompts per manager | 4 (to avoid context overload) |
| Max review-fix cycles | 3 per deliverable, then escalate |

Undersized teams (1-2 agents) should use the single agent fast path or a minimal 2-tier setup. Oversized teams (6+) should be split across multiple teams or restructured as 3-tier.

---

## Agent Identity

Every agent receives a unique `AI_MEMORY_AGENT_ID` that persists across sessions. This enables cross-session memory accumulation -- the same agent working on the same domain builds up relevant context over time.

### Naming Conventions

| Convention | Format | When to Use | Example |
|------------|--------|-------------|---------|
| **Domain-named** (recommended) | `{role}-{domain}` | Agent always works on the same domain/files | `dev-auth`, `dev-api`, `review-auth` |
| **Numbered** | `{role}-{n}` | Interchangeable agents doing generic parallel work | `dev-1`, `dev-2`, `review-1` |
| **Single-instance** | `{role}` | Only one agent of this type exists | `pm`, `architect` |

**Rules:**
- Domain-named agents always work the same domain and files across sessions.
- Numbered agents are interchangeable; any can be assigned any unit of generic work.
- Single-instance agents use the role name directly when there is only one.

---

## Integration with Dispatch

The Team Builder produces a design document. It does not assemble final prompts or activate agents. After the user approves the design, Parzival routes to dispatch:

| Dispatch Skill | When Used |
|----------------|-----------|
| `aim-bmad-dispatch` | Activating BMAD agents (dev, pm, architect, sm, analyst, ux) |
| `aim-agent-dispatch` | Activating generic (non-BMAD) agents |
| `aim-model-dispatch` | Selecting the appropriate model for each agent role |

Dispatch uses the context blocks from Step 4 and the prompt templates (`team-prompt-2tier.template.md` or `team-prompt-3tier.template.md`) to assemble the final prompts when spawning agents.

### Dispatch Routing Flow

```
Team design approved
  --> aim-model-dispatch (select models per agent)
  --> aim-bmad-dispatch or aim-agent-dispatch (activate agents)
  --> aim-agent-lifecycle (monitor, review, accept/loop, shutdown)
```

---

## Constraints

Two global constraints govern how agents are spawned and activated.

### GC-19: Spawn Agents as Teammates

All BMAD agents must be spawned using the Agent tool with the `team_name` parameter. Standalone subagent dispatches (Agent tool without `team_name`) are forbidden for BMAD agent work.

**Why:** Without `team_name`, agents lack Edit and Write tool permissions required for implementation. The teammate pattern also enables SendMessage for follow-up communication and lifecycle management (monitor, review, shutdown).

**Exception:** In 3-tier teams, managers spawn their workers as subagents (without `team_name`). This is intentional -- workers return results to the manager and do not need direct communication with the lead.

### GC-20: Activation and Instruction Are Separate

When activating a BMAD agent, the activation command and the task instruction must be sent as two separate messages.

**Required sequence:**
1. Spawn agent (Agent tool with `team_name`)
2. Send activation command only (e.g., `/bmad-agent-bmm-dev`)
3. Wait for agent menu/greeting (confirms persona is loaded)
4. Send task instruction as a separate message

**Why:** BMAD agents load their full persona, skills, and workflow context during activation. Sending instructions before this loading completes causes the agent to operate with incomplete configuration.

---

## Conflict Avoidance Strategies

The Team Builder selects from these strategies, ranked by effectiveness:

| Rank | Strategy | Description |
|------|----------|-------------|
| 1 | **Git Worktree Isolation** | Each worker gets an independent filesystem copy (`isolation: "worktree"`) |
| 2 | **Exclusive File Ownership** | Enforced by the ownership map -- no file belongs to two agents |
| 3 | **Directory Partitioning** | Workers own directories, not individual files |
| 4 | **Interface Contracts** | Workers producing compatible code agree on interfaces first |
| 5 | **Merge-on-Green** | Code merges to main only when all tests pass |

File locking is never used. Production testing showed it collapsed 20 agents to throughput of 2-3.

For WSL2 environments, in-process mode is recommended. tmux-based execution works best on macOS.

---

## Examples

### Example 1: Parallel Story Implementation (2-Tier)

**Scenario:** Sprint has 3 independent stories: auth flow refactor, API pagination, and dashboard charts. No shared files.

**Team design:**

```
Preset Match: sprint-dev
Structure: 2-tier — SM Lead (Opus) → 3 DEV workers (Sonnet) + 1 reviewer (Opus)
Stories:
  dev-auth  -> Story S-101: Auth flow refactor     -> src/auth/**
  dev-api   -> Story S-102: API pagination          -> src/api/pagination/**
  dev-dash  -> Story S-103: Dashboard charts        -> src/components/charts/**
Conflict Strategy: Exclusive file ownership (no overlap)
Workflow: Workers run /bmad-bmm-dev-story, reviewer runs /bmad-bmm-code-review
```

Why 2-tier: Single domain of concern (implementation), no cross-domain review needed, stories are independent.

### Example 2: Full-Stack Feature Build (3-Tier)

**Scenario:** New feature requires backend API endpoints, frontend UI components, and database migrations. Each domain has multiple tasks with domain-specific review requirements.

**Team design:**

```
Structure: 3-tier
Team: full-stack-feature

Manager 1: mgr-backend (Opus)
  Workers: dev-api (Sonnet), dev-models (Sonnet)
  Review: review-backend (Sonnet)
  Files: src/api/**, src/models/**, tests/api/**

Manager 2: mgr-frontend (Opus)
  Workers: dev-ui (Sonnet), dev-state (Sonnet)
  Review: review-frontend (Sonnet)
  Files: src/components/**, src/store/**, tests/components/**

Conflict Strategy: Git worktree isolation + interface contracts
  Backend publishes API contract -> Frontend consumes
  Contract relay through lead
```

Why 3-tier: Three distinct domains (backend, frontend, database), multiple tasks per domain, domain-level review needed before integration, interface contracts required between domains.

---

## Anti-Patterns

| Anti-Pattern | Why It Fails |
|-------------|-------------|
| Forcing 3-tier when 2-tier suffices | Unnecessary overhead; managers add latency without value |
| Allowing file ownership overlap | Merge conflicts, lost work, unpredictable state |
| Skipping codebase read before designing | Boundaries drawn wrong; ownership conflicts discovered mid-execution |
| Letting managers implement | Managers lose oversight context; review quality degrades |
| Embedding 5+ worker prompts in one manager | Context overload; manager loses track of worker state |
| Unbounded review loops | Infinite cycles; hard cap at 3 then escalate to lead |
| Skipping the pre-delivery review | Missing assignments, ownership gaps, incomplete context blocks |

---

## Optional Features

### Worktree Isolation

Add `isolation: "worktree"` to Agent tool spawn parameters. Each agent (or manager in 3-tier) gets an independent filesystem copy, eliminating all file conflicts.

### Plan Approval Mode

Add `mode: "plan"` to Agent tool spawn parameters. Agents must submit their execution plan for lead approval before implementing. The lead reviews and approves via `SendMessage` (type: `plan_approval_response`).

### Contract-First Build

For teams where agents produce interfaces consumed by other agents. The lead acts as contract relay:
1. Upstream agent publishes contract
2. Lead verifies (exact URLs, JSON shapes, status codes)
3. Lead forwards to downstream agent
4. Implementation proceeds against locked contracts
5. Pre-integration diff catches mismatches

---

## Related Documentation

| Document | Description |
|----------|-------------|
| `_ai-memory/pov/skills/aim-parzival-team-builder/SKILL.md` | Full skill definition |
| `_ai-memory/pov/skills/aim-agent-dispatch/SKILL.md` | Generic agent dispatch skill |
| `_ai-memory/pov/skills/aim-bmad-dispatch/SKILL.md` | BMAD agent dispatch skill |
| `_ai-memory/pov/skills/aim-agent-lifecycle/SKILL.md` | Agent lifecycle management |
| `docs/parzival/BMAD-Multi-Agent-Architecture.md` | Multi-agent architecture research |
