# Troubleshooting Guide

## Quick Diagnostic Commands

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

## Known Issues in v1.0.0

### Embedding Model Re-downloads on Every Restart
**Fixed in**: v1.0.1
**Symptom**: First container start takes 80-90 seconds to download embedding model. Subsequent restarts also take 80-90 seconds.
**Workaround**: None - upgrade to v1.0.1 which persists the model cache.

### Installer Times Out on First Start
**Fixed in**: v1.0.1
**Symptom**: Installation appears to fail with "Timed out waiting for services" but services actually work.
**Workaround**: Ignore the error if `docker compose ps` shows services as healthy. Or upgrade to v1.0.1.

### Missing requirements.txt
**Fixed in**: v1.0.1
**Symptom**: Cannot install Python dependencies for testing.
**Workaround**: Use `requirements-dev.txt` or upgrade to v1.0.1.

## Services Won't Start

### Symptom: Docker Compose Fails

**Error:**

```
Error response from daemon: driver failed programming external connectivity on endpoint bmad-qdrant: Bind for 0.0.0.0:26350 failed: port is already allocated
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
   # Logs will appear in ~/.bmad-memory/logs/hook.log
   tail -f ~/.bmad-memory/logs/hook.log
   ```

### Symptom: Permission Denied Writing to Installation Directory

**Error in logs:**

```
PermissionError: [Errno 13] Permission denied: '/home/user/.bmad-memory/logs/hook.log'
```

**Solution:**

```bash
# Fix permissions on installation directory
chmod -R u+w ~/.bmad-memory

# Verify
ls -la ~/.bmad-memory
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
   docker stats bmad-embedding
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
   docker stats bmad-qdrant
   # If CPU >90% or MEM maxed out, restart
   ```

3. Clear cache if corrupted:
   ```bash
   rm -rf ~/.bmad-memory/cache/*
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

## Still Having Issues?

### Enable Debug Logging

```bash
# Set environment variable
export MEMORY_LOG_LEVEL=DEBUG

# Restart Claude Code session
# Logs will be verbose in ~/.bmad-memory/logs/
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
cp ~/.bmad-memory/.env /tmp/bmad-diagnostics/.env 2>/dev/null || echo "No .env file"
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
