# BMAD Memory Module - Recovery Procedures

**Purpose:** Rapid recovery guide for common memory system failures
**Audience:** Operators troubleshooting Claude Code memory issues
**Owner:** BMAD Memory Module Team
**Version:** 1.0.0
**Last Updated:** 2026-01-13
**Last Validated:** 2026-01-13

---

## Table of Contents

- [Quick Reference](#quick-reference)
- [Qdrant Unavailable](#qdrant-unavailable)
- [Embedding Service Unavailable](#embedding-service-unavailable)
- [Queue File Issues](#queue-file-issues)
- [Comprehensive Health Check](#comprehensive-health-check)
- [Common Issues](#common-issues)
- [Platform-Specific Troubleshooting](#platform-specific-troubleshooting)
- [Performance Troubleshooting](#performance-troubleshooting)
- [Log Interpretation Guide](#log-interpretation-guide)

---

## Quick Reference

**Symptom-to-Solution Mapping** (Fastest recovery path first)

| Symptom | Likely Cause | First Diagnostic Command | Recovery Command | Recovery Time |
|---------|--------------|--------------------------|------------------|---------------|
| Hook returns exit code 1 | Qdrant unavailable | `docker compose ps qdrant` | `docker compose up -d qdrant` | 30-60s |
| `embedding_status: pending` in payloads | Embedding service down | `docker compose ps embedding` | `docker compose restart embedding` | 30-90s |
| Empty session context at SessionStart | No memories captured yet | `ls -lah ~/.claude-memory/pending_queue.jsonl` | Check if hooks configured | Varies |
| Slow hook execution (>2s) | Cold embedding service | `curl http://localhost:28080/health` | `docker compose restart embedding` | 30s |
| "QDRANT_UNAVAILABLE" in logs | Qdrant connection refused | `curl http://localhost:26350/health` | `docker compose up -d qdrant` | 30-60s |
| Backfill script hangs | Stale lock file | `ls -lah ~/.claude-memory/*.lock` | `rm ~/.claude-memory/backfill.lock` | Instant |
| Queue file corrupt | Interrupted write | `python -m json.tool < pending_queue.jsonl` | `python scripts/memory/repair_queue.py` | 1-5min |
| Memory search returns nothing | Embeddings not generated | Check `embedding_status` in Qdrant | `python scripts/memory/backfill_embeddings.py` | 1-10min |
| Port 26350 already in use | Qdrant port conflict | `lsof -i :26350` or `netstat -an \| grep 26350` | Stop conflicting process or change port | Varies |
| Docker Compose fails to start | Insufficient resources | `docker system info \| grep -E 'CPUs\|Total Memory'` | Free resources or adjust limits | Varies |

---

## Qdrant Unavailable

### Symptoms

- Hooks exit with code 1 (graceful degradation - Claude continues working)
- Logs show "QDRANT_UNAVAILABLE" or "Connection refused" errors
- Memories queued to `~/.claude-memory/pending_queue.jsonl` but not stored in Qdrant
- SessionStart hook returns empty context despite previous sessions
- `curl http://localhost:26350/health` returns connection error

### Root Causes

1. **Qdrant container stopped**: Most common - Docker container exited
2. **Docker daemon down**: Rare - entire Docker service stopped
3. **Port conflict**: Another service using port 26350
4. **Resource exhaustion**: Out of memory/disk space

### Diagnosis (Run in Order)

```bash
# Step 1: Check Qdrant container status
docker compose -f ~/.bmad-memory/docker/docker-compose.yml ps qdrant

# Expected if stopped:
# NAME                    COMMAND             SERVICE   STATUS    PORTS
# bmad-memory-qdrant-1    ./qdrant           qdrant    exited

# Step 2: Check Docker daemon
docker ps
# If fails: "Cannot connect to Docker daemon" - Docker daemon down

# Step 3: Check Qdrant logs
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs qdrant --tail 50

# Step 4: Check port conflict (if Qdrant won't start)
lsof -i :26350
# or on Linux:
netstat -tuln | grep 26350

# Step 5: Check Qdrant health endpoint (if container running but unhealthy)
curl http://localhost:26350/health
# Expected healthy response: {"status":"pass"}
```

### Recovery Steps

#### Scenario A: Container Stopped (Most Common)

```bash
# 1. Start Qdrant
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d qdrant

# 2. Wait for healthy (30-60s)
# Retry every 5s until health check passes
while ! curl -f http://localhost:26350/health 2>/dev/null; do
    echo "Waiting for Qdrant..."
    sleep 5
done

echo "✓ Qdrant healthy"

# 3. Verify collections exist
curl http://localhost:26350/collections
# Should show: {"collections":[{"name":"code-patterns"},{"name":"conventions"}]}

# 4. Process queued memories (if any)
python scripts/memory/backfill_embeddings.py

# 5. Verify queue cleared
python scripts/memory/backfill_embeddings.py --stats
# Should show: "Pending items: 0"
```

**Expected Recovery Time:** 1-2 minutes

#### Scenario B: Docker Daemon Down

```bash
# 1. Start Docker daemon
sudo systemctl start docker
# or on macOS:
open -a Docker

# 2. Wait for Docker ready (30-60s)
until docker ps > /dev/null 2>&1; do
    echo "Waiting for Docker..."
    sleep 5
done

# 3. Start full stack
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d

# 4. Wait for Qdrant healthy
# (Use wait loop from Scenario A Step 2)

# 5. Process queued memories
python scripts/memory/backfill_embeddings.py
```

**Expected Recovery Time:** 2-5 minutes

#### Scenario C: Port Conflict

```bash
# 1. Identify conflicting process
lsof -i :26350
# Shows: PID and process name

# 2. Stop conflicting process OR change Qdrant port
# Option 1: Stop conflicting process (if safe)
kill <PID>

# Option 2: Change Qdrant port (permanent fix)
# Edit ~/.bmad-memory/docker/docker-compose.yml
# Change: "26350:6333" to "26351:6333"
# Update QDRANT_URL in src/memory/config.py: QDRANT_URL = "http://localhost:16351"

# 3. Start Qdrant
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d qdrant

# 4. Verify healthy on new port
curl http://localhost:16351/health  # If port changed
```

**Expected Recovery Time:** 5-10 minutes (if port change required)

#### Scenario D: Resource Exhaustion

```bash
# 1. Check disk space
df -h ~/.bmad-memory
# If <1GB free: Clear space

# 2. Check Docker resource limits
docker system info | grep -E 'CPUs|Total Memory'

# 3. Prune unused Docker resources
docker system prune -f

# 4. Start Qdrant
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d qdrant
```

**Expected Recovery Time:** Varies (depends on cleanup)

### Verification Commands

```bash
# 1. Container running
docker compose -f ~/.bmad-memory/docker/docker-compose.yml ps qdrant
# STATUS should be "running" (not "exited")

# 2. Health check passes
curl http://localhost:26350/health
# Response: {"status":"pass"}

# 3. Collections accessible
curl http://localhost:26350/collections
# Response: {"collections":[...]}

# 4. Can store test memory
python -c "
from memory.storage import MemoryStorage
storage = MemoryStorage()
result = storage.store_memory(
    content='Recovery test',
    group_id='test',
    memory_type='implementation',
    source_hook='Manual',
    session_id='recovery-test'
)
print(f'✓ Test memory stored: {result[\"memory_id\"][:8]}...')
"

# 5. Can search
python -c "
from memory.search import MemorySearch
search = MemorySearch()
results = search.search(query='Recovery test', collection='code-patterns', limit=1)
print(f'✓ Search working: {len(results)} results')
"
```

### Rollback Steps (If Recovery Fails)

```bash
# 1. Stop all services
docker compose -f ~/.bmad-memory/docker/docker-compose.yml down

# 2. Check for conflicting processes
docker ps -a | grep qdrant
# Remove any zombie containers:
docker rm -f <container-id>

# 3. Reset volumes (DESTRUCTIVE - only if data loss acceptable)
# WARNING: This deletes all stored memories!
docker compose -f ~/.bmad-memory/docker/docker-compose.yml down -v

# 4. Restart from clean state
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d

# 5. Verify clean start
curl http://localhost:26350/health
```

### Prevention & Monitoring

- **Daily health check**: Add `curl http://localhost:26350/health` to cron
- **Docker auto-restart**: Services configured with `restart: unless-stopped`
- **Disk space monitoring**: Alert when <5GB free in ~/.bmad-memory
- **Log rotation**: Prevent log files from filling disk

### Escalation Path

If recovery fails after 3 attempts:
1. Check GitHub issues: https://github.com/qdrant/qdrant/issues
2. Qdrant documentation: https://qdrant.tech/documentation/
3. Check system logs: `journalctl -u docker` (Linux) or Console.app (macOS)
4. Contact support with:
   - Output of all diagnostic commands
   - Qdrant logs: `docker compose logs qdrant > qdrant.log`
   - System info: `docker system info > system.log`

---

## Embedding Service Unavailable

### Symptoms

- Memories stored with `embedding_status: pending` in Qdrant payloads
- Semantic search returns no/few results despite memories existing
- SessionStart hook returns limited context (sparse vector search only)
- Logs show "EMBEDDING_UNAVAILABLE" or "Connection timeout" errors
- `curl http://localhost:28080/health` returns connection error or timeout

### Root Causes

1. **Service container stopped**: Most common
2. **Model loading incomplete**: Service started but Jina model still loading (~30s)
3. **Resource exhaustion**: Out of memory (model requires ~2GB RAM)
4. **Port conflict**: Another service using port 28080

### Diagnosis (Run in Order)

```bash
# Step 1: Check embedding service status
docker compose -f ~/.bmad-memory/docker/docker-compose.yml ps embedding

# Step 2: Check service logs (look for "Model loaded" message)
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs embedding --tail 50 | grep -E "Model|Ready|Error"

# Expected healthy log line:
# "Jina Embeddings v2 Base EN model loaded successfully (768d)"

# Step 3: Check health endpoint
curl http://localhost:28080/health
# Expected response: {"status":"healthy","model":"jinaai/jina-embeddings-v2-base-en","dimension":768}

# Step 4: Check for pending embeddings in Qdrant
python -c "
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import os

client = QdrantClient(url='http://localhost:26350')
results = client.scroll(
    collection_name='code-patterns',
    scroll_filter=Filter(
        must=[FieldCondition(key='embedding_status', match=MatchValue(value='pending'))]
    ),
    limit=100
)
print(f'Pending embeddings: {len(results[0])}')
"

# Step 5: Test embedding generation
curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["test"]}'
# Expected: {"embeddings":[[0.123,...]], "dimension":768}
```

### Recovery Steps

#### Scenario A: Container Stopped

```bash
# 1. Start embedding service
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d embedding

# 2. Wait for model load (15-45s - watch logs)
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs -f embedding | grep "Model loaded"
# Press Ctrl+C when you see "Jina Embeddings v2 Base EN model loaded successfully"

# 3. Verify health
curl http://localhost:28080/health
# Should return: {"status":"healthy","model":"jinaai/jina-embeddings-v2-base-en","dimension":768}

# 4. Test embedding generation
curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["Recovery test embedding"]}'
# Should return array of 768-dimensional vectors

# 5. Backfill pending embeddings
python scripts/memory/backfill_embeddings.py --verbose

# 6. Verify backfill complete
python scripts/memory/backfill_embeddings.py --stats
# Should show: "Pending embeddings: 0"
```

**Expected Recovery Time:** 2-5 minutes

#### Scenario B: Service Running But Model Not Loaded

```bash
# 1. Restart to force reload
docker compose -f ~/.bmad-memory/docker/docker-compose.yml restart embedding

# 2. Monitor model loading
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs -f embedding

# Look for:
# "Loading Jina Embeddings v2 model..."
# "Model loaded successfully"

# If stuck >3 minutes, restart again
```

**Expected Recovery Time:** 30-90 seconds

#### Scenario C: Resource Exhaustion

```bash
# 1. Check Docker memory limits
docker stats --no-stream embedding
# If MEM USAGE near limit: Increase Docker memory

# 2. Check system memory
free -h  # Linux
vm_stat | perl -ne '/page size of (\d+)/ and $size=$1;/Pages free:\s+(\d+)/&& print($1*$size/1073741824), "GB free\n"'  # macOS

# 3. If insufficient memory (<3GB free):
# - Close other applications
# - Or increase Docker Desktop memory limit (Settings → Resources → Memory)

# 4. Restart embedding service with more resources
docker compose -f ~/.bmad-memory/docker/docker-compose.yml stop embedding
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d embedding

# 5. Monitor startup
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs -f embedding
```

**Expected Recovery Time:** 2-10 minutes (if config change needed)

#### Scenario D: Port Conflict

```bash
# 1. Check port 28080
lsof -i :28080
# or on Linux:
netstat -tuln | grep 28080

# 2. Stop conflicting service OR change embedding port
# Option 1: Stop conflicting service (if safe)
kill <PID>

# Option 2: Change embedding port (permanent)
# Edit ~/.bmad-memory/docker/docker-compose.yml
# Change: "28080:8080" to "28081:8080"
# Update EMBEDDING_URL in src/memory/config.py: EMBEDDING_URL = "http://localhost:8001"

# 3. Start embedding service
docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d embedding
```

**Expected Recovery Time:** 5-10 minutes (if port change required)

### Verification Commands

```bash
# 1. Container running
docker compose -f ~/.bmad-memory/docker/docker-compose.yml ps embedding
# STATUS: running

# 2. Health endpoint responds
curl http://localhost:28080/health
# Response: {"status":"healthy","model":"jinaai/jina-embeddings-v2-base-en","dimension":768}

# 3. Model loaded (check logs)
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs embedding | grep "Model loaded"
# Should show: "Jina Embeddings v2 Base EN model loaded successfully"

# 4. Embedding generation works
time curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["test embedding generation"]}'
# Should complete in <2 seconds
# Response format: {"embeddings":[[0.123,...],"dimension":768}

# 5. No pending embeddings
python scripts/memory/backfill_embeddings.py --stats
# Should show: "Pending embeddings: 0" or very low count

# 6. Semantic search working
python -c "
from memory.search import MemorySearch
search = MemorySearch()
# Store test memory
from memory.storage import MemoryStorage
storage = MemoryStorage()
storage.store_memory(
    content='Embedding recovery test - semantic search validation',
    group_id='test',
    memory_type='implementation',
    source_hook='Manual',
    session_id='recovery-test'
)
# Search should find it
import time
time.sleep(2)  # Wait for embedding generation
results = search.search(
    query='semantic search validation',
    collection='code-patterns',
    limit=5
)
print(f'✓ Semantic search working: {len(results)} results')
"
```

### Performance Monitoring

```bash
# Check embedding generation latency
time curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["performance test"]}'

# Should complete in:
# - <500ms: Cold start (first request after restart)
# - <200ms: Warm (subsequent requests)
# - >2000ms: PROBLEM - investigate resource constraints
```

### Rollback Steps

```bash
# If embedding service recovery fails completely:

# 1. Stop service
docker compose -f ~/.bmad-memory/docker/docker-compose.yml stop embedding

# 2. System still functional - memories stored with pending status
# Semantic search degrades to sparse-only (BM25)

# 3. Escalate to team/support
```

### Prevention & Monitoring

- **Pre-warm on restart**: Docker Compose configured with `restart: unless-stopped`
- **Health checks**: Service includes `/health` endpoint for monitoring
- **Resource allocation**: Ensure ≥3GB RAM available for Docker
- **Model cache**: Jina model cached in Docker volume, fast restarts

### Escalation Path

If recovery fails after 3 attempts:
1. Check embedding service logs: `docker compose logs embedding > embedding.log`
2. Verify model file integrity (inside container): `docker compose exec embedding ls -lh /models`
3. Test with simpler embedding: Replace Jina with all-MiniLM-L6-v2 (384d)
4. Contact support with:
   - Embedding service logs
   - System memory: `free -h` (Linux) or `vm_stat` (macOS)
   - Docker stats: `docker stats --no-stream > stats.log`

---

## Queue File Issues

### Symptoms

- Backfill script fails with "corrupt queue" or JSON parsing error
- Backfill script hangs with "waiting for lock"
- Lock acquisition timeout errors in logs
- Queue file exists but memories not processed
- `cat ~/.claude-memory/pending_queue.jsonl | wc -l` shows entries but backfill reports 0

### Root Causes

1. **Stale lock file**: Previous backfill crashed, lock not released
2. **Corrupt JSON**: Process killed during write, incomplete line
3. **Permission issues**: Queue file not readable/writable
4. **Disk full**: Write interrupted, partial entry

### Diagnosis (Run in Order)

```bash
# Step 1: Check queue file exists and size
ls -lah ~/.claude-memory/pending_queue.jsonl
# Expected: File exists, size > 0 if pending items

# Step 2: Check for stale lock
ls -lah ~/.claude-memory/*.lock
# If lock older than 1 hour: Likely stale

# Example lock check:
find ~/.claude-memory -name "*.lock" -mmin +60 -ls
# If found: Lock not released properly

# Step 3: Validate JSON format (line by line)
python -c "
import json
import sys
try:
    with open('$HOME/.claude-memory/pending_queue.jsonl', 'r') as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                json.loads(line)
    print(f'✓ Queue valid: {i} entries')
except json.JSONDecodeError as e:
    print(f'✗ Corrupt at line {i}: {e}')
    sys.exit(1)
"

# Step 4: Check file permissions
stat -c '%a %U %G' ~/.claude-memory/pending_queue.jsonl
# Expected: 600 (owner-only r/w)

# Step 5: Check disk space
df -h ~/.claude-memory
# If <1GB: Risk of corruption on future writes
```

### Recovery Steps

#### Scenario A: Stale Lock File (Most Common)

```bash
# 1. Verify no backfill process running
ps aux | grep backfill_embeddings.py | grep -v grep
# If empty: Safe to remove lock

# 2. Remove stale lock
rm -f ~/.claude-memory/backfill.lock

# 3. Run backfill
python scripts/memory/backfill_embeddings.py --verbose

# 4. Verify success
python scripts/memory/backfill_embeddings.py --stats
# Should show: "Pending items: 0" or reduced count
```

**Expected Recovery Time:** <1 minute

#### Scenario B: Corrupt Queue File

```bash
# 1. Backup queue file
cp ~/.claude-memory/pending_queue.jsonl ~/.claude-memory/pending_queue.jsonl.backup.$(date +%Y%m%d_%H%M%S)

# 2. Identify corrupt lines
python -c "
import json
import sys

corrupt_lines = []
valid_lines = []

with open('$HOME/.claude-memory/pending_queue.jsonl', 'r') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            valid_lines.append(line)
        except json.JSONDecodeError as e:
            corrupt_lines.append((i, line, str(e)))
            print(f'Line {i} corrupt: {line[:50]}... Error: {e}')

print(f'\nValid: {len(valid_lines)}, Corrupt: {len(corrupt_lines)}')

# Write valid entries to new file
if corrupt_lines:
    with open('$HOME/.claude-memory/pending_queue.jsonl.repaired', 'w') as out:
        for line in valid_lines:
            out.write(line + '\n')
    print(f'Wrote {len(valid_lines)} valid entries to pending_queue.jsonl.repaired')
"

# 3. Replace with repaired file
mv ~/.claude-memory/pending_queue.jsonl ~/.claude-memory/pending_queue.jsonl.corrupt
mv ~/.claude-memory/pending_queue.jsonl.repaired ~/.claude-memory/pending_queue.jsonl

# 4. Run backfill on repaired queue
python scripts/memory/backfill_embeddings.py --verbose

# 5. Verify success
python scripts/memory/backfill_embeddings.py --stats
```

**Expected Recovery Time:** 1-5 minutes

**Data Loss Assessment:**
- Corrupt lines are lost (typically 1-2 entries if interrupted during write)
- Valid entries preserved
- Hook will re-queue any new failures

#### Scenario C: Permission Issues

```bash
# 1. Check current permissions
ls -la ~/.claude-memory/pending_queue.jsonl

# 2. Fix permissions
chmod 600 ~/.claude-memory/pending_queue.jsonl
chown $(whoami) ~/.claude-memory/pending_queue.jsonl

# 3. Verify queue directory permissions
chmod 700 ~/.claude-memory
chown $(whoami) ~/.claude-memory

# 4. Run backfill
python scripts/memory/backfill_embeddings.py --verbose
```

**Expected Recovery Time:** <1 minute

#### Scenario D: Disk Full

```bash
# 1. Check disk space
df -h ~/.claude-memory

# 2. If <1GB free: Clear space
# - Remove old Docker logs: docker system prune -f
# - Remove old backups: rm ~/.claude-memory/*.backup.*
# - Archive old logs: tar -czf logs.tar.gz ~/.claude-memory/logs && rm -rf ~/.claude-memory/logs/*.log

# 3. Verify queue file integrity (might be truncated)
# Use Scenario B repair steps if needed

# 4. Run backfill
python scripts/memory/backfill_embeddings.py --verbose
```

**Expected Recovery Time:** 5-10 minutes (depends on cleanup)

### Verification Commands

```bash
# 1. Queue file valid JSON
python -c "
import json
with open('$HOME/.claude-memory/pending_queue.jsonl', 'r') as f:
    entries = [json.loads(line) for line in f if line.strip()]
print(f'✓ Queue valid: {len(entries)} entries')
"

# 2. No stale locks
find ~/.claude-memory -name "*.lock" -mmin +5 -ls
# Should be empty (no locks older than 5 minutes)

# 3. Backfill runs successfully
python scripts/memory/backfill_embeddings.py --dry-run
# Should complete without errors

# 4. Queue stats accurate
python scripts/memory/backfill_embeddings.py --stats
# Should show current queue size

# 5. File permissions correct
stat -c '%a' ~/.claude-memory/pending_queue.jsonl | grep -q '^600$' && echo "✓ Permissions OK" || echo "✗ Permissions wrong"
```

### Advanced Recovery: Manual Queue Repair

If automated repair fails, manually rebuild queue:

```bash
# 1. Extract valid entries
python -c "
import json

valid = []
with open('$HOME/.claude-memory/pending_queue.jsonl', 'rb') as f:
    data = f.read().decode('utf-8', errors='ignore')
    for line in data.split('\n'):
        try:
            if line.strip():
                entry = json.loads(line)
                # Validate required fields
                assert 'id' in entry
                assert 'memory_data' in entry
                assert 'queued_at' in entry
                valid.append(line)
        except:
            continue

# Write valid entries
with open('$HOME/.claude-memory/pending_queue.jsonl.manual', 'w') as out:
    out.write('\n'.join(valid) + '\n')

print(f'Extracted {len(valid)} valid entries')
"

# 2. Backup old queue
mv ~/.claude-memory/pending_queue.jsonl ~/.claude-memory/pending_queue.jsonl.broken

# 3. Use manually repaired queue
mv ~/.claude-memory/pending_queue.jsonl.manual ~/.claude-memory/pending_queue.jsonl
chmod 600 ~/.claude-memory/pending_queue.jsonl

# 4. Run backfill
python scripts/memory/backfill_embeddings.py --verbose
```

### Prevention & Monitoring

- **File locking**: Queue uses fcntl.flock to prevent concurrent write corruption
- **Atomic writes**: Temp file + rename pattern prevents partial writes
- **Disk monitoring**: Alert when <5GB free
- **Auto-cleanup**: Backfill script removes processed entries
- **Permissions**: Queue files created with 0600 (owner-only)

### Rollback Steps

```bash
# If queue repair fails and data loss unacceptable:

# 1. Restore from backup
cp ~/.claude-memory/pending_queue.jsonl.backup.YYYYMMDD_HHMMSS ~/.claude-memory/pending_queue.jsonl

# 2. Verify backup valid
python -c "import json; [json.loads(l) for l in open('$HOME/.claude-memory/pending_queue.jsonl') if l.strip()]"

# 3. Run backfill
python scripts/memory/backfill_embeddings.py --verbose
```

### Escalation Path

If queue recovery fails after 3 attempts:
1. Collect diagnostics:
   ```bash
   # Save queue state
   cp ~/.claude-memory/pending_queue.jsonl ~/queue_issue.jsonl

   # Hex dump for binary analysis
   hexdump -C ~/.claude-memory/pending_queue.jsonl > queue_hexdump.txt

   # File info
   file ~/.claude-memory/pending_queue.jsonl > queue_file_info.txt
   ls -la ~/.claude-memory/*.lock > locks_info.txt
   ```
2. Check if memories stored in Qdrant despite queue issues:
   ```bash
   python -c "
   from qdrant_client import QdrantClient
   client = QdrantClient(url='http://localhost:26350')
   for collection in ['code-patterns', 'conventions']:
       info = client.get_collection(collection)
       print(f'{collection}: {info.points_count} memories')
   "
   ```
3. Report with collected files to support/GitHub issues

---

## Comprehensive Health Check

### Purpose

Validate all memory system components in one command - useful after:
- Fresh installation
- System restart
- Recovery from any failure
- Before important coding sessions

### Quick Health Check Script

**Location:** `scripts/memory/health_check.sh`

The health check script validates all memory system components and provides actionable recovery commands. See the script source for implementation details.

**What it checks:**
1. Docker daemon status
2. Qdrant container and health endpoint
3. Qdrant collections exist
4. Embedding service container and health
5. Embedding generation functionality
6. Queue file status
7. Stale lock detection
8. Disk space availability
9. End-to-end storage and retrieval test

### Usage

```bash
# Run health check
bash scripts/memory/health_check.sh

# Or make executable and run directly
chmod +x scripts/memory/health_check.sh
./scripts/memory/health_check.sh

# Check return code
if ./scripts/memory/health_check.sh; then
    echo "System healthy"
else
    echo "System needs attention"
fi
```

### Expected Output (Healthy System)

```
=== BMAD Memory Module Health Check ===

Docker daemon... ✓ Running
Qdrant container... ✓ Running
Qdrant health... ✓ Healthy
Qdrant collections... ✓ Found 2 collections
Embedding service... ✓ Running
Embedding health... ✓ Healthy
Embedding generation... ✓ Working
Queue file... ✓ Empty (no pending items)
Stale locks... ✓ None
Disk space... ✓ 25GB free
End-to-end test... ✓ Passed

=== Summary ===
✓ All checks passed - system healthy
```

### Expected Output (Issues Found)

```
=== BMAD Memory Module Health Check ===

Docker daemon... ✓ Running
Qdrant container... ✗ Not running
  → Run: docker compose -f ~/.bmad-memory/docker/docker-compose.yml up -d qdrant
  → See: docs/RECOVERY.md#qdrant-unavailable
Qdrant health... ✗ Unhealthy
  → See: docs/RECOVERY.md#qdrant-unavailable
[... rest of checks ...]

=== Summary ===
✗ 2 errors, 1 warnings - recovery needed

See docs/RECOVERY.md for detailed recovery procedures
```

---

## Common Issues

### Empty Context at SessionStart (No Memories)

**Symptoms:**
- SessionStart hook completes but provides no memory context
- Claude doesn't mention any previous sessions

**Common Causes:**
1. **First time using memory system** - No memories captured yet
2. **Hooks not configured** - PostToolUse hook never ran
3. **Different project detected** - `group_id` mismatch
4. **Qdrant empty** - Data loss or fresh start

**Diagnosis:**
```bash
# Check if any memories exist
curl http://localhost:26350/collections/code-patterns | grep points_count
# If 0: No memories stored yet

# Check hook configuration
cat .claude/settings.json | grep -A 5 hooks

# Check recent PostToolUse hook execution
grep "PostToolUse" ~/.claude/logs/* | tail -10
```

**Resolution:**
- If first use: Normal - memories accumulate after Write/Edit operations
- If hooks missing: See installation docs
- If wrong project: Verify `group_id` matches current directory

---

### Slow Performance (>2s Hook Execution)

**Symptoms:**
- Hooks take >2 seconds to complete
- Claude waits before responding

**Common Causes:**
1. **Cold embedding service** - Model not pre-warmed
2. **Network latency** - Docker containers on slow network
3. **Resource contention** - CPU/memory starved

**Diagnosis:**
```bash
# Check embedding latency
time curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["test"]}'

# Check Docker resource usage
docker stats --no-stream
```

**Resolution:**
```bash
# Restart embedding service to pre-warm model
docker compose -f ~/.bmad-memory/docker/docker-compose.yml restart embedding

# Increase Docker resources (Settings → Resources)
# Recommended: 4GB RAM, 2 CPUs
```

---

### Memories Not Appearing in Search

**Symptoms:**
- Memories stored successfully (visible in Qdrant)
- Search returns no results or wrong results

**Common Causes:**
1. **Embeddings pending** - `embedding_status: pending` in payloads
2. **Query mismatch** - Semantic search requires similar language
3. **Collection mismatch** - Searching wrong collection

**Diagnosis:**
```bash
# Check embedding status in Qdrant
python -c "
from qdrant_client import QdrantClient
client = QdrantClient(url='http://localhost:26350')
results = client.scroll(collection_name='code-patterns', limit=5)
for point in results[0]:
    print(f'ID: {point.id}, embedding_status: {point.payload.get(\"embedding_status\")}')
"

# Check collection counts
curl http://localhost:26350/collections
```

**Resolution:**
```bash
# Backfill pending embeddings
python scripts/memory/backfill_embeddings.py --verbose

# Verify embeddings complete
python scripts/memory/backfill_embeddings.py --stats
```

---

## Platform-Specific Troubleshooting

### macOS (Docker Desktop)

**Issue: Docker Compose not found**
```bash
# Symptom: "docker compose: command not found"
# Resolution: Use docker-compose (hyphenated) for older Docker Desktop
docker-compose -f ~/.bmad-memory/docker/docker-compose.yml up -d
```

**Issue: Port already allocated**
```bash
# Symptom: "port is already allocated"
# Resolution: Check AirPlay Receiver (uses port 5000)
# System Preferences → Sharing → AirPlay Receiver (disable)

# Or change ports in docker-compose.yml
```

**Issue: File sharing permissions**
```bash
# Symptom: "Permission denied" mounting volumes
# Resolution: Add ~/.bmad-memory to Docker Desktop file sharing
# Docker Desktop → Settings → Resources → File Sharing → Add
```

---

### Windows (WSL2)

**Issue: Docker daemon not accessible**
```bash
# Symptom: "Cannot connect to Docker daemon"
# Resolution: Ensure Docker Desktop WSL2 integration enabled
# Docker Desktop → Settings → Resources → WSL Integration → Enable distro
```

**Issue: Line ending issues**
```bash
# Symptom: Scripts fail with "^M: bad interpreter"
# Resolution: Convert line endings
dos2unix scripts/memory/*.sh
# Or in git:
git config core.autocrlf input
```

**Issue: Path resolution**
```bash
# Symptom: "~/.bmad-memory not found"
# Resolution: Use full WSL path
/home/<username>/.bmad-memory
```

---

### Linux

**Issue: Docker permission denied**
```bash
# Symptom: "permission denied while trying to connect to Docker daemon"
# Resolution: Add user to docker group
sudo usermod -aG docker $USER
newgrp docker  # Or logout/login
```

**Issue: Systemd Docker not starting**
```bash
# Symptom: "Failed to start docker.service"
# Resolution: Check journalctl
journalctl -u docker.service -n 50

# Common fix: Clear Docker state
sudo systemctl stop docker
sudo rm -rf /var/lib/docker
sudo systemctl start docker
```

---

## Performance Troubleshooting

### High Memory Usage

**Symptoms:**
- Docker container using >4GB RAM
- System becomes unresponsive

**Diagnosis:**
```bash
# Check Docker stats
docker stats --no-stream

# Check Qdrant memory
curl http://localhost:26350/collections/code-patterns
# Look at vectors_count - high count increases memory
```

**Resolution:**
```bash
# Increase Docker Desktop memory limit
# Settings → Resources → Memory → 8GB+

# Or reduce Qdrant collection size (destructive)
# Delete old memories via Streamlit browser
```

---

### Slow Embedding Generation

**Symptoms:**
- Embedding requests take >2 seconds
- PostToolUse hook slow

**Diagnosis:**
```bash
# Benchmark embedding speed
time curl -X POST http://localhost:28080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts":["benchmark test"]}'
```

**Resolution:**
```bash
# Check if model loaded
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs embedding | grep "Model loaded"

# Restart to force model reload
docker compose -f ~/.bmad-memory/docker/docker-compose.yml restart embedding

# Allocate more CPU to Docker (Settings → Resources → CPUs → 4+)
```

---

## Log Interpretation Guide

### Common Log Patterns

**Successful Memory Storage:**
```
INFO memory_stored extra={'memory_id': 'abc123...', 'type': 'implementation', 'group_id': 'my-project'}
```

**Graceful Degradation (Qdrant Down):**
```
WARNING qdrant_unavailable extra={'error': 'Connection refused', 'code': 'QDRANT_UNAVAILABLE'}
INFO memory_queued extra={'queue_path': '~/.claude-memory/pending_queue.jsonl', 'memory_id': 'abc123'}
```

**Embedding Pending:**
```
INFO memory_stored_pending extra={'memory_id': 'abc123', 'embedding_status': 'pending'}
```

**Backfill Success:**
```
INFO backfill_complete extra={'processed': 42, 'errors': 0, 'duration_seconds': 123.45}
```

### Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| `QDRANT_UNAVAILABLE` | Cannot connect to Qdrant | See [Qdrant Unavailable](#qdrant-unavailable) |
| `EMBEDDING_TIMEOUT` | Embedding service timeout | See [Embedding Service Unavailable](#embedding-service-unavailable) |
| `QUEUE_CORRUPT` | Queue file JSON invalid | See [Queue File Issues](#queue-file-issues) |
| `LOCK_TIMEOUT` | Cannot acquire file lock | Remove stale lock: `rm ~/.claude-memory/*.lock` |
| `INVALID_INPUT` | Malformed request | Check input data format |
| `INTERNAL_ERROR` | Unexpected error | Check logs, escalate if persistent |

### Log Locations

```bash
# Claude Code logs
~/.claude/logs/

# Docker Compose logs
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs

# Qdrant logs
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs qdrant

# Embedding service logs
docker compose -f ~/.bmad-memory/docker/docker-compose.yml logs embedding

# System logs (Linux)
journalctl -u docker

# System logs (macOS)
# Console.app → Show Docker Desktop
```

---

**End of Recovery Documentation**

For installation and setup, see [README.md](../README.md)
For Docker configuration, see [docker/README.md](../docker/README.md)
For project instructions, see [CLAUDE.md](../CLAUDE.md)
