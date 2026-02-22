# Parzival: Technical PM & Quality Gatekeeper

Parzival is your AI project manager for Claude Code. It orchestrates agent teams, enforces quality gates, tracks project state, and persists context across sessions — all backed by structured oversight files and Qdrant vector search.

Without Parzival, you manually re-orient Claude Code at the start of each session, agents skip quality checks, and review findings get acted on blindly regardless of accuracy. With Parzival, context loads automatically, every completed task triggers an enforced review cycle, and every recommendation is checked against your actual project files before you see it.

---

## What Parzival Does

Parzival fills eight distinct roles in your development workflow.

### 1. Technical Project Manager

Tracks sprints, tasks, blockers, risks, and decisions across sessions. Maintains oversight files that persist between sessions. At session start, presents exactly where you left off — last session summary, current task state, active blockers, and live risks. You never re-explain context.

### 2. Quality Gatekeeper

Enforces mandatory review-then-fix cycles until review finds zero issues. Parzival does not accept "looks good enough." After every task, it provides a review agent prompt. If issues are found, it provides a fix prompt. The cycle repeats until the review is clean. Only then does Parzival surface findings for your decision.

### 3. Agent Team Orchestrator

You describe the work. Parzival reads your project files — architecture docs, PRD, standards, existing code — then builds precise agent prompts or 3-tier hierarchical team prompts with exact file paths, line numbers, acceptance criteria, and project-specific constraints. The `/parzival-team` command generates these prompts. Parzival never executes the agents — you do.

### 4. False Positive Catcher

When review agents flag issues, not all findings are valid. Some are false positives from review agents that misunderstand the codebase or project requirements. Parzival verifies all review findings against actual project files and source code before acting on them. This prevents wasted fix cycles for things that were never broken.

### 5. Verified Instructions Provider

Every recommendation is checked against project files first. Confidence levels accompany all guidance:

- **Verified** — Directly confirmed from source
- **Informed** — Good evidence, not directly verified
- **Inferred** — Reasoning from patterns
- **Uncertain** — Insufficient information
- **Unknown** — No basis for position

Parzival never guesses. It checks sources or admits uncertainty.

### 6. Decision Support

When facing a choice, Parzival presents options with pros and cons, tradeoffs, source citations, and confidence levels. Documents decisions with rationale in `oversight/decisions/decisions-log.md` for future reference.

### 7. Risk and Blocker Tracker

Proactively identifies risks. Maintains a risk register and blockers log. Escalation levels determine how urgently an issue is surfaced:

| Level | Trigger | Response |
|-------|---------|----------|
| Critical | Security, data loss, compliance | Interrupt immediately |
| High | Significant impact | Surface at next natural break |
| Medium | Moderate impact | Include in status report |
| Low | Minor concern | Log for future consideration |

### 8. Session Continuity

Session handoffs are dual-written to local oversight files and Qdrant vector search. At session start, the automatic SessionStart hook queries Qdrant for bootstrap context. Running `/parzival-start` loads local oversight files for PM-level project status. Both layers work together to restore full context.

---

## The Parzival Workflow

### Starting a Session

1. Start Claude Code — the SessionStart hook runs automatically and queries Qdrant for bootstrap context (recent session summaries, relevant decisions, active patterns, applicable conventions).
2. Run `/parzival-start` — Parzival reads local oversight files and presents:
   - Last session summary (what was completed)
   - Current task and its status
   - Active blockers
   - Active risks
   - Recommended next step
3. You decide what to work on.

### Working with Parzival

1. Describe what needs to be done.
2. Parzival analyzes requirements — reads architecture docs, PRD, standards, and existing code before responding.
3. Parzival creates agent prompts with:
   - Exact file paths and line numbers
   - Acceptance criteria derived from your project specs
   - Project-specific context and constraints
   - Review requirements
4. You execute the agents. Parzival never executes them.
5. Parzival reviews results:
   - Checks for issues
   - Verifies review findings against actual code (catches false positives)
   - Provides fix prompts for confirmed issues
6. Review → fix → re-review cycle continues until zero issues remain.
7. You approve the work. Parzival never marks work complete on its own.

### Building Agent Teams (`/parzival-team`)

For parallel work, Parzival generates a 3-tier hierarchical team prompt:

- **Tier 1 — Team Lead**: Coordinates workers, manages task distribution, aggregates results
- **Tier 2 — Parallel Workers**: Dev agents with specific, scoped tasks and verified acceptance criteria
- **Tier 3 — Reviewers**: Adversarial code review agents that challenge the workers' output

All prompts include verified project context pulled from your actual project files. A typical team might be 4 Sonnet dev workers with 2 rounds of Opus adversarial review. You paste the generated prompt into a new Claude Code session.

### Ending a Session

