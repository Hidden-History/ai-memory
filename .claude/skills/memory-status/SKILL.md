---
name: memory-status
description: 'Show memory system health and statistics'
allowed-tools: Read, Bash
---

# Memory Status - Health and Statistics

Display real-time health status and statistics for the AI Memory Module, including service availability, collection metrics, and recent activity.

## Usage

```bash
# Show complete system status
/memory-status

# Show specific section
/memory-status --section health
/memory-status --section collections
/memory-status --section activity
/memory-status --section services
```

## Status Sections

### Health
Service availability and operational mode:
- **Qdrant** - Vector database health (healthy/degraded/down)
- **Embedding Service** - Embedding generation availability
- **Operational Mode** - Current degradation mode:
  - `normal` - All services healthy
  - `queue_to_file` - Qdrant unavailable, queuing operations
  - `pending_embedding` - Embedding service unavailable
  - `passthrough` - Both services unavailable, graceful degradation

### Collections
Statistics for each collection (code-patterns, conventions, discussions):
- **Total Points** - Number of stored memories
- **Indexed Points** - Number of indexed vectors
- **Segments** - Number of storage segments
- **Disk Size** - Total storage used (MB)
- **Last Updated** - Most recent memory timestamp
- **Projects** - Number of unique projects
- **Points by Project** - Per-project breakdown

### Activity
Recent memory system activity:
- **Last Session Start** - Most recent SessionStart hook
- **Last Capture** - Most recent PostToolUse capture
- **Last Search** - Most recent memory search
- **Total Searches Today** - Count of searches in last 24h
- **Total Captures Today** - Count of captures in last 24h

### Services
Detailed service status:
- **Qdrant** - URL, status, response time
- **Embedding Service** - URL, status, response time
- **Monitoring API** - URL, health endpoint status
- **Streamlit Dashboard** - URL, accessibility
- **Prometheus** - URL, metrics scraping status
- **Grafana** - URL, dashboard availability
- **Pushgateway** - URL, metrics push status

## Examples

```bash
# Quick health check
/memory-status --section health

# View collection statistics
/memory-status --section collections

# Check service status
/memory-status --section services

# View recent activity
/memory-status --section activity

# Complete status report
/memory-status
```

## Python Health Check Reference

Health checks are implemented in `src/memory/health.py`:

```python
from src.memory.health import check_services

# Fast health check (<2s)
health = check_services()

if health["all_healthy"]:
    print("✓ All services operational")
elif not health["qdrant"]:
    print("⚠ Qdrant unavailable - queuing to file")
elif not health["embedding"]:
    print("⚠ Embedding service unavailable - storing with pending status")
else:
    print("✗ Both services unavailable - passthrough mode")
```

## Collection Statistics Reference

Statistics are provided by `src/memory/stats.py`:

```python
from src.memory.stats import get_collection_stats
from src.memory.qdrant_client import get_qdrant_client

client = get_qdrant_client()
stats = get_collection_stats(client, "code-patterns")

print(f"Total memories: {stats.total_points}")
print(f"Disk size: {stats.disk_size_bytes / 1024 / 1024:.2f} MB")
print(f"Projects: {len(stats.projects)}")
print(f"Last updated: {stats.last_updated}")
```

## Output Format

### Health Status Display
```
🟢 All services healthy
  ✓ Qdrant: healthy (localhost:26350)
  ✓ Embedding: healthy (localhost:28080)
  ✓ Monitoring: healthy (localhost:28000)
```

### Collection Statistics
```
code-patterns (Project-specific implementations)
  Total Points: 1,234
  Indexed Points: 1,234
  Segments: 3
  Disk Size: 12.5 MB
  Last Updated: 2026-01-19T10:30:00Z
  Projects: 5 (bmad-memory-module, project-a, project-b, ...)

conventions (Cross-project shared rules)
  Total Points: 87
  Indexed Points: 87
  Segments: 1
  Disk Size: 2.1 MB
  Last Updated: 2026-01-19T09:15:00Z
  Projects: 1 (shared)
```

## Health Check Thresholds

Collection size warnings (configurable):
- **Warning** - 10,000 points (85% of optimal performance)
- **Critical** - 50,000 points (performance degradation likely)

Service response time thresholds:
- **Healthy** - < 100ms
- **Degraded** - 100ms - 2000ms
- **Down** - > 2000ms or no response

## Performance Metrics

All health checks comply with NFR-P1:
- Total check time: < 2 seconds
- No retries (fail-fast)
- Graceful degradation (never blocks Claude)

## Operational Modes

### Normal Mode
- All services healthy
- Full memory capture and retrieval
- Real-time embedding generation

### Queue to File
- Qdrant unavailable
- Operations queued to `~/.claude-memory/pending_queue.jsonl`
- Automatic replay when Qdrant recovers
- Hook exits immediately (no blocking)

### Pending Embedding
- Embedding service unavailable
- Memories stored with `embedding_status: pending`
- Background job generates embeddings later
- Search falls back to metadata filtering

### Passthrough Mode
- Both services unavailable
- Hook logs warning and exits gracefully
- Claude continues without memory
- No error propagation to user

## Troubleshooting

If any services show as unhealthy:

1. Check Docker containers:
   ```bash
   docker compose -f docker/docker-compose.yml ps
   ```

2. Check service logs:
   ```bash
   docker compose -f docker/docker-compose.yml logs qdrant
   docker compose -f docker/docker-compose.yml logs embedding
   ```

3. Restart services:
   ```bash
   docker compose -f docker/docker-compose.yml restart
   ```

4. Check connectivity:
   ```bash
   curl http://localhost:26350/health    # Qdrant
   curl http://localhost:28080/health    # Embedding
   curl http://localhost:28000/health    # Monitoring
   ```

## Related Skills

- `/memory-settings` - View configuration and thresholds
- `/search-memory` - Search the memory system

## Notes

- Health checks use 2s socket timeout (NFR-P1)
- Statistics queries are O(1) or O(log n) (NFR-M4: <100ms)
- All checks are non-blocking (graceful degradation)
- Queue file location: `~/.claude-memory/pending_queue.jsonl`
- Session logs: `~/.claude-memory/sessions.jsonl`
