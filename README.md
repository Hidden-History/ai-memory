# 🧠 AI-Memory

<p align="center">
  <img src="assets/ai-memory-banner.png" alt="AI-Memory Banner" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.6-green?style=flat-square" alt="Version 2.0.6">
  <a href="https://github.com/Hidden-History/ai-memory/stargazers"><img src="https://img.shields.io/github/stars/Hidden-History/ai-memory?color=blue&style=flat-square" alt="Stars"></a>
  <a href="https://github.com/Hidden-History/ai-memory/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Hidden-History/ai-memory?style=flat-square" alt="License"></a>
  <a href="https://github.com/Hidden-History/ai-memory/issues"><img src="https://img.shields.io/github/issues/Hidden-History/ai-memory?color=red&style=flat-square" alt="Issues"></a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome">
  <img src="https://img.shields.io/badge/GitHub-Sync-2088FF?style=flat-square&logo=github" alt="GitHub Sync">  <img src="https://img.shields.io/badge/Jira-Cloud-0052CC?style=flat-square&logo=jira" alt="Jira Cloud">  <img src="https://img.shields.io/badge/Qdrant-Vector_DB-DC382D?style=flat-square&logo=qdrant" alt="Qdrant">  <img src="https://img.shields.io/badge/Parzival-Project_Manager-8B5CF6?style=flat-square" alt="Parzival">
</p>

---

### **Cure AI Amnesia.**
**AI-Memory** is a persistent context layer designed to give your agents institutional memory. By bridging LLMs with a high-performance vector database (Qdrant), this framework ensures your agents remember architectural decisions, project rules, and past interactions across every session.

