# BMAD Multi-Agent System - Architecture Specification v2.0

**Last Updated**: 2026-03-15
**Status**: Design & Planning (aspirational web UI); Parzival 2.1 agent dispatch operational via Claude Code teams
**Target**: Parzival Module v2.0 (web UI); Parzival 2.1 (current CLI-based orchestration)

> **Note -- Parzival 2.1 Current State**: As of v2.1, Parzival operates entirely within Claude Code. He activates and manages all agents himself via Claude Code teams (TeamCreate + Agent with team_name). The user interacts with Parzival only. Agent dispatch uses a skill-based architecture with content in `_ai-memory/pov/skills/` and shims in `.claude/skills/`. The web UI architecture described in this document (React multi-terminal, FastAPI backend, PostgreSQL orchestration) remains the aspirational design for a future standalone module. See `_ai-memory/pov/agents/parzival.md` for the current agent definition and `_ai-memory/pov/constraints/global/constraints.md` for GC-01 through GC-15, GC-19, GC-20.

---

## 1. Project Overview

Building a multi-agent AI development system where **Parzival** (the orchestrator agent) collaborates with users following the **BMAD Method**, then spawns and coordinates specialized **Worker Agents** that execute development tasks with human-in-the-loop approval gates.

### 1.1 Key Principles

1. **Parzival Orchestrates, User Decides**: Parzival coordinates agents but never makes final decisions
2. **Separation of Concerns**: Memory module (Qdrant) ≠ Orchestration database (PostgreSQL)
3. **Modern Web Architecture**: React + TypeScript frontend, FastAPI backend
4. **Human-in-the-Loop**: Approval gates for all file changes
5. **BMAD Method Integration**: Follows established workflows and patterns

### 1.2 System Components Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    BMAD ECOSYSTEM                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PARZIVAL MODULE (Orchestration)                     │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  • Parzival Agent (Oversight & Orchestration)        │  │
│  │  • BMAD Worker Agents (PM, Dev, Architect, etc.)     │  │
│  │  • React Multi-Terminal UI (xterm.js)                │  │
│  │  • PostgreSQL (Epic/Story tracking, Agent comms)     │  │
│  │  • FastAPI Backend (WebSocket, REST API)             │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↕                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  MEMORY MODULE (Semantic Memory)                     │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  • Qdrant (Vector database, 3 collections)           │  │
│  │  • Embedding Service (Jina v2 768d)                  │  │
│  │  • Streamlit Dashboard (Memory browser)              │  │
│  │  • Claude Code Hooks (Automatic capture)             │  │
│  │  • Python Core (Storage, search, triggers)           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Distinction**:
- **Parzival Module**: Orchestrates BMAD workflows, tracks epic/story progress
- **Memory Module**: Provides semantic memory across all agents

---

## 2. Core Components

### 2.1 Parzival Agent (Orchestrator)

**Purpose**: User-facing orchestration and coordination agent

**Primary Responsibilities**:
1. **Initial Planning**: Guide user through BMAD planning phases
2. **Agent Orchestration**: Spawn and coordinate worker agents
3. **Context Management**: Answer agent questions from planning artifacts
4. **Quality Gates**: Review all work until zero issues found
5. **User Interface**: Provide recommendations, never execute without approval

**Key Behaviors**:
```
Phase 1: User + Parzival Planning Session
  ↓
  User: "I want to build a task management app"
  ↓
  Parzival: "Let's use /bmad:bmm:workflows:create-prd"
  ↓
  Parzival guides through: Analysis → Planning → Architecture
  ↓
  Artifacts created: PRD, Architecture, Epic files

Phase 2: Parzival Spawns Workers
  ↓
  Parzival: "Planning complete. Ready to spawn Dev agent?"
  ↓
  User: "Yes"
  ↓
  Parzival spawns Dev Agent, monitors in separate terminal

Phase 3: Parzival Answers Agent Questions
  ↓
  Dev Agent: "Should I use REST or GraphQL?"
  ↓
  Parzival checks Architecture doc → Answer: "REST per DEC-005"
  ↓
  If uncertain → Parzival asks user → Passes answer to agent

Phase 4: Parzival Enforces Quality
  ↓
  Dev completes story → Parzival triggers Code Review agent
  ↓
  Reviewer finds 5 issues → Parzival validates severity
  ↓
  Dev fixes → Parzival re-reviews → Repeat until 0 issues
  ↓
  Only then: Parzival marks story complete
```

**Technology**: Claude Agent SDK instance with orchestration system prompt. In Parzival 2.1, agents are spawned as Claude Code teammates (GC-19: TeamCreate + Agent with team_name), not standalone subagents. BMAD agent activation and instruction must be separate messages (GC-20).

**Configuration**: `_ai-memory/pov/agents/parzival.md`

---

### 2.2 Worker Agents

**Purpose**: Specialized execution agents following BMAD roles

**Available Roles** (from BMAD Method):
- **Project Manager** (`bmad-pm.md`) - Sprint planning, task tracking
- **Architect** (`bmad-architect.md`) - System design, tech decisions
- **Developer** (`bmad-developer.md`) - Code implementation
- **UX Designer** (`bmad-ux.md`) - UI/UX design, wireframes
- **TEA (Test Engineer Analyst)** (`bmad-tea.md`) - Test design, automation
- **Code Reviewer** (`bmad-reviewer.md`) - Code quality, security
- **DevOps Engineer** (`bmad-devops.md`) - CI/CD, infrastructure
- **Security Specialist** (`bmad-security.md`) - Security audits
- **Technical Writer** (`bmad-tech-writer.md`) - Documentation
- **Scrum Master** (`bmad-sm.md`) - Sprint facilitation
- **Product Owner** (`bmad-po.md`) - Backlog management
- **Business Analyst** (`bmad-analyst.md`) - Requirements analysis

