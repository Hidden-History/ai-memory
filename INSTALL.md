# 📦 Installation Guide

## ⚠️ Before You Begin

> **First-Run Model Download:** On first startup, the embedding service downloads the Jina embeddings model (~500MB). This takes **2-5 minutes** depending on your connection. The service will appear unhealthy during this time - this is normal. Wait for it to complete before testing.

## 💻 System Requirements

| Requirement | Minimum Version | Recommended | Notes |
|-------------|----------------|-------------|-------|
| **Python**  | 3.10           | 3.11+       | Required for async + match statements. **AsyncSDKWrapper requires 3.11+** |
| **Docker**  | 20.10          | Latest      | For Qdrant + embedding service |
| **OS**      | Linux, macOS, WSL2 | Linux   | Windows requires WSL2 |
| **RAM**     | 4GB            | 8GB+        | For Docker services |
| **Disk**    | 2GB free       | 5GB+        | For Docker images + data |

## 🐍 Python Dependencies

The module requires Python packages for core functionality. These are automatically installed by the Docker services, but if you're developing or debugging locally:

```bash
# Install core dependencies
pip install -r requirements.txt

# Install development dependencies (testing, linting)
pip install -r requirements-dev.txt
```

**Core Dependencies:**

- `qdrant-client` - Vector database client
- `httpx` - HTTP client for embedding service
- `pydantic` - Data validation
- `anthropic` - Anthropic API client (for AsyncSDKWrapper)
- `tenacity` - Retry logic with exponential backoff (for AsyncSDKWrapper)
- `prometheus-client` - Metrics collection

**Note:** Docker installation handles all dependencies automatically. The `tenacity` package provides the exponential backoff retry logic used by AsyncSDKWrapper.

### AsyncSDKWrapper Troubleshooting

If you encounter errors when using AsyncSDKWrapper:

| Error | Cause | Fix |
|-------|-------|-----|
| `QueueTimeoutError` | Request queued longer than 60s | Increase `queue_timeout` parameter or reduce request rate |
| `QueueDepthExceededError` | More than 100 requests queued | Reduce request rate or increase `max_queue_depth` parameter |
| `RateLimitError` after retries | API rate limits exceeded | Wait for rate limit window to reset (1 minute) or upgrade API tier |

**Example with custom limits:**
```python
async with AsyncSDKWrapper(
    cwd="/path/to/project",
    queue_timeout=120.0,      # 2 minute timeout
    max_queue_depth=200       # Allow 200 queued requests
) as wrapper:
    result = await wrapper.send_message("Hello")
```

## 📋 Prerequisites

### 1. 🐍 Install Python 3.10+

**macOS (Homebrew):**

```bash
brew install python@3.11
python3 --version  # Verify: Python 3.11.x
```

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
python3 --version  # Verify: Python 3.11.x
```

**Windows (WSL2):**

```bash
# Inside WSL2 terminal
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### 2. 🐳 Install Docker

**macOS:**

```bash
brew install --cask docker
# Start Docker Desktop from Applications
```

**Ubuntu/Debian:**

```bash
# Install Docker Engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group (avoid sudo)
sudo usermod -aG docker $USER
newgrp docker  # Activate group

# Verify
docker ps  # Should not error
```

**Windows:**

- Install Docker Desktop for Windows
- Enable WSL2 integration in Docker Desktop settings

### 3. 🤖 Install Claude Code

