# Installation Guide

## System Requirements

| Requirement | Minimum Version | Recommended | Notes |
|-------------|----------------|-------------|-------|
| **Python**  | 3.10           | 3.11+       | Required for async + match statements |
| **Docker**  | 20.10          | Latest      | For Qdrant + embedding service |
| **OS**      | Linux, macOS, WSL2 | Linux   | Windows requires WSL2 |
| **RAM**     | 4GB            | 8GB+        | For Docker services |
| **Disk**    | 2GB free       | 5GB+        | For Docker images + data |

## Python Dependencies

The module requires Python packages for core functionality. These are automatically installed by the Docker services, but if you're developing or debugging locally:

```bash
# Install core dependencies
pip install -r requirements.txt

# Install development dependencies (testing, linting)
pip install -r requirements-dev.txt
```

**Note:** Docker installation handles all dependencies automatically.

## Prerequisites

### 1. Install Python 3.10+

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

### 2. Install Docker

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

### 3. Install Claude Code

Follow official Claude Code installation: [claude.ai/code](https://claude.ai/code)

## Installation

### Method 1: Automated Installer (Recommended)

The installer handles all setup automatically:

```bash
# 1. Clone repository
git clone https://github.com/your-org/bmad-memory-module.git
cd bmad-memory-module

# 2. Run installer
./scripts/install.sh /path/to/target-project

# Example:
./scripts/install.sh ~/projects/my-app
```

**What the installer does:**

1. ✅ Validates prerequisites (Python, Docker, Claude Code project)
2. ✅ Copies `.claude/hooks/` and `.claude/skills/` to target project
3. ✅ Updates `.claude/settings.json` with hook configuration
4. ✅ Creates `~/.bmad-memory/` installation directory
5. ✅ Installs Python dependencies (qdrant-client, httpx, pydantic)
6. ✅ Starts Docker services (Qdrant, embedding, monitoring)
7. ✅ Runs health check to verify all services

**Installation output:**

```
═══════════════════════════════════════════════════════════
  BMAD Memory Module Installation
═══════════════════════════════════════════════════════════
Target Project: /home/user/projects/my-app
Install Directory: /home/user/.bmad-memory

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
  ✅ Created /home/user/.bmad-memory

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

### Method 2: Manual Installation (Advanced)

For advanced users who want full control:

**Step 1: Clone repository**

```bash
git clone https://github.com/your-org/bmad-memory-module.git
cd bmad-memory-module
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
      {"type": "command", "command": ".claude/hooks/scripts/session_start.py"}
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/post_tool_capture.py"}
        ]
      }
    ],
    "Stop": [
      {"type": "command", "command": ".claude/hooks/scripts/stop_hook.py"}
    ]
  }
}
```

**Step 4: Create installation directory**

```bash
mkdir -p ~/.bmad-memory/{logs,cache,templates/best_practices}
```

**Step 5: Install Python dependencies**

```bash
pip install qdrant-client httpx pydantic prometheus-client
```

**Step 6: Start Docker services**

```bash
docker compose -f docker/docker-compose.yml up -d
```

**Step 7: Verify health**

```bash
python scripts/health-check.py
```

## Upgrading

### Upgrading from v1.0.0 to v1.0.1

If you already have v1.0.0 installed, upgrade by re-running the installer:

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
- Hook scripts update to latest versions
- Docker volumes persist automatically (your data is safe)

**No manual migration needed** - The installer handles all updates automatically.

### Version Check

To verify your installed version:

```bash
# Check Docker Compose version (if using Git)
git describe --tags

# Or check CHANGELOG.md
cat CHANGELOG.md | head -20
```

## Post-Installation Verification

### 1. Check Docker Services

```bash
docker compose -f docker/docker-compose.yml ps
```

**Expected output:**

```
NAME                  STATUS              PORTS
bmad-qdrant           running             0.0.0.0:26350->6333/tcp
bmad-embedding        running             0.0.0.0:28080->8080/tcp
bmad-monitoring-api   running             0.0.0.0:28000->8000/tcp
```

### 2. Run Health Check

```bash
python scripts/health-check.py
```

**Expected output:**

```
═══════════════════════════════════════════════════════════
  BMAD Memory Module Health Check
═══════════════════════════════════════════════════════════

[1/3] Checking Qdrant (localhost:26350)...
  ✅ Qdrant is healthy
  📊 Collections: memories, best_practices

[2/3] Checking Embedding Service (localhost:28080)...
  ✅ Embedding service is healthy
  📊 Model: nomic-embed-code

[3/3] Checking Monitoring API (localhost:28000)...
  ✅ Monitoring API is healthy
  📊 Metrics: 42 registered

═══════════════════════════════════════════════════════════
  All Services Healthy ✅
═══════════════════════════════════════════════════════════
```

### 3. Test Memory Capture

In your target project, start Claude Code and run a simple command:

```bash
cd /path/to/target/project
# Use Claude Code to write a test file
# Memory should be captured automatically
```

Verify memory was stored:

```bash
curl http://localhost:26350/collections/memories/points/scroll | jq
```

### 4. Access Dashboards

- **Streamlit Dashboard:** http://localhost:28501
- **Grafana:** http://localhost:23000 (user: `admin`, pass: `admin`)
- **Prometheus:** http://localhost:29090

## Configuration

### Environment Variables

Create `~/.bmad-memory/.env` to override defaults:

```bash
# Service endpoints
QDRANT_HOST=localhost
QDRANT_PORT=26350
EMBEDDING_HOST=localhost
EMBEDDING_PORT=28080

# Installation directory
MEMORY_INSTALL_DIR=/home/user/.bmad-memory

# Logging
MEMORY_LOG_LEVEL=INFO  # DEBUG for verbose

# Performance tuning
MEMORY_BATCH_SIZE=100
MEMORY_CACHE_TTL=3600
```

### Hook Configuration

Edit `.claude/settings.json` in your target project to customize hook behavior:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          {"type": "command", "command": ".claude/hooks/scripts/post_tool_capture.py"}
        ]
      }
    ]
  }
}
```

## Uninstallation

### Complete Removal

```bash
# 1. Stop Docker services
docker compose -f docker/docker-compose.yml down -v

# 2. Remove installation directory
rm -rf ~/.bmad-memory

# 3. Remove hooks from target project
cd /path/to/target/project
rm -rf .claude/hooks/scripts/{session_start,post_tool_capture,stop_hook}.py
rm -rf .claude/skills/bmad-memory-*

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

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.

---

**Sources (2026 Best Practices):**

- [Python Package Structure](https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-structure.html)
- [Structuring Your Project - Hitchhiker's Guide](https://docs.python-guide.org/writing/structure/)
- [Documentation - Hitchhiker's Guide](https://docs.python-guide.org/writing/documentation/)
- [Packaging Python Projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
