# AI-Memory

<p align="center">
  <img src="assets/ai-memory-banner.png" alt="AI-Memory Banner" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.5.0-green?style=flat-square" alt="Version 2.5.0">
  <a href="https://github.com/Hidden-History/ai-memory/stargazers"><img src="https://img.shields.io/github/stars/Hidden-History/ai-memory?color=blue&style=flat-square" alt="Stars"></a>
  <a href="https://github.com/Hidden-History/ai-memory/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Hidden-History/ai-memory?style=flat-square" alt="License"></a>
  <a href="https://github.com/Hidden-History/ai-memory/issues"><img src="https://img.shields.io/github/issues/Hidden-History/ai-memory?color=red&style=flat-square" alt="Issues"></a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome">
  <img src="https://img.shields.io/badge/Claude_Code-Supported-6B4FBB?style=flat-square" alt="Claude Code">
  <img src="https://img.shields.io/badge/Gemini_CLI-Supported-4285F4?style=flat-square&logo=google" alt="Gemini CLI">
  <img src="https://img.shields.io/badge/Cursor-Supported-00D4AA?style=flat-square" alt="Cursor">
  <img src="https://img.shields.io/badge/Codex_CLI-Supported-412991?style=flat-square&logo=openai" alt="Codex CLI">
</p>

---

**AI-Memory** is a persistent context layer that gives AI coding agents institutional memory across sessions — storing architectural decisions, code patterns, conventions, and project history in a vector database (Qdrant), and surfacing the right context automatically when you need it.