Follow official Claude Code installation: [claude.ai/code](https://claude.ai/code)

## 🚀 Installation

> **⚠️ Install ONCE, Add Projects:** AI-Memory is installed to a single location. Clone the repository once, then run the installer for each project you want to add. **Do NOT clone ai-memory into each project!**

### Method 1: Automated Installer (Recommended)

The installer handles all setup automatically:

```bash
# 1. Clone repository (DO THIS ONCE!)
git clone https://github.com/Hidden-History/ai-memory.git
cd ai-memory

# 2. Run installer for your first project
./scripts/install.sh /path/to/target-project

# Example:
./scripts/install.sh ~/projects/my-app
```

**What the installer does:**

1. ✅ Validates prerequisites (Python, Docker, Claude Code project)
2. ✅ Copies `.claude/hooks/` and `.claude/skills/` to target project
3. ✅ Updates `.claude/settings.json` with hook configuration
4. ✅ Creates `~/.ai-memory/` installation directory
5. ✅ Installs Python dependencies (qdrant-client, httpx, pydantic)
6. ✅ Starts Docker services (Qdrant, embedding, monitoring)
7. ✅ Runs health check to verify all services

> **Note:** The installer generates `~/.ai-memory/docker/.env` with random secrets for Qdrant, Grafana, and Prometheus automatically. To customize these values (e.g., change the Grafana admin password or configure the LLM classifier provider), edit `~/.ai-memory/docker/.env` after installation. See `docker/.env.example` for all available options.

**Installation output:**

```
═══════════════════════════════════════════════════════════
  AI Memory Module Installation
═══════════════════════════════════════════════════════════
Target Project: /home/user/projects/my-app
Install Directory: /home/user/.ai-memory

[1/7] Validating prerequisites...
  ✅ Python 3.11.0 found
  ✅ Docker 24.0.6 found
  ✅ Claude Code project detected

[2/7] Copying hooks and skills...
  ✅ Copied .claude/hooks/scripts/
  ✅ Copied .claude/skills/

[3/7] Updating .claude/settings.json...
  ✅ Hook configuration added

[4/7] Creating installation directory...
  ✅ Created /home/user/.ai-memory

[5/7] Installing Python dependencies...
  ✅ Installed: qdrant-client==1.12.1, httpx==0.27.0, pydantic==2.10.3

[6/7] Starting Docker services...
  ✅ Qdrant started (port 26350)
  ✅ Embedding service started (port 28080)
  ✅ Monitoring API started (port 28000)

[7/7] Running health check...
  ✅ Qdrant healthy
  ✅ Embedding service healthy
  ✅ Monitoring API healthy

═══════════════════════════════════════════════════════════
  Installation Complete!
═══════════════════════════════════════════════════════════

Next steps:
  1. Start using Claude Code in: /home/user/projects/my-app
  2. Memories will be captured automatically
  3. Access Streamlit dashboard: http://localhost:28501
  4. Access Grafana: http://localhost:23000 (user: admin, pass: admin)
```

### Adding Additional Projects

> **⚠️ Do NOT clone ai-memory again!** Navigate to your existing ai-memory directory and run the installer from there.

AI Memory uses a **single Docker stack** for all projects. Memories are isolated using `group_id` (project name) in Qdrant.

**Adding a second (or third, etc.) project:**

```bash
# Navigate to your EXISTING ai-memory directory (where you cloned it)
cd /path/to/ai-memory

# Run installer on the new project directory
./scripts/install.sh ~/projects/my-second-app

# The installer auto-detects existing installation and:
# - Skips Docker setup (already running)
# - Skips port checks (services are expected to be running)
# - Prompts for project name
# - Copies hooks to the new project
```

**Project Name Prompt:**

```
┌─────────────────────────────────────────────────────────────┐
│  Project Configuration                                      │
└─────────────────────────────────────────────────────────────┘

📁 Project directory: /home/user/projects/my-second-app

   The project name is used to isolate memories in Qdrant.
   Each project gets its own memory space (group_id).

   Project name [my-second-app]: _
```

**Custom Project Name via CLI:**

```bash
# Skip interactive prompt by providing project name as argument
./scripts/install.sh ~/projects/my-app my-custom-project-id
```

**How Multi-Project Isolation Works:**

1. Each project gets unique `AI_MEMORY_PROJECT_ID` in `.claude/settings.json`
2. Hooks use this ID as `group_id` when storing memories
3. SessionStart retrieves only memories matching the current project
4. One Qdrant instance, multiple isolated memory spaces

**Example Multi-Project Setup:**

```bash
# Project A - e-commerce app
./scripts/install.sh ~/projects/ecommerce-app

# Project B - API service (add-project mode auto-detected)
./scripts/install.sh ~/projects/api-service

# Project C - with custom ID
./scripts/install.sh ~/projects/frontend frontend-dashboard
```

Each project has completely isolated memories while sharing the same Docker infrastructure.

### Method 2: Manual Installation (Advanced)

For advanced users who want full control:

**Step 1: Clone repository**

```bash
git clone https://github.com/Hidden-History/ai-memory.git
cd ai-memory
```

**Step 2: Copy files to target project**

```bash
TARGET_PROJECT="/path/to/your/project"

# Copy hooks
cp -r .claude/hooks "$TARGET_PROJECT/.claude/"

# Copy skills
cp -r .claude/skills "$TARGET_PROJECT/.claude/"
```

**Step 3: Update .claude/settings.json**

Add hook configuration to `$TARGET_PROJECT/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/session_start.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
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
    ]
  }
}
```

**Step 4: Create installation directory**

```bash
mkdir -p ~/.ai-memory/{logs,cache,templates/conventions}
```

**Step 5: Install Python dependencies**

```bash
pip install qdrant-client httpx pydantic prometheus-client
```

**Step 6: Configure Docker environment**

The Docker services require credentials and configuration. Create a `.env` file from the example:

```bash
cd docker
cp .env.example .env
```

Edit `docker/.env` and set these required values:

| Variable | How to Generate | Required? |
|----------|----------------|-----------|
| `QDRANT_API_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` | Yes |
| `GRAFANA_ADMIN_PASSWORD` | `python3 -c "import secrets; print(secrets.token_urlsafe(16))"` | Yes |
| `GRAFANA_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` | Yes |
| `PROMETHEUS_ADMIN_PASSWORD` | `python3 -c "import secrets; print(secrets.token_urlsafe(16))"` | Yes (if using monitoring) |
| `AI_MEMORY_INSTALL_DIR` | Set to your ai-memory clone path (e.g., `/home/user/ai-memory`) | Yes |

After setting `PROMETHEUS_ADMIN_PASSWORD`, you also need to configure Prometheus basic auth:

1. Generate the bcrypt hash:
   ```bash
   python3 -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD_HERE', bcrypt.gensalt(rounds=12)).decode())"
   ```
2. Paste the hash into `docker/prometheus/web.yml` under `basic_auth_users.admin`
3. Generate the base64 auth header:
   ```bash
   echo -n "admin:YOUR_PASSWORD_HERE" | base64
   ```
4. Set `PROMETHEUS_BASIC_AUTH_HEADER` to `Basic <base64-output>`

The classifier configuration (Ollama, OpenRouter, etc.) at the bottom of `.env` can use defaults for local development. See the comments in `.env.example` for provider-specific setup.

**Step 7: Start Docker services**

```bash
docker compose -f docker/docker-compose.yml up -d
```

**Step 8: Verify health**

```bash
python scripts/health-check.py
```

## ⬆️ Upgrading

### Upgrading to V2.0

If you already have v1.x installed, upgrade by re-running the installer:

```bash
# 1. Navigate to installation directory
cd /path/to/target-project

# 2. Pull latest changes (if installed from Git)
git pull origin main

# 3. Run installer to update
./scripts/install.sh .
```

**What gets upgraded:**
- Docker services restart with new configurations
- Hook scripts update to latest versions (including V2.0 automatic triggers)
- Docker volumes persist automatically (your data is safe)
- Collections automatically migrate from v1.x names to v2.0 names

**V2.0 Migration Notes:**
- Old collection names (`implementations`, `best_practices`, `agent-memory`) automatically renamed
- New collections: `code-patterns`, `conventions`, `discussions`
- Memory types updated to V2.0 schema (15 types)
- Automatic triggers enabled (error detection, new file, first edit, decision keywords, best practices)
- No data loss - all existing memories preserved

**No manual migration needed** - The installer handles all updates automatically.

### Version Check

To verify your installed version:

```bash
# Check Docker Compose version (if using Git)
git describe --tags

# Or check CHANGELOG.md
cat CHANGELOG.md | head -20
```

## ✅ Post-Installation Verification

### 1. 🐳 Check Docker Services

```bash
docker compose -f docker/docker-compose.yml ps
```

**Expected output:**

```
NAME                  STATUS              PORTS
ai-memory-qdrant           running             0.0.0.0:26350->6333/tcp
ai-memory-embedding        running             0.0.0.0:28080->8080/tcp
ai-memory-monitoring-api   running             0.0.0.0:28000->8000/tcp
```

### 2. 🏥 Run Health Check

```bash
python scripts/health-check.py
```

**Expected output:**

```
═══════════════════════════════════════════════════════════
  AI Memory Module Health Check
═══════════════════════════════════════════════════════════

[1/3] Checking Qdrant (localhost:26350)...
  ✅ Qdrant is healthy
  📊 Collections: code-patterns, conventions, discussions

[2/3] Checking Embedding Service (localhost:28080)...
  ✅ Embedding service is healthy
  📊 Model: jinaai/jina-embeddings-v2-base-en

[3/3] Checking Monitoring API (localhost:28000)...
  ✅ Monitoring API is healthy
  📊 Metrics: 42 registered

═══════════════════════════════════════════════════════════
  All Services Healthy ✅
═══════════════════════════════════════════════════════════
```

### 3. 🧪 Test Memory Capture

In your target project, start Claude Code and run a simple command:

```bash
cd /path/to/target/project
# Use Claude Code to write a test file
# Memory should be captured automatically
```

Verify memory was stored:

```bash
curl http://localhost:26350/collections/code-patterns/points/scroll | jq
```

### 4. 📊 Access Dashboards

- **Streamlit Dashboard:** http://localhost:28501 - Memory browser and statistics
- **Grafana:** http://localhost:23000 (user: `admin`, pass: `admin`) - Performance dashboards
- **Prometheus:** http://localhost:29090 - Raw metrics explorer
- **Pushgateway:** http://localhost:29091 - Hook metrics collection (requires `--profile monitoring`)

### 5. 📈 Monitoring Profile Services

The module includes comprehensive monitoring via the `--profile monitoring` flag:

```bash
docker compose -f docker/docker-compose.yml --profile monitoring up -d
```

**Monitoring Stack:**

| Service | Port | Purpose |
|---------|------|---------|
| **Prometheus** | 29090 | Metrics collection and storage |
| **Pushgateway** | 29091 | Metrics from short-lived processes (hooks) |
| **Grafana** | 23000 | Pre-configured dashboards and visualization |

**Key Features:**
- Pre-built dashboards for memory performance, hook latency, and system health
- Hook execution metrics pushed from session_start, post_tool_capture, and other hooks
- Collection size warnings and threshold alerts
- Embedding service performance tracking

## Monitoring Setup (Optional)

### Enable Monitoring Profile

```bash
docker compose -f docker/docker-compose.yml --profile monitoring up -d
```

This starts:
- Prometheus (port 29090): Metrics collection
- Pushgateway (port 29091): Hook metrics ingestion
- Grafana (port 23000): Dashboards and visualization

### Access Grafana

1. Open http://localhost:23000
2. Login: admin / admin
3. Navigate to Dashboards → AI Memory

### Verify Metrics Flow

```bash
# Check Pushgateway has metrics
curl http://localhost:29091/metrics | grep aimemory_

# Check Prometheus is healthy
curl -s http://localhost:29090/-/healthy
```

## Seed Best Practices (Recommended)

Seed the conventions collection with common best practices:

```bash
# Preview what will be seeded
python3 scripts/memory/seed_best_practices.py --dry-run

# Seed from default templates
python3 scripts/memory/seed_best_practices.py

# Seed from custom directory
python3 scripts/memory/seed_best_practices.py --templates-dir ./my-conventions
```

Or enable during installation:

```bash
SEED_BEST_PRACTICES=true ./scripts/install.sh /path/to/project
```

## 🔄 Managing the Stack

### Starting Services

```bash
# Start core services (Qdrant, Embedding, Monitoring API)
docker compose -f docker/docker-compose.yml up -d

# Start with full monitoring (adds Prometheus, Grafana, Pushgateway)
docker compose -f docker/docker-compose.yml --profile monitoring up -d
```

### Stopping Services

```bash
# Stop core services (preserves data)
docker compose -f docker/docker-compose.yml down

# Stop core + monitoring services (if started with --profile monitoring)
docker compose -f docker/docker-compose.yml --profile monitoring down

# Stop services AND delete data volumes (DESTRUCTIVE)
docker compose -f docker/docker-compose.yml down -v

# Stop ALL including monitoring AND delete volumes (DESTRUCTIVE)
docker compose -f docker/docker-compose.yml --profile monitoring down -v
```

> **Important:** If you started with `--profile monitoring`, you must stop with the same flag to properly shut down Prometheus, Grafana, and Pushgateway.

### Restarting Services

```bash
# Restart core services
docker compose -f docker/docker-compose.yml restart

# Restart core + monitoring services
docker compose -f docker/docker-compose.yml --profile monitoring restart

# Restart a specific service
docker compose -f docker/docker-compose.yml restart ai-memory-qdrant
docker compose -f docker/docker-compose.yml restart ai-memory-embedding
docker compose -f docker/docker-compose.yml restart ai-memory-prometheus  # monitoring profile only
```

### Checking Status

```bash
# View running services
docker compose -f docker/docker-compose.yml ps

# Quick health check
curl -s http://localhost:26350/health | head -1  # Qdrant
curl -s http://localhost:28080/health             # Embedding

# Full health check
python scripts/health-check.py
```

### Viewing Logs

```bash
# All services
docker compose -f docker/docker-compose.yml logs

# Follow logs in real-time
docker compose -f docker/docker-compose.yml logs -f

# Specific service logs
docker compose -f docker/docker-compose.yml logs ai-memory-qdrant
docker compose -f docker/docker-compose.yml logs ai-memory-embedding
```

### After System Restart

If your computer restarts, the Docker services need to be started manually:

```bash
cd /path/to/ai-memory  # or wherever you cloned the repo
docker compose -f docker/docker-compose.yml up -d
```

To enable auto-start on boot, configure Docker Desktop (macOS/Windows) or systemd (Linux) to start the Docker daemon automatically.

## ⚙️ Configuration

### 🌍 Environment Variables

Create `~/.ai-memory/.env` to override defaults:

```bash
# Service endpoints
QDRANT_HOST=localhost
QDRANT_PORT=26350
EMBEDDING_HOST=localhost
EMBEDDING_PORT=28080

# Installation directory
AI_MEMORY_INSTALL_DIR=/home/user/.ai-memory

# Logging
MEMORY_LOG_LEVEL=INFO  # DEBUG for verbose

# Performance tuning
MEMORY_BATCH_SIZE=100
MEMORY_CACHE_TTL=3600
```

### 🔧 Hook Configuration

Edit `.claude/settings.json` in your target project to customize hook behavior:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/session_start.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
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
    ]
  }
}
```

> **Note:** The PreCompact hook is critical for session continuity. It saves your session summary before context compaction, enabling the "aha moment" when Claude remembers previous sessions.

See [docs/HOOKS.md](docs/HOOKS.md) for comprehensive hook documentation.

## 🗑️ Uninstallation

### Complete Removal

```bash
# 1. Stop Docker services
docker compose -f docker/docker-compose.yml down -v