[**Explore the Docs**](#-usage) | [**Report a Bug**](https://github.com/Hidden-History/ai-memory/issues) | [**Request a Feature**](https://github.com/Hidden-History/ai-memory/issues)

---

## 🚀 Key Features

* **🧠 Cross-Session Memory:** Claude remembers your last session automatically — no re-explaining needed.
* **⏳ Semantic Decay:** Memories age naturally — recent patterns rank higher than stale ones.
* **🛡️ 3-Layer Security:** PII and secrets caught before storage via regex + detect-secrets + SpaCy NER.
* **🐙 GitHub History Sync:** PRs, issues, commits, CI results searchable by meaning.
* **🎯 Progressive Context Injection:** Right memories, right time, within token budgets.

---

## 🧬 Bespoke Neural Memory

<table>
<tr>
<td width="60%">

**This isn't a database you configure. It's institutional memory that forms as you build.**

Traditional knowledge bases require upfront schema design and manual curation. AI-Memory takes a different approach: let the LLM and human decide what matters, and capture it as it happens.

> 🎯 Error fixed? **Captured.**
> 📐 Architecture decision made? **Stored.**
> 📏 Convention established? **Remembered.**

**Your agents don't just execute—they learn.**

</td>
<td width="40%">

| | Aspect | Benefit |
|:--:|--------|---------|
| 🎨 | **Bespoke** | Memory unique to YOUR project |
| ⚡ | **JIT Creation** | Emerges from work, not config |
| 💫 | **Transient → Persistent** | Sessions become knowledge |
| 🪶 | **Token Efficient** | ~500 token focused memories |
| 🚀 | **Lightweight** | Docker + Qdrant + Python |

</td>
</tr>
</table>

---

## 🛡️ Parzival: Technical PM & Quality Gatekeeper

Parzival is your AI project manager embedded in Claude Code. Describe what needs doing, and Parzival orchestrates the work with verified precision — reading your architecture, PRD, and standards before creating prompts, never after.

**Core capabilities:**

- **Agent team orchestration**: `/parzival-team` builds 3-tier parallel team prompts (lead → workers → reviewers) with exact file paths, line numbers, acceptance criteria, and project-specific context — derived from your actual project files, not assumptions
- **Quality gate enforcement**: Mandatory review→fix→review cycles that continue until zero issues are found. Parzival never accepts "looks good enough"
- **Verified instructions**: Every recommendation is checked against project files first and rated with a confidence level (Verified/Informed/Inferred/Uncertain/Unknown), with source citations included
- **False positive catching**: When review agents flag issues, Parzival verifies findings against actual source code before acting — preventing wasted cycles on non-issues
- **Decision support**: Presents options with pros/cons, tradeoffs, source citations, and confidence levels, then waits for your approval before proceeding
- **Risk and blocker tracking**: Identifies risks proactively with severity levels and escalation paths; surfaces critical issues immediately
- **Session continuity**: Handoffs are dual-written to local oversight files and the Qdrant `discussions` collection, enabling automatic cross-session resume at every `SessionStart`
- **Sprint and task management**: Tracks sprints, tasks, blockers, and decisions across sessions via structured oversight files (`task-tracker.md`, `decisions-log.md`, `SESSION_WORK_INDEX.md`)

**How the workflow works:**

1. You describe the work to Parzival
2. Parzival reads your architecture, PRD, and standards before making any recommendation
3. Parzival builds a precise agent team prompt — or individual dev prompt — with exact file paths and acceptance criteria
4. You run the agents; Parzival reviews the results
5. Review→fix→review continues until zero issues are found, then you approve

**The core principle: Parzival recommends. You decide.** Parzival is the radar operator on the ship — you are the captain who steers. It monitors, navigates, and verifies. It never writes code, makes final decisions, or executes agents autonomously. A 5-layer constraint system prevents the behavioral drift that causes AI agents to forget their role over long conversations.

Parzival is optional — AI Memory's core features (semantic decay, GitHub sync, search skills, freshness detection) work independently without it. For teams managing complex projects across many sessions, Parzival is the orchestration layer that keeps everything on track.

See [docs/PARZIVAL-SESSION-GUIDE.md](docs/PARZIVAL-SESSION-GUIDE.md) for setup, commands, and the full skills reference.

---

## 🏆 What No Other Tool Has

AI-Memory combines capabilities that exist nowhere else as a single integrated system:

| Capability | What It Does |
|------------|-------------|
| **Semantic Decay Scoring** | Memories age naturally via exponential decay — recent patterns rank higher than stale ones, automatically |
| **Cross-Session Memory** | Qdrant vector search resurfaces exactly the right context at session start, without you asking |
| **3-Layer Security Pipeline** | PII and secrets screened via regex + detect-secrets + SpaCy NER before any content is stored |
| **GitHub History → Semantic Search** | PRs, issues, commits, CI results, code blobs, diffs, reviews, and releases searchable by meaning |
| **Freshness Detection** | Stale code-pattern memories flagged automatically by comparing stored patterns against current git state (3/10/25 commit thresholds) |
| **Dual Embedding Routing** | Code uses `jina-v2-base-code`; prose uses `jina-v2-base-en` — 10-30% better retrieval accuracy |
| **Progressive Context Injection** | Token-budget-aware 3-tier delivery: session bootstrap, per-turn injection, confidence-filtered retrieval |

---

## ✨ V2.0 Memory System

- 🗂️ **Four Specialized Collections**: code-patterns (HOW), conventions (WHAT), discussions (WHY), jira-data (JIRA)
- 🎯 **30 Memory Types**: Precise categorization for implementation, errors, decisions, Jira issues, GitHub data, agent memory, and more
- ⚡ **6 Automatic Triggers**: Smart context injection when you need it most
- 🔍 **Intent Detection**: Automatically routes queries to the right collection
- 💬 **Conversation Memory**: Turn-by-turn capture with post-compaction context continuity
- 🔁 **Cascading Search**: Falls back across collections for comprehensive results
- 📊 **Monitoring**: Prometheus metrics + Grafana dashboards
- 🛡️ **Graceful Degradation**: Works even when services are temporarily unavailable
- 👥 **Multi-Project Isolation**: `group_id` filtering keeps projects separate

---

> **New here?** Jump to [Quick Start](#-quick-start-1) to get running in 5 minutes.

---

## 🕰️ V2.0.6 — Temporal Memory

v2.0.6 adds the **WHEN dimension** — your memories now understand time, freshness, and relevance decay.

- ⏳ **Semantic Decay Scoring**: Older memories naturally lose relevance via exponential decay with type-specific half-lives (code: 14d, discussions: 21d, conventions: 60d)
- 🔄 **GitHub History Sync**: Ingest PRs, issues, commits, CI results, and code blobs from your GitHub repo into the memory system
- 🛡️ **Security Scanning Pipeline**: 3-layer PII and secrets detection (regex + detect-secrets + SpaCy NER) runs before any content is stored
- 🎯 **Progressive Context Injection**: Smart 3-tier context delivery — session bootstrap, per-turn injection, and confidence-filtered retrieval
- 🔍 **Freshness Detection**: Automatically identifies stale memories by comparing against current git state
- 🔐 **SOPS+age Encryption**: Encrypt sensitive configuration with modern age encryption
- 🧭 **Dual Embedding Routing**: Code content uses `jina-v2-base-code`, prose uses `jina-v2-base-en` for 10-30% better retrieval
- 🤖 **Parzival Oversight Agent**: Technical PM, quality gatekeeper, and agent team orchestrator with cross-session memory backed by Qdrant
- 🧰 **8 New Skills**: `/memory-purge`, `/search-github`, `/github-sync`, `/pause-updates`, `/memory-refresh`, `/parzival-save-handoff`, `/parzival-save-insight`, `/freshness-report`

---

## 🔗 Jira Cloud Integration

Bring your work context into semantic memory with built-in Jira Cloud support:

- **Semantic Search**: Search Jira issues and comments by meaning, not just keywords
- **Full & Incremental Sync**: Initial backfill or fast daily updates via JQL
- **ADF Conversion**: Atlassian Document Format → plain text for accurate embeddings
- **Rich Filtering**: Search by project, issue type, status, priority, or author
- **Issue Lookup**: Retrieve complete issue context (issue + all comments, chronologically)
- **Dedicated Collection**: `jira-data` collection keeps Jira content separate from code memory
- **Tenant Isolation**: `group_id` based on Jira instance hostname prevents cross-instance leakage
- **Two Skills**: `/jira-sync` for synchronization, `/search-jira` for semantic search

See [docs/JIRA-INTEGRATION.md](docs/JIRA-INTEGRATION.md) for setup and usage guide.

---

## 🐙 GitHub Integration

Bring your repository history into semantic memory with built-in GitHub support:

- **Semantic Search**: Search PRs, issues, commits, CI results, and code blobs by meaning, not keywords
- **9 Content Types**: `github_pr`, `github_issue`, `github_commit`, `github_ci_result`, `github_code_blob`, `github_pr_diff`, `github_pr_review`, `github_issue_comment`, `github_release`
- **Full & Incremental Sync**: First run backfills full history; subsequent runs fetch only new or updated items
- **AST-Aware Code Chunking**: Code blobs are split at AST boundaries (functions, classes), not arbitrary character offsets
- **Freshness Feedback Loop**: Merged PRs automatically flag stale code-pattern memories for review
- **Adaptive Rate Limiting**: Reads `X-RateLimit-Remaining` response headers and backs off automatically
- **Two Skills**: `/github-sync` for synchronization, `/search-github` for semantic search

See [docs/GITHUB-INTEGRATION.md](docs/GITHUB-INTEGRATION.md) for setup and usage guide.

---

## 🔬 Knowledge Discovery

### Best Practices Researcher

When you ask "how should I..." or "what's the best way to...", AI-Memory's best-practices-researcher activates:

1. **Search Local Knowledge** - Checks the conventions collection first
2. **Web Research** - Searches 2024-2026 sources if needed
3. **Save Findings** - Stores to `oversight/knowledge/best-practices/BP-XXX.md`
4. **Database Storage** - Adds to Qdrant for future retrieval
5. **Skill Evaluation** - Determines if findings warrant a reusable skill

### Skill Creator Agent

When research reveals a repeatable process, the skill-creator agent can generate a Claude Code skill:

```
User: "Research best practices for writing commit messages"
→ Best Practices Researcher finds patterns
→ Evaluates: "This is a repeatable process with clear steps"
→ User confirms: "Yes, create a skill"
→ Skill Creator generates .claude/skills/writing-commits/SKILL.md
```

**The Result:** Your AI agents continuously discover and codify knowledge into reusable skills.

---

## 🏗️ Architecture

### V2.0 Memory System

```
Claude Code Session
    ├── SessionStart Hooks (resume|compact) → Context injection on session resume and post-compaction
    ├── UserPromptSubmit Hooks → Unified keyword trigger (decisions/best practices/session history)
    ├── PreToolUse Hooks → Smart triggers (new file/first edit conventions)
    ├── PostToolUse Hooks → Capture code patterns + error detection
    ├── PreCompact Hook → Save conversation before compaction
    └── Stop Hook → Capture agent responses

Python Core (src/memory/)
    ├── config.py         → Environment configuration
    ├── storage.py        → Qdrant CRUD operations
    ├── search.py         → Semantic search + cascading
    ├── intent.py         → Intent detection + routing
    ├── triggers.py       → Automatic trigger configuration
    ├── embeddings.py     → Jina AI embeddings — jina-v2-base-en (prose) + jina-v2-base-code (code)
    └── deduplication.py  → Hash + similarity dedup

Docker Services
    ├── Qdrant (port 26350)
    ├── Embedding Service (port 28080)
    ├── Classifier Worker (LLM reclassification)
    ├── Streamlit Dashboard (port 28501)
    └── Monitoring Stack (--profile monitoring)
        ├── Prometheus (port 29090)
        ├── Pushgateway (port 29091)
        └── Grafana (port 23000)
```

**v2.0.6 additions**: GitHub sync service ingests repository data (PRs, issues, commits, code blobs) into the discussions collection. A 3-layer security scanning pipeline (regex + detect-secrets + SpaCy NER) screens all content before storage. Semantic decay scoring applies time-weighted relevance to all search queries. The Parzival session agent stores cross-session memory in the discussions collection for project continuity.

### Collection Structure

| Collection | Purpose | Example Types |
|------------|---------|---------------|
| **code-patterns** | HOW things are built | implementation, error_fix, refactor |
| **conventions** | WHAT rules to follow | rule, guideline, naming, structure |
| **discussions** | WHY things were decided | decision, session, preference, user_message, agent_response, blocker |
| **jira-data** | External work items from Jira Cloud | jira_issue, jira_comment |

> **Note:** The `jira-data` collection is conditional — it is only created when Jira sync is enabled (`JIRA_SYNC_ENABLED=true`).

### Automatic Triggers

The memory system automatically retrieves relevant context:

- **Error Detection**: When a command fails, retrieves past error fixes
- **New File Creation**: Retrieves naming conventions and structure patterns
- **First Edit**: Retrieves file-specific patterns on first modification
- **Decision Keywords**: "Why did we..." triggers decision memory retrieval
- **Best Practices Keywords**: "How should I..." triggers convention retrieval
- **Session History Keywords**: "What have we done..." triggers session summary retrieval

### Trigger Keyword Reference

The following keywords automatically activate memory retrieval when detected in your prompts:

<details>
<summary><b>Decision Keywords</b> (20 patterns) → Searches <code>discussions</code> for past decisions</summary>

| Category | Keywords |
|----------|----------|
| Decision recall | `why did we`, `why do we`, `what was decided`, `what did we decide` |
| Memory recall | `remember when`, `remember the decision`, `remember what`, `remember how`, `do you remember`, `recall when`, `recall the`, `recall how` |
| Session references | `last session`, `previous session`, `earlier we`, `before we`, `previously`, `last time we`, `what did we do`, `where did we leave off` |

</details>

<details>
<summary><b>Session History Keywords</b> (16 patterns) → Searches <code>discussions</code> for session summaries</summary>

| Category | Keywords |
|----------|----------|
| Project status | `what have we done`, `what did we work on`, `project status`, `where were we`, `what's the status` |
| Continuation | `continue from`, `pick up where`, `continue where` |
| Remaining work | `what's left to do`, `remaining work`, `what's next for`, `what's next on`, `what's next in the`, `next steps`, `todo`, `tasks remaining` |

</details>

<details>
<summary><b>Best Practices Keywords</b> (27 patterns) → Searches <code>conventions</code> for guidelines</summary>

| Category | Keywords |
|----------|----------|
| Standards | `best practice`, `best practices`, `coding standard`, `coding standards`, `convention`, `conventions for` |
| Patterns | `what's the pattern`, `what is the pattern`, `naming convention`, `style guide` |
| Guidance | `how should i`, `how do i`, `what's the right way`, `what is the right way` |
| Research | `research the pattern`, `research best practice`, `look up`, `find out about`, `what do the docs say` |
| Recommendations | `should i use`, `what's recommended`, `what is recommended`, `recommended approach`, `preferred approach`, `preferred way`, `industry standard`, `common pattern` |

</details>

> **Note**: Keywords are case-insensitive. Only structured patterns trigger retrieval to avoid false positives on casual conversation.

### LLM Memory Classifier

The optional LLM Classifier automatically reclassifies captured memories into more precise types:

- **Rule-based first**: Fast pattern matching (free, <10ms)
- **LLM fallback**: AI classification when rules don't match
- **Provider chain**: Primary provider with automatic fallback

**Quick Setup:**

```bash
# Configure in docker/.env
MEMORY_CLASSIFIER_ENABLED=true
MEMORY_CLASSIFIER_PRIMARY_PROVIDER=ollama    # or: openrouter, claude, openai
MEMORY_CLASSIFIER_FALLBACK_PROVIDERS=openrouter

# For Ollama (free, local)
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=sam860/LFM2:2.6b

# For OpenRouter (free tier available)
OPENROUTER_API_KEY=sk-or-v1-your-key
OPENROUTER_MODEL=google/gemma-2-9b-it:free
```

See [docs/llm-classifier.md](docs/llm-classifier.md) for complete setup guide, provider options, and troubleshooting.

## 🚀 Quick Start

### 1. Start Services

```bash
# Core services (Qdrant + Embedding)
docker compose -f docker/docker-compose.yml up -d

# With monitoring (adds Prometheus, Grafana, Pushgateway)
docker compose -f docker/docker-compose.yml --profile monitoring up -d
```

### 2. Verify Services

```bash
# Check Qdrant (port 26350)
curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/health

# Check Embedding Service (port 28080)
curl http://localhost:28080/health

# Check Grafana (port 23000) - if monitoring enabled
open http://localhost:23000  # credentials from installation
```

### 3. Install to Project

```bash
./scripts/install.sh /path/to/your-project

# With convention seeding (recommended)
SEED_BEST_PRACTICES=true ./scripts/install.sh /path/to/your-project
```

**Expected Output:**

```
═══════════════════════════════════════════════════════════
  AI Memory Module Health Check
═══════════════════════════════════════════════════════════

[1/3] Checking Qdrant (localhost:26350)...
  ✅ Qdrant is healthy

[2/3] Checking Embedding Service (localhost:28080)...
  ✅ Embedding service is healthy

[3/3] Checking Monitoring API (localhost:28000)...
  ✅ Monitoring API is healthy

═══════════════════════════════════════════════════════════
  All Services Healthy ✅
═══════════════════════════════════════════════════════════
```

## 📦 Installation

### Prerequisites

- **Python 3.10+** (3.11+ required for AsyncSDKWrapper)
- **Docker 20.10+** (for Qdrant + embedding service)
- **Claude Code** (target project where memory will be installed)

### Resource Requirements

AI Memory runs on 16 GiB RAM (4 cores minimum). Adding the optional Langfuse LLM observability module increases the requirement to 32 GiB RAM (8 cores recommended).

| Tier | Services | Minimum RAM | Recommended CPU |
|------|----------|-------------|-----------------|
| **Core** (default) | 8 services | 16 GiB | 4 cores |
| **Core + Langfuse** (opt-in) | 14 services | 32 GiB | 8 cores |

### Installation Steps

See [INSTALL.md](INSTALL.md) for detailed installation instructions including:

- System requirements with version compatibility
- Step-by-step installation for macOS, Linux, and Windows (WSL2)
- Automated installer and manual installation methods
- Post-installation verification
- Configuration options
- Uninstallation procedures

## ⚙️ Configuration

### 🔌 Service Ports

All services use `2XXXX` prefix to avoid conflicts:

| Service          | External | Internal | Access URL                  |
|------------------|----------|----------|-----------------------------|
| Qdrant           | 26350    | 6333     | `localhost:26350`           |
| Embedding        | 28080    | 8080     | `localhost:28080/embed`     |
| Monitoring API   | 28000    | 8000     | `localhost:28000/health`    |
| Streamlit        | 28501    | 8501     | `localhost:28501`           |
| Grafana          | 23000    | 3000     | `localhost:23000`           |
| Prometheus       | 29090    | 9090     | `localhost:29090` (--profile monitoring) |
| Pushgateway      | 29091    | 9091     | `localhost:29091` (--profile monitoring) |

**Optional: Langfuse LLM Observability Ports (opt-in):**

| Port | Service | Notes |
|------|---------|-------|
| 23100 | Langfuse Web UI | Optional (Langfuse) |
| 23130 | Langfuse Worker | Optional (Langfuse) |
| 25432 | Langfuse PostgreSQL | Optional (Langfuse) |
| 26379 | Langfuse Redis | Optional (Langfuse) |
| 28123 | Langfuse ClickHouse | Optional (Langfuse) |
| 29000 | Langfuse MinIO | Optional (Langfuse) |

### Environment Variables

| Variable               | Default               | Description                       |
|------------------------|----------------------|-----------------------------------|
| `QDRANT_HOST`          | `localhost`          | Qdrant server hostname            |
| `QDRANT_PORT`          | `26350`              | Qdrant external port              |
| `EMBEDDING_HOST`       | `localhost`          | Embedding service hostname        |
| `EMBEDDING_PORT`       | `28080`              | Embedding service port            |
| `AI_MEMORY_INSTALL_DIR`   | `~/.ai-memory`     | Installation directory            |
| `MEMORY_LOG_LEVEL`     | `INFO`               | Logging level (DEBUG/INFO/WARNING)|

**Jira Cloud Integration (Optional):**

| Variable               | Default               | Description                       |
|------------------------|----------------------|-----------------------------------|
| `JIRA_INSTANCE_URL`    | *(empty)*            | Jira Cloud URL (e.g., `https://company.atlassian.net`) |
| `JIRA_EMAIL`           | *(empty)*            | Jira account email for Basic Auth |
| `JIRA_API_TOKEN`       | *(empty)*            | API token from [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_PROJECTS`        | *(empty)*            | JSON array of project keys (e.g., `["PROJ","DEV","OPS"]`). Comma-separated also accepted for backwards compatibility. |
| `JIRA_SYNC_ENABLED`    | `false`              | Enable Jira synchronization       |
| `JIRA_SYNC_DELAY_MS`   | `100`                | Delay between API requests (ms)   |

See [docs/JIRA-INTEGRATION.md](docs/JIRA-INTEGRATION.md) for complete Jira setup guide.

**Override Example:**

```bash
export QDRANT_PORT=16333  # Use custom port
export MEMORY_LOG_LEVEL=DEBUG  # Enable verbose logging
```

## 💡 Usage

### 🔧 Automatic Memory Capture

Memory capture happens automatically via Claude Code hooks:

1. **SessionStart** (resume/compact only): Injects relevant memories when resuming a session or after context compaction
2. **PostToolUse**: Captures code patterns (Write/Edit/NotebookEdit tools) in background (<500ms)
3. **PreCompact**: Saves session summary before context compaction (auto or manual `/compact`)
4. **Stop**: Optional per-response cleanup

No manual intervention required - hooks handle everything.

> **The "Aha Moment"**: Claude remembers your previous sessions automatically. Start a new session and Claude will say "Welcome back! Last session we worked on..." without you reminding it.

### 🎯 Manual Memory Operations

Use slash commands for manual control:

```bash
# Check system status
/memory-status

# Manually save current session
/save-memory

# Search across all memories
/search-memory <query>

# Jira Cloud Integration (requires JIRA_SYNC_ENABLED=true)
/jira-sync              # Incremental sync from Jira
/jira-sync --full       # Full sync (all issues and comments)
/search-jira "query"    # Semantic search across Jira content
/search-jira --issue PROJ-42  # Lookup issue + all comments
```

#### v2.0.6 Skills

| Command | Description |
|---------|-------------|
| `/memory-purge` | Purge old memories with dry-run safety (e.g., `--older-than 90d`) |
| `/search-github` | Semantic search of GitHub data (PRs, issues, commits, code) |
| `/github-sync` | Manually trigger GitHub repository sync |
| `/pause-updates` | Toggle automatic memory updates on/off (kill switch) |
| `/memory-refresh` | Trigger freshness scan on changed files |
| `/parzival-save-handoff` | Save Parzival session handoff to Qdrant memory |
| `/parzival-save-insight` | Save a Parzival insight for cross-session recall |
| `/freshness-report` | Scan code-patterns for stale memories by comparing against current git state |

#### Upgraded Skills (v2.0.6)

| Command | What Changed |
|---------|-------------|
| `/memory-status` | 4 new sections: decay stats, GitHub sync status, security scan summary, Parzival session info |
| `/search-memory` | Now displays decay scores alongside relevance scores |
| `/save-memory` | Supports agent memory types (handoff, insight, task) |

See [docs/HOOKS.md](docs/HOOKS.md) for hook documentation, [docs/COMMANDS.md](docs/COMMANDS.md) for commands, [docs/llm-classifier.md](docs/llm-classifier.md) for LLM classifier setup, and [docs/JIRA-INTEGRATION.md](docs/JIRA-INTEGRATION.md) for Jira integration guide.

### 🤖 AsyncSDKWrapper (Agent SDK Integration)

The AsyncSDKWrapper provides full async/await support for building custom Agent SDK agents with persistent memory.

**Features:**

- Full async/await support compatible with Agent SDK
- Rate limiting with token bucket algorithm (Tier 1: 50 RPM, 30K TPM)
- Exponential backoff retry with jitter (3 retries: 1s, 2s, 4s ±20%)
- Automatic conversation capture to discussions collection
- Background storage (fire-and-forget pattern)
- Prometheus metrics integration

**Basic Usage:**

```python
import asyncio
from src.memory import AsyncSDKWrapper

async def main():
    async with AsyncSDKWrapper(cwd="/path/to/project") as wrapper:
        # Send message with automatic rate limiting and retry
        result = await wrapper.send_message(
            prompt="What is async/await?",
            model="claude-sonnet-4-5-20250929",
            max_tokens=500
        )

        print(f"Response: {result['content']}")
        print(f"Session ID: {result['session_id']}")

asyncio.run(main())
```

**Streaming Responses (Buffered):**

> **Note**: Current implementation buffers the full response for retry reliability. True progressive streaming planned for future release.

```python
async with AsyncSDKWrapper(cwd="/path/to/project") as wrapper:
    async for chunk in wrapper.send_message_buffered(
        prompt="Explain Python async",
        model="claude-sonnet-4-5-20250929",
        max_tokens=800
    ):
        print(chunk, end='', flush=True)
```

**Custom Rate Limits:**

```python
async with AsyncSDKWrapper(
    cwd="/path/to/project",
    requests_per_minute=100,   # Tier 2
    tokens_per_minute=100000   # Tier 2
) as wrapper:
    result = await wrapper.send_message("Hello!")
```

**Examples:**

- `examples/async_sdk_basic.py` - Basic async/await usage, context manager pattern, session ID logging, rate limiting demonstration
- `examples/async_sdk_streaming.py` - Streaming response handling (buffered), progressive chunk processing, retry behavior
- `examples/async_sdk_rate_limiting.py` - Custom rate limit configuration, queue depth/timeout settings, error handling for different API tiers

**Configuration:**

Set `ANTHROPIC_API_KEY` environment variable before using AsyncSDKWrapper:

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

**Rate Limiting:**

The wrapper implements token bucket algorithm matching Anthropic's rate limits:

| Tier | Requests/Min | Tokens/Min |
|------|-------------|------------|
| Free | 5           | 10,000     |
| Tier 1 | 50 (default) | 30,000 (default) |
| Tier 2 | 100         | 100,000    |
| Tier 3+ | 1,000+      | 400,000+   |

Circuit breaker protections:
- Max queue depth: 100 requests
- Queue timeout: 60 seconds
- Raises `QueueTimeoutError` or `QueueDepthExceededError` if exceeded

**Retry Strategy:**

Automatic exponential backoff retry (DEC-029):
- Max retries: 3
- Delays: 1s, 2s, 4s (with ±20% jitter)
- Retries on: 429 (rate limit), 529 (overload), network errors
- No retry on: 4xx client errors (except 429), auth failures
- Respects `retry-after` header when provided

**Memory Capture:**

All messages are automatically captured to the `discussions` collection:
- User messages → `user_message` type
- Agent responses → `agent_response` type
- Background storage (non-blocking)
- Session-based grouping with turn numbers

See `src/memory/async_sdk_wrapper.py` for complete API documentation.

For complete design rationale, see `oversight/specs/tech-debt-035/phase-2-design.md`.

### 👥 Multi-Project Support

Memories are automatically isolated by `group_id` (derived from project directory):

```python
# Project A: group_id = "project-a"
# Project B: group_id = "project-b"
# Searches only return memories from current project
```

**V2.0 Collection Isolation:**
- **code-patterns**: Implementation patterns (per-project isolation)
- **conventions**: Coding standards and rules (shared across projects by default)
- **discussions**: Decisions, sessions, conversations (per-project isolation)

## 🔧 Troubleshooting

### Common Issues

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for comprehensive troubleshooting, including:

- Services won't start
- Health check failures
- Memories not captured
- Search not working
- Performance problems
- Data persistence issues

### Recovery Script

If hooks are misbehaving (e.g., after a failed install or upgrade), use the recovery script to scan and repair all project configurations:

```bash
# Dry-run: shows what would change (safe, no modifications)
python scripts/recover_hook_guards.py

# Apply fixes across all discovered projects
python scripts/recover_hook_guards.py --apply

# Scan only: list all discovered project settings.json files
python scripts/recover_hook_guards.py --scan
```

The recovery script automatically discovers projects via:
1. `~/.ai-memory/installed_projects.json` manifest (primary)
2. Sibling directories of `AI_MEMORY_INSTALL_DIR` (fallback)
3. Common project paths (additional fallback)

It fixes: unguarded hook commands (BUG-066), broad SessionStart matchers (BUG-078), and other known configuration issues. Always run with dry-run first to review changes.

### Quick Diagnostic Commands

```bash
# Check all services
docker compose -f docker/docker-compose.yml ps

# Check logs
docker compose -f docker/docker-compose.yml logs

# Check health
python scripts/health-check.py

# Check ports
lsof -i :26350  # Qdrant
lsof -i :28080  # Embedding
lsof -i :28000  # Monitoring API
```

### Services Won't Start

**Symptom:** `docker compose up -d` fails or services exit immediately

**Solution:**

1. Check port availability:
   ```bash
   lsof -i :26350  # Qdrant
   lsof -i :28080  # Embedding
   ```

2. Check Docker logs:
   ```bash
   docker compose -f docker/docker-compose.yml logs
   ```

3. Ensure Docker daemon is running:
   ```bash
   docker ps  # Should not error
   ```

### Health Check Fails

**Symptom:** `python scripts/health-check.py` shows unhealthy services

**Solution:**

1. Check service status:
   ```bash
   docker compose -f docker/docker-compose.yml ps
   ```

2. Verify ports are accessible:
   ```bash
   curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/health  # Qdrant
   curl http://localhost:28080/health  # Embedding
   ```

3. Check logs for errors:
   ```bash
   docker compose -f docker/docker-compose.yml logs qdrant
   docker compose -f docker/docker-compose.yml logs embedding
   ```

### Memories Not Captured

**Symptom:** PostToolUse hook doesn't store memories

**Solution:**

1. Check hook configuration in `.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PostToolUse": [{
         "matcher": "Write|Edit",
         "hooks": [{"type": "command", "command": ".claude/hooks/scripts/post_tool_capture.py"}]
       }]
     }
   }
   ```

2. Verify hook script is executable:
   ```bash
   ls -la .claude/hooks/scripts/post_tool_capture.py
   chmod +x .claude/hooks/scripts/post_tool_capture.py
   ```

3. Check hook logs (if logging enabled):
   ```bash
   cat ~/.ai-memory/logs/hook.log
   ```

For more detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## 📊 Monitoring

### Grafana Dashboards (V3)

Access Grafana at `http://localhost:23000` (credentials set during installation):

