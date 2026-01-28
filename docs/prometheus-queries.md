# Prometheus Query Patterns

Comprehensive guide to Prometheus queries for BMAD Memory Module monitoring. This documentation captures patterns and best practices learned during Epic 6 development, particularly addressing histogram aggregation mistakes that caused 6 HIGH issues in Story 6.3.

**Related:** See DEC-012 for port configuration (Prometheus: 29090, Grafana: 23000)

---

## Table of Contents

1. [Authenticated Queries](#authenticated-queries)
2. [Overview](#overview)
3. [Histogram Queries (CRITICAL)](#histogram-queries-critical)
4. [Rate vs Increase](#rate-vs-increase)
5. [Aggregation Patterns](#aggregation-patterns)
6. [Label Cardinality](#label-cardinality)
7. [Project-Specific Queries](#project-specific-queries)
8. [Token Metrics](#token-metrics)
9. [Multi-Embedding Metrics](#multi-embedding-metrics)
10. [V2 Trigger Metrics](#v2-trigger-metrics)
11. [Queue Metrics](#queue-metrics)
12. [Dashboard Query Examples](#dashboard-query-examples)

---

## Authenticated Queries

Prometheus requires basic auth. Use the helper script:

```bash
# Instant query
python3 scripts/monitoring/prometheus_query.py "bmad_collection_size"

# Range query (last hour)
python3 scripts/monitoring/prometheus_query.py --range --start 1h "bmad_hook_duration_seconds_sum"

# Raw JSON output
python3 scripts/monitoring/prometheus_query.py --raw "up"

# Manual curl (if needed)
curl -u admin:5HCf9v5laO0jxxLcXtnyYj7G "http://localhost:29090/api/v1/query?query=up"
```

**Environment variables for custom credentials:**
- `PROMETHEUS_URL` (default: http://localhost:29090)
- `PROMETHEUS_USER` (default: admin)
- `PROMETHEUS_PASSWORD` (default from web.yml)

**Helper Script:** `scripts/monitoring/prometheus_query.py`

---

## Overview

### Exposed Metrics

BMAD Memory Module exposes metrics on port **28000** at `/metrics` endpoint. All metrics use the `bmad_memory_*` naming convention (project convention: `snake_case`, `bmad_` prefix).

**Metric Types:**

| Type | Metric Name | Description | Labels |
|------|-------------|-------------|--------|
| **Counter** | `bmad_memory_captures_total` | Memory capture attempts | `hook_type`, `status`, `project` |
| **Counter** | `bmad_memory_retrievals_total` | Memory retrieval attempts | `collection`, `status` |
| **Counter** | `bmad_embedding_requests_total` | Embedding generation requests | `status`, `embedding_type` |
| **Counter** | `bmad_deduplication_events_total` | Deduplicated memories | `project` |
| **Counter** | `bmad_failure_events_total` | Failure events for alerting | `component`, `error_code` |
| **Counter** | `bmad_tokens_consumed_total` | Token consumption tracking | `operation`, `direction`, `project` |
| **Counter** | `bmad_trigger_fires_total` | Trigger activations | `trigger_type`, `status`, `project` |
| **Gauge** | `bmad_collection_size` | Points in collection | `collection`, `project` |
| **Gauge** | `bmad_queue_size` | Pending retry queue items | `status` |
| **Histogram** | `bmad_hook_duration_seconds` | Hook execution time | `hook_type` |
| **Histogram** | `bmad_embedding_duration_seconds` | Embedding generation time | `embedding_type` |
| **Histogram** | `bmad_retrieval_duration_seconds` | Memory retrieval time | None |
| **Histogram** | `bmad_context_injection_tokens` | Context injection token counts | `hook_type`, `collection`, `project` |
| **Histogram** | `bmad_trigger_results_returned` | Results returned per trigger | `trigger_type` |
| **Info** | `bmad_memory_system_info` | Static system metadata | `version`, `embedding_model`, `vector_dimensions`, `collections` |

**Performance NFRs:**
- Hook overhead: <500ms (NFR-P1)
- Embedding generation: <2s (NFR-P2)
- SessionStart retrieval: <3s (NFR-P3)

---

## Histogram Queries (CRITICAL)

**Most Common Mistake:** Missing aggregation in `histogram_quantile()` queries.

### The Problem

Histograms in Prometheus are cumulative counters stored in `_bucket` metrics with an `le` (less than or equal) label. When querying percentiles across multiple instances or time series, you **must aggregate by `le`** before applying `histogram_quantile()`.

### ❌ WRONG - Missing Aggregation

```promql
# This will fail or return incorrect results
histogram_quantile(0.95, rate(bmad_hook_duration_seconds_bucket[5m]))
```

**Why it's wrong:**
- `rate()` returns per-instance bucket counters
- `histogram_quantile()` requires aggregated buckets across all time series
- Without aggregation, percentiles are calculated incorrectly or the query fails

### ✅ CORRECT - Aggregation by `le`

```promql
# Always use sum by (le) with histogram_quantile
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

**Why it's correct:**
- `rate()` calculates per-second rate over 5 minutes
- `sum by (le)` aggregates all bucket counters while preserving the `le` label
- `histogram_quantile()` calculates the 95th percentile from aggregated distribution

### Preserving Additional Labels

If you need to preserve other labels (like `hook_type`), include them in the aggregation:

```promql
# Preserve hook_type to see p95 per hook type
histogram_quantile(0.95, sum by (le, hook_type) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

### Common Percentiles

```promql
# p50 (median) - typical latency
histogram_quantile(0.50, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# p95 - catches most outliers
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# p99 - extreme outliers
histogram_quantile(0.99, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

### Complete Example: Multi-Quantile Dashboard Panel

```promql
# Panel with p50, p95, p99 (from memory-performance.json)
# Query A - p50
histogram_quantile(0.50, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# Query B - p95
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# Query C - p99
histogram_quantile(0.99, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

---

## Rate vs Increase

### `rate()` - Per-Second Average

Use `rate()` when you want the **per-second rate of increase** over a time window.

```promql
# Captures per second over last 5 minutes
rate(bmad_memory_captures_total[5m])

# Typical use: dashboards showing ops/sec
sum(rate(bmad_memory_captures_total[1h]))
```

**Characteristics:**
- Returns per-second average
- Automatically handles counter resets
- Best for: rates, throughput, ops/sec metrics
- Unit: events/second

### `increase()` - Total Increase

Use `increase()` when you want the **total increase** over a time window.

```promql
# Total captures in last 1 hour
increase(bmad_memory_captures_total[1h])

# Total failures in last 24 hours
sum(increase(bmad_failure_events_total[24h]))
```

**Characteristics:**
- Returns total count increase
- Automatically handles counter resets
- Best for: totals, counts over period
- Unit: total events

### Common Mistakes

```promql
# ❌ WRONG - Using increase() for per-second rate
sum(increase(bmad_memory_captures_total[5m]))  # Returns total, not rate

# ✅ CORRECT - Using rate() for per-second rate
sum(rate(bmad_memory_captures_total[5m]))  # Returns ops/sec

# ❌ WRONG - Using rate() when you want totals
sum(rate(bmad_memory_captures_total[1h]))  # Returns ops/sec, not total

# ✅ CORRECT - Using increase() for totals
sum(increase(bmad_memory_captures_total[1h]))  # Returns total count
```

### Rule of Thumb

- **Dashboard gauges/graphs showing rate**: Use `rate()`
- **Alerting on total events**: Use `increase()`
- **Calculating percentages**: Use `rate()` for both numerator and denominator

---

## Aggregation Patterns

Aggregation operators determine which labels are preserved or removed in results.

### `sum by (label)` - Preserve Specific Labels

Keep only the specified labels, aggregate everything else:

```promql
# Group by project only
sum by (project) (rate(bmad_memory_captures_total[5m]))

# Group by collection and status
sum by (collection, status) (rate(bmad_memory_retrievals_total[5m]))

# Group by component and error_code
sum by (component, error_code) (rate(bmad_failure_events_total[5m]))
```

**Use when:** You want to see breakdowns by specific dimensions.

### `sum without (label)` - Remove Specific Labels

Remove specified labels, keep everything else:

```promql
# Remove only the instance label
sum without (instance) (bmad_collection_size)

# Remove multiple labels
sum without (instance, job) (rate(bmad_memory_captures_total[5m]))
```

**Use when:** You want to aggregate across some labels but preserve most.

### Why Aggregation Matters for Histograms

**Critical Rule:** `histogram_quantile()` requires buckets aggregated by `le`.

```promql
# ❌ WRONG - Missing le aggregation
histogram_quantile(0.95, rate(bmad_hook_duration_seconds_bucket[5m]))

# ✅ CORRECT - sum by (le)
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# ✅ CORRECT - sum by (le, hook_type) to preserve hook_type dimension
histogram_quantile(0.95, sum by (le, hook_type) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

### Other Aggregation Operators

```promql
# max - highest value across series
max(bmad_queue_size{status="pending"})

# min - lowest value
min(bmad_collection_size)

# avg - average value
avg by (project) (bmad_collection_size)

# count - number of time series
count(bmad_collection_size)
```

---

## Label Cardinality

**Golden Rule:** Keep label cardinality low to maintain Prometheus performance.

### Good Labels (Low Cardinality)

These are **safe** to use as labels:

| Label | Cardinality | Examples |
|-------|-------------|----------|
| `hook_type` | ~5 | `PostToolUse`, `SessionStart`, `PreToolUse`, `PreCompact`, `Stop` |
| `status` | ~3 | `success`, `failed`, `queued` |
| `collection` | ~3 | `code-patterns`, `conventions`, `discussions` |
| `component` | ~4 | `qdrant`, `embedding`, `queue`, `hook` |
| `error_code` | ~5 | `QDRANT_UNAVAILABLE`, `EMBEDDING_TIMEOUT`, etc. |
| `project` | <100 | Project names (acceptable if bounded) |

### Bad Labels (High Cardinality)

**Never use these as labels:**

| Anti-Pattern | Why It's Bad |
|-------------|-------------|
| `user_id` | Unbounded - grows with users |
| `session_id` | Unbounded - new session every execution |
| `memory_id` | Unbounded - new UUID per memory |
| `timestamp` | Unbounded - infinite unique values |
| `file_path` | High cardinality - thousands of files |
| `error_message` | High cardinality - unique messages |

### Impact of High Cardinality

```promql
# ❌ BAD - Creates thousands of time series
my_metric{user_id="user123", session_id="sess_456", memory_id="uuid-789"}

# ✅ GOOD - Bounded labels only
bmad_memory_captures_total{hook_type="PostToolUse", status="success", project="my-project"}
```

**Problems with high cardinality:**
- Prometheus memory exhaustion
- Slow query performance
- Expensive storage costs
- Query timeouts

### Project Label Strategy

The `project` label is used for multi-tenancy:

```promql
# Safe - project count is bounded to active projects
bmad_collection_size{collection="code-patterns", project="my-project"}
```

**Why it works:**
- Limited number of active projects per installation (<100)
- Projects are long-lived (not per-request)
- Enables per-project monitoring and alerting

---

## Project-Specific Queries

### Memory Operations by Type

```promql
# Capture rate by hook type
sum by (hook_type) (rate(bmad_memory_captures_total[5m]))

# Retrieval rate by collection
sum by (collection) (rate(bmad_memory_retrievals_total[5m]))

# Embedding request rate
sum(rate(bmad_embedding_requests_total[5m]))

# Deduplication rate by project
sum by (project) (rate(bmad_deduplication_events_total[5m]))
```

### Error Rates

```promql
# Total failure rate
sum(rate(bmad_failure_events_total[5m]))

# Failure rate by component
sum by (component) (rate(bmad_failure_events_total[5m]))

# Failure rate by error code
sum by (error_code) (rate(bmad_failure_events_total[5m]))

# Failure rate by component and error code
sum by (component, error_code) (rate(bmad_failure_events_total[5m]))
```

### Success Rate Calculations

```promql
# Overall capture success rate (percentage)
sum(rate(bmad_memory_captures_total{status="success"}[1h])) / sum(rate(bmad_memory_captures_total[1h])) * 100

# Success rate by hook type
sum by (hook_type) (rate(bmad_memory_captures_total{status="success"}[1h])) / sum by (hook_type) (rate(bmad_memory_captures_total[1h])) * 100

# Retrieval success rate by collection
sum by (collection) (rate(bmad_memory_retrievals_total{status="success"}[5m])) / sum by (collection) (rate(bmad_memory_retrievals_total[5m])) * 100
```

### Latency Percentiles

```promql
# Hook p50, p95, p99 (as shown in dashboards)
histogram_quantile(0.50, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
histogram_quantile(0.99, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# Embedding p95 (NFR-P2: <2s target)
histogram_quantile(0.95, sum by (le) (rate(bmad_embedding_duration_seconds_bucket[5m])))

# Retrieval p95 (NFR-P3: <3s target)
histogram_quantile(0.95, sum by (le) (rate(bmad_retrieval_duration_seconds_bucket[5m])))
```

### Collection Statistics

```promql
# Current collection sizes
bmad_collection_size

# Collection size by project
bmad_collection_size{project="my-project"}

# Total points across all collections
sum(bmad_collection_size)

# Queue size (pending items)
bmad_queue_size{status="pending"}

# Queue size (exhausted items)
bmad_queue_size{status="exhausted"}
```

### Alerting Queries

```promql
# Hook duration exceeds 500ms (NFR-P1)
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m]))) > 0.5

# Embedding duration exceeds 2s (NFR-P2)
histogram_quantile(0.95, sum by (le) (rate(bmad_embedding_duration_seconds_bucket[5m]))) > 2.0

# Retrieval duration exceeds 3s (NFR-P3)
histogram_quantile(0.95, sum by (le) (rate(bmad_retrieval_duration_seconds_bucket[5m]))) > 3.0

# High failure rate (>1 failure/min)
sum(rate(bmad_failure_events_total[5m])) > 1/60

# Collection approaching threshold (>8000 points)
max(bmad_collection_size) > 8000

# Queue backlog growing (>10 pending)
bmad_queue_size{status="pending"} > 10
```

---

---

## V2.0 Metrics

### Trigger Metrics

```promql
# Trigger fires by type (last hour)
sum by (trigger_type) (
  increase(bmad_trigger_fires_total[1h])
)

# Trigger success rate
sum(bmad_trigger_fires_total{status="success"}) /
sum(bmad_trigger_fires_total) * 100

# Average results per trigger type
histogram_quantile(0.5,
  sum by (trigger_type, le) (
    rate(bmad_trigger_results_returned_bucket[5m])
  )
)
```

### Token Consumption

```promql
# Total tokens by operation (last 24h)
sum by (operation) (
  increase(bmad_tokens_consumed_total[24h])
)

# Input vs output tokens
sum by (direction) (
  increase(bmad_tokens_consumed_total[1h])
)

# Tokens per project
sum by (project) (
  increase(bmad_tokens_consumed_total[24h])
)
```

### Collection Health

```promql
# Collection sizes by project
bmad_collection_size{project!="all"}

# Total memories across all collections
sum(bmad_collection_size{project="all"})

# Deduplication rate (last hour)
sum(increase(bmad_deduplication_events_total[1h])) /
sum(increase(bmad_memory_captures_total[1h])) * 100
```

### Failure Monitoring

```promql
# Failures by component
sum by (component) (
  increase(bmad_failure_events_total[1h])
)

# Alert: High failure rate
increase(bmad_failure_events_total[5m]) > 5
```

---

## Token Metrics

**TECH-DEBT-067:** V2.0 token usage tracking for context injection and memory operations.

### Total Tokens Consumed

```promql
# Total tokens consumed in last 1 hour
sum(increase(bmad_tokens_consumed_total[1h]))

# By direction (input vs output)
sum by (direction) (rate(bmad_tokens_consumed_total[5m]))

# By operation type
sum by (operation) (rate(bmad_tokens_consumed_total[5m]))

# By project
sum by (project) (rate(bmad_tokens_consumed_total[5m]))
```

**Labels:**
- `operation`: `capture`, `retrieval`, `trigger`, `injection`, `classification` (TECH-DEBT-071)
- `direction`: `input` (TO system), `output` (FROM system), `stored` (persisted to memory) (TECH-DEBT-071)
- `project`: Project name (from group_id) or `"classifier"` for system-level operations

**Direction Semantics (TECH-DEBT-071):**
- `input` - Data flowing INTO an operation (e.g., prompt to classifier, query to search)
- `output` - Data flowing OUT of an operation (e.g., LLM response, search results)
- `stored` - Data persisted to Qdrant collections (e.g., captured code, user messages)

### Context Injection Size

```promql
# Median tokens injected per hook
histogram_quantile(0.50, sum by (le, hook_type) (rate(bmad_context_injection_tokens_bucket[5m])))

# p95 tokens injected
histogram_quantile(0.95, sum by (le, hook_type) (rate(bmad_context_injection_tokens_bucket[5m])))

# By collection
histogram_quantile(0.95, sum by (le, collection) (rate(bmad_context_injection_tokens_bucket[5m])))

# By project (BUG-046 fix)
histogram_quantile(0.95, sum by (le, project) (rate(bmad_context_injection_tokens_bucket[5m])))

# Specific project filtering
histogram_quantile(0.95, sum by (le, hook_type) (rate(bmad_context_injection_tokens_bucket{project="my-project"}[5m])))
```

**Use Cases:**
- Monitor context window usage (target: 70-80% of available tokens)
- Track token consumption patterns by operation type
- Alert on excessive token usage
- Per-project token injection monitoring (BUG-046)

---

## Multi-Embedding Metrics

**TECH-DEBT-067:** V2.0 multi-embedding support for dense, BM25, and SPLADE embeddings.

> **NOTE:** Panels show "No data" for disabled embedding types. This is expected behavior.

### Request Rate by Embedding Type

```promql
# Overall request rate by type
sum by (embedding_type) (rate(bmad_embedding_requests_total[5m]))

# Success rate by embedding type
sum by (embedding_type) (rate(bmad_embedding_requests_total{status="success"}[5m]))

# Failure rate by type
sum by (embedding_type) (rate(bmad_embedding_requests_total{status="failed"}[5m]))
```

**Expected Behavior:**
- If only dense embeddings enabled: Only `embedding_type="dense"` shows data
- BM25/SPLADE series show "No data" until respective services are enabled

### Latency by Embedding Type

```promql
# p95 latency by embedding type (CRITICAL: use sum by (le, embedding_type))
histogram_quantile(0.95,
  sum by (le, embedding_type) (rate(bmad_embedding_duration_seconds_bucket[5m]))
)

# p50 latency by type
histogram_quantile(0.50,
  sum by (le, embedding_type) (rate(bmad_embedding_duration_seconds_bucket[5m]))
)

# p99 latency by type
histogram_quantile(0.99,
  sum by (le, embedding_type) (rate(bmad_embedding_duration_seconds_bucket[5m]))
)
```

**NFR Targets:**
- Dense: <2s (NFR-P2)
- BM25: <500ms (expected)
- SPLADE: <1s (expected)

### Success Rate by Embedding Type

```promql
# Success rate percentage by type
sum by (embedding_type) (rate(bmad_embedding_requests_total{status="success"}[5m]))
  / sum by (embedding_type) (rate(bmad_embedding_requests_total[5m])) * 100
```

**Panel Config:** Unit: `percent`, Range: 0-100, Thresholds: 90→red, 95→yellow, 98→green

### Embedding Type Distribution

```promql
# Total requests by type (for pie chart)
sum by (embedding_type) (increase(bmad_embedding_requests_total[1h]))
```

**Use Cases:**
- Monitor which embedding types are in use
- Compare latency across embedding services
- Alert on embedding service failures

---

## V2 Trigger Metrics

**TECH-DEBT-067:** V2.0 automatic trigger system for decision keywords, best practices, and session history.

### Trigger Fire Rate

```promql
# Overall trigger fire rate
sum(rate(bmad_trigger_fires_total[5m]))

# By trigger type
sum by (trigger_type) (rate(bmad_trigger_fires_total[5m]))

# By status (success, empty, failed)
sum by (status) (rate(bmad_trigger_fires_total[5m]))

# By project
sum by (project) (rate(bmad_trigger_fires_total[5m]))
```

**Trigger Types:**
- `decision_keywords`: "why did we...", "what was decided"
- `best_practices_keywords`: "best practice", "how should I"
- `session_history_keywords`: "what have we done", "project status"
- `error_detection`: Automatic on Bash errors
- `new_file`: Automatic on Write tool
- `first_edit`: Automatic on first Edit to file

### Trigger Success Rate

```promql
# Overall success rate (percentage)
sum(rate(bmad_trigger_fires_total{status="success"}[5m]))
  / sum(rate(bmad_trigger_fires_total[5m])) * 100

# Success rate by trigger type
sum by (trigger_type) (rate(bmad_trigger_fires_total{status="success"}[5m]))
  / sum by (trigger_type) (rate(bmad_trigger_fires_total[5m])) * 100
```

**Statuses:**
- `success`: Trigger fired and returned results
- `empty`: Trigger fired but no relevant memories found
- `failed`: Trigger failed (Qdrant unavailable, etc.)

### Results per Trigger

```promql
# Median results returned per trigger type
histogram_quantile(0.50, sum by (le, trigger_type) (rate(bmad_trigger_results_returned_bucket[5m])))

# p95 results returned
histogram_quantile(0.95, sum by (le, trigger_type) (rate(bmad_trigger_results_returned_bucket[5m])))
```

**Expected Values:**
- Decision triggers: Typically 1-2 results
- Best practices triggers: Typically 2-3 results
- Session history triggers: Typically 1-3 results
- 0 results indicates `status="empty"`

### Trigger Activity by Project

```promql
# Trigger fire rate by project
sum by (project, trigger_type) (rate(bmad_trigger_fires_total[5m]))

# Most active trigger types per project
topk(3, sum by (project, trigger_type) (rate(bmad_trigger_fires_total[5m])))
```

**Use Cases:**
- Monitor which triggers are most active
- Identify projects with high trigger activity
- Alert on trigger failures
- Validate trigger configuration changes

---

## Queue Metrics

**QUEUE-UNIFY:** Unified retry queue for all memory storage failures with exponential backoff.

### Queue Size by Status

```promql
# Current queue size by status
bmad_queue_size

# Ready for retry (can be processed now)
bmad_queue_size{status="ready"}

# Pending (awaiting backoff timer)
bmad_queue_size{status="pending"}

# Exhausted (exceeded max retries)
bmad_queue_size{status="exhausted"}
```

**Statuses:**
- `ready`: Items where `next_retry_at <= now`, can be processed immediately
- `pending`: Items awaiting backoff timer (`next_retry_at > now`)
- `exhausted`: Items that exceeded `max_retries` (default: 3)

### Total Queue Health

```promql
# Total items in queue (should be 0 in healthy system)
sum(bmad_queue_size)

# Alert threshold: Any exhausted items is a problem
bmad_queue_size{status="exhausted"} > 0
```

### Queue Trend Over Time

```promql
# Queue size over time (for trend analysis)
# Note: This is a gauge, not a counter - no rate() needed
bmad_queue_size

# Max queue size in last hour
max_over_time(bmad_queue_size[1h])
```

**Backoff Schedule:**
- Retry 1: 1 minute
- Retry 2: 5 minutes
- Retry 3+: 15 minutes (capped)

**Use Cases:**
- Monitor queue health (all values should be 0)
- Alert on exhausted items (indicates persistent failures)
- Track retry patterns over time
- Validate Qdrant/embedding service availability

**Dashboard:** Memory Overview → "Retry Queue" row

---

## Dashboard Query Examples

Complete working queries extracted from our Grafana dashboards (`docker/grafana/dashboards/*.json`).

### Memory Overview Dashboard

#### Capture Rate (Stat Panel)

```promql
# Shows overall captures/sec across all hooks
sum(rate(bmad_memory_captures_total[1h]))
```

**Panel Config:** Unit: `ops`, Decimals: `2`, Thresholds: 0→green, 10→yellow, 50→red

#### Retrieval Rate (Stat Panel)

```promql
# Shows overall retrievals/sec across all collections
sum(rate(bmad_memory_retrievals_total[1h]))
```

**Panel Config:** Unit: `ops`, Decimals: `2`, Thresholds: 0→green, 5→yellow, 20→red

#### Collection Sizes (Gauge Panel)

```promql
# Shows current size of each collection-project combination
bmad_collection_size
```

**Legend:** `{{collection}} - {{project}}`
**Panel Config:** Unit: `short`, Thresholds: 0→green, 8000→yellow, 10000→red, Max: 12000

#### Queue Status (Stat Panel)

```promql
# Shows pending items in retry queue
bmad_queue_size{status="pending"}
```

**Panel Config:** Unit: `short`, Thresholds: 0→green, 10→yellow, 50→red

#### Capture/Retrieval Timeline (Time Series)

```promql
# Query A - Captures by project
sum by (project) (rate(bmad_memory_captures_total[5m]))

# Query B - Retrievals by collection
sum by (collection) (rate(bmad_memory_retrievals_total[5m]))
```

**Legend A:** `Captures - {{project}}`
**Legend B:** `Retrievals - {{collection}}`
**Panel Config:** Unit: `ops`, Smooth interpolation, 10% fill opacity

#### Failure Events (Time Series)

```promql
# Shows failure rate by component and error code
sum by (component, error_code) (rate(bmad_failure_events_total[5m]))
```

**Legend:** `{{component}} - {{error_code}}`
**Panel Config:** Unit: `ops`, Smooth interpolation, 20% fill opacity

---

### Memory Performance Dashboard

#### Hook Duration Percentiles (Time Series)

```promql
# Query A - p50 (median)
histogram_quantile(0.50, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# Query B - p95
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))

# Query C - p99
histogram_quantile(0.99, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

**Legend A:** `p50 - {{hook_type}}`
**Legend B:** `p95 - {{hook_type}}`
**Legend C:** `p99 - {{hook_type}}`
**Panel Config:** Unit: `s`, Thresholds: 0.5s→yellow, 1.0s→red, Line threshold display

#### Embedding Duration Distribution (Heatmap)

```promql
# Shows distribution of embedding durations as heatmap
rate(bmad_embedding_duration_seconds_bucket[5m])
```

**Legend:** `{{le}}`
**Format:** `heatmap`
**Panel Config:** Exponential scale, Spectral color scheme, Y-axis unit: `s`

#### Retrieval Duration p95 (Stat Panel)

```promql
# Shows 95th percentile retrieval time
histogram_quantile(0.95, sum by (le) (rate(bmad_retrieval_duration_seconds_bucket[5m])))
```

**Panel Config:** Unit: `s`, Decimals: `3`, Thresholds: 0→green, 2s→yellow, 3s→red

#### Success Rate by Hook Type (Bar Gauge)

```promql
# Calculate success percentage per hook type
sum(rate(bmad_memory_captures_total{status="success"}[1h])) by (hook_type) / sum(rate(bmad_memory_captures_total[1h])) by (hook_type) * 100
```

**Legend:** `{{hook_type}}`
**Panel Config:** Unit: `percent`, Decimals: `1`, Range: 0-100, Thresholds: 0→red, 90→yellow, 95→green

---

## Common Query Patterns Summary

### Instant Queries (Current State)

```promql
# Current gauge values
bmad_collection_size
bmad_queue_size{status="pending"}

# Latest histogram bucket values (rarely used directly)
bmad_hook_duration_seconds_bucket
```

### Range Queries (Time Series)

```promql
# Rate over time
rate(bmad_memory_captures_total[5m])

# Increase over time
increase(bmad_memory_captures_total[1h])

# Histogram percentiles over time
histogram_quantile(0.95, sum by (le) (rate(bmad_hook_duration_seconds_bucket[5m])))
```

### Aggregations

```promql
# Sum across all series
sum(rate(bmad_memory_captures_total[5m]))

# Sum preserving labels
sum by (project) (rate(bmad_memory_captures_total[5m]))

# Average
avg(bmad_collection_size)

# Max/Min
max(bmad_queue_size)
min(bmad_hook_duration_seconds_bucket)
```

### Calculations

```promql
# Ratio/Percentage
(metric_a / metric_b) * 100

# Difference
metric_a - metric_b

# Rate of change
rate(metric[5m])
```

---

## Best Practices Checklist

- ✅ Always use `sum by (le)` with `histogram_quantile()`
- ✅ Use `rate()` for per-second rates, `increase()` for totals
- ✅ Keep label cardinality low (<100 unique values per label)
- ✅ Choose appropriate time ranges: `[5m]` for real-time, `[1h]` for trends
- ✅ Preserve necessary labels with `sum by (label1, label2)`
- ✅ Use consistent time ranges in numerator and denominator for ratios
- ✅ Test queries in Prometheus UI (`http://localhost:29090`) before adding to dashboards
- ✅ Include units in panel configs (`s`, `ops`, `percent`, `short`)
- ✅ Set meaningful thresholds based on NFRs
- ✅ Use descriptive legend formats with label templating: `{{label}}`

---

## References

- **Metrics Definitions:** `src/memory/metrics.py`
- **Monitoring API:** `monitoring/main.py`
- **Dashboards:** `docker/grafana/dashboards/*.json`
- **Port Configuration:** DEC-012 (Prometheus: 29090, Grafana: 23000)
- **Performance NFRs:** NFR-P1 (<500ms hooks), NFR-P2 (<2s embedding), NFR-P3 (<3s retrieval)

---

*Document created per ACT-001 - Captures Prometheus query patterns from Epic 6 development*