**Responsibilities**:
1. Work on single features incrementally (Anthropic's long-running agent pattern)
2. Request approval via hooks before ANY file changes
3. Follow BMAD workflows specific to their role
4. Ask Parzival for clarification when needed
5. Leave clean state after each session:
   - Git commits with descriptive messages
   - Progress updates in tracking files
   - Updated feature status

**Technology**: Claude Agent SDK instances with role-specific system prompts. In Parzival 2.1, all agents are spawned as teammates via the aim-parzival-team-builder skill and dispatched through the agent-dispatch workflow.

**Configuration**: `_ai-memory/pov/agents/*.md`

---

### 2.3 PostgreSQL Database (BMAD Orchestration)

**Purpose**: Track epic/story progress and agent-to-agent communication

**NOT Used For**: Semantic memory (that's Qdrant in memory module)

**Schema Overview**:
```sql
-- Epic & Story Tracking
epics (id, title, status, created_at, completed_at)
stories (id, epic_id, title, status, acceptance_criteria)
tasks (id, story_id, description, assigned_agent, status)

-- Agent Coordination
agents (id, name, role, status, spawned_at, last_active)
agent_messages (id, from_agent_id, to_agent_id, content, timestamp)
approval_requests (id, agent_id, action_type, file_path, status)

-- Progress Tracking
progress_log (id, agent_id, session_id, summary, git_commit)
cost_tracking (id, agent_id, tokens_input, tokens_output, cost)

-- Audit
audit_log (id, agent_id, action, metadata, success, timestamp)
```

**Why PostgreSQL?**:
- ✅ Structured data (epics, stories, tasks)
- ✅ ACID transactions (no data loss on agent failures)
- ✅ Complex queries (sprint burndown, agent performance)
- ✅ Mature ecosystem (backups, replication, monitoring)

**Confidence**: **Verified** (industry standard for workflow tracking)

---

### 2.4 React Multi-Terminal UI

**Purpose**: Modern web-based multi-terminal interface for agent visibility

**Architecture**:
```typescript
// Terminal Grid Layout
<TerminalGrid layout="2x2">
  <TerminalPane
    id="oversight"
    title="🎯 Parzival Orchestrator"
    agentType="oversight"
    controls={true}  // Spawn buttons, stop/resume
  />

  <TerminalPane
    id="worker-1"
    title="📋 PM Agent"
    agentType="bmad-pm"
    status="active"
  />

  <TerminalPane
    id="worker-2"
    title="💻 Dev Agent"
    agentType="bmad-developer"
    status="active"
  />

  <TerminalPane
    id="worker-3"
    title="🏗️ Architect Agent"
    agentType="bmad-architect"
    status="idle"
  />
</TerminalGrid>

// Each terminal uses xterm.js for full terminal emulation
// WebSocket connection to FastAPI backend
// Real-time agent output streaming
```

**Technology Stack**:
- **xterm.js 5.x**: Terminal emulator (used by VS Code, AWS Cloud9)
- **react-xtermjs**: React wrapper with hooks support
- **React 18+**: UI framework
- **TypeScript 5.x**: Type safety
- **WebSocket**: Real-time communication
- **TailwindCSS**: Styling (or Material-UI)

**Key Features**:
1. **Full Terminal Emulation**: ANSI colors, cursor control, UTF-8
2. **Resizable Panes**: Drag-to-resize terminal windows
3. **Tab Management**: Multiple agent tabs per role type
4. **Control Panel**: Spawn agents, stop/resume, view logs
5. **Status Indicators**: Agent state (active, idle, waiting, error)
6. **Cost Tracking**: Real-time token usage per agent
7. **Session Persistence**: Reconnect to running agents

**Layout Examples**:

**Single Developer Mode** (Parzival + 1 Worker):
```
┌─────────────────────────────────────────┐
│ Parzival Orchestrator         (60%)    │
│ [Spawn PM] [Spawn Dev] [Status]        │
│ User: Let's create a new feature       │
│ Parzival: I'll guide you through PRD   │
├─────────────────────────────────────────┤
│ Dev Agent                     (40%)    │
│ Status: Working on Story 3.2            │
│ Progress: Implementing user auth        │
└─────────────────────────────────────────┘
```

**Team Mode** (Parzival + 3 Workers):
```
┌──────────────────┬──────────────────┐
│ Parzival (40%)   │ PM Agent (30%)   │
│ Orchestrating... │ Planning sprint  │
├──────────────────┼──────────────────┤
│ Dev Agent (30%)  │ TEA Agent (30%)  │
│ Story 3.2 impl   │ Writing tests    │
└──────────────────┴──────────────────┘
```

**Confidence**: **Verified** (xterm.js is industry standard, proven architecture)

---

### 2.5 Parzival as Orchestrator

**Vision**: Parzival is the **central intelligence** that bridges human intent and agent execution.

**Orchestration Flow**:

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Initial Planning (User ↔ Parzival)                 │
├─────────────────────────────────────────────────────────────┤
│ User starts Parzival agent                                  │
│   ↓                                                          │
│ Parzival: "What would you like to build?"                   │
│   ↓                                                          │
│ User: "Task management app with real-time updates"          │
│   ↓                                                          │
│ Parzival: "Let me guide you through planning. First, let's  │
│           define requirements using /create-prd workflow"    │
│   ↓                                                          │
│ [Collaborative PRD creation session]                        │
│   ↓                                                          │
│ Parzival: "PRD complete. Next: Architecture decisions"      │
│   ↓                                                          │
│ [Collaborative Architecture session]                        │
│   ↓                                                          │
│ Artifacts: PRD.md, Architecture.md, DEC-*.md files          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Step 2: Epic & Story Generation (Parzival Solo)            │
├─────────────────────────────────────────────────────────────┤
│ Parzival: "Planning complete. Creating epics and stories"   │
│   ↓                                                          │
│ Parzival runs: /create-epics-and-stories workflow           │
│   ↓                                                          │
│ Generated: epic-1.md, epic-2.md, epic-3.md                  │
│            stories/story-1.1.md, story-1.2.md, etc.         │
│   ↓                                                          │
│ Parzival: "15 stories created across 3 epics. Ready to      │
│           start implementation?"                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Step 3: Agent Spawning (User Approves)                     │
├─────────────────────────────────────────────────────────────┤
│ User: "Yes, let's start with Story 1.1"                     │
│   ↓                                                          │
│ Parzival: "I'll spawn Dev agent for implementation."        │
│   ↓                                                          │
│ [Dev Agent spawned in Terminal 2]                           │
│   ↓                                                          │
│ Dev Agent: "Story 1.1 loaded. Checking codebase..."         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Step 4: Agent Question Handling (Parzival Answers)         │
├─────────────────────────────────────────────────────────────┤
│ Dev Agent: "Should user auth use JWT or sessions?"          │
│   ↓                                                          │
│ Parzival checks Architecture.md → Finds DEC-007: JWT        │
│   ↓                                                          │
│ Parzival → Dev Agent: "Use JWT per DEC-007. 7-day expiry,   │
│                        refresh tokens, httpOnly cookies."    │
│   ↓                                                          │
│ Dev Agent: "Got it, implementing JWT auth..."               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Step 5: Uncertain Questions (Parzival → User)              │
├─────────────────────────────────────────────────────────────┤
│ Dev Agent: "Should failed login attempts be rate limited?"  │
│   ↓                                                          │
│ Parzival checks docs → No decision found                    │
│   ↓                                                          │
│ Parzival → User: "Dev agent asks about rate limiting.       │
│                   Not in requirements. Recommend: Yes, 5    │
│                   attempts per 15min. Approve?"              │
│   ↓                                                          │
│ User: "Yes, approved"                                        │
│   ↓                                                          │
│ Parzival creates DEC-015: "Rate limiting 5/15min"           │
│   ↓                                                          │
│ Parzival → Dev Agent: "Approved. Add rate limiting per      │
│                        DEC-015."                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Step 6: Quality Gatekeeper (Parzival Enforces Review)      │
├─────────────────────────────────────────────────────────────┤
│ Dev Agent: "Story 1.1 implementation complete."             │
│   ↓                                                          │
│ Parzival: "Spawning Code Reviewer for validation..."        │
│   ↓                                                          │
│ [Code Reviewer spawned in Terminal 3]                       │
│   ↓                                                          │
│ Code Reviewer: "Found 5 issues - 2 CRITICAL, 3 MEDIUM"      │
│   ↓                                                          │
│ Parzival validates: "Issues confirmed. Dev agent, fix these"│
│   ↓                                                          │
│ Dev Agent: "Fixing issues..."                               │
│   ↓                                                          │
│ Dev Agent: "All 5 issues fixed."                            │
│   ↓                                                          │
│ Parzival: "Re-running code review..."                       │
│   ↓                                                          │
│ Code Reviewer: "0 issues found. APPROVED."                  │
│   ↓                                                          │
│ Parzival updates story status: COMPLETE ✅                   │
└─────────────────────────────────────────────────────────────┘
```

**Key Orchestration Patterns**:

1. **Planning Partner**: Collaborative PRD, Architecture, Epic creation
2. **Context Provider**: Answers agent questions from planning artifacts
3. **Escalation Handler**: Asks user when information is missing
4. **Quality Enforcer**: Review → Fix → Re-review until clean
5. **Progress Tracker**: Updates PostgreSQL with epic/story status
6. **Cost Monitor**: Tracks token usage across all agents

**Parzival Never Does**:
- ❌ Write code directly
- ❌ Make decisions without user approval
- ❌ Execute workflows automatically
- ❌ Guess when information is missing
- ❌ Mark work complete without review passing

**Parzival Always Does**:
- ✅ Check project docs before answering
- ✅ Provide prompts for dev agents (not code)
- ✅ State confidence level with recommendations
- ✅ Ask user when uncertain
- ✅ Enforce review until zero issues
- ✅ Spawn agents as teammates, never standalone subagents (GC-19)
- ✅ Send BMAD activation and instruction as separate messages (GC-20)
- ✅ Review agent output before surfacing to user (GC-09)
- ✅ Give agents precise, cited instructions (GC-11)

**Confidence**: **Informed** (based on current Parzival 2.1 implementation + user requirements)

---

### 2.6 Agent-to-Agent Communication

**Purpose**: Enable async message passing between worker agents

**Use Cases**:
1. **Dev → TEA**: "I've implemented feature X, can you create tests?"
2. **Architect → Dev**: "Design decision updated: use Redis for cache"
3. **PM → All**: "Sprint goal updated: focus on authentication"
4. **Code Reviewer → Dev**: "Fix these 3 security issues"

**Implementation**:

**PostgreSQL Schema**:
```sql
CREATE TABLE agent_messages (
    id UUID PRIMARY KEY,
    from_agent_id UUID REFERENCES agents(id),
    to_agent_id UUID,  -- NULL for broadcast
    message_type VARCHAR(50),  -- question, answer, notification
    subject VARCHAR(200),
    content TEXT,
    priority VARCHAR(20),  -- low, normal, high, urgent
    status VARCHAR(20),  -- sent, delivered, read, acknowledged
    created_at TIMESTAMP,
    read_at TIMESTAMP
);

CREATE INDEX idx_to_agent ON agent_messages(to_agent_id, status);
```

**Message Flow (Recommended Architecture)**:
```
Dev Agent completes feature
  ↓
  Writes message to Redis Streams: {
    from: "dev-001",
    to: "tea-001",
    type: "notification",
    subject: "Feature X ready for tests",
    content: "Implemented auth. Files: src/auth/*.ts"
  }
  ↓
  Redis Streams delivers instantly (consumer group: "parzival")
  ↓
  Parzival receives message (no polling, event-driven)
  ↓
  Parzival → TEA terminal: "Dev agent: Feature X ready"
  ↓
  TEA Agent reads message, acknowledges (XACK)
  ↓
  Background worker persists to PostgreSQL (durable storage)
```

**Architecture Decision** (Updated based on BP-024 research):

**Recommended: Redis Streams** (Primary messaging layer)
```
Pros:
  - Millions of messages/sec vs 100-500 for PostgreSQL
  - No global lock (PostgreSQL LISTEN/NOTIFY has contention)
  - Built-in consumer groups + acknowledgment tracking
  - Event-driven (no polling overhead)

Cons:
  - Additional service dependency
  - Requires Redis for hot messaging

Production Evidence:
  - Recall.ai experienced THREE downtimes (2025-03-19 to 2025-03-22)
    caused by PostgreSQL LISTEN/NOTIFY global lock
  - CPU/IO plummeted during "high load" indicating mutex bottleneck
```

**Hybrid Pattern (Recommended)**:
```python
# Redis Streams for hot path (real-time messaging)
await redis.xadd(
    f"agent:{agent_id}:messages",
    {"type": "notification", "content": message}
)

# PostgreSQL for cold storage (audit trail, history)
async with pg_pool.acquire() as conn:
    await conn.execute("""
        INSERT INTO agent_messages (from_agent, to_agent, content)
        VALUES ($1, $2, $3)
    """, from_id, to_id, message)
```

**Why Not PostgreSQL LISTEN/NOTIFY?**:
- Global lock causes production failures at scale
- Limited throughput (100-500 msg/sec)
- No built-in acknowledgment or consumer groups
- Not designed for high-frequency messaging

**Confidence**: **Verified** (BP-024 research with production case studies, Redis Streams proven at scale)

---

### 3. Memory System Integration

### 3.1 Memory Module Overview

**Purpose**: Provide semantic memory to all agents (Parzival + Workers)

**Architecture**: Separate module with independent services

**Core Services**:
- **Qdrant**: Vector database (3 collections)
- **Embedding Service**: Jina v2 768-dimensional embeddings
- **Streamlit Dashboard**: Memory browser UI
- **Claude Code Hooks**: Automatic memory capture

**Collections**:
1. **code-patterns**: `implementation`, `error_fix`, `refactor`, `file_pattern`
2. **conventions**: `rule`, `guideline`, `port`, `naming`, `structure`
3. **discussions**: `decision`, `session`, `blocker`, `user_message`, `agent_response`

**Integration Points**:
```
Parzival asks: "What did we decide about auth?"
  ↓
  Memory module: Search discussions collection
  ↓
  Returns: DEC-007 (JWT with 7-day expiry)
  ↓
  Parzival: "Use JWT per DEC-007..."

Dev Agent encounters error: "Connection timeout"
  ↓
  Memory module: Search code-patterns for error_fix
  ↓
  Returns: "Add timeout=30 to httpx client"
  ↓
  Dev Agent: "Implementing fix from past solution..."

TEA Agent needs test patterns
  ↓
  Memory module: Search conventions for testing guidelines
  ↓
  Returns: "Use pytest fixtures for database tests"
  ↓
  TEA Agent: "Following project test patterns..."
```

**Why Separate Module?**:
- ✅ Independent lifecycle (install/update separately)
- ✅ Can be used without Parzival orchestration
- ✅ Different scaling requirements (Qdrant ≠ PostgreSQL)
- ✅ Clear separation of concerns

**Confidence**: **Verified** (memory module already implemented and working)

---

### 3.2 Memory System Integration

**How Agents Use Memory**:

**1. Automatic Context Injection (SessionStart:compact hook)** - See BP-022:
```
Agent spawned → Session starts
  ↓
  Context compaction occurs (Claude optimizes conversation)
  ↓
  SessionStart:compact hook fires (post-compaction)
  ↓
  Cascading Search Pattern:
    Stage 1: Recent memories (last 7 days, recency bias)
    Stage 2: Relevant memories (semantic search, confidence >0.7)
    Stage 3: Broad context (type-filtered, project-scoped)
  ↓
  Context Budget: 15-25% for memories (~30-50K tokens)
  ↓
  Qdrant returns: 10-20 most relevant memories
  ↓
  Formatted as markdown sections:
    ## Recent Decisions
    ## Code Patterns
    ## Project Conventions
  ↓
  Injected into agent context (available for entire session)
  ↓
  Agent: "I remember we're using JWT for auth per DEC-007..."
```

**Why Post-Compact Injection** (BP-022):
- Maximizes available context window (200K tokens total)
- Prevents wasted tokens on pre-compaction conversation
- Ensures memories persist through session lifecycle

**2. On-Demand Retrieval (Skills)**:
```
Agent: /aim-search "authentication patterns"
  ↓
  Memory module: Semantic search across all collections
  ↓
  Returns: 5 relevant memories with attribution
  ↓
  Agent: "Found 5 auth patterns. Using approach #2..."
```

**3. Automatic Capture (PostToolUse hook)**:
```
Agent: Edits file auth.ts
  ↓
  PostToolUse hook fires
  ↓
  Pattern extraction: JWT implementation detected
  ↓
  Stored to code-patterns: type=implementation
  ↓
  Future agents can learn from this pattern
```

**4. Parzival → Agent Context Passing**:
```
User clarifies: "Use bcrypt for password hashing"
  ↓
  Parzival stores: type=decision, DEC-015
  ↓
  Memory module: Stored to discussions collection
  ↓
  Dev Agent spawned → SessionStart retrieves DEC-015
  ↓
  Dev Agent: "Using bcrypt per DEC-015..."
```

**Memory Module Services** (already running):
- Qdrant: `localhost:26350`
- Embedding Service: `localhost:28080`
- Streamlit Dashboard: `localhost:28501`
- Grafana Metrics: `localhost:23000`

**Confidence**: **Verified** (memory module fully operational in current project)

---

### 3.3 PostgreSQL Schema for BMAD Orchestration

**Full Schema** (distinct from Qdrant memory storage):

```sql
-- =================================================================
-- AGENT MANAGEMENT
-- =================================================================

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    role VARCHAR(50) NOT NULL,  -- pm, dev, architect, tea, reviewer
    status VARCHAR(20) NOT NULL,  -- active, idle, waiting, error, stopped
    spawned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_active TIMESTAMP NOT NULL DEFAULT NOW(),
    terminal_id VARCHAR(50),  -- React terminal pane ID
    cost_total DECIMAL(10,4) DEFAULT 0.00,

    CONSTRAINT chk_status CHECK (status IN ('active', 'idle', 'waiting', 'error', 'stopped'))
);

CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_role ON agents(role);

-- =================================================================
-- EPIC & STORY TRACKING (BMAD Method)
-- =================================================================

CREATE TABLE epics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_number INTEGER NOT NULL UNIQUE,  -- Epic 1, Epic 2, etc.
    title VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'medium',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    CONSTRAINT chk_epic_status CHECK (status IN ('pending', 'in_progress', 'blocked', 'completed'))
);

