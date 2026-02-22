# ⚙️ Configuration Reference

> Complete guide to all configuration options and environment variables

## 📋 Table of Contents

- [Overview](#overview)
- [Configuration Files](#configuration-files)
- [Environment Variables](#environment-variables)
  - [Core Settings](#core-settings)
  - [Qdrant Configuration](#qdrant-configuration)
  - [Embedding Configuration](#embedding-configuration)
  - [Search & Retrieval](#search--retrieval)
  - [Performance Tuning](#performance-tuning)
  - [Logging & Monitoring](#logging--monitoring)
- [Temporal Configuration](#temporal-configuration)
  - [Decay & Freshness](#decay--freshness)
  - [GitHub Sync](#github-sync)
- [Feature Configuration](#feature-configuration)
  - [Parzival Session Agent](#parzival-session-agent)
  - [Security Scanning](#security-scanning)
  - [Context Injection](#context-injection)
- [Docker Configuration](#docker-configuration)
- [Hook Configuration](#hook-configuration)
- [Agent-Specific Configuration](#agent-specific-configuration)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

AI Memory Module configuration uses a layered approach:

1. **Default values** (hardcoded in `src/memory/config.py`)
2. **Environment variables** (`.env` file override)
3. **Runtime overrides** (programmatic via Python API)

```
Defaults → Environment Variables → Runtime Overrides
(lowest priority)                    (highest priority)
```

### Configuration Locations

| File/Location | Purpose | Tracked in Git |
|---------------|---------|----------------|
| `~/.ai-memory/.env` | User environment variables | ❌ No (gitignored) |
| `.claude/settings.json` | Hook configuration | ✅ Yes (project-specific) |
| `docker/docker-compose.yml` | Docker service config | ✅ Yes |
| `docker/.env` | Docker environment overrides | ❌ No (gitignored) |
| `src/memory/config.py` | Default values | ✅ Yes |

---

## 📁 Configuration Files

### ~/.ai-memory/.env

**Purpose:** User-level environment variables (highest priority)

**Location:** `~/.ai-memory/.env`

**Format:**
```bash
# Core Settings
QDRANT_HOST=localhost
QDRANT_PORT=26350
LOG_LEVEL=INFO

# Performance
MAX_RETRIEVALS=10
SIMILARITY_THRESHOLD=0.7
```

**When to use:**
- Override defaults without modifying code
- Per-user customization
- Testing different configurations

### docker/.env

**Purpose:** Docker Compose environment overrides

**Location:** `docker/.env` (in module directory)

**Format:**
```bash
# Port overrides
QDRANT_EXTERNAL_PORT=26350
EMBEDDING_EXTERNAL_PORT=28080

# Resource limits
QDRANT_MEMORY_LIMIT=2g
EMBEDDING_MEMORY_LIMIT=1g
```

### .claude/settings.json

**Purpose:** Claude Code hook configuration

**Location:** `$PROJECT/.claude/settings.json` (target project)

**Format:** See [Hook Configuration](#hook-configuration) section

---

## 🌍 Environment Variables

### Core Settings

#### AI_MEMORY_INSTALL_DIR
**Purpose:** Installation directory for AI Memory Module

**Default:** `~/.ai-memory`

**Format:** Absolute path

**Example:**
```bash
export AI_MEMORY_INSTALL_DIR=/opt/ai-memory
```

**When to change:**
- Custom installation location
- Multi-user systems
- Containerized environments

---

#### AI_MEMORY_PROJECT_ID
**Purpose:** Project identifier for memory isolation (group_id in Qdrant)

**Default:** Directory name of the project

**Format:** String (alphanumeric, hyphens, underscores)

**Example:**
```bash
# Set in .claude/settings.json env section
export AI_MEMORY_PROJECT_ID=my-awesome-project

# Or via installer CLI
./install.sh ~/projects/my-app my-awesome-project
```

**When to change:**
- **Multi-project setups**: Each project needs a unique identifier
- **Custom naming**: Use descriptive names instead of directory names
- **Migration**: When moving projects between directories

**Behavior:**
- All memories stored with this `group_id` in Qdrant
- SessionStart retrieves only memories matching this project
- Prevents cross-project memory pollution

**Set Automatically By:**
- Installer prompts for project name during installation
- Defaults to directory name if not provided
- Stored in project's `.claude/settings.json`

**Example Configuration** (`.claude/settings.json`):
```json
{
  "hooks": { ... },
  "env": {
    "AI_MEMORY_PROJECT_ID": "my-awesome-project",
    "AI_MEMORY_INSTALL_DIR": "/home/user/.ai-memory"
  }
}
```

**Related:**
- `group_id` payload field - Record-level isolation

---

#### LOG_LEVEL
**Purpose:** Logging verbosity

**Default:** `INFO`

**Options:**
- `DEBUG` - Verbose logging (all operations)
- `INFO` - Standard logging (important events)
- `WARNING` - Warnings and errors only
- `ERROR` - Errors only
- `CRITICAL` - Critical errors only

**Example:**
```bash
export LOG_LEVEL=DEBUG
```

**When to change:**
- **DEBUG**: Troubleshooting hooks or searching for bugs
- **WARNING**: Production environments (reduce log noise)

**Impact:**
- Disk usage (DEBUG generates 10x more logs)
- Performance (minimal, <10ms overhead)

---

### Qdrant Configuration

#### QDRANT_HOST
**Purpose:** Qdrant vector database hostname

**Default:** `localhost`

**Format:** Hostname or IP address

**Example:**
```bash
# Local development (default)
export QDRANT_HOST=localhost

# Remote Qdrant Cloud
export QDRANT_HOST=xyz.qdrant.io

# Docker network
export QDRANT_HOST=ai-memory-qdrant
```

**Related:**
- `QDRANT_PORT` - Qdrant server port
- `QDRANT_API_KEY` - For Qdrant Cloud authentication
- `QDRANT_USE_HTTPS` - Enable HTTPS for connections

---

#### QDRANT_PORT
**Purpose:** Qdrant vector database port

**Default:** `26350`

**Format:** Integer (port number)

**Example:**
```bash
# Default
export QDRANT_PORT=26350

# Custom port
export QDRANT_PORT=16333
```

**When to change:**
- **Custom port**: Avoid conflicts with other services
- **Remote Qdrant**: Using Qdrant Cloud or shared instance

---

#### QDRANT_API_KEY
**Purpose:** Authentication for Qdrant Cloud or secured instances

**Default:** `None` (no authentication)

**Format:** String token

**Example:**
```bash
export QDRANT_API_KEY=your-api-key-here
```

**When to use:**
- Qdrant Cloud deployment
- Production with authentication enabled
- Shared Qdrant instance

**Security:**
⚠️ **Never commit API keys to git!**
- Use `~/.ai-memory/.env` (gitignored)
- Use environment variables
- Use secrets management (Vault, AWS Secrets Manager)

---

#### QDRANT_USE_HTTPS
**Purpose:** Use HTTPS instead of HTTP for Qdrant connections

**Default:** `false`

**Options:** `true`, `false`

**Format:** Boolean (`true`/`false`)

**Example:**
```bash
# Required for Qdrant Cloud or secured remote instances
export QDRANT_USE_HTTPS=true

# Local development (default — Docker services use plain HTTP)
export QDRANT_USE_HTTPS=false
```

**When to change:**
- **Qdrant Cloud**: Always set to `true` (Qdrant Cloud requires HTTPS)
- **Remote production**: Enable when connecting to a secured Qdrant instance with TLS
- **Local development**: Leave `false` (local Docker services use plain HTTP)

**Related:**
- `QDRANT_HOST` - Qdrant server hostname
- `QDRANT_API_KEY` - Authentication key

---

### Embedding Configuration

#### EMBEDDING_HOST
**Purpose:** Embedding service hostname

**Default:** `localhost`

**Format:** Hostname or IP address

**Example:**
```bash
# Local development (default)
export EMBEDDING_HOST=localhost

# Docker network
export EMBEDDING_HOST=ai-memory-embedding
```

**Related:**
- `EMBEDDING_PORT` - Embedding service port

---

#### EMBEDDING_PORT
**Purpose:** Embedding service port

**Default:** `28080`

**Format:** Integer (port number)

**Example:**
```bash
# Default
export EMBEDDING_PORT=28080

# Custom port
export EMBEDDING_PORT=18080
```

**When to change:**
- **Custom port**: Avoid conflicts with other services

---

#### EMBEDDING_MODEL_DENSE_EN
**Purpose:** Prose embedding model identifier (used for non-code content)

**Default:** `jinaai/jina-embeddings-v2-base-en` (768 dimensions)

**Example:**
```bash
export EMBEDDING_MODEL_DENSE_EN=jinaai/jina-embeddings-v2-base-en
```

**When to change:**
- Upgrading to a new Jina embedding model release

⚠️ **Warning:** Changing models invalidates existing embeddings. You must:
1. Stop services
2. Delete Qdrant collections
3. Recapture memories with new model

---

#### EMBEDDING_MODEL_DENSE_CODE
**Purpose:** Code embedding model identifier (used for code content)

**Default:** `jinaai/jina-embeddings-v2-base-code` (768 dimensions)

**Example:**
```bash
export EMBEDDING_MODEL_DENSE_CODE=jinaai/jina-embeddings-v2-base-code
```

**When to change:**
- Upgrading to a new Jina code embedding model release

---

### Search & Retrieval

#### MAX_RETRIEVALS
**Purpose:** Maximum memories to retrieve in search/SessionStart

**Default:** `5`

**Format:** Integer (1-50)

**Example:**
```bash
# Conservative (faster, less context)
export MAX_RETRIEVALS=3

# Default
export MAX_RETRIEVALS=5

# Comprehensive (slower, more context)
export MAX_RETRIEVALS=10

# Maximum
export MAX_RETRIEVALS=50
```

**When to change:**
- **Performance**: Lower for faster SessionStart (<2s)
- **Context richness**: Higher for more comprehensive memory recall
- **Token budget**: Adjust based on Claude context limits

**Impact:**
- **SessionStart duration**: ~0.1s per memory retrieved
- **Context tokens**: ~200-400 tokens per memory

---

#### SIMILARITY_THRESHOLD
**Purpose:** Minimum similarity score for search results (0-1)

**Default:** `0.7` (70%)

**Format:** Float (0.0 to 1.0)

**Example:**
```bash
# Strict (only high relevance)
export SIMILARITY_THRESHOLD=0.8

# Default (medium relevance)
export SIMILARITY_THRESHOLD=0.7

# Permissive (include low relevance)
export SIMILARITY_THRESHOLD=0.3
```

**When to change:**
- **Precision**: Increase to get only highly relevant results
- **Recall**: Decrease to get more results (even if less relevant)
- **Testing**: Lower to verify memories exist

**Score Interpretation:**
- **0.9-1.0**: Near-exact match
- **0.7-0.9**: Highly relevant
- **0.5-0.7**: Moderately relevant
- **0.3-0.5**: Loosely related
- **0.0-0.3**: Barely related (usually filtered)

---

### Logging & Monitoring

#### MONITORING_PORT
**Purpose:** Monitoring API port (health checks and metrics endpoint)

**Default:** `28000`

**Format:** Integer (port number)

**Example:**
```bash
export MONITORING_PORT=28000
```

**When to change:**
- Port conflicts with other services
- Custom monitoring setup

**Access:** `http://localhost:28000/metrics`

---

#### LOG_FORMAT
**Purpose:** Log output format

**Default:** `json`

**Options:** `json`, `text`

**Example:**
```bash
# Structured logging (JSON) — default, recommended for production
export LOG_FORMAT=json

# Human-readable logging
export LOG_FORMAT=text
```

**When to change:**
- **Production**: Keep `json` for log aggregation (ELK, Splunk)
- **Development**: Use `text` for human readability

**Output Example:**

```json
// Structured (LOG_FORMAT=json)
{"timestamp": "2026-01-17T10:30:00Z", "level": "INFO", "event": "memory_stored", "memory_id": "abc123", "type": "implementation"}

// Human-readable (LOG_FORMAT=text)
2026-01-17 10:30:00 INFO memory_stored memory_id=abc123 type=implementation
```

---

## ⏱️ Temporal Configuration

### Decay & Freshness

Controls how memories are scored and ranked over time using a combined semantic + temporal decay model.

**Scoring formula:**
```
final_score = DECAY_SEMANTIC_WEIGHT * semantic + (1 - DECAY_SEMANTIC_WEIGHT) * temporal
temporal    = 0.5 ^ (age_days / half_life_days)
```

The temporal weight is implicitly `1 - DECAY_SEMANTIC_WEIGHT`. At the half-life age, the temporal component is exactly 0.5, meaning memories age naturally without disappearing.

---

#### DECAY_SEMANTIC_WEIGHT
**Purpose:** Semantic score weight in the final decay-ranked retrieval score

**Default:** `0.7`

**Format:** Float (0.0 to 1.0)

**Example:**
```bash
# Default (semantic-heavy — relevance matters more than recency)
export DECAY_SEMANTIC_WEIGHT=0.7

# Balanced
export DECAY_SEMANTIC_WEIGHT=0.5

# Recency-heavy (temporal matters more)
export DECAY_SEMANTIC_WEIGHT=0.3
```

**When to change:**
- **Relevance-first**: Keep at 0.7 (default) when correctness matters more than freshness
- **Recency-first**: Lower (0.3–0.5) for fast-moving projects where stale patterns are harmful
- The temporal weight is automatically computed as `1 - DECAY_SEMANTIC_WEIGHT`

---

#### DECAY_HALF_LIFE_CODE_PATTERNS
**Purpose:** Half-life in days for memories in the `code-patterns` collection

**Default:** `14`

**Format:** Integer (days)

**Example:**
```bash
# Default (14 days)
export DECAY_HALF_LIFE_CODE_PATTERNS=14

# Slow decay (stable library/framework)
export DECAY_HALF_LIFE_CODE_PATTERNS=30

# Very slow decay
export DECAY_HALF_LIFE_CODE_PATTERNS=90
```

**When to change:**
- **Lower**: Projects with frequent refactors where old patterns quickly become outdated
- **Higher**: Mature codebases with stable conventions that evolve slowly

---

#### DECAY_HALF_LIFE_DISCUSSIONS
**Purpose:** Half-life in days for memories in the `discussions` collection

**Default:** `21`

**Format:** Integer (days)

**Example:**
```bash
export DECAY_HALF_LIFE_DISCUSSIONS=21
```

**When to change:**
- **Lower**: High-velocity teams where decisions are revisited frequently
- **Higher**: Slow-moving projects where architectural discussions remain relevant for months

---

#### DECAY_HALF_LIFE_CONVENTIONS
**Purpose:** Half-life in days for memories in the `conventions` collection

**Default:** `60`

**Format:** Integer (days)

**Example:**
```bash
# Default (60 days — conventions change slowly)
export DECAY_HALF_LIFE_CONVENTIONS=60

# Fast-evolving style guide
export DECAY_HALF_LIFE_CONVENTIONS=30
```

**When to change:**
- Conventions typically evolve more slowly than implementation patterns — the higher default reflects this
- **Lower**: Teams that actively revise coding standards sprint-over-sprint

---

#### DECAY_TYPE_OVERRIDES
**Purpose:** Per memory-type half-life overrides, applied on top of collection defaults

**Default:** `"github_ci_result:7,agent_task:14,github_code_blob:14,github_commit:14,github_issue:30,github_pr:30,jira_issue:30,agent_memory:30,guideline:60,rule:60,agent_handoff:180,agent_insight:180"` (12 type:days pairs)

**Format:** Comma-separated `type:days` pairs

**Example:**
```bash
# Override specific memory types (REPLACES all built-in defaults)
export DECAY_TYPE_OVERRIDES="github_ci_result:7,agent_task:14,guideline:60"
```

**When to change:**
- When certain memory types should have different half-lives than the built-in defaults
- When adding custom memory types that need specific decay rates

**Type override precedence:** `DECAY_TYPE_OVERRIDES` > collection-level half-life defaults

> **Warning:** Setting this env var **replaces** all built-in type overrides, it does not append. If you set `DECAY_TYPE_OVERRIDES=agent_task:14`, only `agent_task` will have a type override — all other types fall back to their collection defaults.

---

#### FRESHNESS_ENABLED
**Purpose:** Enable freshness detection for code-patterns memories using commit-count thresholds

**Default:** `true`

**Options:** `true`, `false`

**Example:**
```bash
# Enable (default) — commit-count freshness tiers used during /freshness-report
export FRESHNESS_ENABLED=true

# Disable — skip freshness checks (faster scans, no git dependency)
export FRESHNESS_ENABLED=false
```

**When to change:**
- **Disable**: Environments without git access (CI containers, non-git directories)
- **Disable**: When freshness scans are too slow and git history lookups are the bottleneck

**Impact:**
- When disabled, freshness scoring relies solely on timestamp-based decay; commit-count tier classification is skipped

---

### GitHub Sync

Controls synchronisation of GitHub issues, pull requests, and CI results into the AI Memory collections.

---

#### GITHUB_SYNC_ENABLED
**Purpose:** Enable the GitHub sync background service

**Default:** `false`

**Options:** `true`, `false`

**Example:**
```bash
export GITHUB_SYNC_ENABLED=true
```

**When to change:**
- Set to `true` when you want GitHub issues, PRs, and CI results automatically indexed as memories
- Requires `GITHUB_TOKEN` and `GITHUB_REPO` to be set

---

#### GITHUB_TOKEN
**Purpose:** GitHub Personal Access Token (fine-grained) for API authentication

**Default:** `""` (no token — sync disabled)

**Format:** String (GitHub PAT)

**Required scopes:** `repo:read`, `issues:read`, `pull_requests:read`

**Example:**
```bash
export GITHUB_TOKEN=github_pat_xxxxxxxxxxxxxxxxxxxx
```

**When to use:**
- Required when `GITHUB_SYNC_ENABLED=true`
- Use fine-grained tokens scoped to the specific repository for least privilege

**Security:**
⚠️ **Never commit tokens to git!**
- Use `~/.ai-memory/.env` (gitignored)
- Use your OS keychain or secrets manager
- Rotate tokens regularly and set expiry dates in GitHub settings

---

#### GITHUB_REPO
**Purpose:** GitHub repository to sync, in `owner/name` format

**Default:** `""` (no repository)

**Format:** `owner/repo` string

**Example:**
```bash
# Public or private repository
export GITHUB_REPO=Hidden-History/ai-memory

# Personal project
export GITHUB_REPO=myusername/my-project
```

**When to change:**
- Set to your project's repository when enabling GitHub sync
- Each project's `.env` should specify its own repository

---

#### GITHUB_SYNC_INTERVAL
**Purpose:** How often (in seconds) the GitHub sync service polls for new data

**Default:** `1800` (30 minutes)

**Format:** Integer (seconds); set to `0` to disable automatic sync

**Example:**
```bash
# Default (30 minutes)
export GITHUB_SYNC_INTERVAL=1800

# Hourly
export GITHUB_SYNC_INTERVAL=3600

# Disable automatic sync (manual only via /github-sync skill)
export GITHUB_SYNC_INTERVAL=0
```

**When to change:**
- **Lower**: High-velocity projects where you want PR/issue context refreshed more often
- **Higher**: Cost-sensitive setups or low-activity repositories
- **0**: When you prefer on-demand sync via the `/github-sync` skill

---

#### GITHUB_CODE_BLOB_ENABLED
**Purpose:** Enable code blob synchronisation — fetches source files from the repository and stores them as memories in the `code-patterns` collection (separate from PR/issue/commit sync)

**Default:** `true` (when `GITHUB_SYNC_ENABLED=true`)

**Options:** `true`, `false`

**Format:** Boolean (`true`/`false`)

**Example:**
```bash
# Enable code blob sync (default)
export GITHUB_CODE_BLOB_ENABLED=true

# Disable — only sync PRs, issues, and commits; skip source files
export GITHUB_CODE_BLOB_ENABLED=false
```

**When to change:**
- **Disable**: To reduce GitHub API calls and storage when code context is not needed
- **Disable**: For repositories with very large codebases where blob sync is slow
- **Enable**: When you want Claude to have access to current source file content as memories

**Related:**
- `GITHUB_SYNC_ENABLED` — master switch for all GitHub sync
- `GITHUB_SYNC_INTERVAL` — polling frequency

---

## 🤖 Feature Configuration

### Parzival Session Agent

Controls the Parzival session continuity agent, which manages handoffs between sessions, project oversight, and PM-style tracking.

---

#### PARZIVAL_ENABLED
**Purpose:** Enable the Parzival session agent and session continuity features

**Default:** `false`

**Options:** `true`, `false`

**Example:**
```bash
export PARZIVAL_ENABLED=true
```

**When to change:**
- Set to `true` to enable session-to-session continuity, handoff documents, and oversight tracking
- Requires the oversight folder to be present (see `PARZIVAL_OVERSIGHT_FOLDER`)

---

#### PARZIVAL_USER_NAME
**Purpose:** Display name used by Parzival when addressing the user in handoffs and status reports

**Default:** `"Developer"`

**Format:** String

**Example:**
```bash
export PARZIVAL_USER_NAME="Alice"
export PARZIVAL_USER_NAME="Team Lead"
```

**When to change:**
- Personalise Parzival's communications to use your name or role

---

#### PARZIVAL_LANGUAGE
**Purpose:** Language Parzival uses for all interactions and spoken output

**Default:** `"English"`

**Format:** Language name string

**Example:**
```bash
export PARZIVAL_LANGUAGE="English"
export PARZIVAL_LANGUAGE="French"
```

**When to change:**
- Set to your preferred language for Parzival's verbal communication during sessions

---

#### PARZIVAL_DOC_LANGUAGE
**Purpose:** Language used in generated documents (handoffs, status reports, oversight files)

**Default:** `"English"`

**Format:** Language name string

**Example:**
```bash
export PARZIVAL_DOC_LANGUAGE="English"
export PARZIVAL_DOC_LANGUAGE="German"
```

**When to change:**
- When documentation must be in a different language than verbal interactions (e.g., English communication, German docs)

---

#### PARZIVAL_OVERSIGHT_FOLDER
**Purpose:** Relative path from the project root to the oversight directory used by Parzival

**Default:** `"oversight"`

**Format:** Relative path string

**Example:**
```bash
# Default
export PARZIVAL_OVERSIGHT_FOLDER=oversight

# Custom location
export PARZIVAL_OVERSIGHT_FOLDER=docs/oversight
export PARZIVAL_OVERSIGHT_FOLDER=.parzival
```

**When to change:**
- When your project uses a non-standard directory layout
- When oversight files should be co-located with other documentation

---

#### PARZIVAL_HANDOFF_RETENTION
**Purpose:** Maximum number of handoff files loaded at session start (older handoffs are not deleted, just skipped)

**Default:** `10`

**Format:** Integer (count)

**Example:**
```bash
# Default (last 10 handoffs loaded at startup)
export PARZIVAL_HANDOFF_RETENTION=10

# Minimal (last 3 handoffs)
export PARZIVAL_HANDOFF_RETENTION=3

# Extended (last 20 handoffs)
export PARZIVAL_HANDOFF_RETENTION=20
```

**When to change:**
- **Lower**: Reduce SessionStart token usage when handoff history is long
- **Higher**: Long-running projects where deeper history is needed for continuity

**Note:** Older handoffs beyond the retention count are **not deleted** — they remain in the oversight folder and can be read manually.

---

### Security Scanning

Controls the 3-layer content security scanning pipeline applied before any content is stored in memory.

**Pipeline layers:**
1. **Layer 1 — Regex patterns**: Fast detection of common secret patterns (API keys, tokens, connection strings)
2. **Layer 2 — detect-secrets**: Baseline-aware secret scanning
3. **Layer 3 — SpaCy NER**: Named entity recognition for PII and sensitive data classification

---

#### SECURITY_SCANNING_ENABLED
**Purpose:** Enable the full 3-layer security scanning pipeline for all incoming content

**Default:** `true`

**Options:** `true`, `false`

**Example:**
```bash
# Enable (default — recommended for all environments)
export SECURITY_SCANNING_ENABLED=true

# Disable (testing only — never in production)
export SECURITY_SCANNING_ENABLED=false
```

**When to change:**
- **Disable only for local testing** where you are deliberately storing test content that would otherwise be flagged
- ⚠️ Never disable in production or shared environments

---

#### SECURITY_SCANNING_NER_ENABLED
**Purpose:** Enable Layer 3 SpaCy NER scanning (can be disabled independently if SpaCy is not installed)

**Default:** `true`

**Options:** `true`, `false`

**Example:**
```bash
# Enable NER (default)
export SECURITY_SCANNING_NER_ENABLED=true

# Disable NER (SpaCy not installed or performance concerns)
export SECURITY_SCANNING_NER_ENABLED=false
```

**When to change:**
- **Disable**: SpaCy is not installed in the environment
- **Disable**: NER scanning adds unacceptable latency in high-throughput hooks
- Layers 1 and 2 remain active even when NER is disabled

---

#### SECURITY_BLOCK_ON_SECRETS
**Purpose:** When secrets are detected, block content from being stored (rather than warn-only)

**Default:** `true`

**Options:** `true`, `false`

**Example:**
```bash
# Block mode (default — secrets prevent storage)
export SECURITY_BLOCK_ON_SECRETS=true

# Warn-only mode (secrets logged but content stored anyway)
export SECURITY_BLOCK_ON_SECRETS=false
```

**When to change:**
- **Warn-only mode**: Only during debugging of false-positive detection rules
- ⚠️ Never set to `false` in production — secrets stored in vector databases are difficult to audit and purge

---

#### SECURITY_SCAN_SESSION_MODE
**Purpose:** Controls scanning intensity for session content (user prompts, agent responses captured by hooks)

**Default:** `"relaxed"`

**Options:**
- `relaxed` — Layer 1 regex patterns only (catches real secrets like API keys, tokens). Layer 2 detect-secrets entropy scanning is skipped for session content. This is the recommended default because session discussions about API keys/tokens would otherwise be false-positive blocked.
- `strict` — Full Layer 1 + Layer 2 scanning for session content (same as non-session content). May cause false positives when discussing security topics.
- `off` — No security scanning for session content. Not recommended.

**When to change:**
- Keep `relaxed` (default) for most workflows
- Use `strict` only if your sessions never discuss API keys, tokens, or security configuration
- Use `off` only for testing

**Example:**
```bash
export SECURITY_SCAN_SESSION_MODE=relaxed
```

**Background:** Added in v2.0.6 to fix BUG-110, where session content discussing API keys was being blocked by Layer 2 entropy scanning, preventing any session data from being stored.

---

### `AUTO_UPDATE_ENABLED`

Controls whether the memory system automatically updates stale memories when changes are detected.

| Property | Value |
|----------|-------|
| **Type** | Boolean |
| **Default** | `true` |
| **Required** | No |
| **Tier** | 2 (Has default, user can override) |

**Usage:**
- Set to `false` to pause all automatic memory updates (kill switch)
- Can be toggled via the `/pause-updates` skill
- When disabled, manual operations (`/github-sync`, `/memory-refresh`) still work
- Status visible in `/memory-status` output

**Example:**
```env
AUTO_UPDATE_ENABLED=true    # Default: automatic updates active
AUTO_UPDATE_ENABLED=false   # Pause all automatic updates
```

---

### Context Injection

Controls the two-tier token budget system for injecting memories into Claude's context.

**Tier overview:**
- **Tier 1 (Bootstrap):** Runs at session start — injects high-priority context: conventions, architectural decisions, Parzival handoffs
- **Tier 2 (Dynamic):** Runs per-turn — injects decay-ranked memories relevant to the current tool use or query

Budgets are measured in **tokens** (approximately 4 characters per token).

---

#### INJECTION_ENABLED
**Purpose:** Master switch for the progressive context injection system (both Tier 1 bootstrap and Tier 2 per-turn)

**Default:** `true`

**Options:** `true`, `false`

**Format:** Boolean (`true`/`false`)

**Example:**
```bash
# Enable (default)
export INJECTION_ENABLED=true

# Disable — no memories injected into Claude's context
export INJECTION_ENABLED=false
```

**When to change:**
- **Disable**: When testing or debugging and you want to verify Claude's response without memory context
- **Disable**: In minimal setups where context injection overhead is not desired
- Disabling overrides all other injection settings (budget, confidence threshold, etc.)

---

#### BOOTSTRAP_TOKEN_BUDGET
**Purpose:** Token budget for Tier 1 bootstrap context injection at session start

**Default:** `2500`

**Format:** Integer (tokens, range 500–5000)

**Example:**
```bash
# Default
export BOOTSTRAP_TOKEN_BUDGET=2500

# Reduced (faster SessionStart, less bootstrap context)
export BOOTSTRAP_TOKEN_BUDGET=1500

# Expanded (richer session bootstrap)
export BOOTSTRAP_TOKEN_BUDGET=5000
```

**When to change:**
- **Lower**: When SessionStart is slow and you want to reduce initial context load
- **Higher**: On projects with many critical conventions and decisions that must all be visible at session start
- **Impact**: ~200–400 tokens per memory injected; budget controls how many fit

---

#### INJECTION_CONFIDENCE_THRESHOLD
**Purpose:** Minimum retrieval confidence score for Tier 2 per-turn injection — if the best match is below this threshold, injection is skipped entirely for that turn

**Default:** `0.6`

**Format:** Float (0.0 to 1.0)

**Example:**
```bash
# Default (skip injection when best match is below 60% confidence)
export INJECTION_CONFIDENCE_THRESHOLD=0.6

# Strict (only inject when highly confident)
export INJECTION_CONFIDENCE_THRESHOLD=0.8

# Permissive (always attempt injection)
export INJECTION_CONFIDENCE_THRESHOLD=0.3
```

**When to change:**
- **Raise**: Reduce irrelevant per-turn injections (fewer but higher-quality injections)
- **Lower**: Ensure more injection attempts, even for loosely related queries
- **Impact**: Directly controls whether Tier 2 fires per turn; Tier 1 bootstrap is unaffected

---

#### INJECTION_BUDGET_FLOOR
**Purpose:** Minimum token budget for Tier 2 per-turn dynamic context injection

**Default:** `500`

**Format:** Integer (tokens, range 100–2000)

**Example:**
```bash
# Default
export INJECTION_BUDGET_FLOOR=500

# Lower minimum (minimal per-turn overhead)
export INJECTION_BUDGET_FLOOR=200
```

**When to change:**
- **Lower**: Reduce minimum per-turn context when memory overhead is a concern
- Must be ≤ `INJECTION_BUDGET_CEILING` (validated at startup)

---

#### INJECTION_BUDGET_CEILING
**Purpose:** Maximum token budget for Tier 2 per-turn dynamic context injection

**Default:** `1500`

**Format:** Integer (tokens, range 500–5000)

**Example:**
```bash
# Default
export INJECTION_BUDGET_CEILING=1500

# Rich per-turn context
export INJECTION_BUDGET_CEILING=2500

# Minimal ceiling
export INJECTION_BUDGET_CEILING=800
```

**When to change:**
- **Lower**: Reduce per-turn latency in fast-paced interactive sessions
- **Higher**: When per-turn memory recall frequently misses important context
- Must be ≥ `INJECTION_BUDGET_FLOOR` (validated at startup)
- Per-turn injection uses decay-ranked scores, so the highest-relevance memories fill the budget first

---

## 🐳 Docker Configuration

### docker-compose.yml Environment

Edit `docker/docker-compose.yml` for service-level configuration:

```yaml
services:
  ai-memory-qdrant:
    environment:
      - QDRANT__SERVICE__MAX_REQUEST_SIZE=10485760  # 10MB
      - QDRANT__STORAGE__OPTIMIZERS__DEFAULT_SEGMENT_NUMBER=0
    mem_limit: 2g
    cpus: 1.0

  ai-memory-embedding:
    environment:
      - EMBEDDING_MODEL=jinaai/jina-embeddings-v2-base-en
      - MAX_BATCH_SIZE=32
    mem_limit: 1g
    cpus: 0.5
```

### Port Mapping

**External Ports** (accessible from host):

| Service | Default External | Environment Variable |
|---------|-----------------|---------------------|
| Qdrant | 26350 | `QDRANT_EXTERNAL_PORT` |
| Embedding | 28080 | `EMBEDDING_EXTERNAL_PORT` |
| Streamlit | 28501 | `STREAMLIT_EXTERNAL_PORT` |
| Prometheus | 29090 | `PROMETHEUS_EXTERNAL_PORT` |
| Grafana | 23000 | `GRAFANA_EXTERNAL_PORT` |
| Monitoring API | 28000 | `MONITORING_API_EXTERNAL_PORT` |

**Example Override:**
```bash
# docker/.env
QDRANT_EXTERNAL_PORT=16333
EMBEDDING_EXTERNAL_PORT=18080
```

---

## 🔧 Hook Configuration

### .claude/settings.json

Complete hook configuration example:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "resume|compact",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/session_start.py", "timeout": 30000}
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/user_prompt_capture.py"}
        ]
      },
      {
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/context_injection_tier2.py", "timeout": 5000}
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/new_file_trigger.py", "timeout": 2000}
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/first_edit_trigger.py", "timeout": 2000}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/error_detection.py", "timeout": 2000},
          {"type": "command", "command": ".claude/hooks/scripts/error_pattern_capture.py"}
        ]
      },
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/post_tool_capture.py"}
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/pre_compact_save.py", "timeout": 10000}
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/agent_response_capture.py"}
        ]
      }
    ]
  }
}
```

### Hook Timeouts

| Hook | Recommended Timeout | Maximum |
|------|-------------------|---------|
| SessionStart | 30000ms (30s) | 30000ms |
| UserPromptSubmit | none / 5000ms (5s) | — |
| PreToolUse | 2000ms (2s) | 2000ms |
| PostToolUse | 2000ms (2s) / none | — |
| PreCompact | 10000ms (10s) | 30000ms |
| Stop | none | — |

---

## 👤 Agent-Specific Configuration

### Token Budgets Per Agent

Configure different token budgets for BMAD agents:

**File:** `src/memory/config.py`

```python
AGENTS = {
    "architect": {"budget": 1500},       # Architecture planning
    "analyst": {"budget": 1200},         # Analysis sessions
    "pm": {"budget": 1200},              # PM sessions
    "developer": {"budget": 1200},       # Development
    "dev": {"budget": 1200},             # Development (alias)
    "solo-dev": {"budget": 1500},        # Solo development
    "quick-flow-solo-dev": {"budget": 1500},
    "ux-designer": {"budget": 1000},     # UX design
    "qa": {"budget": 1000},              # QA testing
    "tea": {"budget": 1000},             # TEA agent
    "code-review": {"budget": 1200},     # Code review
    "code-reviewer": {"budget": 1200},   # Code reviewer (alias)
    "scrum-master": {"budget": 800},     # Scrum Master (minimal)
    "sm": {"budget": 800},               # Scrum Master (alias)
    "tech-writer": {"budget": 800},      # Technical writing
    "default": {"budget": 1000},         # General sessions
}
```

**When to customize:**
- **Architect**: Needs more context (architecture decisions, patterns)
- **Dev**: Moderate context (implementation details)
- **SM**: Less context (just tracking)

**Impact:**
- Higher budget = More memories in SessionStart
- Lower budget = Faster SessionStart, less context

---

## 📚 Examples

### Development Configuration

```bash
# ~/.ai-memory/.env

# Verbose logging
LOG_LEVEL=DEBUG

# Lower threshold (see more results)
SIMILARITY_THRESHOLD=0.3

# More retrievals (comprehensive context)
MAX_RETRIEVALS=10
```

### Production Configuration

```bash
# ~/.ai-memory/.env

# Standard logging
LOG_LEVEL=INFO

# Strict relevance
SIMILARITY_THRESHOLD=0.7

# Balanced retrievals
MAX_RETRIEVALS=5

# Structured logging for aggregation
LOG_FORMAT=json
```

### Testing Configuration

```bash
# ~/.ai-memory/.env

# Debug logging
LOG_LEVEL=DEBUG

# Permissive threshold
SIMILARITY_THRESHOLD=0.2
```

### Remote Qdrant Cloud

```bash
# ~/.ai-memory/.env

# Qdrant Cloud host and HTTPS
QDRANT_HOST=xyz-abc.qdrant.io
QDRANT_USE_HTTPS=true

# API key (from Qdrant Cloud console)
QDRANT_API_KEY=your-api-key-here
```

---

## 🔧 Troubleshooting

### Configuration Not Loading

<details>
<summary><strong>Environment variables not taking effect</strong></summary>

**Diagnosis:**
```bash
# Check if .env file exists
ls -la ~/.ai-memory/.env

# Verify variable is set
python3 -c "from memory.config import get_config; c = get_config(); print(c.get_qdrant_url())"
```

**Solutions:**
1. **File location**: Must be `~/.ai-memory/.env` (absolute path)
2. **Format**: No quotes around values
   ```bash
   # Correct
   QDRANT_HOST=localhost
   QDRANT_PORT=26350

   # Wrong
   QDRANT_HOST="localhost"
   ```
3. **Restart**: Restart hooks/services after changing
</details>

### Port Conflicts

<details>
<summary><strong>"Port already in use" error</strong></summary>

**Diagnosis:**
```bash
# Check what's using the port
lsof -i :26350
```

**Solution:**
```bash
# Option 1: Stop conflicting service
# Option 2: Change port in docker/.env
echo "QDRANT_EXTERNAL_PORT=16333" >> docker/.env
docker compose -f docker/docker-compose.yml up -d
```
</details>

### Performance Issues

<details>
<summary><strong>SessionStart too slow (>5 seconds)</strong></summary>

**Optimizations:**
```bash
# Reduce retrievals
export MAX_RETRIEVALS=3

# Increase threshold (fewer results)
export SIMILARITY_THRESHOLD=0.7
```
</details>

---

## 📚 See Also

- [HOOKS.md](HOOKS.md) - Hook configuration examples
- [INSTALL.md](../INSTALL.md) - Installation and setup
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Common issues
- [prometheus-queries.md](prometheus-queries.md) - Metrics and monitoring
- [TEMPORAL-FEATURES.md](TEMPORAL-FEATURES.md) - Decay scoring and freshness detection
- [GITHUB-INTEGRATION.md](GITHUB-INTEGRATION.md) - GitHub sync setup and usage
- [PARZIVAL-SESSION-GUIDE.md](PARZIVAL-SESSION-GUIDE.md) - Parzival session agent

---

**2026 Best Practices Applied:**
- Complete reference table format
- Default values clearly stated
- When-to-change guidance for each variable
- Real-world configuration examples
- Impact analysis for each setting