[**Report a Bug**](https://github.com/Hidden-History/ai-memory/issues) | [**Request a Feature**](https://github.com/Hidden-History/ai-memory/issues) | [**CHANGELOG**](CHANGELOG.md)

---

## Key Features

- **Cross-Session Memory** — Resumes where you left off; no re-explaining past decisions.
- **Multi-IDE Support** — Works with Claude Code, Gemini CLI, Cursor, and Codex CLI via a unified adapter layer.
- **Semantic Decay** — Older memories lose relevance automatically via exponential decay; recent patterns rank higher.
- **3-Layer Security** — PII and secrets screened before storage via regex + detect-secrets + SpaCy NER.
- **GitHub & Jira Integration** — PRs, issues, commits, CI results, and Jira items searchable by meaning.
- **LLM Observability** — Full pipeline tracing via Langfuse (opt-in); every hook span visible with timing and payloads.
- **Progressive Context Injection** — Token-budget-aware delivery: session bootstrap, per-turn injection, confidence-filtered retrieval.

See [docs/TEMPORAL-FEATURES.md](docs/TEMPORAL-FEATURES.md) for temporal decay configuration and freshness settings.

---

## Quick Start

### 1. Start Services

```bash
# Recommended: unified stack manager
./scripts/stack.sh start    # Start all services
./scripts/stack.sh status   # Check health
./scripts/stack.sh stop     # Graceful shutdown
```

### 2. Install to a Project

```bash
./scripts/install.sh /path/to/your-project

# With convention seeding (recommended for new projects)
SEED_BEST_PRACTICES=true ./scripts/install.sh /path/to/your-project
```

### 3. Verify

```bash
python scripts/health-check.py
```

After installation, start a new Claude Code session in your project — AI Memory injects relevant context automatically on session resume.

### Upgrading an existing install

After pulling a new version and re-running `./scripts/install.sh /path/to/your-project`, run `~/.ai-memory/scripts/stack.sh restart` to apply container/image changes. The installer brings services up with `--no-recreate` and won't restart already-running containers, so image and compose updates (for example, the prebuilt embedding image) take effect only after a restart.

---

## Installation

### Prerequisites

- Python 3.10+ (3.11+ required for AsyncSDKWrapper)
- Docker 20.10+
- Claude Code (or another supported IDE)

### Resource Requirements

| Tier | Services | Minimum RAM | Recommended CPU |
|------|----------|-------------|-----------------|
| Core (default) | 8 services | 16 GiB | 4 cores |
| Core + Langfuse (opt-in) | 15 services | 32 GiB | 8 cores |

See [INSTALL.md](INSTALL.md) for step-by-step instructions covering macOS, Linux, and Windows (WSL2), manual installation, configuration options, and uninstallation.
See [docs/MULTI-IDE-SUPPORT.md](docs/MULTI-IDE-SUPPORT.md) for Gemini CLI, Cursor, and Codex CLI adapter setup.

---

## Architecture

```
Claude Code Session
    ├── SessionStart Hooks (resume|compact) → Context injection on session resume
    ├── UserPromptSubmit Hooks  → Per-turn context injection
    ├── PreToolUse Hooks        → New file / first-edit convention retrieval
    ├── PostToolUse Hooks       → Code pattern capture (background, <500ms)
    ├── PreCompact Hook         → Save session summary before compaction
    └── Stop Hook               → Optional per-response capture

Python Core (src/memory/)
    ├── storage.py      → Qdrant CRUD
    ├── search.py       → Semantic search + cascading
    ├── intent.py       → Intent detection + collection routing
    ├── embeddings.py   → Jina AI (jina-v2-base-en prose + jina-v2-base-code)
    └── deduplication.py

Docker Services
    ├── Qdrant (port 26350)
    ├── Embedding Service (port 28080)
    ├── Classifier Worker
    ├── Streamlit Dashboard (port 28501)
    ├── Monitoring Stack (--profile monitoring)
    │   ├── Prometheus (port 29090)
    │   ├── Pushgateway (port 29091)
    │   └── Grafana (port 23000)
    └── Langfuse Stack (--profile langfuse)  — opt-in
        └── Web UI, Worker, PostgreSQL, ClickHouse, Redis, MinIO, Flush Worker
```

### Collections

| Collection | Purpose | Content Types |
|------------|---------|---------------|
| **code-patterns** | HOW things are built | implementation, error_pattern, file_pattern, refactor |
| **conventions** | WHAT rules to follow | rule, guideline, naming, structure |
| **discussions** | WHY things were decided | decision, session, preference, agent_response |
| **github** | WHEN things changed | github_pr, github_issue, github_commit, github_ci_result, github_code_blob |
| **jira-data** | External work items | jira_issue, jira_comment (conditional: `JIRA_SYNC_ENABLED=true`) |

### Automatic Triggers

Memory retrieval fires automatically on:

- **Error Detection** — failed command → retrieves past error fixes
- **New File Creation** — retrieves naming conventions and structure patterns
- **First Edit** — retrieves file-specific patterns
- **Decision Keywords** — "Why did we..." → searches `discussions`
- **Best Practices Keywords** — "How should I..." → searches `conventions`
- **Session History Keywords** — "What have we done..." → searches session summaries

See [docs/HOOKS.md](docs/HOOKS.md) for complete hook documentation and the full trigger keyword reference.
See [docs/AI_MEMORY_ARCHITECTURE.md](docs/AI_MEMORY_ARCHITECTURE.md) for the full system architecture reference.
See [docs/AIM-SOT.md](docs/AIM-SOT.md) for the Source-of-Truth subsystem — registry schema, consult / detect-propose / verify engine, and automatic drift detection hooks.

---

## Parzival: AI Project Manager

Parzival is an AI project manager for Claude Code. He manages the full project lifecycle — planning work, activating parallel agent teams, reviewing output adversarially, and maintaining cross-session continuity. You talk to Parzival; he manages everything else.

**Session commands:**

```bash
/pov:parzival          # Activate. Detects project phase and recommends next steps.
/pov:parzival-start    # Load context from last session and continue.
/pov:parzival-closeout # Save progress, log decisions, create handoff for next session.
```

Parzival is optional but recommended for complex multi-session projects. AI Memory's core features (semantic search, GitHub sync, skills, freshness detection) work independently.

See [Parzival documentation](docs/parzival/README-POV.md) for the full Parzival documentation suite and [docs/DISPATCH-SKILLS.md](docs/DISPATCH-SKILLS.md) for multi-provider dispatch setup.

---

## Configuration

All configuration is via environment variables in `docker/.env`. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference.

**Service ports** (all use `2XXXX` prefix to avoid conflicts):

| Service | Port |
|---------|------|
| Qdrant | 26350 |
| Embedding Service | 28080 |
| Monitoring API | 28000 |
| Streamlit Dashboard | 28501 |
| Grafana | 23000 |
| Prometheus | 29090 (--profile monitoring) |
| Langfuse Web UI | 23100 (--profile langfuse) |

**Key variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `localhost` | Qdrant hostname |
| `QDRANT_PORT` | `26350` | Qdrant port |
| `AI_MEMORY_INSTALL_DIR` | `~/.ai-memory` | Installation directory |
| `AI_MEMORY_LOG_LEVEL` | `INFO` | Logging level |
| `JIRA_SYNC_ENABLED` | `false` | Enable Jira integration |
| `LANGFUSE_ENABLED` | `false` | Enable LLM observability |

---

## Usage

### Automatic Memory Capture

Memory capture runs via hooks — no manual steps required:

1. **SessionStart** (resume/compact): Injects relevant memories automatically
2. **PostToolUse**: Captures code patterns on Write/Edit (background, <500ms)
3. **PreCompact**: Saves session summary before compaction
4. **Stop**: Optional per-response capture

### Slash Commands

```bash
/aim-status            # System status and health
/aim-save              # Manually save current session
/aim-search <query>    # Semantic search across all memories
/aim-github-sync       # Sync GitHub repository history
/aim-github-search     # Semantic search of GitHub data
/aim-jira-sync         # Sync Jira issues and comments
/aim-jira-search       # Semantic search of Jira content
/aim-purge             # Purge old memories (dry-run by default)
/aim-refresh           # Trigger freshness scan on changed files
/aim-pause-updates     # Toggle automatic memory capture on/off
/aim-freshness-report  # Report stale code-pattern memories
```

See [docs/COMMANDS.md](docs/COMMANDS.md) for the full commands reference.

### Integrations

- **GitHub**: Full repository history (PRs, issues, commits, CI results, code blobs) ingested into the `github` collection. See [docs/GITHUB-INTEGRATION.md](docs/GITHUB-INTEGRATION.md).
- **Jira Cloud**: Issues and comments ingested into the `jira-data` collection. See [docs/JIRA-INTEGRATION.md](docs/JIRA-INTEGRATION.md).
- **Langfuse** (opt-in): LLM observability with 9-step pipeline tracing. See [docs/LANGFUSE-INTEGRATION.md](docs/LANGFUSE-INTEGRATION.md).
- **LLM Classifier** (opt-in): Reclassifies captured memories using a local or cloud LLM. See [docs/llm-classifier.md](docs/llm-classifier.md).
- **AsyncSDKWrapper**: Async/await Agent SDK integration with rate limiting and automatic memory capture. See [docs/ASYNC-SDK.md](docs/ASYNC-SDK.md).

### Multi-Project Support

Memories are isolated by `group_id` (derived from project directory). Searches return only memories from the current project. See [docs/multi-project.md](docs/multi-project.md).

---

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues (services won't start, memories not captured, search not working).

For hook recovery after a failed install or upgrade:

```bash
# Dry-run (safe, no modifications)
python scripts/recover_hook_guards.py

# Apply fixes
python scripts/recover_hook_guards.py --apply
```

See [docs/RECOVERY.md](docs/RECOVERY.md) for the complete recovery guide.
See [docs/BACKUP-RESTORE.md](docs/BACKUP-RESTORE.md) for collection backup and restore procedures.

---

## Development

### Running Tests

```bash
pytest tests/
pytest tests/test_storage.py -v     # specific file
pytest tests/integration/ -v        # integration only
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
└── docs/                # Reference documentation
```

### Coding Conventions

- **Python**: PEP 8 strict — `snake_case` files/functions, `PascalCase` classes, `UPPER_SNAKE` constants
- **Qdrant Payload Fields**: Always `snake_case` (`content_hash`, `group_id`, `source_hook`)
- **Structured Logging**: `logger.info("event", extra={"key": "value"})` — no f-strings in log calls
- **Hook Exit Codes**: `0` success, `1` non-blocking error, `2` blocking error
- **Graceful Degradation**: All components must fail silently — Claude works without memory

See [CONTRIBUTING.md](CONTRIBUTING.md) for complete development setup and pull request process.

---

## Contributing

1. Fork the repository and create a feature branch
2. Follow the coding conventions above
3. Write tests for all new functionality
4. Ensure all tests pass: `pytest tests/`
5. Update documentation if adding features
6. Submit a pull request with a clear description

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Accessibility

This documentation follows WCAG 2.2 Level AA accessibility standards:

- Proper heading hierarchy (h1 → h2 → h3)
- Descriptive link text
- Code blocks with language identifiers
- Tables with headers for screen readers
- Consistent bullet style

For accessibility concerns, please open an issue.