| Dashboard | Purpose |
|-----------|---------|
| **NFR Performance Overview** | All 6 NFR metrics with SLO compliance |
| **Hook Activity** | Hook execution rates, latency heatmaps |
| **Memory Operations** | Captures, retrievals, deduplication |
| **System Health** | Service status, error rates |

### Performance Targets (NFRs)

| NFR | Metric | Target |
|-----|--------|--------|
| NFR-P1 | Hook execution | <500ms |
| NFR-P2 | Batch embedding | <2s |
| NFR-P3 | Session injection | <3s |
| NFR-P4 | Dedup check | <100ms |
| NFR-P5 | Retrieval query | <500ms |
| NFR-P6 | Real-time embedding | <500ms |

### Service Ports

| Service | Port |
|---------|------|
| Grafana | 23000 |
| Prometheus | 29090 |
| Pushgateway | 29091 |

### Key Metrics

All metrics use `aimemory_` prefix (BP-045 compliant):

| Metric | Description |
|--------|-------------|
| `aimemory_hook_duration_seconds` | Hook execution time (NFR-P1) |
| `aimemory_captures_total` | Total memory capture attempts |
| `aimemory_retrievals_total` | Total retrieval operations |
| `aimemory_trigger_fires_total` | Automatic trigger activations |

See [docs/MONITORING.md](docs/MONITORING.md) for complete monitoring guide and [docs/prometheus-queries.md](docs/prometheus-queries.md) for query examples.

