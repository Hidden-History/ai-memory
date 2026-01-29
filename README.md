# 🧠 AI-Memory

<p align="center">
  <img src="assets/ai-memory-banner.png" alt="AI-Memory Banner" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-green?style=flat-square" alt="Version 2.0.0">
  <a href="https://github.com/Hidden-History/ai-memory/stargazers"><img src="https://img.shields.io/github/stars/Hidden-History/ai-memory?color=blue&style=flat-square" alt="Stars"></a>
  <a href="https://github.com/Hidden-History/ai-memory/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Hidden-History/ai-memory?style=flat-square" alt="License"></a>
  <a href="https://github.com/Hidden-History/ai-memory/issues"><img src="https://img.shields.io/github/issues/Hidden-History/ai-memory?color=red&style=flat-square" alt="Issues"></a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome">
</p>

---

### **Cure AI Amnesia.**
**AI-Memory** is a persistent context layer designed to give your agents institutional memory. By bridging LLMs with a high-performance vector database (Qdrant), this framework ensures your agents remember architectural decisions, project rules, and past interactions across every session.

[**Explore the Docs**](#-usage) | [**Report a Bug**](https://github.com/Hidden-History/ai-memory/issues) | [**Request a Feature**](https://github.com/Hidden-History/ai-memory/issues)

---

## 🚀 Key Features

* **💾 Long-Term Persistence:** Stop re-explaining your codebase. Agents retrieve past context automatically.
* **📂 Structured BMAD Integration:** Purpose-built for BMAD workflows and multi-agent "Party Mode."
* **🔍 Semantic Retrieval:** Uses vector embeddings to find relevant memories based on intent, not just keywords.
* **⚖️ Decision Tracking:** Automatically captures "lessons learned" and integration rules during the dev cycle.

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

## ✨ V2.0 Memory System

- 🗂️ **Three Specialized Collections**: code-patterns (HOW), conventions (WHAT), discussions (WHY)
- 🎯 **15 Memory Types**: Precise categorization for implementation, errors, decisions, and more
- ⚡ **5 Automatic Triggers**: Smart context injection when you need it most
- 🔍 **Intent Detection**: Automatically routes queries to the right collection
- 💬 **Conversation Memory**: Turn-by-turn capture with post-compaction context continuity
- 🔁 **Cascading Search**: Falls back across collections for comprehensive results
- 📊 **Monitoring**: Prometheus metrics + Grafana dashboards
- 🛡️ **Graceful Degradation**: Works even when services are temporarily unavailable
- 👥 **Multi-Project Isolation**: `group_id` filtering keeps projects separate

---

## 🚀 Quick Start

### First-Time Installation (Do This ONCE)

```bash
# 1. Clone the AI-Memory module (one time only!)
git clone https://github.com/Hidden-History/ai-memory.git
cd ai-memory

# 2. Install to your first project
./scripts/install.sh /path/to/your-project
```

### Adding More Projects (From Same Directory)

> **Important:** AI-Memory is installed ONCE. To add more projects, run the installer again from the **same ai-memory directory**.

```bash
# Navigate to your AI-Memory installation (where you cloned it)
cd /path/to/ai-memory

# Add another project to the memory system
./scripts/install.sh /path/to/another-project
```

All projects share the same Docker services but have isolated memory spaces via `group_id`.

See [INSTALL.md](INSTALL.md) for detailed installation guide and multi-project setup.

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

## 🛡️ Complete Your AI Stack: Parzival Oversight Agent

<table>
<tr>
<td width="55%">

**Memory is only half the equation. Quality is the other half.**

AI-Memory gives your agents institutional knowledge. **Parzival** ensures they use it wisely.

> 🎯 **Quality Gatekeeper** — Never ship bugs, always verify before approval
> 🔄 **Review Cycles** — Automated review → fix → verify loops
> 🚫 **Drift Prevention** — Behavioral constraints keep agents on track
> 📋 **Structured Oversight** — Templates for bugs, decisions, specs, tracking
> 📊 **Observability Built-In** — Metrics, logging, Grafana dashboards from day one

**Parzival recommends. You decide.**

</td>
<td width="45%">

| Component | Purpose |
|-----------|---------|
| 🧠 **AI-Memory** | *Remembers* — Context persistence |
| 🛡️ **Parzival** | *Validates* — Quality assurance |
| 🔗 **Together** | Agents that learn AND verify |

<br>

```
Memory + Oversight = Reliable AI
```

**[→ Get Parzival](https://github.com/Hidden-History/pov-oversight-agent)**

</td>
</tr>
</table>

> **Works with [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)** — Enhances BMAD workflows with persistent memory, but works standalone with any Claude Code project.

---

## 🏗️ Architecture

### V2.0 Memory System

```
Claude Code Session
    ├── SessionStart Hook → Context injection after compaction
    ├── UserPromptSubmit Hook → Keyword triggers (decision/best practices)
    ├── PreToolUse Hooks → Smart triggers (new file/first edit)
    ├── PostToolUse Hook → Capture code patterns + error detection
    ├── PreCompact Hook → Save conversation before compaction
    └── Stop Hook → Capture agent responses

Python Core (src/memory/)
    ├── config.py         → Environment configuration
    ├── storage.py        → Qdrant CRUD operations
    ├── search.py         → Semantic search + cascading
    ├── intent.py         → Intent detection + routing
    ├── triggers.py       → Automatic trigger configuration
    ├── embeddings.py     → Jina AI embeddings (768d)
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

### Three-Collection Structure

| Collection | Purpose | Example Types |
|------------|---------|---------------|
| **code-patterns** | HOW things are built | implementation, error_fix, refactor |
| **conventions** | WHAT rules to follow | rule, guideline, naming, structure |
| **discussions** | WHY things were decided | decision, session, preference |

### Automatic Triggers

The memory system automatically retrieves relevant context:

- **Error Detection**: When a command fails, retrieves past error fixes
- **New File Creation**: Retrieves naming conventions and structure patterns
- **First Edit**: Retrieves file-specific patterns on first modification
- **Decision Keywords**: "Why did we..." triggers decision memory retrieval
- **Best Practices**: "How should I..." triggers convention retrieval

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
curl http://localhost:26350/health

# Check Embedding Service (port 28080)
curl http://localhost:28080/health

# Check Grafana (port 23000) - if monitoring enabled
open http://localhost:23000  # admin/admin
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

- **Python 3.10+** (required for async + match statements)
- **Docker 20.10+** (for Qdrant + embedding service)
- **Claude Code** (target project where memory will be installed)

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

### Environment Variables

| Variable               | Default               | Description                       |
|------------------------|----------------------|-----------------------------------|
| `QDRANT_HOST`          | `localhost`          | Qdrant server hostname            |
| `QDRANT_PORT`          | `26350`              | Qdrant external port              |
| `EMBEDDING_HOST`       | `localhost`          | Embedding service hostname        |
| `EMBEDDING_PORT`       | `28080`              | Embedding service port            |
| `AI_MEMORY_INSTALL_DIR`   | `~/.ai-memory`     | Installation directory            |
| `MEMORY_LOG_LEVEL`     | `INFO`               | Logging level (DEBUG/INFO/WARNING)|

**Override Example:**

```bash
export QDRANT_PORT=16333  # Use custom port
export MEMORY_LOG_LEVEL=DEBUG  # Enable verbose logging
```

## 💡 Usage

### 🔧 Automatic Memory Capture

Memory capture happens automatically via Claude Code hooks:

1. **SessionStart**: Loads relevant memories from previous sessions and injects as context
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
```

See [docs/HOOKS.md](docs/HOOKS.md) for hook documentation, [docs/COMMANDS.md](docs/COMMANDS.md) for commands, and [docs/llm-classifier.md](docs/llm-classifier.md) for LLM classifier setup.

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
            model="claude-3-5-sonnet-20241022",
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
    async for chunk in wrapper.send_message_streaming(
        prompt="Explain Python async",
        model="claude-3-5-sonnet-20241022",
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
   curl http://localhost:26350/health  # Qdrant
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

### Grafana Dashboards

Access Grafana at `http://localhost:23000` (admin/admin):

- **Memory Overview**: Captures, retrievals, collection sizes
- **Trigger Performance**: Trigger fires, response times, results
- **Collection Health**: Per-collection metrics, deduplication
- **Embedding Metrics**: Generation times, success rates

### Key Metrics

| Metric | Description |
|--------|-------------|
| `ai_memory_memory_captures_total` | Total memory capture attempts |
| `ai_memory_trigger_fires_total` | Automatic trigger activations |
| `ai_memory_retrieval_duration_seconds` | Search response times |
| `ai_memory_tokens_consumed_total` | Token usage by operation |

See `docs/prometheus-queries.md` for query examples.

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

2. **Adjust batch size** for large projects:
   ```bash
   export MEMORY_BATCH_SIZE=100  # Default: 50
   ```

3. **Increase cache TTL** for stable projects:
   ```bash
   export MEMORY_CACHE_TTL=3600  # Default: 1800 seconds
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

See [CLAUDE.md](CLAUDE.md) for complete coding standards and project conventions.

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
