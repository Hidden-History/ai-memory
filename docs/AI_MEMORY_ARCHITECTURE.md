# AI Memory Module - Complete Architecture Reference

**Purpose:** This document defines the complete architecture of the AI Memory Module. It explains WHAT we're building, WHY each component exists, and HOW they work together. This is the authoritative reference to prevent implementation mistakes.

**Last Updated:** 2026-03-02 (V2.0.9 — five-collection architecture, github collection separation)

---

## Table of Contents

1. [AI Memory Module Integration](#ai-memory-module-integration)
2. [The Vision](#the-vision)
3. [The "Aha Moment" Explained](#the-aha-moment-explained)
4. [Five-Collection Architecture](#five-collection-architecture)
5. [Hook System Overview](#hook-system-overview)
6. [Session Lifecycle Hooks](#session-lifecycle-hooks)
7. [Workflow Hooks (BMAD Integration)](#workflow-hooks-bmad-integration)
8. [Agent-Specific Memory Usage](#agent-specific-memory-usage)
9. [Token Budgets](#token-budgets)
10. [Validation Requirements](#validation-requirements)
11. [Data Flow Diagrams](#data-flow-diagrams)
12. [Common Mistakes to Avoid](#common-mistakes-to-avoid)

---

## AI Memory Module Integration

### What is BMAD?

BMAD (BMad Method) is a structured AI-assisted development methodology that uses specialized agents to guide software projects through phases: Analysis → Product Requirements → Architecture → Sprint Planning → Implementation → Testing.

**This memory module is an AI Memory Module** - it integrates with the BMAD system to provide persistent memory across all agents and workflows.

### Module Structure

The AI Memory Module follows the cohesive module pattern:

```
ai-memory/
  module.yaml              # Module configuration
  _bmad/
    agents/                # Agent memory integrations
    workflows/
      tools/               # Workflow hook scripts
        pre-work-search.py
        post-work-store.py
        store-chat-memory.py
        load-chat-context.py
  .claude/
    hooks/
      scripts/             # Claude Code lifecycle hooks
        session_start.py
        post_tool_capture.py
        agent_response_capture.py
        archived/          # Deprecated hooks
          session_stop.py
  src/
    memory/                # Core Python memory system
  docker/                  # Qdrant + monitoring stack
```

### Installation

**New Project:**
```bash
npx bmad-method install
# When prompted about custom modules, provide path to ai-memory
```

**Existing Project:**
```bash
npx bmad-method install
# Select "Modify BMad Installation"
# Choose "Add or update custom modules"
# Provide path to ai-memory
```

### How Agents Use Memory

Every BMAD agent can leverage the memory system. The memory hooks integrate at specific workflow steps:

| Agent | Memory Read | Memory Write | Primary Collection |
|-------|-------------|--------------|-------------------|
| **Analyst (Mary)** | Load previous research | Store analysis decisions | discussions |
| **PM (John)** | Load PRD patterns | Store requirement decisions | discussions |
| **Architect (Winston)** | Load architecture patterns | Store architecture decisions | code-patterns + discussions |
| **SM (Bob)** | Load story outcomes | Store sprint decisions | discussions |
| **DEV (Amelia)** | Load implementation patterns | Store code patterns | code-patterns |
| **Barry (Quick Flow)** | Load all relevant context | Store outcomes | code-patterns + discussions |
| **TEA (Murat)** | Load test strategies | Store test patterns | code-patterns |
| **Sally (UX)** | Load UX patterns | Store design decisions | discussions |
| **Paige (Tech Writer)** | Load documentation patterns | Store doc patterns | conventions |

### Workflow Integration Points

Memory hooks are injected at standard workflow steps:

```
Workflow Step 1:    Load story/task
Workflow Step 1.5:  PRE-WORK MEMORY SEARCH (blocking)
                    ├── Search code-patterns for feature patterns
                    └── Search discussions for previous decisions

Workflow Steps 2-6: Execute work (with memory context)

Workflow Step 6.5:  POST-WORK MEMORY STORAGE (non-blocking)
                    ├── Store implementation patterns
                    └── Store decisions made

Workflow Step 7:    Complete
```

### Module Configuration (module.yaml)

```yaml
code: ai-memory
name: AI Memory Module
version: 1.0.0
description: Persistent semantic memory for Claude Code and BMAD workflows
author: BMAD Community

# Module type
type: add-on
unitary: false

# Dependencies
requires:
  - docker
  - python3.10+

# Components provided
provides:
  - hooks: Claude Code lifecycle hooks
  - workflows: Memory search/store workflow tools
  - infrastructure: Qdrant vector database + monitoring

# Agent integrations
agent-integrations:
  - analyst
  - pm
  - architect
  - sm
  - dev
  - quick-flow-solo-dev
  - tea
  - ux-designer
  - tech-writer
```

### Claude Code + BMAD Dual Operation

This module works in TWO modes:

**1. Standalone Claude Code (without BMAD workflows)**
- SessionStart hook provides session continuity ("aha moment")
- PostToolUse hook captures code patterns automatically
- Stop hook saves session summary for next time

**2. Within BMAD Workflows**
- All standalone features PLUS:
- pre-work-search provides feature-specific patterns before implementation
- post-work-store captures structured outcomes after completion
- store-chat-memory preserves agent decisions
- load-chat-context retrieves previous agent reasoning

Both modes use the same five collections (`discussions`, `code-patterns`, `conventions`, `github`, `jira-data`) and the same Qdrant infrastructure.

---

## The Vision

### What We're Building

A **persistent semantic memory system** for Claude Code that provides:

1. **Session Continuity** - Claude remembers what happened in previous sessions
2. **Implementation Patterns** - Claude recalls how similar features were built before
3. **Shared Learning** - Best practices learned in one project help all projects

### Why We're Building It

**The Problem:**
- Claude Code sessions are stateless - each new session starts from zero
- Developers waste 30%+ of tokens re-establishing context every session
- Complex multi-session work is impractical because Claude "forgets"
- Lessons learned are lost between sessions

**The Solution:**
- Automatic memory capture during work (no manual effort)
- Automatic memory retrieval at session start and before tasks
- Semantic search finds relevant memories even with different wording
- Three separate memory types serve different purposes

### The Magic Moment

> "If I uninstalled this module right now, how would you feel?"
> - "Whatever" = Failed
> - "I'd be annoyed" = Partial success
> - "Please don't, I rely on it now" = **Success**

---

## The "Aha Moment" Explained

### What It Is

The "aha moment" is when Claude **proactively demonstrates memory of previous sessions** without the user having to remind it.

**Example - Without Memory:**
```
User: [Starts new session]
Claude: "Hello! How can I help you today?"
User: "Continue working on the Grafana dashboard fix"
Claude: "I don't have context about that. Can you explain what you're working on?"
```

**Example - With Memory (The Aha Moment):**
```
User: [Starts new session]
Claude: "Welcome back! In our last session, we worked on fixing the Grafana
dashboards. We identified that the Prometheus metrics weren't being scraped
correctly and updated memory-overview.json. Would you like to continue
where we left off?"
```

### How It Works

1. **Session 1 ends** → Stop hook captures session summary
2. Summary stored in `discussions` collection with project ID
3. **Session 2 starts** → SessionStart hook searches `discussions`
4. Previous session summaries retrieved and injected into Claude's context
5. Claude can reference previous work without being told

### Why It's a Separate Collection

Session summaries are **fundamentally different** from implementation patterns:

| Session Summaries (discussions) | Implementation Patterns (code-patterns) |
|----------------------------------|------------------------------------------|
| "What we did last time" | "How we built feature X" |
| High-level narrative | Specific code with file:line references |
| Always relevant at session start | Only relevant when working on similar features |
| Short-term continuity | Long-term reference |

**Mixing them causes problems:**
- Generic SessionStart query returns random code patterns (low relevance)
- User asks about Grafana, gets unrelated Python snippets
- The "aha moment" never happens

---

## Five-Collection Architecture

> **v2.0.9 Change:** The original three-collection architecture (discussions, code-patterns, conventions) has been expanded to five collections. GitHub-synced data was moved from `discussions` to a dedicated `github` collection (PLAN-010) to eliminate noise — 79.6% of discussions was GitHub framework markdown drowning real conversation data. The `jira-data` collection stores Jira issue and comment data.

### Collection 1: `discussions`

**Purpose:** Store session memories, chat decisions, and workflow context for continuity across sessions.

**What Goes Here:**
- Session summaries (from PreCompact hook)
- Workflow decisions (PM chose PostgreSQL over MongoDB)
- Agent reasoning (why we picked this architecture)
- Project classifications (greenfield/brownfield)

**What Does NOT Go Here (v2.0.9):**
- GitHub-synced data (`github_code_blob`, `github_issue`, `github_pr`, `github_commit`) → use `github` collection
- Low-value messages ("ok", "yes", "nothing to add") → filtered by quality gate

**Scope:** Project-isolated via `group_id`

**Searched By:** SessionStart hook, Tier 2 context injection (filtered by type), load-chat-context workflow hook

**Written By:** PreCompact hook, store-chat-memory workflow hook

**Example Payload:**
```json
{
  "content": "Session summary: Fixed Grafana dashboards by updating Prometheus queries. Modified memory-overview.json to use correct metric names. Verified dashboards show data.",
  "group_id": "ai-memory",
  "type": "session_summary",
  "session_id": "sess_abc123",
  "timestamp": "2026-01-15T20:30:00Z",
  "importance": "high"
}
```

---

### Collection 2: `code-patterns`

**Purpose:** Store implementation patterns, code snippets, architecture decisions with specific file:line references.

**What Goes Here:**
- Story/task outcomes (what was built)
- Code patterns with file:line references
- Error patterns and solutions
- Integration examples
- Architecture decisions with technical details

**Scope:** Project-isolated via `group_id`

**Searched By:** Pre-work search (before implementing specific features)

**Written By:** PostToolUse hook (automatic), post-work-store (workflow)

**Example Payload:**
```json
{
  "content": "JWT middleware implementation with RS256 algorithm.\n\nFile: src/auth/jwt.py:89-145\n\nPattern: Two-phase token validation with refresh token rotation.",
  "group_id": "ecommerce-api",
  "type": "implementation",
  "component": "authentication",
  "story_id": "AUTH-12",
  "file_references": ["src/auth/jwt.py:89-145", "tests/test_jwt.py:23-67"],
  "importance": "high"
}
```

**Critical Requirement:** Must include file:line references. Implementations without code locations are not useful.

---

### Collection 3: `conventions`

**Purpose:** Store universal patterns that apply across ALL projects. Shared learning.

**What Goes Here:**
- Proven implementation patterns
- Performance optimizations
- Security best practices
- Architecture patterns
- Error handling strategies

**Scope:** Universal (`group_id = "universal"`) - NOT project-isolated

**Searched By:** Best practices search (on-demand), can supplement pre-work search

**Written By:** Manual curation, post-work-store (when pattern is universal)

**Example Payload:**
```json
{
  "content": "Token-Efficient Context Loading: Load only relevant context before agent work. Evidence: 95.2% token savings in production systems.",
  "group_id": "universal",
  "type": "best_practice",
  "category": "performance",
  "pattern": "Token-Efficient Context Loading",
  "evidence": "95.2% token savings",
  "tags": ["tokens", "context", "optimization"]
}
```

---

### Collection 4: `github`

**Purpose:** Store GitHub-synced data — pull requests, issues, commits, CI results, and code blobs. Separated from `discussions` in v2.0.9 (PLAN-010) because GitHub code blobs were drowning real conversation data.

**What Goes Here:**
- Code blobs via AST-aware chunking (`github_code_blob`)
- Pull requests and diffs (`github_pr`, `github_pr_diff`, `github_pr_review`)
- Issues and comments (`github_issue`, `github_issue_comment`)
- Commits (`github_commit`)
- CI results (`github_ci_result`)
- Releases (`github_release`)

**Scope:** Project-isolated via `group_id`

**Embedding:** Dual-routed — code blobs use `jina-embeddings-v2-base-code` (768d), prose content uses `jina-embeddings-v2-base-en` (768d)

**Searched By:** Parzival L4 GitHub enrichment, `/aim-github-search` skill

**Written By:** `github_sync.py`, `code_sync.py` (automated Docker service)

**Indexes:** `source`, `github_id`, `file_path`, `sha`, `state`, `last_synced`, `update_batch_id`, plus standard `group_id`, `type`, `timestamp`

**Example Payload:**
```json
{
  "content": "## PR #42: Add JWT authentication\n\nImplements JWT token-based auth...",
  "group_id": "ai-memory",
  "type": "github_pr",
  "source": "github",
  "github_id": "PR-42",
  "state": "merged",
  "timestamp": "2026-02-15T14:30:00Z"
}
```

---

### Collection 5: `jira-data`

**Purpose:** Store Jira issues and comments for semantic search across project management data.

**What Goes Here:**
- Jira issues (summary, description, status, assignee)
- Issue comments

**Scope:** Project-isolated via `group_id`

**Searched By:** `/aim-jira-search` skill

**Written By:** `jira_sync.py` (automated Docker service)

---

### Collection Comparison Summary

| Aspect | discussions | code-patterns | conventions | github | jira-data |
|--------|--------------|-----------------|----------------|--------|-----------|
| **Purpose** | Session continuity | Code patterns | Universal patterns | GitHub data | Jira data |
| **Scope** | Per-project | Per-project | All projects | Per-project | Per-project |
| **group_id** | Project name | Project name | "universal" | Project name | Project name |
| **Content** | Summaries, decisions | Code with file:line | Patterns, evidence | PRs, issues, code | Issues, comments |
| **SessionStart** | ✅ Primary source | ❌ Not searched | ⚠️ Non-Parzival path | ✅ Parzival L4 | ❌ Not searched |
| **Pre-work** | ❌ Not searched | ✅ Primary source | ⚠️ Supplemental | ❌ Not searched | ❌ Not searched |
| **Tier 2** | ✅ Type-filtered | ⚠️ HOW/file-path routing | ⚠️ Best-practices routing | ❌ By design | ❌ Not searched |
| **Typical size** | 100-500 tokens | 50-500 tokens | 100-500 tokens | 50-2000 tokens | 100-500 tokens |

---

## Hook System Overview

### Two Categories of Hooks

**1. Session Lifecycle Hooks (Claude Code Native)**

These hooks are triggered by Claude Code itself during session events:

| Hook | Trigger | Purpose |
|------|---------|---------|
| SessionStart | New session, resume, compact | Load previous session context |
| PostToolUse | After Edit/Write/NotebookEdit | Capture implementation patterns |
| PreCompact | Before compaction (auto/manual) | **Store session summary** (NEW) |
| Stop | After Claude responds (NOT session end) | Optional continue logic |

**2. Workflow Hooks (BMAD Integration)**

These hooks are triggered by BMAD workflows during structured work:

| Hook | Trigger | Purpose |
|------|---------|---------|
| pre-work-search | Before story/task implementation | Load relevant patterns |
| post-work-store | After story/task completion | Store implementation outcome |
| store-chat-memory | After agent decisions | Store decisions for continuity |
| load-chat-context | When agent needs history | Load previous decisions |

---

## Session Lifecycle Hooks

### SessionStart Hook

**File:** `session_start.py`

**Trigger:** Claude Code session starts (startup, resume, compact)

**Purpose:** Provide Claude with context from previous sessions - the "aha moment"

**What It Does:**
1. Detects current project from working directory
2. Searches `discussions` collection for this project's previous sessions
3. Formats session summaries for Claude's context
4. Outputs JSON with `additionalContext` field

**What It Searches:** `discussions` collection ONLY

**Why Not code-patterns?** Session start needs high-level "what did we do" context, not specific code patterns. Code patterns are for when you know what feature you're working on.

**Output Format:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "## Previous Sessions for project-name\n\n### Last Session (2026-01-15)\nWorked on Grafana dashboards..."
  }
}
```

**Critical Rule:** Exit code 0 always. Never block Claude from starting.

---

### PostToolUse Hook

**File:** `post_tool_capture.py`

**Trigger:** After Claude successfully uses Edit, Write, or NotebookEdit tools

**Purpose:** Automatically capture implementation patterns as Claude writes code

**What It Does:**
1. Validates tool completed successfully (has filePath, no error)
2. Extracts file path, content, and context
3. Forks to background process (must return in <500ms)
4. Background process stores to `code-patterns` collection

**What It Stores To:** `code-patterns` collection

**Why Background Fork?** PostToolUse must not slow down Claude's tool execution. The 500ms limit is critical for user experience.

**What Gets Captured:**
- File path and line numbers
- Code content (truncated if too long)
- Language/framework detection
- Session ID for correlation

**Critical Rule:** Never block. Fork immediately, exit 0.

---

### Stop Hook

**Files:** `activity_logger.py`, `agent_response_capture.py`

**Trigger:** Claude Code finishes generating a response (NOT session end!)

**Purpose:** Agent response capture and activity logging

**DEPRECATED:** `session_stop.py` (archived 2026-01-21)
- Original purpose: Session storage at Stop hook
- Reason for deprecation: Duplicated PreCompact functionality, created noise
- Replacement: PreCompact hook for session storage, SDK wrapper for agent responses
- Location: `.claude/hooks/scripts/archived/session_stop.py`

**IMPORTANT DISCOVERY (2026-01-17):** The Stop hook fires when Claude finishes responding to a message, NOT when the session actually ends. This makes it unsuitable for reliable session storage because:
- It fires multiple times per session (once per response)
- Session may end abruptly without triggering
- Race condition with process termination

**Current Usage:** Agent response capture via SDK wrapper, activity logging. See PreCompact hook for session storage.

**What It Does:**
1. Fires after each Claude response completes
2. Captures agent responses via `agent_response_capture.py` (SDK wrapper)
3. Logs activity via `activity_logger.py`
4. NOT used for session storage (use PreCompact instead)

**Critical Rule:** Must complete quickly. Session continues after this hook.

---

### PreCompact Hook (NEW - Session Storage Solution)

**File:** `pre_compact_save.py`

**Trigger:** Before context compaction (manual `/compact` or automatic)

**Purpose:** Store session summary to discussions - the CORRECT solution for session storage

**Why PreCompact?**
1. Fires BEFORE compaction with full transcript access
2. Session is still running - time to complete storage
3. Reliable - unlike SessionEnd which races against termination
4. Automatic - triggers on both manual and auto-compact

**What It Does:**
1. Reads session transcript from stdin
2. Generates summary of accomplishments, decisions, files modified
3. Stores to `discussions` collection with project group_id
4. Logs activity for debugging

**What It Stores To:** `discussions` collection

**Configuration:**
```json
{
  "PreCompact": [
    {
      "matcher": "auto|manual",
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.ai-memory/.claude/hooks/scripts/pre_compact_save.py",
        "timeout": 10000
      }]
    }
  ]
}
```

**Critical Rule:** Must complete within timeout. Session waits for this hook.

---

### Manual Slash Commands

In addition to automatic hooks, three manual commands are available:

#### /aim-save

**Purpose:** Manually save current session context to discussions

**When to Use:**
- Before ending a session early (without compaction)
- To capture important context mid-session
- As backup if PreCompact doesn't trigger

**Implementation:** `manual_save_memory.py`

#### /aim-search <query>

**Purpose:** Search across all memory collections

**Example:** `/aim-search JWT authentication patterns`

**Implementation:** `scripts/memory/search_cli.py`

#### /aim-status

**Purpose:** Check memory system health

**Shows:**
- Service status (Qdrant, Embedding)
- Collection point counts
- Recent activity

**Implementation:** `scripts/memory/memory_status.py`

---

## Workflow Hooks (BMAD Integration)

> **Implementation Status:** These workflow hooks are designed but NOT YET IMPLEMENTED.
> Current version (v1.0) provides session lifecycle hooks only.
> Workflow hooks are planned for Phase 2 (v2.0).

These hooks integrate with BMAD Method workflows (dev-story, create-architecture, etc.)

### pre-work-search.py

**Trigger:** Step 1.5 in workflows - BEFORE implementation starts

**Purpose:** Load relevant implementation patterns for the specific feature being worked on

**Parameters:**
- `--agent` - Agent type (dev, architect, pm)
- `--feature` - Feature description ("JWT authentication")
- `--story-id` - Story identifier
- `--limit` - Max results (default: 3)

**What It Searches:** `code-patterns` collection (+ optionally `conventions`)

**Query:** The `--feature` parameter - specific, not generic

**Why This Works:** Unlike SessionStart's generic query, pre-work search knows WHAT you're about to work on, so it can find highly relevant patterns.

**Timing:** Synchronous/blocking - context MUST arrive before implementation starts

---

### post-work-store.py

**Trigger:** Step 6.5 in workflows - AFTER implementation completes

**Purpose:** Store implementation outcome for future reference

**Parameters:**
- `--agent` - Agent type
- `--story-id` - Story identifier
- `--epic-id` - Epic identifier
- `--component` - Component name
- `--what-built` - Description with file:line references (REQUIRED)
- `--integration-points` - How it integrates
- `--common-errors` - Errors encountered
- `--testing` - Test information

**What It Stores To:** `code-patterns` collection

**Validation:**
- MUST include file:line references
- Minimum 50 tokens content
- Maximum 500 tokens per shard

**Timing:** Asynchronous/non-blocking - don't delay workflow completion

---

### store-chat-memory.py

**Trigger:** After important agent decisions (PM, Analyst, Architect)

**Purpose:** Store workflow decisions for long-term context

**Parameters:**
- `agent` - Agent name (pm, analyst, architect)
- `component` - Workflow component
- `decision` - Decision text
- `--importance` - critical/high/medium/low

**What It Stores To:** `discussions` collection

**Why discussions?** Decisions are about continuity ("why did we choose PostgreSQL?"), not code patterns.

---

### load-chat-context.py

**Trigger:** When agent needs previous conversation history

**Purpose:** Retrieve previous decisions from agent memory

**Parameters:**
- `agent` - Agent name
- `topic` - What to search for
- `--limit` - Max memories

**What It Searches:** `discussions` collection

---

## Agent-Specific Memory Usage

Each BMAD agent has specific memory patterns based on their role. Understanding these patterns ensures the right memories are stored and retrieved.

### Analyst Agent (Mary)

**Role:** Business analysis and research

**Memory Reads:**
- Previous research findings for this project
- Market analysis from similar projects
- Competitive analysis patterns

**Memory Writes:**
- Research findings and insights
- Project classification decisions (greenfield/brownfield)
- Discovery workflow selections

**Primary Collection:** `discussions`

**Workflow Integration:**
```
workflow-init Step 9.5: store-chat-memory analyst "workflow-classification" "<decision>"
```

---

### PM Agent (John)

**Role:** Product strategy and requirements

**Memory Reads:**
- Previous PRD patterns and structures
- Requirement decisions from similar projects
- Epic/story breakdown patterns

**Memory Writes:**
- PRD key decisions
- Requirements clarifications
- Epic breakdown rationale

**Primary Collection:** `discussions`

**Workflow Integration:**
```
create-prd Step A.1: load-project-context pm prd
create-prd Step P.5: store-chat-memory pm "prd-decisions" "<summary>"
```

---

### Architect Agent (Winston)

**Role:** Technical system design

**Memory Reads:**
- Architecture patterns from code-patterns
- Database schema designs
- Integration patterns
- Previous architecture decisions

**Memory Writes:**
- 5 architectural patterns (database, API, auth, errors, integrations)
- Architecture decision rationale
- Technical trade-off decisions

**Primary Collections:** `code-patterns` + `discussions`

**Workflow Integration:**
```
create-architecture Step A.1: load-project-context architect architecture
create-architecture Step 5.5: store-architecture-patterns (stores 5 patterns + decision)
```

**Special:** Architect stores to BOTH collections:
- Technical patterns → `code-patterns`
- Decision rationale → `discussions`

---

### Scrum Master Agent (Bob)

**Role:** Sprint planning and execution

**Memory Reads:**
- Previous story outcomes
- Sprint velocity data
- Story completion patterns

**Memory Writes:**
- Sprint commitment decisions
- Story specification decisions
- Retrospective learnings

**Primary Collection:** `discussions`

**Token Budget:** 800 (lowest - needs only story outcomes)

**Workflow Integration:**
```
sprint-planning Step A.1: load-project-context sm sprint-planning
sprint-planning Step P.5: store-chat-memory sm "sprint-decisions" "<summary>"
create-story Step A.1: load-project-context sm create-story <story-id>
```

---

### Developer Agent (Amelia)

**Role:** Story implementation and code review

**Memory Reads:**
- Implementation patterns for similar features
- Error patterns and solutions
- Integration examples
- Architecture patterns (from Architect)

**Memory Writes:**
- Story outcomes with file:line references
- Error patterns encountered
- Integration examples created
- Testing approaches used

**Primary Collection:** `code-patterns`

**Token Budget:** 1000

**Workflow Integration:**
```
dev-story Step 1.5: pre-work-search dev <story-id> "<feature>"
dev-story Step 6.5: post-work-store <story-id> <component> "<what-built>"
```

**Critical:** Developer memories MUST include file:line references.

---

### Quick Flow Solo Dev Agent (Barry)

**Role:** Streamlined solo development (architecture + spec + implementation)

**Memory Reads:**
- All relevant context (combines Architect + Dev needs)
- Implementation patterns
- Architecture patterns
- Best practices

**Memory Writes:**
- Combined architecture + implementation outcomes
- Quick decisions made
- Patterns discovered

**Primary Collections:** `code-patterns` + `discussions`

**Token Budget:** 1000

**Note:** Barry combines multiple agent roles, so memory usage is broader.

---

### TEA Agent (Murat)

**Role:** Test strategy and automation

**Memory Reads:**
- Test strategies from similar features
- CI/CD patterns
- Quality gate configurations
- Test automation patterns

**Memory Writes:**
- Test strategy decisions
- Automation patterns created
- Quality gate configurations

**Primary Collection:** `code-patterns`

**Token Budget:** 1000

---

### UX Designer Agent (Sally)

**Role:** User experience design

**Memory Reads:**
- UX patterns from similar projects
- Design decisions made
- Component patterns

**Memory Writes:**
- UX design decisions
- User flow patterns
- Component specifications

**Primary Collection:** `discussions`

**Token Budget:** 1000

---

### Technical Writer Agent (Paige)

**Role:** Documentation and standards

**Memory Reads:**
- Documentation patterns
- Standards from best practices
- Previous documentation structures

**Memory Writes:**
- Documentation patterns (if universal)
- Standards compliance findings

**Primary Collection:** `conventions` (reads), `discussions` (writes)

**Token Budget:** 1000

---

### Agent Memory Summary Table

| Agent | Reads From | Writes To | Token Budget | file:line Required |
|-------|------------|-----------|--------------|-------------------|
| Analyst | discussions | discussions | 1200 | No |
| PM | discussions | discussions | 1200 | No |
| Architect | code-patterns, discussions | code-patterns, discussions | 1500 | Yes (for code-patterns) |
| SM | discussions | discussions | 800 | No |
| Developer | code-patterns | code-patterns | 1000 | Yes |
| Quick Flow | code-patterns, discussions | code-patterns, discussions | 1000 | Yes (for code-patterns) |
| TEA | code-patterns | code-patterns | 1000 | Yes |
| UX Designer | discussions | discussions | 1000 | No |
| Tech Writer | conventions, discussions | discussions, conventions | 1000 | No |

---

## Token Budgets

### Why Token Budgets Matter

Memory retrieval adds tokens to Claude's context. Without limits:
- Too much context overwhelms Claude
- Irrelevant memories dilute useful ones
- Response quality degrades
- API costs increase

### Per-Agent Token Budgets

Different agents need different amounts of context:

| Agent | Token Budget | Rationale |
|-------|-------------|-----------|
| Architect | 1500 | Needs full architecture context |
| Analyst | 1200 | Needs market/competitive analysis |
| PM | 1200 | Needs requirements/priorities |
| Developer | 1000 | Needs implementation patterns |
| TEA | 1000 | Needs test strategies |
| Tech Writer | 1000 | Needs documentation patterns |
| UX Designer | 1000 | Needs design patterns |
| Quick Flow | 1000 | Needs workflow context |
| Scrum Master | 800 | Needs story outcomes only |

### Per-Shard Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Minimum tokens | 50 | Below this isn't useful |
| Maximum tokens | 500 | Ensures multiple shards fit in budget |

### How Budgets Are Enforced

1. Search returns results ranked by relevance score
2. Results added to context until budget exhausted
3. Lower-relevance results dropped if budget exceeded
4. Per-shard limit ensures no single memory dominates

---

## Validation Requirements

### For `code-patterns` Collection

**File:Line References (REQUIRED)**

All implementation memories MUST include file:line references.

**Valid formats:**
- `src/auth/jwt.py:89` (single line)
- `src/auth/jwt.py:89-145` (line range)
- `tests/test_auth.py:23-67` (test files)

**Why required?** Implementations without code locations are not actionable. "We built JWT auth" is useless. "JWT auth in src/auth/jwt.py:89-145" is useful.

**Validation regex:**
```
[a-zA-Z0-9_/\-\.]+\.(py|js|ts|md|yaml|sql|sh):\d+(-\d+)?
```

### Duplicate Detection

**Stage 1: Exact Duplicate (SHA256 hash)**
- Hash content, check if exists
- Prevents identical memories

**Stage 2: Semantic Duplicate (similarity > 0.85)**
- Embed content, search for similar
- Prevents paraphrased duplicates

### Metadata Validation

All memories must include required metadata fields:
- `unique_id` - Unique identifier
- `group_id` - Project identifier
- `type` - Memory type
- `timestamp` - When created
- `importance` - Priority level

---

## Data Flow Diagrams

### Session Lifecycle Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SESSION LIFECYCLE                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  SESSION START                                               │
│  ┌──────────────────┐                                       │
│  │ SessionStart     │──→ Search discussions                │
│  │ Hook             │──→ Get previous session summaries     │
│  └──────────────────┘──→ Inject "aha moment" context        │
│           │                                                  │
│           ▼                                                  │
│  DURING SESSION                                              │
│  ┌──────────────────┐                                       │
│  │ PostToolUse      │──→ Capture code patterns              │
│  │ Hook             │──→ Store to code-patterns           │
│  └──────────────────┘──→ (background, non-blocking)         │
│           │                                                  │
│           ▼                                                  │
│  BEFORE COMPACTION (NEW!)                                    │
│  ┌──────────────────┐                                       │
│  │ PreCompact       │──→ Read session transcript            │
│  │ Hook             │──→ Generate session summary           │
│  └──────────────────┘──→ Store to discussions              │
│           │                                                  │
│           ▼                                                  │
│  ON RESPONSE COMPLETE                                        │
│  ┌──────────────────┐                                       │
│  │ Stop Hook        │──→ (Optional) Continue logic          │
│  │ (per-response!)  │──→ NOT for session storage            │
│  └──────────────────┘                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### BMAD Workflow Memory Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 BMAD WORKFLOW MEMORY FLOW                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Load Story AUTH-12 (JWT authentication)            │
│           │                                                  │
│           ▼                                                  │
│  Step 1.5: PRE-WORK SEARCH (blocking)                       │
│  ┌──────────────────┐                                       │
│  │ pre-work-search  │──→ Query: "JWT authentication"        │
│  │                  │──→ Search: code-patterns            │
│  │                  │──→ Return: Relevant code patterns     │
│  └──────────────────┘                                       │
│           │                                                  │
│           ▼                                                  │
│  Steps 2-6: IMPLEMENT WITH CONTEXT                          │
│  [Agent has relevant patterns from memory]                  │
│           │                                                  │
│           ▼                                                  │
│  Step 6.5: POST-WORK STORAGE (non-blocking)                 │
│  ┌──────────────────┐                                       │
│  │ post-work-store  │──→ Store: What was built              │
│  │                  │──→ Include: file:line references      │
│  │                  │──→ Collection: code-patterns        │
│  └──────────────────┘                                       │
│           │                                                  │
│           ▼                                                  │
│  Step 7: COMPLETE ✅                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Collection Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  COLLECTION DATA FLOW                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  WRITES TO discussions:                                    │
│  ├── PreCompact hook (session summaries)                    │
│  └── store-chat-memory (workflow decisions)                 │
│                                                              │
│  READS FROM discussions:                                   │
│  ├── SessionStart hook (aha moment)                         │
│  └── load-chat-context (workflow history)                   │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  WRITES TO code-patterns:                                  │
│  ├── PostToolUse hook (automatic code capture)              │
│  └── post-work-store (workflow outcomes)                    │
│                                                              │
│  READS FROM code-patterns:                                 │
│  └── pre-work-search (before implementing features)         │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  WRITES TO conventions:                                   │
│  └── Manual curation / post-work-store (universal patterns) │
│                                                              │
│  READS FROM conventions:                                  │
│  ├── search-best-practices (on-demand)                      │
│  └── pre-work-search (supplemental)                         │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  WRITES TO github:                                        │
│  └── github_sync.py / code_sync.py (automated Docker sync)  │
│                                                              │
│  READS FROM github:                                       │
│  ├── Parzival L4 enrichment (SessionStart)                  │
│  └── /aim-github-search (on-demand)                         │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  WRITES TO jira-data:                                     │
│  └── jira_sync.py (automated Docker sync)                   │
│                                                              │
│  READS FROM jira-data:                                    │
│  └── /aim-jira-search (on-demand)                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Common Mistakes to Avoid

### Mistake 1: SessionStart Searching code-patterns

**Wrong:** SessionStart searches `code-patterns` collection
**Result:** Generic query returns random code patterns (low relevance)
**Correct:** SessionStart searches `discussions` for session summaries

### Mistake 2: Storing Session Summaries to code-patterns

**Wrong:** Storing session summary to `code-patterns`
**Result:** Session summaries mixed with code patterns, wrong retrieval
**Correct:** PreCompact hook stores session summaries to `discussions`

### Mistake 3: Generic Queries for Feature Search

**Wrong:** Pre-work search uses "Working on project-name"
**Result:** Low relevance results, no useful context
**Correct:** Pre-work search uses specific feature: "JWT authentication"

### Mistake 4: Adding UserPromptSubmit for Memory

**Wrong:** Adding UserPromptSubmit hook to search on every prompt
**Result:** Unnecessary complexity, not in original design
**Correct:** SessionStart for session context, pre-work-search for features

### Mistake 5: Implementations Without file:line

**Wrong:** Storing "Implemented JWT authentication" without code location
**Result:** Memory exists but isn't actionable
**Correct:** "JWT auth implementation in src/auth/jwt.py:89-145"

### Mistake 6: Ignoring Token Budgets

**Wrong:** Returning unlimited memory results to agent
**Result:** Context overflow, degraded responses
**Correct:** Enforce per-agent token budgets, truncate as needed

### Mistake 7: Blocking in PostToolUse

**Wrong:** Doing full storage synchronously in PostToolUse
**Result:** Tool execution slows down, bad UX
**Correct:** Fork to background, return immediately (<500ms)

### Mistake 8: Mixing Universal and Project Patterns

**Wrong:** Storing project-specific code in `conventions`
**Result:** Irrelevant patterns appear in other projects
**Correct:** Only universal, proven patterns go in `conventions`

### Mistake 9: Using Stop Hook for Session Storage

**Wrong:** Relying on Stop hook to store session summaries
**Result:** Multiple writes per session, unreliable capture, race conditions
**Correct:** Use PreCompact hook which fires once before compaction with full transcript access

---

## Summary: The Complete Picture

### What We're Building

A five-collection memory system:

1. **Session Memory (discussions)** - "What did we do last time?"
2. **Implementation Patterns (code-patterns)** - "How did we build similar features?"
3. **Universal Patterns (conventions)** - "What works across all projects?"
4. **GitHub Data (github)** - "What changed in the repo recently?"
5. **Jira Data (jira-data)** - "What are we supposed to be working on?"

### Why Each Piece Exists

| Component | Why It Exists |
|-----------|---------------|
| discussions collection | Session continuity - the "aha moment" |
| code-patterns collection | Feature-specific code patterns |
| conventions collection | Cross-project learning |
| github collection | GitHub PRs, issues, commits, code blobs |
| jira-data collection | Jira issues and comments |
| SessionStart hook | Load previous session context |
| PostToolUse hook | Auto-capture code as you work |
| PreCompact hook | Save session for next time |
| pre-work-search | Load relevant patterns before features |
| post-work-store | Save outcomes after features |
| Token budgets | Prevent context overflow |
| file:line validation | Ensure actionable memories |

### The User Experience

**Without Memory:**
- Every session starts from zero
- "Can you remind me what we did yesterday?"
- Re-explaining context wastes time and tokens

**With Memory:**
- "Welcome back! Last session we fixed the Grafana dashboards..."
- Before implementing auth: "I found similar JWT patterns from AUTH-08..."
- Learns from every project, gets smarter over time

---

**Document Version:** 1.2.0
**Last Updated:** 2026-03-02 (V2.0.9 five-collection architecture)
**Changes:** Expanded from 3 to 5 collections (added github, jira-data). Updated data flow diagrams. Added Tier 2 type filtering. Documented quality gate and error detection rewrite.
**Author:** Architecture documentation from AI Memory Module development
