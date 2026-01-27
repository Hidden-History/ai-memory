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
| `~/.bmad-memory/.env` | User environment variables | ❌ No (gitignored) |
| `.claude/settings.json` | Hook configuration | ✅ Yes (project-specific) |
| `docker/docker-compose.yml` | Docker service config | ✅ Yes |
| `docker/.env` | Docker environment overrides | ❌ No (gitignored) |
| `src/memory/config.py` | Default values | ✅ Yes |

---

## 📁 Configuration Files

### ~/.bmad-memory/.env

**Purpose:** User-level environment variables (highest priority)

**Location:** `~/.bmad-memory/.env`

**Format:**
```bash
# Core Settings
QDRANT_URL=http://localhost:26350
MEMORY_LOG_LEVEL=INFO

# Performance
MEMORY_MAX_RETRIEVALS=10
MEMORY_SIMILARITY_THRESHOLD=0.7
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

#### BMAD_INSTALL_DIR
**Purpose:** Installation directory for AI Memory Module

**Default:** `~/.bmad-memory`

**Format:** Absolute path

**Example:**
```bash
export BMAD_INSTALL_DIR=/opt/bmad-memory
```

**When to change:**
- Custom installation location
- Multi-user systems
- Containerized environments

---

#### BMAD_PROJECT_ID
**Purpose:** Project identifier for memory isolation (group_id in Qdrant)

**Default:** Directory name of the project

**Format:** String (alphanumeric, hyphens, underscores)

**Example:**
```bash
# Set in .claude/settings.json env section
export BMAD_PROJECT_ID=my-awesome-project

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
    "BMAD_PROJECT_ID": "my-awesome-project",
    "BMAD_INSTALL_DIR": "/home/user/.bmad-memory"
  }
}
```

**Related:**
- `QDRANT_COLLECTION_PREFIX` - Collection-level isolation
- `group_id` payload field - Record-level isolation

---

#### MEMORY_LOG_LEVEL
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
export MEMORY_LOG_LEVEL=DEBUG
```

**When to change:**
- **DEBUG**: Troubleshooting hooks or searching for bugs
- **WARNING**: Production environments (reduce log noise)

**Impact:**
- Disk usage (DEBUG generates 10x more logs)
- Performance (minimal, <10ms overhead)

---

### Qdrant Configuration

#### QDRANT_URL
**Purpose:** Qdrant vector database connection URL

**Default:** `http://localhost:26350`

**Format:** `http://HOST:PORT` or `https://HOST:PORT`

**Example:**
```bash
# Local development
export QDRANT_URL=http://localhost:26350

# Remote Qdrant Cloud
export QDRANT_URL=https://xyz.qdrant.io

# Custom port
export QDRANT_URL=http://localhost:16333
```

**When to change:**
- **Custom port**: Avoid conflicts with other services
- **Remote Qdrant**: Using Qdrant Cloud or shared instance
- **Docker network**: Using custom Docker network

**Related:**
- `QDRANT_API_KEY` - For Qdrant Cloud authentication

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
- Use `~/.bmad-memory/.env` (gitignored)
- Use environment variables
- Use secrets management (Vault, AWS Secrets Manager)

---

#### QDRANT_COLLECTION_PREFIX
**Purpose:** Prefix for collection names (multi-tenancy)

**Default:** `bmad_` (results in `bmad_code-patterns`, `bmad_discussions`, etc.)

**Format:** String (alphanumeric + underscore)

**Example:**
```bash
# Default
export QDRANT_COLLECTION_PREFIX=bmad_

# Testing
export QDRANT_COLLECTION_PREFIX=test_

# Per-user
export QDRANT_COLLECTION_PREFIX=user_alice_
```

**When to change:**
- **Testing**: Isolate test data from production
- **Multi-user**: Separate collections per user
- **Multi-environment**: dev/staging/prod isolation

**Impact:**
- Collections created: `{prefix}code-patterns`, `{prefix}discussions`, `{prefix}conventions`

---

### Embedding Configuration

#### EMBEDDING_URL
**Purpose:** Embedding service endpoint

**Default:** `http://localhost:28080/embed`

**Format:** `http://HOST:PORT/PATH`

**Example:**
```bash
# Local development
export EMBEDDING_URL=http://localhost:28080/embed

# Custom port
export EMBEDDING_URL=http://localhost:18080/embed

# External service (Jina AI API)
export EMBEDDING_URL=https://api.jina.ai/v1/embeddings
```

**When to change:**
- **Custom port**: Avoid conflicts
- **External service**: Using Jina AI API instead of self-hosted
- **Load balancer**: Multiple embedding service instances

---

#### EMBEDDING_MODEL
**Purpose:** Embedding model identifier

**Default:** `jinaai/jina-embeddings-v2-base-en` (768 dimensions)

**Options:**
- `jinaai/jina-embeddings-v2-base-en` - General purpose with code support (768d) ✅ Recommended
- `jinaai/jina-embeddings-v2-base-code` - Code-specific variant (768d)

**Example:**
```bash
export EMBEDDING_MODEL=jinaai/jina-embeddings-v2-base-en
```