## 💾 Backup & Restore

Protect your AI memories with built-in backup and restore scripts.

### Quick Backup

```bash
# Setup (one-time)
cd /path/to/ai-memory
python3 -m venv .venv && source .venv/bin/activate
pip install httpx

# Get your Qdrant API key
cat ~/.ai-memory/docker/.env | grep QDRANT_API_KEY
export QDRANT_API_KEY="your-key-here"

# Run backup
python scripts/backup_qdrant.py
```

Backups are stored in `backups/` directory with timestamped folders containing:

- Collection snapshots (discussions, conventions, code-patterns)
- Configuration files
- Verification manifest

### Quick Restore

```bash
python scripts/restore_qdrant.py backups/2026-02-03_143052
```

See [docs/BACKUP-RESTORE.md](docs/BACKUP-RESTORE.md) for complete instructions including troubleshooting.

> **Coming soon:** Backup and restore scripts will be updated in the next version to support the `jira-data` collection, including Jira database backup and reinstall.

## 📈 Performance

### ⚡ Benchmarks

- **Hook overhead**: <500ms (PostToolUse forks to background)
- **Embedding generation**: <2s (pre-warmed Docker service)
- **SessionStart context injection**: <3s
- **Deduplication check**: <100ms

### Optimization Tips

1. **Enable monitoring profile** for production use:
   ```bash
   docker compose -f docker/docker-compose.yml --profile monitoring up -d
   ```