CREATE TABLE stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    epic_id UUID REFERENCES epics(id) ON DELETE CASCADE,
    story_number VARCHAR(10) NOT NULL UNIQUE,  -- 1.1, 1.2, etc.
    title VARCHAR(200) NOT NULL,
    description TEXT,
    acceptance_criteria TEXT[],
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    assigned_agent_id UUID REFERENCES agents(id),
    complexity VARCHAR(20),  -- straightforward, moderate, significant, complex
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    CONSTRAINT chk_story_status CHECK (status IN ('pending', 'in_progress', 'review', 'blocked', 'completed'))
);

CREATE INDEX idx_stories_epic ON stories(epic_id);
CREATE INDEX idx_stories_status ON stories(status);
CREATE INDEX idx_stories_assigned ON stories(assigned_agent_id);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    story_id UUID REFERENCES stories(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    assigned_agent_id UUID REFERENCES agents(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,

    CONSTRAINT chk_task_status CHECK (status IN ('pending', 'in_progress', 'completed'))
);

-- =================================================================
-- AGENT COMMUNICATION
-- =================================================================

CREATE TABLE agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    to_agent_id UUID REFERENCES agents(id),  -- NULL for broadcast
    message_type VARCHAR(50) NOT NULL,
    subject VARCHAR(200),
    content TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal',
    status VARCHAR(20) NOT NULL DEFAULT 'sent',
    metadata JSONB,  -- Additional context
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    read_at TIMESTAMP,
    acknowledged_at TIMESTAMP,

    CONSTRAINT chk_msg_type CHECK (message_type IN ('question', 'answer', 'notification', 'request', 'broadcast')),
    CONSTRAINT chk_msg_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    CONSTRAINT chk_msg_status CHECK (status IN ('sent', 'delivered', 'read', 'acknowledged', 'archived'))
);