**When to change:**
- **Specialized needs**: Use code-specific variant for pure code embeddings
- **Testing**: Compare model performance

⚠️ **Warning:** Changing models invalidates existing embeddings. You must:
1. Stop services
2. Delete Qdrant collections
3. Recapture memories with new model

---

#### EMBEDDING_TIMEOUT
**Purpose:** Maximum time to wait for embedding generation

**Default:** `30` seconds

**Format:** Integer (seconds)

**Example:**
```bash
# Default
export EMBEDDING_TIMEOUT=30

# Faster timeout (aggressive)
export EMBEDDING_TIMEOUT=10

# Slower connection
export EMBEDDING_TIMEOUT=60
```

**When to change:**
- **Slow network**: Increase timeout
- **Production**: Lower timeout to fail fast (use graceful degradation)

**Graceful Degradation:**
If embedding fails, system stores memory with zero vector and `embedding_status=pending`

---

### Search & Retrieval

#### MEMORY_MAX_RETRIEVALS
**Purpose:** Maximum memories to retrieve in search/SessionStart

**Default:** `5`

**Format:** Integer (1-20)

**Example:**
```bash
# Conservative (faster, less context)
export MEMORY_MAX_RETRIEVALS=3

# Default
export MEMORY_MAX_RETRIEVALS=5

# Comprehensive (slower, more context)
export MEMORY_MAX_RETRIEVALS=10

# Maximum
export MEMORY_MAX_RETRIEVALS=20
```

**When to change:**
- **Performance**: Lower for faster SessionStart (<2s)
- **Context richness**: Higher for more comprehensive memory recall
- **Token budget**: Adjust based on Claude context limits

**Impact:**
- **SessionStart duration**: ~0.1s per memory retrieved
- **Context tokens**: ~200-400 tokens per memory

---

#### MEMORY_SIMILARITY_THRESHOLD
**Purpose:** Minimum similarity score for search results (0-1)

**Default:** `0.5` (50%)

**Format:** Float (0.0 to 1.0)

**Example:**
```bash
# Strict (only high relevance)
export MEMORY_SIMILARITY_THRESHOLD=0.8

# Default (medium relevance)
export MEMORY_SIMILARITY_THRESHOLD=0.5

# Permissive (include low relevance)
export MEMORY_SIMILARITY_THRESHOLD=0.3
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

#### MEMORY_SESSION_WINDOW_HOURS
**Purpose:** SessionStart retrieval time window (hours)

**Default:** `48` (2 days)

**Format:** Integer (hours)

**Example:**
```bash
# Short window (recent sessions only)
export MEMORY_SESSION_WINDOW_HOURS=24

# Default
export MEMORY_SESSION_WINDOW_HOURS=48

# Long window (full history)
export MEMORY_SESSION_WINDOW_HOURS=168  # 1 week
```

**When to change:**
- **Recent focus**: Short window for active projects
- **Long-term recall**: Longer window for dormant projects
- **Performance**: Shorter window = faster searches

**Impact:**
- SessionStart only retrieves memories with `created_at` within this window
- Older memories still exist but won't appear in automatic context

---

### Performance Tuning

#### MEMORY_BATCH_SIZE
**Purpose:** Batch size for bulk operations

**Default:** `100`

**Format:** Integer (1-1000)

**Example:**
```bash
export MEMORY_BATCH_SIZE=100
```

**When to change:**
- **Large imports**: Increase for better throughput
- **Memory constraints**: Decrease if hitting RAM limits

**Impact:**
- Embedding generation: Processes N items at once
- Qdrant upsert: Batches N points per request

---

#### MEMORY_CACHE_TTL
**Purpose:** Cache time-to-live for embeddings and search results

**Default:** `1800` (30 minutes)

**Format:** Integer (seconds)

**Example:**
```bash
# No caching
export MEMORY_CACHE_TTL=0

# Default (30 minutes)
export MEMORY_CACHE_TTL=1800

# Long cache (1 hour)
export MEMORY_CACHE_TTL=3600
```

**When to change:**
- **Development**: Set to 0 to disable caching
- **Production**: Increase for better performance

**What's cached:**
- Query embeddings (same query = reuse embedding)
- Search results (for identical queries)

---

#### MEMORY_FORK_TIMEOUT
**Purpose:** PostToolUse fork timeout (background process spawn)

**Default:** `1000` (1 second)

**Format:** Integer (milliseconds)

**Example:**
```bash
export MEMORY_FORK_TIMEOUT=1000
```

**When to change:**
- Slow disk I/O (increase timeout)
- Should rarely need adjustment (fork is fast)

---

### Logging & Monitoring

#### MEMORY_PROMETHEUS_PORT
**Purpose:** Prometheus metrics exporter port

**Default:** `28000`

**Format:** Integer (port number)

**Example:**
```bash
export MEMORY_PROMETHEUS_PORT=28000
```

**When to change:**
- Port conflicts with other services
- Custom monitoring setup

**Access:** `http://localhost:28000/metrics`

---

#### MEMORY_STRUCTURED_LOGGING
**Purpose:** Enable structured JSON logging

**Default:** `true`

**Options:** `true`, `false`

