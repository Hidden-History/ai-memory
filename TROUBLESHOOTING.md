# 🔧 Troubleshooting Guide

> Comprehensive troubleshooting for common issues and advanced diagnostics

## 📋 Table of Contents

- [Quick Diagnostic Commands](#quick-diagnostic-commands)
- [Known Issues](#known-issues-in-v100)
- [Services Won't Start](#services-wont-start)
- [WSL-Specific Issues](#wsl-hook-files-use-copies-instead-of-symlinks-bug-032)
- [Hook Issues](#hook-issues)
- [Memory & Search Issues](#memory--search-issues)
- [Command Issues](#command-issues)
- [V2.0 Automatic Triggers](#v20-automatic-triggers)
- [Performance Issues](#performance-issues)
- [Configuration Issues](#configuration-issues)

See also:
- [HOOKS.md](docs/HOOKS.md) - Hook-specific troubleshooting
- [COMMANDS.md](docs/COMMANDS.md) - Command-specific troubleshooting
- [CONFIGURATION.md](docs/CONFIGURATION.md) - Configuration troubleshooting

---

## 🚀 Quick Diagnostic Commands

Run these first to gather information:

```bash
# Check all services
docker compose -f docker/docker-compose.yml ps

# Check logs for all services
docker compose -f docker/docker-compose.yml logs

# Check health
python scripts/health-check.py

# Check ports
lsof -i :26350  # Qdrant
lsof -i :28080  # Embedding
lsof -i :28000  # Monitoring API
```

## Known Issues in v1.x

### Embedding Model Re-downloads on Every Restart
**Fixed in**: v1.0.1+
**Symptom**: First container start takes 80-90 seconds to download embedding model. Subsequent restarts also take 80-90 seconds.
**Workaround**: Upgrade to v1.0.1+ which persists the model cache.

### Installer Times Out on First Start
**Fixed in**: v1.0.1+
**Symptom**: Installation appears to fail with "Timed out waiting for services" but services actually work.
**Workaround**: Ignore the error if `docker compose ps` shows services as healthy. Or upgrade to v1.0.1+.

### Missing requirements.txt
**Fixed in**: v1.0.1+
**Symptom**: Cannot install Python dependencies for testing.
**Workaround**: Use `requirements-dev.txt` or upgrade to v1.0.1+.

### Old Collection Names (v1.x)
**Fixed in**: V2.0
**Symptom**: Collections named `implementations`, `best_practices`, `agent-memory`.
**Workaround**: Upgrade to V2.0 which uses new collection names: `code-patterns`, `conventions`, `discussions`.

---

## Venv and Dependency Issues (TECH-DEBT-136)

### Symptoms
- Hooks fail with `ModuleNotFoundError`
- "tree-sitter not installed" message
- Memory operations silently fail
- Health check shows "venv unhealthy"

### Diagnosis

Run the health check:
```bash
python scripts/health-check.py
```

Or test manually:
```bash
~/.ai-memory/.venv/bin/python -c "import qdrant_client; print('OK')"
```

If this fails with `ModuleNotFoundError`, the venv is broken or incomplete.

### Fix

**Option 1: Re-run the installer**
```bash
cd /path/to/ai-memory
./scripts/install.sh
```

The installer now verifies all critical packages after installation and will fail loudly if any are missing.

**Option 2: Manually recreate venv**
```bash
rm -rf ~/.ai-memory/.venv
python3 -m venv ~/.ai-memory/.venv
~/.ai-memory/.venv/bin/pip install -e /path/to/ai-memory[dev]
```

**Option 3: Install missing packages**
```bash
~/.ai-memory/.venv/bin/pip install qdrant-client prometheus-client httpx pydantic structlog
```

### Critical Packages

These packages are required for hooks to function:

| Package | Purpose |
|---------|---------|
| `qdrant_client` | Qdrant client for memory storage |
| `prometheus_client` | Prometheus metrics |
| `httpx` | HTTP client for embedding service |
| `pydantic` | Configuration validation |
| `structlog` | Logging |

### Optional Packages

These packages enable additional features but are not required:

| Package | Purpose |
|---------|---------|
| `tree_sitter` | AST-based code chunking |
| `tree_sitter_python` | Python code parsing |

If these are missing, you'll see warnings but core functionality works.

---

## Services Won't Start

### Symptom: Docker Compose Fails

**Error:**

```
Error response from daemon: driver failed programming external connectivity on endpoint ai-memory-qdrant: Bind for 0.0.0.0:26350 failed: port is already allocated
```

**Cause:** Port conflict - another process is using the port.

**Solution:**

1. Find conflicting process:
   ```bash
   lsof -i :26350
   # OUTPUT:
   # COMMAND   PID     USER   FD   TYPE   DEVICE SIZE/OFF NODE NAME
   # qdrant  12345  user   3u  IPv6  0x...      0t0  TCP *:26350 (LISTEN)
   ```

2. **Option A:** Stop conflicting process:
   ```bash
   kill 12345  # Replace with actual PID
   ```

3. **Option B:** Change port in `docker/docker-compose.yml`:
   ```yaml
   services:
     qdrant:
       ports:
         - "16333:6333"  # Use different external port
   ```

   Then update `.env`:
   ```bash
   QDRANT_PORT=16333
   ```

### Symptom: Docker Daemon Not Running

**Error:**

```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
```

**Cause:** Docker daemon is not running.

**Solution:**

**macOS:**

```bash
open -a Docker  # Start Docker Desktop
```

**Linux:**

```bash
sudo systemctl start docker
sudo systemctl enable docker  # Auto-start on boot
```

**Windows (WSL2):**

- Start Docker Desktop from Windows Start menu
- Ensure WSL2 integration is enabled in Docker Desktop settings

### WSL: Hook Files Use Copies Instead of Symlinks (BUG-032)

**Background:**

On WSL (Windows Subsystem for Linux), the installer automatically uses file copies instead of symlinks for hook scripts. This is because WSL symlinks are not visible from Windows applications (VS Code, Windows Explorer, etc.).

**Behavior:**

- **Native Linux/macOS:** Symlinks point to shared installation (`~/.ai-memory/.claude/hooks/scripts/`)
- **WSL:** Copies of hook scripts are placed in project directory

**Trade-off:**

When using file copies on WSL, updates to the shared installation do NOT automatically propagate to projects. After updating the AI Memory Module, re-run the installer for each project:

```bash
# Re-run installer to sync updated hooks
./scripts/install.sh /path/to/your/project
```

**Verification:**

```bash
# Check if files are symlinks or copies
ls -la .claude/hooks/scripts/

# Symlinks show: session_start.py -> /home/user/.ai-memory/.claude/hooks/scripts/session_start.py
# Copies show: session_start.py (no arrow)
```

**Note:** The copies are for **visibility** in Windows apps (VS Code, Explorer). The hooks themselves execute from the shared installation (`~/.ai-memory/`) via `settings.json`. Edit scripts in the shared location, not the project copies.

### Symptom: Permission Denied

**Error:**

```
permission denied while trying to connect to the Docker daemon socket
```

**Cause:** User not in `docker` group.

**Solution:**

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Apply group changes (logout/login alternative)
newgrp docker

# Verify
docker ps  # Should not require sudo
```

## Health Check Failures

### Symptom: Qdrant Unhealthy

**Error from health check:**

```
❌ Qdrant is unhealthy
   Status: Connection refused
```

**Solution:**

1. Check if Qdrant container is running:
   ```bash
   docker compose -f docker/docker-compose.yml ps qdrant
   ```

2. Check Qdrant logs:
   ```bash
   docker compose -f docker/docker-compose.yml logs qdrant
   ```

3. Common issues in logs:
   - **"Permission denied"** → Volume mount permissions issue
     ```bash
     sudo chown -R 1000:1000 docker/qdrant_data/
     ```

   - **"Address already in use"** → Port conflict (see above)

   - **"Out of memory"** → Insufficient RAM
     ```bash
     # Check Docker resource limits
     docker info | grep -i memory
     # Increase in Docker Desktop: Settings → Resources → Memory
     ```

4. Restart Qdrant:
   ```bash
   docker compose -f docker/docker-compose.yml restart qdrant
   ```

### Symptom: Embedding Service Unhealthy

**Error from health check:**

```
❌ Embedding service is unhealthy
   Status: 502 Bad Gateway
```

**Solution:**

1. Check embedding service logs:
   ```bash
   docker compose -f docker/docker-compose.yml logs embedding
   ```

2. Common issues:
   - **"Model not found"** → Model download failed
     ```bash
     # Check model is downloaded
     docker compose -f docker/docker-compose.yml exec embedding ls -la /app/models/

     # Restart to re-download
     docker compose -f docker/docker-compose.yml restart embedding
     ```

   - **"CUDA error"** → GPU not available (expected, CPU fallback should work)
     - Check logs for "Using CPU" message
     - Performance will be slower but functional

   - **"Port already in use"** → Port conflict
     ```bash
     lsof -i :28080
     # Kill conflicting process or change port in docker-compose.yml
     ```

3. Test embedding endpoint manually:
   ```bash
   curl -X POST http://localhost:28080/embed \
     -H "Content-Type: application/json" \
     -d '{"texts": ["test embedding"]}'

   # Expected: {"embeddings": [[0.123, -0.456, ...]]}
   ```

### Symptom: Classifier Worker Unhealthy (BUG-045)

**Fixed in**: v2.0.1+ (BUG-045)

**Error from docker ps:**

```
ai-memory-classifier-worker    Up 15 minutes (unhealthy)
```

**Cause:** Health check looks for `/tmp/worker.health` file which was only created after the first batch processed. If the queue is empty at startup, the health file never gets created.

**Solution:**

Fixed in v2.0.1+. The worker now creates the health file immediately at startup (not just after processing batches).

**Workaround for v2.0.0:**

Manually create the health file:
```bash
docker exec ai-memory-classifier-worker touch /tmp/worker.health
```

**Verification:**

```bash
# Check container status
docker ps | grep classifier-worker
# Should show: (healthy) after 60 seconds

# Check health file exists
docker exec ai-memory-classifier-worker ls -la /tmp/worker.health
# Should show: -rw-r--r-- 1 classifier users 0 ...
```

## Context Injection Issues (NOT YET VERIFIED SOLUTION)

### Symptom: Hooks Execute But Claude Doesn't Use Context

⚠️ **WARNING**: This is an active investigation. The solution described below is **NOT YET VERIFIED** in production.

**Signs:**

- SessionStart hooks execute successfully (proven via debug logs)
- Manual tests show memory search retrieves correct results
- JSON output is valid
- But Claude searches for files/code instead of using provided context
- No errors in hook logs
- `/hooks` command shows hooks registered correctly

**Example Behavior:**

User asks: "Fix the Grafana dashboards showing no data"

Expected: Claude uses Grafana Dashboard Fix Guide from memory (42% relevance)

Actual: Claude searches for `docker/grafana/*.json` files instead

**Root Cause (INVESTIGATION IN PROGRESS):**

SessionStart hooks with JSON `additionalContext` output appear to not inject context into Claude's reasoning process in Claude Code v2.1.9. The hooks execute, the JSON is valid, but Claude doesn't see or use the context.

**Evidence:**
```bash
# Manual test shows hooks work and retrieve correct memories
echo '{"session_id":"test","cwd":"/path/to/your/project","source":"startup"}' | \
  python3 ~/.ai-memory/.claude/hooks/scripts/session_start.py

# Output: Valid JSON with 4 memories including Grafana guides at 42% relevance
```

But in live Claude Code session, Claude ignores this and searches files.

**Potential Solution (NOT YET VERIFIED):**

Based on working reference architecture (`ai-memory-qdrant-knowledge-management`), use **PreToolUse hooks with STDERR output** instead of SessionStart with JSON:

1. **Create PreToolUse hook** that outputs to STDERR before tool execution:
   ```python
   # Output formatted text to STDERR (NOT JSON)
   print(f"\n{'='*70}", file=sys.stderr)
   print(f"🧠 RELEVANT CONTEXT FOR {tool_name.upper()}", file=sys.stderr)
   print(f"{'='*70}", file=sys.stderr)

   for i, result in enumerate(results, 1):
       print(f"\n{i}. [{result['type']}] (Relevance: {result['score']:.0%})", file=sys.stderr)
       print(f"{result['content'][:600]}...", file=sys.stderr)

   print(f"\n{'='*70}\n", file=sys.stderr)
   sys.exit(0)
   ```

2. **Configure in settings.json**:
   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Read|Search|Bash|Edit|Write",
           "hooks": [{
             "type": "command",
             "command": "python3 /tmp/memory_context_pretool_stderr.py",
             "timeout": 5000
           }]
         }
       ]
     }
   }
   ```

**Status**: Hook implemented at `/tmp/memory_context_pretool_stderr.py` but **NOT YET VERIFIED** in live Claude Code session.

**Testing Plan**:

1. Restart Claude Code in test project: `cd /path/to/your/project && claude`
2. Use test prompt: "The Grafana dashboards at docker/grafana/dashboards/ are showing 'No data' for most panels. Please fix the dashboard JSON files so they use metrics that actually exist in Prometheus."
3. Watch for formatted box with "🧠 RELEVANT CONTEXT" in terminal
4. Verify Claude mentions "Grafana Dashboard Fix Guide" in response
5. Confirm Claude uses metrics from memory instead of blindly searching files

**See Also:**
- `oversight/TESTING_QUICK_REFERENCE.md` - Step-by-step testing instructions
- `oversight/session-logs/SESSION_HANDOFF_2026-01-16_HOOKS_CONTEXT_INJECTION.md` - Complete investigation details
- `oversight/tracking/blockers-log.md` (BLK-002) - Current status

---

## Memory Capture Issues

### Symptom: PostToolUse Hook Not Triggering

**Signs:**

- No memories appear in Qdrant after using Write/Edit tools
- Hook script logs show no activity

**Solution:**

1. Verify hook configuration in `.claude/settings.json`:
   ```json
   {
     "hooks": {
       "PostToolUse": [
         {
           "matcher": "Write|Edit",
           "hooks": [
             {"type": "command", "command": ".claude/hooks/scripts/post_tool_capture.py"}
           ]
         }
       ]
     }
   }
   ```

2. Check hook script exists and is executable:
   ```bash
   ls -la .claude/hooks/scripts/post_tool_capture.py
   # Expected: -rwxr-xr-x (executable bit set)

   # Make executable if needed
   chmod +x .claude/hooks/scripts/post_tool_capture.py
   ```

3. Test hook manually:
   ```bash
   echo '{"tool": "Write", "content": "test"}' | python3 .claude/hooks/scripts/post_tool_capture.py
   # Should exit with code 0 (success)
   echo $?  # Should print: 0
   ```

4. Enable hook logging:
   ```bash
   export MEMORY_LOG_LEVEL=DEBUG
   # Logs will appear in ~/.ai-memory/logs/hook.log
   tail -f ~/.ai-memory/logs/hook.log
   ```

### Symptom: Permission Denied Writing to Installation Directory

**Error in logs:**

```
PermissionError: [Errno 13] Permission denied: '/home/user/.ai-memory/logs/hook.log'
```

**Solution:**

```bash
# Fix permissions on installation directory
chmod -R u+w ~/.ai-memory

# Verify
ls -la ~/.ai-memory
# All directories should be writable by user
```

## Search Not Working

### Symptom: No Results for Known Content

**Signs:**

- Search returns empty results
- Memories exist in Qdrant (verified via curl)

**Solution:**

1. Check if embeddings are generated:
   ```bash
   curl http://localhost:26350/collections/memories/points/scroll \
     -H "Content-Type: application/json" \
     -d '{"limit": 10}' | jq '.result.points[].payload.embedding_status'

   # Expected: "complete"
   # If "pending": Embedding service issue (see below)
   ```

2. Test embedding service:
   ```bash
   curl -X POST http://localhost:28080/embed \
     -H "Content-Type: application/json" \
     -d '{"texts": ["test"]}' \
     --max-time 30

   # Should return within 2 seconds
   # Timeout = embedding service hung
   ```

3. If `embedding_status` is "pending", regenerate embeddings:
   ```python
   # scripts/regenerate_embeddings.py (create if doesn't exist)
   # This is a manual fix for pending embeddings
   ```

### Symptom: Embedding Timeout Errors

**Error in logs:**

```
embedding_timeout: timeout_seconds=30
```

**Solution:**

1. Check embedding service resource usage:
   ```bash
   docker stats ai-memory-embedding
   # CPU should be <80%, MEM should have headroom
   ```

2. If CPU/memory maxed out:
   ```bash
   # Increase Docker resources in Docker Desktop:
   # Settings → Resources → CPU: 4+, Memory: 8GB+
   ```

3. Restart embedding service:
   ```bash
   docker compose -f docker/docker-compose.yml restart embedding
   ```

## Performance Problems

### Symptom: Hooks Take >500ms

**Signs:**

- Claude Code feels sluggish after Write/Edit operations
- Hook logs show slow execution times

**Solution:**

1. Verify fork pattern is used in PostToolUse hook:
   ```python
   # post_tool_capture.py should fork to background
   subprocess.Popen([...], stdout=DEVNULL, stderr=DEVNULL)
   sys.exit(0)  # Return immediately
   ```

2. Check if Qdrant is overloaded:
   ```bash
   docker stats ai-memory-qdrant
   # If CPU >90% or MEM maxed out, restart
   ```

3. Clear cache if corrupted:
   ```bash
   rm -rf ~/.ai-memory/cache/*
   ```

### Symptom: Qdrant Slow Queries

**Signs:**

- Search takes >3 seconds
- Qdrant dashboard shows slow queries

**Solution:**

1. Check collection size:
   ```bash
   curl http://localhost:26350/collections/memories | jq '.result.points_count'
   # If >100,000 points, consider archiving old memories
   ```

2. Rebuild indexes:
   ```bash
   # Restart Qdrant (rebuilds indexes on startup)
   docker compose -f docker/docker-compose.yml restart qdrant
   ```

3. Optimize Docker resources:
   ```yaml
   # docker-compose.yml
   services:
     qdrant:
       deploy:
         resources:
           limits:
             memory: 4G  # Increase if available
   ```

## Data Persistence Issues

### Symptom: Memories Lost After Restart

**Signs:**

- Memories disappear when Docker restarts
- Qdrant shows 0 points after restart

**Solution:**

1. Verify volume mounts in `docker-compose.yml`:
   ```yaml
   services:
     qdrant:
       volumes:
         - ./qdrant_data:/qdrant/storage  # MUST be present
   ```

2. Check if volume directory exists:
   ```bash
   ls -la docker/qdrant_data/
   # Should contain qdrant database files
   ```

3. If volume missing, recreate:
   ```bash
   mkdir -p docker/qdrant_data
   docker compose -f docker/docker-compose.yml up -d
   ```

### Symptom: "Volume Mount Failed"

**Error:**

```
Error response from daemon: invalid mount config for type "bind": bind source path does not exist
```

**Solution:**

```bash
# Create missing volume directories
mkdir -p docker/qdrant_data
mkdir -p docker/grafana_data
mkdir -p docker/prometheus_data

# Fix permissions
sudo chown -R 1000:1000 docker/qdrant_data
sudo chown -R 472:472 docker/grafana_data  # Grafana user ID

# Restart services
docker compose -f docker/docker-compose.yml up -d
```

## 🔧 Hook Issues

For comprehensive hook troubleshooting, see [docs/HOOKS.md](docs/HOOKS.md).

### SessionStart Hook Not Firing

**Diagnosis:**
```bash
# Check if matcher is present in .claude/settings.json
grep -A 5 "SessionStart" .claude/settings.json
```

**Solution:**
SessionStart hooks **REQUIRE** a `matcher` field:
```json
{
  "SessionStart": [{
    "matcher": "startup|resume|compact",  // REQUIRED
    "hooks": [...]
  }]
}
```

See [HOOKS.md - SessionStart Troubleshooting](docs/HOOKS.md#sessionstart) for complete details.

---

### PostToolUse Not Capturing Memories

**Diagnosis:**
```bash
# Check if background process is forking
grep "background_forked" ~/.ai-memory/logs/hooks.log

# Check if memories are being stored
grep "memory_stored" ~/.ai-memory/logs/hooks.log
```

**Common Causes:**
1. **Duplicate content** - Hash already exists
2. **Qdrant unavailable** - Cannot connect
3. **Tool matcher mismatch** - Hook not triggered for tool type

**Solution:**
```bash
# Verify matcher includes your tool
# In .claude/settings.json:
"matcher": "Write|Edit|NotebookEdit"  // All tools that modify files
```

See [HOOKS.md - PostToolUse Troubleshooting](docs/HOOKS.md#posttooluse) for complete details.

---

### PreCompact Session Summaries Missing

**Diagnosis:**
```bash
# Check if summaries are stored (V2.0 collection name)
curl http://localhost:26350/collections/discussions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "session")'
```

**Common Causes:**
1. **Hook timeout** - Timeout too short (<10s)
2. **Wrong collection** - Stored in code-patterns instead of discussions
3. **Older than 48 hours** - SessionStart filters recent only

**Solution:**
```json
{
  "PreCompact": [{
    "matcher": "auto|manual",
    "hooks": [{
      "command": ".claude/hooks/scripts/pre_compact_save.py",
      "timeout": 10000  // 10 seconds minimum
    }]
  }]
}
```

See [HOOKS.md - PreCompact Troubleshooting](docs/HOOKS.md#precompact) for complete details.

---

## 🔍 Memory & Search Issues

### No Memories Appearing in SessionStart

**Diagnosis:**
```bash
# Check if memories exist for this project (V2.0: check discussions collection)
PROJECT_NAME=$(basename $(pwd))
curl http://localhost:26350/collections/discussions/points/scroll \
  | jq ".result.points[] | select(.payload.group_id == \"$PROJECT_NAME\")"
```

**Common Causes:**
1. **First session** - No memories captured yet
2. **Wrong project detection** - group_id mismatch
3. **Similarity threshold too high** - Memories don't match query
4. **Older than 48 hours** - Filtered by time window

**Solutions:**
```bash
# Check project detection
python3 -c "from memory.project import detect_project; print(detect_project('.'))"

# Lower similarity threshold temporarily
export MEMORY_SIMILARITY_THRESHOLD=0.3

# Extend time window
export MEMORY_SESSION_WINDOW_HOURS=168  # 1 week
```

See [CONFIGURATION.md](docs/CONFIGURATION.md) for all configuration options.

---

### Search Returns No Results

**Diagnosis:**
```bash
# Test embedding service
curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["test query"]}' \
  --max-time 5

# Should return 768-dimensional vector
```

**Common Causes:**
1. **Embedding service down** - Cannot generate query embedding
2. **Semantic mismatch** - Query doesn't match memory meaning
3. **Collection filtering** - Searching wrong collection
4. **Empty collection** - No memories stored yet

**Solutions:**
```bash
# Try broader query
/aim-search auth  # instead of "JWT HS256 asymmetric token validation"

# Search all collections
/aim-search your-query --collection all

# Check collection sizes
curl http://localhost:26350/collections
```

See [COMMANDS.md - /aim-search Troubleshooting](docs/COMMANDS.md#search-memory) for complete details.

---

## 💬 Command Issues

For comprehensive command troubleshooting, see [docs/COMMANDS.md](docs/COMMANDS.md).

### /aim-status Shows Service Unavailable

**Quick Fix:**
```bash
# Restart all services
docker compose -f docker/docker-compose.yml restart

# Verify services running
docker compose -f docker/docker-compose.yml ps
```

See [COMMANDS.md - /aim-status](docs/COMMANDS.md#memory-status) for detailed troubleshooting.

---

### /aim-save Succeeds But Summary Not in SessionStart

**Diagnosis:**
```bash
# Check if summary was stored with recent timestamp (V2.0 collection)
curl http://localhost:26350/collections/discussions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "session") | .payload.created_at'
```

**Common Causes:**
1. **Time window filter** - Summary older than 48 hours
2. **Wrong collection** - Stored in wrong collection
3. **Low similarity** - Doesn't match next session's query

See [COMMANDS.md - /aim-save](docs/COMMANDS.md#save-memory) for complete details.

---

## V2.0 Specific Issues

### Triggers Not Firing

**Symptoms**: No automatic context injection on errors/new files

**Check**:
```bash
# Verify hooks are configured
cat .claude/settings.json | jq '.hooks'

# Check hook scripts exist
ls -la .claude/hooks/scripts/

# Test trigger detection
python3 -c "from memory.triggers import detect_decision_keywords; print(detect_decision_keywords('why did we choose React'))"
```

**Fix**: Ensure .claude/settings.json has UserPromptSubmit and PreToolUse hooks configured.

### Metrics Not Appearing in Grafana

**Symptoms**: Grafana panels show "No data"

**Check**:
```bash
# Verify Pushgateway is receiving metrics
curl -s http://localhost:29091/metrics | grep ai_memory_

# Verify Prometheus is scraping
curl -s http://localhost:29090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job == "pushgateway")'
```

**Fix**:
1. Ensure --profile monitoring was used when starting Docker
2. Restart the monitoring stack: docker compose --profile monitoring restart

### Wrong Collection Being Searched

**Symptoms**: Getting code patterns when expecting decisions

**Check**:
```bash
# Test intent detection
python3 -c "from memory.intent import detect_intent; print(detect_intent('why did we choose this approach'))"
```

Expected: IntentType.WHY → searches discussions collection

---

## 🎯 V2.0 Automatic Triggers

V2.0 introduces 5 automatic triggers that retrieve memories based on specific signals. Use this section to debug when triggers aren't working.

### Trigger Overview

| Trigger | Hook | Signal | Collection | Type Filter |
|---------|------|--------|------------|-------------|
| Error Detection | PostToolUse (Bash) | Error text ('Exception:', 'Traceback'), exit code != 0 | code-patterns | `error_fix` |
| New File | PreToolUse (Write) | File doesn't exist | conventions | `naming`, `structure` |
| First Edit | PreToolUse (Edit) | First edit to file in session | code-patterns | `file_pattern` |
| Decision Keywords | UserPromptSubmit | "why did we...", "what was decided" | discussions | `decision` |
| Best Practices | UserPromptSubmit | "best practice", "convention" | conventions | `guideline` |

### Verifying Triggers Fire

**Check hook logs for trigger activation:**

```bash
# Error Detection trigger
grep "error_detection" ~/.ai-memory/logs/hooks.log

# New File trigger
grep "new_file_trigger" ~/.ai-memory/logs/hooks.log

# First Edit trigger
grep "first_edit_trigger" ~/.ai-memory/logs/hooks.log

# Decision Keywords trigger
grep "decision_keyword" ~/.ai-memory/logs/hooks.log

# Best Practices trigger
grep "best_practices_keyword" ~/.ai-memory/logs/hooks.log
```

### Error Detection Trigger Not Working

**Symptoms:** Claude encounters errors but doesn't retrieve relevant error_fix patterns.

**Diagnosis:**

```bash
# 1. Check if error_fix memories exist
curl http://localhost:26350/collections/code-patterns/points/scroll \
  | jq '.result.points[] | select(.payload.type == "error_fix")'

# 2. Check if trigger is configured in settings.json
grep -A 10 "PreToolUse\|PostToolUse" .claude/settings.json | grep -i bash
```

**Common Causes:**
1. **No error_fix memories stored** - Need to capture errors first
2. **Bash tool not in matcher** - Add `Bash` to PostToolUse matcher
3. **Error text not detected** - Check error detection patterns

### New File Trigger Not Working

**Symptoms:** Creating new files doesn't retrieve naming/structure conventions.

**Diagnosis:**

```bash
# 1. Check if conventions exist
curl http://localhost:26350/collections/conventions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "naming" or .payload.type == "structure")'

# 2. Check PreToolUse hook configuration
grep -A 10 "PreToolUse" .claude/settings.json
```

**Common Causes:**
1. **No conventions seeded** - Run `python3 scripts/memory/seed_best_practices.py`
2. **PreToolUse hook not configured** - Add Write to PreToolUse matcher
3. **File already exists** - Trigger only fires for new files

### First Edit Trigger Not Working

**Symptoms:** Editing files doesn't retrieve file_pattern memories.

**Diagnosis:**

```bash
# 1. Check if file_pattern memories exist for the file
FILE_PATH="/path/to/your/file.py"
curl -X POST http://localhost:26350/collections/code-patterns/points/scroll \
  -H "Content-Type: application/json" \
  -d "{\"filter\": {\"must\": [{\"key\": \"file_path\", \"match\": {\"value\": \"$FILE_PATH\"}}]}}" \
  | jq '.result.points'

# 2. Check session tracking (first edit only triggers once per session)
grep "first_edit" ~/.ai-memory/logs/hooks.log | grep "$(date +%Y-%m-%d)"
```

**Common Causes:**
1. **No file_pattern for that file** - Edit and save to create pattern
2. **Already edited in session** - Trigger only fires on first edit
3. **Session tracking issue** - Restart Claude Code session

### Decision Keywords Trigger Not Working

**Symptoms:** Asking "why did we..." doesn't retrieve past decisions.

**Diagnosis:**

```bash
# 1. Check if decisions exist
curl http://localhost:26350/collections/discussions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "decision")'

# 2. Test keyword detection manually
echo "why did we choose Qdrant?" | grep -iE "why did we|what was decided|remember when"
```

**Common Causes:**
1. **No decisions stored** - Decisions must be explicitly saved
2. **Keywords not matching** - Use exact phrases: "why did we", "what was decided"
3. **UserPromptSubmit hook not configured** - Check settings.json

### Best Practices Trigger Not Working

**Symptoms:** Asking about conventions doesn't retrieve guidelines.

**Diagnosis:**

```bash
# 1. Check if best practices exist
curl http://localhost:26350/collections/conventions/points/scroll \
  | jq '.result.points[] | select(.payload.type == "guideline")' | head -50

# 2. Check collection size
curl http://localhost:26350/collections/conventions | jq '.result.points_count'

# 3. Test keyword detection
echo "what is the best practice for logging?" | grep -iE "best practice|convention|how should I"
```

**Common Causes:**
1. **No guidelines seeded** - Run seeding script with `--templates-dir templates/conventions`
2. **Keywords not matching** - Use: "best practice", "convention", "how should I"
3. **Low similarity score** - Guidelines don't match query semantically

### Testing All Triggers

**Quick verification script:**

```bash
#!/bin/bash
echo "=== V2.0 Trigger Verification ==="

# Check collections exist
echo -e "\n1. Collections:"
curl -s http://localhost:26350/collections | jq -r '.result.collections[].name'

# Check memory counts per collection
echo -e "\n2. Memory Counts:"
for col in code-patterns conventions discussions; do
  count=$(curl -s http://localhost:26350/collections/$col | jq -r '.result.points_count // 0')
  echo "  $col: $count"
done

# Check recent hook activity
echo -e "\n3. Recent Hook Activity:"
grep -E "trigger|retrieval" ~/.ai-memory/logs/hooks.log 2>/dev/null | tail -5 || echo "  No recent activity"

echo -e "\n=== Verification Complete ==="
```

---

## ⚡ Performance Issues

### SessionStart Too Slow (>5 seconds)

**Performance Targets:**
- Embedding: <2s
- Search: <500ms
- Total: <3s

**Quick Optimizations:**
```bash
# Reduce retrievals (fewer memories = faster)
export MEMORY_MAX_RETRIEVALS=3

# Increase threshold (fewer low-relevance results)
export MEMORY_SIMILARITY_THRESHOLD=0.7

# Shorter time window
export MEMORY_SESSION_WINDOW_HOURS=24
```

**Diagnosis:**
```bash
# Check hook duration
grep "hook_duration" ~/.ai-memory/logs/hooks.log | tail -20
```

See [CONFIGURATION.md - Performance Tuning](docs/CONFIGURATION.md#performance-tuning) for complete guide.

---

### PostToolUse Blocking (>500ms)

**Should Never Happen** - PostToolUse uses fork pattern to return immediately.

**Diagnosis:**
```bash
# Check if fork is working
grep "background_forked" ~/.ai-memory/logs/hooks.log

# If missing, fork failed - check logs
grep "ERROR" ~/.ai-memory/logs/hooks.log
```

**Solution:**
Verify `post_tool_capture.py` uses subprocess.Popen:
```python
subprocess.Popen([...], start_new_session=True)
sys.exit(0)  # Returns immediately
```

---

## ⚙️ Configuration Issues

For comprehensive configuration troubleshooting, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Environment Variables Not Taking Effect

**Diagnosis:**
```bash
# Check if .env exists
ls -la ~/.ai-memory/.env

# Verify variable is loaded
python3 -c "from memory.config import get_config; print(get_config().qdrant_url)"
```

**Common Mistakes:**
```bash
# WRONG - Don't use quotes
QDRANT_URL="http://localhost:26350"

# CORRECT
QDRANT_URL=http://localhost:26350
```

**File Location:** Must be `~/.ai-memory/.env` (absolute path)

---

### Port Conflicts

**Error:**
```
Bind for 0.0.0.0:26350 failed: port is already allocated
```

**Quick Fix:**
```bash
# Find what's using the port
lsof -i :26350

# Option 1: Kill process
kill <PID>

# Option 2: Change port
echo "QDRANT_EXTERNAL_PORT=16333" >> docker/.env
docker compose -f docker/docker-compose.yml up -d
```

See [CONFIGURATION.md - Port Mapping](docs/CONFIGURATION.md#docker-configuration) for details.

---

## Still Having Issues?

### Enable Debug Logging

```bash
# Set environment variable
export MEMORY_LOG_LEVEL=DEBUG

# Restart Claude Code session
# Logs will be verbose in ~/.ai-memory/logs/
```

### Collect Diagnostic Information

```bash
# Create diagnostic report
mkdir -p /tmp/bmad-diagnostics

# Collect logs
docker compose -f docker/docker-compose.yml logs > /tmp/bmad-diagnostics/docker-logs.txt

# Collect health check
python scripts/health-check.py > /tmp/bmad-diagnostics/health-check.txt 2>&1

# Collect system info
docker info > /tmp/bmad-diagnostics/docker-info.txt
python3 --version > /tmp/bmad-diagnostics/python-version.txt
uname -a > /tmp/bmad-diagnostics/system-info.txt

# Collect config
cp ~/.ai-memory/.env /tmp/bmad-diagnostics/.env 2>/dev/null || echo "No .env file"
cp .claude/settings.json /tmp/bmad-diagnostics/settings.json 2>/dev/null || echo "No settings.json"

# Create archive
tar -czf bmad-diagnostics.tar.gz -C /tmp bmad-diagnostics/

echo "Diagnostic archive created: bmad-diagnostics.tar.gz"
```

### Report an Issue

When reporting issues, include:

1. Diagnostic archive (see above)
2. Steps to reproduce the issue
3. Expected vs actual behavior
4. Claude Code version
5. OS and Docker version

---

**Sources (2026 Best Practices):**

- [Best practices | Docker Docs](https://docs.docker.com/build/building/best-practices/)
- [Docker Best Practices 2025](https://thinksys.com/devops/docker-best-practices/)
- [NEW Docker 2025: 42 Prod Best Practices](https://docs.benchhub.co/docs/tutorials/docker/docker-best-practices-2025)
- [Engine v29 Release Notes](https://docs.docker.com/engine/release-notes/29/)
- [10 Docker Best Practices](https://www.nilebits.com/blog/2024/03/10-docker-best-practices/)