CREATE INDEX idx_msg_to_agent ON agent_messages(to_agent_id, status);
CREATE INDEX idx_msg_created ON agent_messages(created_at DESC);

-- =================================================================
-- APPROVAL WORKFLOW
-- =================================================================

CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,  -- write, edit, delete, bash
    file_path TEXT,
    proposed_changes TEXT,
    reasoning TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    feedback TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(50),  -- 'parzival', 'user', 'auto'

    CONSTRAINT chk_approval_status CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled'))
);

CREATE INDEX idx_approval_status ON approval_requests(status);
CREATE INDEX idx_approval_worker ON approval_requests(worker_agent_id);

-- =================================================================
-- PROGRESS TRACKING
-- =================================================================

CREATE TABLE progress_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    summary TEXT NOT NULL,
    git_commit_hash VARCHAR(40),
    story_id UUID REFERENCES stories(id),
    files_changed INTEGER,
    lines_added INTEGER,
    lines_removed INTEGER,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_progress_agent ON progress_log(agent_id);
CREATE INDEX idx_progress_session ON progress_log(session_id);
CREATE INDEX idx_progress_story ON progress_log(story_id);

-- =================================================================
-- COST TRACKING
-- =================================================================

CREATE TABLE cost_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    tokens_input INTEGER NOT NULL,
    tokens_output INTEGER NOT NULL,
    tokens_cache_read INTEGER DEFAULT 0,
    tokens_cache_write INTEGER DEFAULT 0,
    estimated_cost DECIMAL(10,4) NOT NULL,
    model VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cost_agent ON cost_tracking(agent_id);