**Example:**
```bash
# Structured logging (JSON)
export MEMORY_STRUCTURED_LOGGING=true

# Human-readable logging
export MEMORY_STRUCTURED_LOGGING=false
```

**When to change:**
- **Production**: Enable for log aggregation (ELK, Splunk)
- **Development**: Disable for human readability

**Output Example:**

```json
// Structured (MEMORY_STRUCTURED_LOGGING=true)
{"timestamp": "2026-01-17T10:30:00Z", "level": "INFO", "event": "memory_stored", "memory_id": "abc123", "type": "implementation"}

// Human-readable (MEMORY_STRUCTURED_LOGGING=false)
2026-01-17 10:30:00 INFO memory_stored memory_id=abc123 type=implementation
```

---

## 🐳 Docker Configuration

### docker-compose.yml Environment

Edit `docker/docker-compose.yml` for service-level configuration:

```yaml
services:
  bmad-qdrant:
    environment:
      - QDRANT__SERVICE__MAX_REQUEST_SIZE=10485760  # 10MB
      - QDRANT__STORAGE__OPTIMIZERS__DEFAULT_SEGMENT_NUMBER=0
    mem_limit: 2g
    cpus: 1.0

  bmad-embedding:
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
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/session_start.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/post_tool_capture.py",
            "timeout": 1000
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/scripts/pre_compact_save.py",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

### Hook Timeouts

| Hook | Recommended Timeout | Maximum |
|------|-------------------|---------|
| SessionStart | 5000ms (5s) | 10000ms |
| PostToolUse | 1000ms (1s) | 2000ms |
| PreCompact | 10000ms (10s) | 30000ms |

---

## 👤 Agent-Specific Configuration

### Token Budgets Per Agent

Configure different token budgets for BMAD agents:

**File:** `src/memory/config.py`

```python
AGENT_TOKEN_BUDGETS = {
    "default": 2000,        # General sessions
    "architect": 3000,      # Architecture planning (more context)
    "pm": 1500,            # PM sessions (less technical)
    "dev": 2500,           # Development (code-heavy)
    "tea": 2000,           # Testing (balanced)
    "sm": 1000,            # Scrum Master (minimal)
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
# ~/.bmad-memory/.env

# Verbose logging
MEMORY_LOG_LEVEL=DEBUG

# Lower threshold (see more results)
MEMORY_SIMILARITY_THRESHOLD=0.3

# More retrievals (comprehensive context)
MEMORY_MAX_RETRIEVALS=10

# No caching (always fresh)
MEMORY_CACHE_TTL=0
```

### Production Configuration

```bash
# ~/.bmad-memory/.env

# Standard logging
MEMORY_LOG_LEVEL=INFO

# Strict relevance
MEMORY_SIMILARITY_THRESHOLD=0.7

# Balanced retrievals
MEMORY_MAX_RETRIEVALS=5

# Long cache (performance)
MEMORY_CACHE_TTL=3600

# Structured logging for aggregation
MEMORY_STRUCTURED_LOGGING=true
```

### Testing Configuration

```bash
# ~/.bmad-memory/.env

# Test collection prefix
QDRANT_COLLECTION_PREFIX=test_

# Debug logging
MEMORY_LOG_LEVEL=DEBUG

# Permissive threshold
MEMORY_SIMILARITY_THRESHOLD=0.2

# Fast timeout (fail fast)
EMBEDDING_TIMEOUT=5
```

### Remote Qdrant Cloud

```bash
# ~/.bmad-memory/.env

# Qdrant Cloud URL
QDRANT_URL=https://xyz-abc.qdrant.io

# API key (from Qdrant Cloud console)
QDRANT_API_KEY=your-api-key-here

# Use external embedding service
EMBEDDING_URL=https://api.jina.ai/v1/embeddings
JINA_API_KEY=your-jina-key
```

---

## 🔧 Troubleshooting

### Configuration Not Loading

<details>
<summary><strong>Environment variables not taking effect</strong></summary>

**Diagnosis:**
```bash
# Check if .env file exists
ls -la ~/.bmad-memory/.env

# Verify variable is set
python3 -c "from memory.config import get_config; print(get_config().qdrant_url)"
```

**Solutions:**
1. **File location**: Must be `~/.bmad-memory/.env` (absolute path)
2. **Format**: No quotes around values
   ```bash
   # Correct
   QDRANT_URL=http://localhost:26350

   # Wrong
   QDRANT_URL="http://localhost:26350"
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
export MEMORY_MAX_RETRIEVALS=3

# Increase threshold (fewer results)
export MEMORY_SIMILARITY_THRESHOLD=0.7

# Shorter time window
export MEMORY_SESSION_WINDOW_HOURS=24
```
</details>

---

## 📚 See Also

- [HOOKS.md](HOOKS.md) - Hook configuration examples
- [INSTALL.md](../INSTALL.md) - Installation and setup
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Common issues
- [prometheus-queries.md](prometheus-queries.md) - Metrics and monitoring

---

**2026 Best Practices Applied:**
- Complete reference table format
- Default values clearly stated
- When-to-change guidance for each variable
- Real-world configuration examples
- Impact analysis for each setting