1. Run `/parzival-closeout`
2. Parzival creates a handoff file in `oversight/session-logs/`
3. Dual-writes the handoff to Qdrant `discussions` collection
4. Updates `SESSION_WORK_INDEX.md`
5. Next session picks up exactly where you left off

---

## Session Start — Technical Details

Context loading uses two independent layers that complement each other.

### Layer 1 — Automatic: SessionStart Hook

The SessionStart hook (`.claude/hooks/scripts/session_start.py`) runs on every session event without any manual invocation.

**On `startup` trigger (new session):**

Calls `retrieve_bootstrap_context()` via `MemorySearch`, querying Qdrant for conventions, guidelines, and recent findings. Token budget: `BOOTSTRAP_TOKEN_BUDGET` (default 2,500 tokens).

**On `resume` or `compact` trigger (session restore):**

1. Queries `discussions` collection for recent session summaries
2. Searches `discussions` for relevant decisions
3. Searches `code-patterns` for relevant patterns
4. Searches `conventions` for applicable conventions

**Fallback (Qdrant unavailable):**

Outputs empty context and logs a warning. Claude continues without memory injection.

### Layer 2 — Manual: `/parzival-start` Command

Reads local oversight files for PM-level project status. Always reads from the filesystem — does not require Qdrant:

1. `oversight/SESSION_WORK_INDEX.md` — running log of sessions and sprint state
2. Latest `oversight/session-logs/SESSION_HANDOFF_*.md` — last session closeout snapshot
3. `oversight/tracking/task-tracker.md` — active task list
4. `oversight/tracking/blockers-log.md` — open blockers
5. `oversight/tracking/risk-register.md` — risk register

This provides the PM-level status view independently of Qdrant availability.

---

## Commands Reference

Commands live in `.claude/commands/parzival/` and are invoked with `/`.

### Session Management

| Command | When to Use | What It Does |
|---------|------------|--------------|
| `/parzival-start` | Beginning of every work session | Loads local oversight files, presents session summary, current task, blockers, and risks |
| `/parzival-closeout` | End of session or before a break | Creates handoff file, dual-writes to Qdrant, updates work index |
| `/parzival-status` | Quick check mid-session | Shows current state without full context reload — faster than start |
| `/parzival-handoff` | After completing significant work during a session | Creates a mid-session snapshot without ending the session |

### Problem Solving

| Command | When to Use | What It Does |
|---------|------------|--------------|
| `/parzival-blocker` | Stuck on a problem | Analyzes the blocker, presents resolution options with tradeoffs and confidence levels |
| `/parzival-decision` | Choosing between approaches | Presents options with pros, cons, source citations, and a recommendation |

### Quality Gates

| Command | When to Use | What It Does |
|---------|------------|--------------|
| `/parzival-verify` | After implementation is complete | Runs the verification checklist against acceptance criteria |
| `/pov:agents:code-reviewer` | After any implementation | Invokes the Code Reviewer subagent for adversarial code review |
| `/pov:agents:verify-implementation` | After code review passes | Verifies implementation against acceptance criteria end-to-end |

### Agent Coordination

| Command | When to Use | What It Does |
|---------|------------|--------------|
| `/parzival-team` | Complex work requiring parallel agents | Generates a complete 3-tier hierarchical team prompt with verified project context |

---

## Skills Reference

Skills provide direct Qdrant storage operations and are invoked as Claude Code skills.

| Skill | Description |
|-------|-------------|
| `/parzival-save-handoff` | Manually store handoff content to Qdrant (used internally by `/parzival-closeout`) |
| `/parzival-save-insight` | Store a learned insight to Qdrant for future retrieval |

### Saving an Insight Mid-Session

Use `/parzival-save-insight` to capture important knowledge before it gets lost:

```bash
/parzival-save-insight "Qdrant requires the api-key header on ALL endpoints including /health"
```

Stored with `type: agent_insight`, `half_life_days: 180` for long-lived learned knowledge.

---

## Quality Gate Deep Dive

Parzival enforces quality gates — it does not suggest them. The cycle is non-negotiable.

### The Mandatory Review Cycle

After every task completion:

```
1. Parzival provides a review agent prompt
2. You run the review (code-reviewer or verify-implementation subagent)
3. Review agent reports findings
4. Parzival checks each finding against actual project files
      └─ False positive? → Flag it, skip the fix
      └─ Confirmed issue? → Provide fix prompt
5. You apply confirmed fixes
6. Return to step 1 (re-review)
7. Repeat until review finds ZERO issues
8. Parzival presents clean findings for your approval
9. You decide whether to mark work complete
```

### False Positive Verification

This step is what separates Parzival from a simple review wrapper. Before providing a fix prompt, Parzival reads the relevant source files, architecture docs, and project standards to confirm whether the flagged issue is genuinely a problem in the context of your project. If the review agent misunderstood the codebase or is applying generic patterns that conflict with your project's documented approach, Parzival catches it.