# 2. Remove installation directory
rm -rf ~/.ai-memory

# 3. Remove hooks from target project
cd /path/to/target/project
rm -rf .claude/hooks/scripts/{session_start,post_tool_capture,stop_hook}.py
rm -rf .claude/skills/ai-memory-*

# 4. Remove hook configuration from .claude/settings.json
# (Manual edit required - remove hooks section)

# 5. Uninstall Python dependencies (optional)
pip uninstall qdrant-client httpx pydantic prometheus-client
```

### Docker Data Only

To remove data but keep services:

```bash
docker compose -f docker/docker-compose.yml down -v
```

## 🔧 Troubleshooting

### Common Installation Issues

<details>
<summary><strong>Installation fails with "Python not found"</strong></summary>

**Solution:**
```bash
# Verify Python 3.10+ is installed
python3 --version

# If not installed, see Prerequisites section above
```
</details>

<details>
<summary><strong>Docker services won't start</strong></summary>

**Solution:**
```bash
# Check if Docker daemon is running
docker ps

# Check for port conflicts
lsof -i :26350  # Qdrant
lsof -i :28080  # Embedding

# View detailed logs
docker compose -f docker/docker-compose.yml logs
```
</details>

<details>
<summary><strong>Hooks not triggering in Claude Code</strong></summary>

**Solution:**
1. Verify `.claude/settings.json` was updated correctly
2. Restart Claude Code session
3. Check hook scripts are executable:
   ```bash
   chmod +x .claude/hooks/scripts/*.py
   ```
4. Check hook logs for errors (if logging enabled)
</details>

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for comprehensive troubleshooting guide.

---

**Sources (2026 Best Practices):**

- [Python Package Structure](https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-structure.html)
- [Structuring Your Project - Hitchhiker's Guide](https://docs.python-guide.org/writing/structure/)
- [Documentation - Hitchhiker's Guide](https://docs.python-guide.org/writing/documentation/)
- [Packaging Python Projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
