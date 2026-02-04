# AI-Memory Monitoring Guide

## Overview

AI-Memory uses Prometheus for metrics collection and Grafana for visualization. All metrics follow the naming convention: `aimemory_{component}_{metric}_{unit}` per BP-045.

### Quick Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | `http://localhost:23000` | admin/admin |
| Prometheus | `http://localhost:29090` | - |
| Pushgateway | `http://localhost:29091` | - |

## Dashboards

### NFR Performance Overview (V3)

**Purpose**: Monitor all 6 Non-Functional Requirements

**Key Panels**:

- **NFR Status Summary**: Current p95 vs target for each NFR
- **Hook Latency by Type**: Breakdown by hook_type
- **Embedding Latency**: Batch vs Realtime comparison
- **SLO Compliance**: Percentage meeting each NFR target

**Thresholds**:

| Status | Condition |
|--------|-----------|
| Green | <80% of target |
| Yellow | 80-100% of target |
| Red | >100% of target |

### Hook Activity (V3)

**Purpose**: Monitor hook execution patterns

**Key Panels**:

- Execution rate by hook_type
- CAPTURE vs RETRIEVAL comparison
- Success/Error rate
- Latency heatmap
- Keyword trigger activity

**Hook Types**:

**CAPTURE** (store to memory):

| Hook | Trigger | Purpose |
|------|---------|---------|
| `UserPromptSubmit` | User message | Capture user prompts |
| `Stop` | Agent complete | Capture agent responses |
| `PostToolUse` | Edit/Write | Capture code patterns |
| `PostToolUse_Error` | Bash error | Capture error patterns |
| `PreCompact` | Before compact | Save session summary |

**RETRIEVAL** (query memory):

| Hook | Trigger | Purpose |
|------|---------|---------|
| `PostToolUse_ErrorDetection` | Bash error | Retrieve error fixes |
| `PreToolUse_NewFile` | Write new file | Retrieve conventions |
| `PreToolUse_FirstEdit` | First edit | Retrieve file patterns |
| `SessionStart` | resume/compact | Inject context |
| `PreToolUse` | Any tool use | Retrieve best practices |

### Memory Operations (V3)

**Purpose**: Monitor storage and retrieval operations

**Key Panels**:

- Captures/Retrievals by collection
- Deduplication statistics
- Token usage
- Storage by project

**Collections**:

| Collection | Purpose |
|------------|---------|
| `discussions` | Session summaries, decisions |
| `code-patterns` | Implementation patterns, error fixes |
| `conventions` | Rules, guidelines, naming conventions |

### System Health (V3)

**Purpose**: Infrastructure monitoring

**Key Panels**:

- Service status (Qdrant, Embedding, Prometheus, Pushgateway)
- Error rates by component
- Embedding service latency
- Queue size

## Metrics Reference

### Hook Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `aimemory_hook_duration_seconds` | Histogram | hook_type, status, project | Hook execution time |
| `aimemory_captures_total` | Counter | hook_type, status, project, collection | Storage operations |
| `aimemory_retrievals_total` | Counter | collection, status, project | Retrieval operations |

### NFR Metrics

| Metric | NFR | Target |
|--------|-----|--------|
| `aimemory_hook_duration_seconds` | NFR-P1 | <500ms |
| `aimemory_embedding_batch_duration_seconds` | NFR-P2 | <2s |
| `aimemory_session_injection_duration_seconds` | NFR-P3 | <3s |
| `aimemory_dedup_check_duration_seconds` | NFR-P4 | <100ms |
| `aimemory_retrieval_query_duration_seconds` | NFR-P5 | <500ms |
| `aimemory_embedding_realtime_duration_seconds` | NFR-P6 | <500ms |

### Trigger Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `aimemory_trigger_fires_total` | Counter | trigger_type, status, project | Keyword trigger activations |
| `aimemory_trigger_results_returned` | Histogram | trigger_type, project | Results per trigger |

### Other Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `aimemory_tokens_consumed_total` | Counter | operation, direction, project | Token usage tracking |
| `aimemory_collection_size` | Gauge | collection, project | Memory count per collection |
| `aimemory_queue_size` | Gauge | status | Retry queue depth |
| `aimemory_failure_events_total` | Counter | component, error_code, project | Failure tracking for alerts |

## Alerting (Future)

Recommended alert thresholds:

| Alert | Condition |
|-------|-----------|
| NFR violation | p95 > target for 5 minutes |
| Service down | Any service unavailable for 1 minute |
| Error rate spike | >5% errors in 5 minutes |
| Queue backup | >100 items for 10 minutes |

## Troubleshooting

### Metrics Not Appearing

1. Check Pushgateway is receiving metrics:

   ```bash
   curl http://localhost:29091/metrics | grep aimemory
   ```

2. Check Prometheus is scraping:

   ```bash
   curl http://localhost:29090/api/v1/targets
   ```

3. Verify hooks are pushing:

   ```bash
   tail -f ~/.ai-memory/logs/hooks.log | grep push_
   ```

### Dashboard Shows No Data

1. Verify time range matches when hooks fired
2. Check project filter matches actual project names
3. Ensure hook_type filter includes active hooks

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| All panels empty | Wrong time range | Set to "Last 1 hour" or when hooks ran |
| Project dropdown empty | No metrics pushed yet | Execute a hook (e.g., edit a file) |
| Some NFRs missing | Metric not triggered | That operation hasn't occurred yet |

## Migration from V2

V3 dashboards use new metric names:

| V2 Metric | V3 Metric |
|-----------|-----------|
| `ai_memory_*` | `aimemory_*` |
| Shared NFR metrics | Separate NFR metrics |
| No project label | Project label on all metrics |

V2 dashboards remain available during migration period.

**Tech Debt**: Remove V2 dashboards after verifying V3 works (TECH-DEBT-125)

## Related Documentation

- [prometheus-queries.md](prometheus-queries.md) - Example PromQL queries
- [Core-Architecture-Principle-V2.md](../../oversight/specs/Core-Architecture-Principle-V2.md) - Section 9: NFR Requirements
- [BP-045-prometheus-metrics.md](../../oversight/knowledge/best-practices/BP-045-prometheus-metrics.md) - Naming conventions