## 🛠️ Development

### 🧪 Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_storage.py -v

# Run integration tests only
pytest tests/integration/ -v
```

### Project Structure

```
ai-memory/
├── src/memory/          # Core Python modules
├── .claude/
│   ├── hooks/scripts/   # Hook implementations
│   └── skills/          # Skill definitions
├── docker/              # Docker Compose and service configs
├── scripts/             # Installation and management scripts
├── tests/               # pytest test suite
└── docs/                # Additional documentation
```

### Coding Conventions

- **Python (PEP 8 Strict)**: Files `snake_case.py`, Functions `snake_case()`, Classes `PascalCase`, Constants `UPPER_SNAKE`
- **Qdrant Payload Fields**: Always `snake_case` (`content_hash`, `group_id`, `source_hook`)
- **Structured Logging**: Use `logger.info("event", extra={"key": "value"})`, never f-strings
- **Hook Exit Codes**: `0` (success), `1` (non-blocking error), `2` (blocking error - rare)
- **Graceful Degradation**: All components must fail silently - Claude works without memory

See [CONTRIBUTING.md](CONTRIBUTING.md) for complete development setup and coding standards.

## 🤝 Contributing

We welcome contributions! To contribute:

1. **Fork the repository** and create a feature branch
2. **Follow coding conventions** (see Development section above)
3. **Write tests** for all new functionality
4. **Ensure all tests pass**: `pytest tests/`
5. **Update documentation** if adding features
6. **Submit a pull request** with a clear description

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development setup and pull request process.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## Accessibility

This documentation follows WCAG 2.2 Level AA accessibility standards (ISO/IEC 40500:2025):

- ✅ Proper heading hierarchy (h1 → h2 → h3)
- ✅ Descriptive link text (no "click here")
- ✅ Code blocks with language identifiers
- ✅ Tables with headers for screen readers
- ✅ Consistent bullet style (hyphens)
- ✅ ASCII art diagrams for universal compatibility

For accessibility concerns or suggestions, please open an issue.

---

**Documentation Best Practices Applied (2026):**

This README follows current best practices for technical documentation:

- Documentation as Code ([Technical Documentation Best Practices](https://desktopcommander.app/blog/2025/12/08/markdown-best-practices-technical-documentation/))
- Markdown standards with consistent formatting ([Markdown Best Practices](https://www.markdownlang.com/advanced/best-practices.html))
- Essential sections per README standards ([Make a README](https://www.makeareadme.com/))
- Quick value communication ([README Best Practices - Tilburg Science Hub](https://tilburgsciencehub.com/topics/collaborate-share/share-your-work/content-creation/readme-best-practices/))
- WCAG 2.2 accessibility compliance ([W3C WCAG 2.2 as ISO Standard](https://www.w3.org/WAI/news/2025-10-21/wcag22-iso/))