### What Parzival Never Does

- Accepts work with known issues
- Says "looks good" without running a review
- Skips review because something is "probably fine"
- Suggests moving on while issues remain
- Approves or marks work complete — that decision always belongs to you

If you try to skip the review cycle:

```
Parzival: "I cannot approve moving forward without verification (Quality Gatekeeper
Constraint). We need to run code review before proceeding.

Review agent prompt: [prompt provided]

This is non-negotiable for quality gates."
```

---

## Confidence Levels

Every recommendation from Parzival includes a confidence level. This tells you how much to trust the recommendation and whether additional verification is warranted before acting.

| Level | Meaning | When You See It |
|-------|---------|-----------------|
| **Verified** | Directly confirmed from the cited source | Parzival read the file and confirmed the specific claim |
| **Informed** | Good evidence exists, not directly verified | Strong indicators but Parzival did not read the primary source |
| **Inferred** | Reasoning from similar patterns | No direct source — extrapolating from related context |
| **Uncertain** | Insufficient information to recommend confidently | Parzival needs more context or source access |
| **Unknown** | No basis for a position | Parzival does not have enough context and will not guess |

When Parzival is Uncertain or Unknown, it will say so explicitly and either ask for clarification or offer to check a specific file before proceeding. It does not fill gaps with assumptions.

---

## Oversight Directory Structure

The installer deploys a set of template directories to `oversight/` that Parzival uses for tracking and documentation. These files are the persistent state of your project from Parzival's perspective.

```
oversight/
├── SESSION_WORK_INDEX.md          ← Running log of sessions and sprint state; loaded at /parzival-start
├── session-logs/                  ← One handoff file per /parzival-closeout run; complete session history
│   └── YYYY-MM-DD-HH-MM-session-handoff.md
├── tracking/
│   ├── task-tracker.md            ← Current sprint tasks, statuses, assignees
│   ├── blockers-log.md            ← Open blockers with severity and owner
│   └── risk-register.md           ← Active risks with escalation level and mitigation status
├── decisions/
│   └── decisions-log.md           ← Architectural decisions with context, options, rationale, tradeoffs
├── plans/                         ← Sprint and project plans (PLAN-NNN-*.md)
├── specs/                         ← Technical specifications (SPEC-NNN-*.md)
├── knowledge/
│   └── best-practices/            ← Cached research findings (BP-NNN-*.md)
└── standards/
    └── PROJECT_STANDARDS.yaml     ← Project-specific conventions checked before every recommendation
```

**Critical:** The `oversight/` folder contains active session data. The installer never overwrites it during updates. Old handoffs in Qdrant are subject to decay scoring (180-day half-life) and can be archived with `/memory-purge` if the directory grows large.

---

## Enabling Parzival

### During Install

The installer prompts for Parzival setup:

```
Enable Parzival session agent? [y/N]
Your name (for handoffs and oversight docs): YourName
Preferred language [English]:
```

On confirmation, the installer deploys:
- Commands to `.claude/commands/parzival/`
- Agent files to `.claude/agents/parzival/`
- Oversight directory templates to `oversight/`

### Manual Enable

If you skipped Parzival during install, add these to your `.env`:

```bash
PARZIVAL_ENABLED=true
PARZIVAL_USER_NAME=YourName
PARZIVAL_LANGUAGE=English
```

Then re-run the installer targeting the Parzival component:

```bash
bash install.sh --component parzival
```

### Activating the Agent

```bash
cd /path/to/your-project
claude
```

Then activate Parzival with the slash command:

```
/pov:agents:parzival
```

Parzival loads its configuration, greets you by name, and displays its command menu.

---

## Without Parzival

All core AI Memory features work independently of Parzival. What you lose is the oversight layer.

| Capability | Without Parzival |
|------------|-----------------|
| Agent team orchestration | Not available — you write team prompts manually |
| Quality gate enforcement | Not available — review cycles are optional, not enforced |
| Verified instructions | Not available — agents work from their own assumptions |
| False positive catching | Not available — all review findings acted on without verification |
| Cross-session project management | Not available — manual context-setting each session |
| Risk and blocker tracking | Not available — no structured register or escalation |
| Decision support with confidence levels | Not available — no structured options or source citations |
| Session continuity via Qdrant | Not available |
| `agent_handoff` / `agent_insight` namespace | Not available |
| Decay scoring, freshness detection, GitHub sync | Available — independent of Parzival |
| `/search-memory`, `/search-jira`, `/search-github` | Available — independent of Parzival |

If you do not need cross-session continuity or quality enforcement, you can skip Parzival and rely on manual context-setting. But if you run multi-session projects with agent teams, quality gates, and complex architectural decisions, Parzival is what keeps that work coherent.