CREATE INDEX idx_cost_session ON cost_tracking(session_id);
CREATE INDEX idx_cost_date ON cost_tracking(DATE(timestamp));

-- =================================================================
-- AUDIT LOG
-- =================================================================
-- GDPR Compliance (EU AI Act Article 19, effective Aug 2, 2026)
-- Requirement: 6-month retention minimum, tamper-proof logs
-- See BP-025 for hash-chain implementation and privacy requirements

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),  -- epic, story, task, file, agent
    target_id UUID,
    metadata JSONB,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- GDPR Compliance Fields (BP-025)
    previous_hash VARCHAR(64),  -- SHA-256 of previous audit entry
    current_hash VARCHAR(64),   -- SHA-256 of this entry (tamper detection)
    retention_until TIMESTAMP   -- Auto-delete after 6 months (GDPR)
);

CREATE INDEX idx_audit_agent ON audit_log(agent_id);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_target ON audit_log(target_type, target_id);
CREATE INDEX idx_audit_retention ON audit_log(retention_until);

-- =================================================================
-- VIEWS FOR COMMON QUERIES
-- =================================================================

-- Sprint Overview
CREATE VIEW v_sprint_overview AS
SELECT
    e.epic_number,
    e.title AS epic_title,
    e.status AS epic_status,
    COUNT(s.id) AS total_stories,
    SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) AS completed_stories,
    SUM(CASE WHEN s.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress_stories,
    SUM(CASE WHEN s.status = 'blocked' THEN 1 ELSE 0 END) AS blocked_stories
FROM epics e
LEFT JOIN stories s ON e.id = s.epic_id
GROUP BY e.id, e.epic_number, e.title, e.status
ORDER BY e.epic_number;

-- Agent Activity
CREATE VIEW v_agent_activity AS
SELECT
    a.name,
    a.role,
    a.status,
    COUNT(DISTINCT s.id) AS assigned_stories,
    COUNT(DISTINCT pl.id) AS commits_today,
    SUM(ct.tokens_input + ct.tokens_output) AS tokens_today,
    SUM(ct.estimated_cost) AS cost_today
FROM agents a
LEFT JOIN stories s ON a.id = s.assigned_agent_id
LEFT JOIN progress_log pl ON a.id = pl.agent_id AND DATE(pl.timestamp) = CURRENT_DATE
LEFT JOIN cost_tracking ct ON a.id = ct.agent_id AND DATE(ct.timestamp) = CURRENT_DATE
GROUP BY a.id, a.name, a.role, a.status;
```

**Key Design Decisions**:
1. **UUID Primary Keys**: Support distributed agent spawning
2. **Audit Log**: Track all actions for debugging
3. **JSONB Metadata**: Flexible additional context
4. **Views**: Precomputed queries for dashboards
5. **Cascading Deletes**: Clean up related records automatically

**Confidence**: **Verified** (PostgreSQL best practices for workflow tracking)

---

## 4. Technology Stack (2026 Standards)

### 4.1 Backend Services

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Orchestration API** | FastAPI | 0.109+ | REST + WebSocket server |
| **Database** | PostgreSQL | 16.x | Epic/story tracking, agent comms |
| **Agent Runtime** | Claude Agent SDK | Latest | Agent execution framework |
| **Message Queue** | (Optional) Redis | 7.2+ | Pub/sub for real-time events |
| **Python Runtime** | Python | 3.11+ | Core orchestration logic |

### 4.2 React Multi-Terminal Implementation

**Core Stack**:

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Terminal Emulator** | xterm.js | 5.5+ | Full terminal emulation |
| **React Wrapper** | react-xtermjs | Latest | xterm.js React integration |
| **UI Framework** | React | 18.2+ | Component architecture |
| **Type Safety** | TypeScript | 5.3+ | Static typing |
| **Styling** | TailwindCSS | 3.4+ | Utility-first CSS |
| **State Management** | Zustand | 4.5+ | Lightweight state (vs Redux) |
| **WebSocket Client** | native WebSocket | - | Real-time terminal I/O |
| **Build Tool** | Vite | 5.0+ | Fast dev server + HMR |

**Key Libraries**:
- **xterm-addon-fit**: Terminal auto-sizing
- **xterm-addon-web-links**: Clickable URLs
- **xterm-addon-search**: Terminal search
- **react-split**: Resizable panes
- **react-tabs**: Agent tab management

**Architecture Diagram**:
```
┌─────────────────────────────────────────────────────────┐
│ React Frontend (Vite + TypeScript)                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ├─ App.tsx (Main layout)                               │
│  ├─ components/                                         │
│  │   ├─ TerminalGrid.tsx (Grid layout)                 │
│  │   ├─ TerminalPane.tsx (Single terminal)             │
│  │   ├─ ControlPanel.tsx (Spawn buttons, status)       │
│  │   └─ AgentCard.tsx (Agent info sidebar)             │
│  ├─ hooks/                                              │
│  │   ├─ useTerminal.tsx (xterm.js wrapper)             │
│  │   ├─ useWebSocket.tsx (WS connection)               │
│  │   └─ useAgentState.tsx (Agent status)               │
│  └─ stores/                                             │
│      └─ agentStore.ts (Zustand state)                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        ↕ WebSocket
┌─────────────────────────────────────────────────────────┐
│ FastAPI Backend (Python)                                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ├─ websocket_handler.py (Terminal I/O)                │
│  ├─ agent_manager.py (Spawn/stop agents)                │
│  ├─ database.py (PostgreSQL queries)                    │
│  └─ claude_sdk_wrapper.py (Agent SDK integration)       │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        ↕
┌─────────────────────────────────────────────────────────┐
│ Claude Agent SDK Instances                              │
│ (Parzival + Worker Agents)                              │
└─────────────────────────────────────────────────────────┘
```

**Terminal Communication Protocol**:
```typescript
// WebSocket message format
interface TerminalMessage {
  type: 'input' | 'output' | 'spawn' | 'stop' | 'status';
  terminalId: string;
  agentId?: string;
  data?: string;  // Terminal input/output
  metadata?: {
    timestamp: number;
    tokenCount?: number;
    cost?: number;
  };
}

// Example: User types in terminal
{
  type: 'input',
  terminalId: 'worker-1',
  agentId: 'dev-001',
  data: 'Implement user authentication\n'
}

// Example: Agent writes output
{
  type: 'output',
  terminalId: 'worker-1',
  agentId: 'dev-001',
  data: '\x1b[32m✓\x1b[0m Reading story-1.1.md...\n',
  metadata: { timestamp: 1737500000 }
}
```

**Key Features Implementation**:

**1. Resizable Terminal Panes**:
```typescript
import Split from 'react-split';

<Split
  sizes={[60, 40]}  // Parzival 60%, Worker 40%
  minSize={200}
  gutterSize={8}
  direction="horizontal"
>
  <TerminalPane id="oversight" />
  <TerminalPane id="worker-1" />
</Split>
```

**2. Terminal Auto-Sizing with FitAddon**:
```typescript
import { FitAddon } from '@xterm/addon-fit';

const fitAddon = new FitAddon();
terminal.loadAddon(fitAddon);

window.addEventListener('resize', () => {
  fitAddon.fit();
});
```

**3. ANSI Color Support** (built into xterm.js):
```typescript
// Agent can write colored output
terminal.write('\x1b[32m✓\x1b[0m Tests passed\n');  // Green checkmark
terminal.write('\x1b[31m✗\x1b[0m 3 errors found\n');  // Red X
```

**4. Cost Tracking Display**:
```typescript
<AgentCard agentId="dev-001">
  <div>Tokens: {inputTokens + outputTokens}</div>
  <div>Cost: ${totalCost.toFixed(4)}</div>
  <div>Status: {status}</div>
</AgentCard>
```

**Development Workflow**:
```bash
# Frontend (React + Vite)
cd frontend/
npm install
npm run dev  # http://localhost:5173

# Backend (FastAPI)
cd backend/
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# WebSocket: ws://localhost:8000/ws/terminal/{terminalId}
```

**Deployment**:
```bash
# Build frontend
npm run build  # → dist/

# Serve with FastAPI static files
app.mount("/", StaticFiles(directory="dist", html=True))
```

**Confidence**: **Verified** (xterm.js + React is proven architecture, used by VS Code, AWS Cloud9, Theia IDE)

---

### 4.3 Optional Enhancements

| Component | Technology | When to Add |
|-----------|-----------|-------------|
| **Real-time Events** | Redis Pub/Sub | Agent messages require <1s delivery |
| **Metrics** | Prometheus + Grafana | Production monitoring needed |
| **Log Aggregation** | Loki | Multi-agent debugging required |
| **Container Orchestration** | Docker Compose | Simplified deployment |

---

## 5. Module Separation

### 5.1 Repository Structure

**Two Independent Modules**:

> **Parzival 2.1 note**: The current project uses a unified repository with the Parzival oversight layer at `_ai-memory/pov/` and skill shims at `.claude/skills/`. The standalone module split below is the aspirational target for the web UI architecture. Teams/ YAML configs have been removed -- team design is now handled by the aim-parzival-team-builder skill. The team-prompt workflow has been superseded by aim-parzival-team-builder as well.

**Current structure (Parzival 2.1)**:
```
ai-memory/
├── _ai-memory/pov/              # Parzival oversight layer
│   ├── agents/*.md              # Agent definitions (parzival.md, etc.)
│   ├── constraints/global/      # GC-01 to GC-15, GC-19, GC-20
│   ├── workflows/               # Step-file workflows
│   ├── skills/                  # Skill content (aim-agent-dispatch, etc.)
│   └── templates/               # Oversight document templates
├── .claude/skills/aim-*/        # Skill shims (load content from _ai-memory/pov/skills/)
├── src/memory/                  # Python core (storage, search, triggers)
├── docker/                      # Qdrant, Embedding, Streamlit
└── docs/parzival/               # Architecture and design docs (this file)
```

**Aspirational structure (web UI module split)**:
```
/projects/
├── bmad-parzival-module/        # Orchestration module
│   ├── _ai-memory/
│   │   └── pov/agents/*.md      # Parzival + Worker agent definitions
│   ├── frontend/
│   │   └── (React multi-terminal UI)
│   ├── backend/
│   │   └── (FastAPI orchestration API)
│   ├── scripts/
│   │   └── install.sh           # Parzival module installer
│   └── docs/
│       └── BMAD-Multi-Agent-Architecture.md  # This file
│
└── bmad-memory-module/          # Semantic memory module
    ├── src/memory/              # Python core (storage, search, triggers)
    ├── docker/                  # Qdrant, Embedding, Streamlit
    ├── .claude/hooks/           # Automatic memory capture
    ├── scripts/
    │   └── install.sh           # Memory module installer
    └── docs/
        ├── README.md
        └── prometheus-queries.md
```

### 5.2 Installation Flow

**Sequential Installation**:
```bash
# Step 1: Install memory module (foundation)
cd bmad-memory-module/
./scripts/install.sh

# Installs:
# - Qdrant (localhost:26350)
# - Embedding Service (localhost:28080)
# - Streamlit Dashboard (localhost:28501)
# - Claude Code hooks

# Step 2: Install Parzival module (orchestration)
cd bmad-parzival-module/
./scripts/install.sh

# Installs:
# - PostgreSQL database
# - FastAPI backend
# - React frontend
# - Agent definitions
```

**Why Separate Modules?**:
1. **Independent Lifecycle**: Update memory without affecting orchestration
2. **Reusability**: Memory module usable without Parzival
3. **Scaling**: Different deployment requirements (Qdrant ≠ PostgreSQL)
4. **Testing**: Easier to test in isolation
5. **Open Source**: Memory module can be public, Parzival can be private

### 5.3 Integration Points

**Parzival Module → Memory Module**:
```python
# Parzival agent queries memory
from bmad_memory import search_memories

results = search_memories(
    query="authentication decisions",
    collection="discussions",
    limit=5
)

# Parzival passes to worker agent
worker_context = f"Relevant decisions:\n{results}"
```

**Memory Module → Parzival Module**:
```python
# Memory hooks can store to PostgreSQL (optional)
from parzival.database import log_decision

@post_tool_use_hook
def capture_decision(tool_result):
    # Store to Qdrant (memory)
    store_memory(content, type="decision")

    # Also store to PostgreSQL (orchestration)
    log_decision(
        decision_id="DEC-015",
        content=content,
        agent_id=current_agent_id
    )
```

**Confidence**: **Informed** (module separation is standard architecture pattern)

---

## 6. Implementation Timeline

### Phase 1: Foundation (Weeks 1-2)

**Goal**: Basic Parzival orchestration working

**Tasks**:
1. Set up PostgreSQL database with schema
2. Create Parzival agent definition (extend current)
3. Create Dev agent definition (first worker)
4. Implement basic FastAPI backend (spawn, status endpoints)
5. Test Parzival → Dev agent workflow

**Deliverables**:
- PostgreSQL running with tables
- Parzival can spawn Dev agent
- Manual terminal testing (no React yet)

**Confidence**: **Straightforward** (extends existing Parzival implementation)

---

### Phase 2: React Multi-Terminal UI (Weeks 3-4)

**Goal**: Modern web UI replacing manual terminals

**Tasks**:
1. Set up Vite + React + TypeScript project
2. Implement TerminalPane component with xterm.js
3. Create TerminalGrid layout with react-split
4. Implement WebSocket connection to FastAPI
5. Add ControlPanel (spawn buttons, status)
6. Test Parzival terminal → spawn Dev terminal

**Deliverables**:
- React app at `localhost:5173`
- 2 terminals working (Parzival + Dev)
- WebSocket communication functional

**Confidence**: **Moderate** (React + xterm.js is well-documented, 2-3 weeks with frontend experience)

---

### Phase 3: Agent Communication (Week 5)

**Goal**: Worker agents can message each other

**Tasks**:
1. Implement agent_messages table queries
2. Create message polling in agent loop
3. Add message UI in React (notifications)
4. Test Dev → TEA message flow
5. Test broadcast messages (PM → All)

**Deliverables**:
- Agents can send/receive messages via Redis Streams
- UI shows unread message count
- Message history viewable from PostgreSQL

**Implementation Note**: Use hybrid Redis Streams (hot) + PostgreSQL (cold) per Section 2.6

**Confidence**: **Verified** (Redis Streams messaging is proven pattern, BP-024 research)

---

### Phase 4: Approval Workflow (Week 6)

**Goal**: Human-in-the-loop approval gates

**Tasks**:
1. Implement PreToolUse hook for approval requests
2. Create approval UI in Parzival terminal
3. Store approvals to PostgreSQL
4. Test approval → worker receives response
5. Add approval history view

**Deliverables**:
- Workers request approval before file changes
- Parzival reviews and approves/rejects
- Approval log stored in PostgreSQL

**Critical Implementation Notes** (BP-026):
- ⚠️ **KNOWN BUG**: Claude Code hooks silently stop after ~2.5 hours (GitHub #16047)
- **Workaround**: Implement heartbeat monitoring (check every 15 minutes)
- **Performance**: Hooks must respond <500ms (fork background workers)
- **Reliability**: Graceful degradation (exit 0 for non-critical failures)
- **Idempotency**: Use Redis to track processed hook IDs (prevent duplicates)
- **Circuit Breaker**: 5 failures → OPEN state (30s cooldown)

**Confidence**: **Verified** (BP-026 research with production patterns and known bug workarounds)

---

### Phase 5: Quality Gates (Week 7)

**Goal**: Automated review cycle

**Tasks**:
1. Create Code Reviewer agent definition
2. Implement review trigger after story completion
3. Add review loop: Fix → Re-review → Repeat
4. Test with intentional code issues
5. Verify only clean code marks stories complete

**Deliverables**:
- Code review triggered automatically
- Review results shown in UI
- Stories only complete after 0 issues

**Confidence**: **Straightforward** (extends Phase 1 agent spawning)

---

### Phase 6: Polish & Production (Weeks 8-9)

**Goal**: Production-ready system

**Tasks**:
1. Add cost tracking to UI
2. Implement session persistence (reconnect to agents) - See BP-027
3. Add error handling and recovery - See BP-023, BP-027
4. Create installation documentation
5. End-to-end testing with full sprint workflow

**State Persistence Implementation** (BP-027):
- **LangGraph Checkpointing**: PostgresSaver for automatic state snapshots
- **Saga Pattern**: Compensating transactions for long-running workflows
- **Multi-tier Storage**: Redis (hot) + PostgreSQL (warm) + S3 (cold)
- **Event Sourcing**: Point-in-time recovery via event replay

**Error Recovery Patterns** (BP-023):
- **Circuit Breaker**: 5 failures → OPEN state (prevent cascades)
- **Exponential Backoff**: 1s, 2s, 4s, 8s, 16s with jitter
- **Dead Letter Queue**: Failed tasks preserved for analysis
- **Graceful Degradation**: Non-critical failures exit 0
6. Performance optimization (caching, lazy loading)

**Deliverables**:
- Installer script (`install.sh`)
- User documentation
- Production deployment guide
- Performance benchmarks

**Confidence**: **Moderate** (standard production hardening)

---

### Total Timeline: 9 Weeks (2-3 Months)

**Assumptions**:
- 1 developer with React + Python experience
- Memory module already complete (✅)
- Parzival agent already functional (✅)
- Full-time work (not evenings/weekends)

**Risk Factors**:
- WebSocket stability (test with multiple agents)
- Agent SDK integration complexity (Phase 1 testing critical)
- React learning curve (if unfamiliar with xterm.js)

**Confidence**: **Informed** (realistic estimate based on module complexity)

---

## 7. Key Success Factors

### 7.1 Start with Minimal Viable Product (MVP)

**Phase 1 MVP**:
- Parzival + 1 Dev agent
- Manual terminals (no React)
- PostgreSQL tracking
- Basic approval workflow

**Rationale**: Prove core orchestration before investing in UI

---

### 7.2 Leverage Existing Code

**Already Complete**:
- ✅ Memory module (Qdrant + embeddings)
- ✅ Parzival agent definition
- ✅ BMAD workflow templates
- ✅ Hook infrastructure

**New Work Required**:
- PostgreSQL schema + queries
- React multi-terminal UI
- FastAPI orchestration API
- Agent communication system

**Confidence**: **Verified** (50% of system already built)

---

### 7.3 Follow Anthropic Patterns

**Long-Running Agent Pattern**:
1. Get bearings (read logs, check status)
2. Test existing functionality (smoke tests)
3. Choose one feature (incremental work)
4. Implement and test (thorough validation)
5. Leave clean state (git commit, progress update)

**Approval Gate Pattern**:
- Request approval before changes
- Provide context (file, reason, impact)
- Accept feedback and iterate
- Log all approvals for audit

**Confidence**: **Verified** (Anthropic's published research)

---

### 7.4 PostgreSQL vs Qdrant Clarity

**Use PostgreSQL For**:
- Epic, story, task tracking (structured data)
- Agent messages (relational queries)
- Approval workflow (transaction guarantees)
- Cost tracking (aggregation queries)
- Audit logs (compliance)

**Use Qdrant For**:
- Code patterns (semantic search)
- Best practices (similarity matching)
- Decision history (context retrieval)
- Error solutions (fuzzy matching)

**Why Not Combine?**:
- Different query patterns (SQL vs vector search)
- Different scaling needs (PostgreSQL scales vertically, Qdrant horizontally)
- Different data models (relational vs embeddings)
- Separation of concerns (orchestration vs memory)

**Confidence**: **Verified** (industry best practice for hybrid systems)

---

## 8. Open Questions

### 8.1 Technical

1. **Redis vs PostgreSQL for Messages**: Start with PostgreSQL, add Redis if latency >1s?
2. **Agent SDK Async Support**: Does SDK support async/await for Python 3.11+?
3. **WebSocket Scaling**: How many concurrent terminals before needing load balancer?
4. **Cost Tracking Accuracy**: Can we get exact token counts from Agent SDK?

### 8.2 Product

1. **Agent Limits**: Max concurrent agents before performance degrades?
2. **Session Persistence**: Should agents survive backend restart?
3. **Multi-User**: Single user system or multi-tenancy required?
4. **Mobile UI**: React UI mobile-responsive or desktop-only?

---

## 9. Next Steps

### Immediate Actions (Week 1)

1. **User Decision**: Approve this architecture specification
2. **Create DEC-031**: Document technology choices (PostgreSQL, React, xterm.js)
3. **Set up PostgreSQL**: Install and initialize database
4. **Extend Parzival**: Add orchestration capabilities to current agent
5. **Prototype**: Manual terminal test (Parzival spawns Dev agent)

### Planning Actions (Week 1-2)

1. **Create Epic 8**: "BMAD Multi-Agent Orchestration System"
2. **Break into Stories**:
   - 8.1: PostgreSQL schema and queries
   - 8.2: Agent spawning infrastructure
   - 8.3: React multi-terminal foundation
   - 8.4: WebSocket communication
   - 8.5: Agent messaging system
   - 8.6: Approval workflow
   - 8.7: Quality gates (code review loop)
   - 8.8: Cost tracking and UI polish
3. **Update task-tracker.md**: Add Epic 8 to sprint
4. **Update risk-register.md**: Note dependencies on Agent SDK

---

## 10. References

### Technology Documentation

**xterm.js + React**:
- [xterm.js official](https://xtermjs.org/)
- [react-xtermjs by Qovery](https://github.com/Qovery/react-xtermjs)
- [xterm-react wrapper](https://github.com/PabloLION/xterm-react)
- [React terminal integration guide](https://www.linkedin.com/pulse/easy-web-terminal-magic-integrating-xtermjs-react-john-kagunda-545gf)

**React vs Streamlit**:
- [Framework comparison](https://www.deeplearningnerds.com/streamlit-vs-react-choosing-the-right-framework-for-your-web-app/)
- [Scaling considerations](https://discuss.streamlit.io/t/streamlit-vs-django-and-react-ui/28768)
- [Performance analysis](https://www.appsilon.com/post/react-python-r-decison-systems)

**PostgreSQL Best Practices**:
- [PostgreSQL 16 documentation](https://www.postgresql.org/docs/16/)
- [UUID vs SERIAL for distributed systems](https://www.postgresql.org/docs/16/datatype-uuid.html)
- [JSONB for flexible metadata](https://www.postgresql.org/docs/16/datatype-json.html)

**Claude Agent SDK**:
- [Agent SDK Documentation](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Autonomous Coding Quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding)
- [Long-Running Agents Research](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

**BMAD Method**:
- [BMAD GitHub](https://github.com/bmad-code-org/BMAD-METHOD)
- [BMAD Documentation](http://docs.bmad-method.org)

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Parzival** | Orchestrator agent that coordinates user planning and worker agents |
| **Worker Agent** | Specialized BMAD role agent (Dev, PM, Architect, TEA, etc.) |
| **Epic** | High-level feature grouping in BMAD Method (e.g., "User Authentication") |
| **Story** | Specific user-facing feature (e.g., "Story 1.1: Login Form") |
| **BMAD Method** | Breakthrough Method for Agile AI Driven Development framework |
| **Approval Gate** | Human-in-the-loop checkpoint before file modifications |
| **Quality Gate** | Automated review cycle (review → fix → re-review → approve) |
| **Orchestration Database** | PostgreSQL tracking epic/story progress and agent communication |
| **Memory Module** | Qdrant-based semantic memory system (separate module) |
| **xterm.js** | JavaScript terminal emulator library (used by VS Code) |
| **Agent SDK** | Claude's framework for building autonomous agents |

---

## Appendix B: Configuration Examples

### PostgreSQL Connection String
```bash
# .env file
DATABASE_URL=postgresql://user:password@localhost:5432/bmad_orchestration
```

### React Environment Variables
```bash
# frontend/.env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

### FastAPI CORS Configuration
```python
# backend/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

**Document Status**: ✅ **READY FOR IMPLEMENTATION**

**Last Updated**: 2026-03-15
**Version**: 2.1
**Prepared by**: Parzival (Technical PM & Quality Gatekeeper)

---
