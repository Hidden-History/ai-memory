---
name: aim-jira-search
description: 'Search Jira issues and comments with semantic search and filters'
allowed-tools: Read, Bash
---

# Search Jira - Semantic Search for Jira Content

Search the jira-data collection for issues and comments using semantic similarity with advanced filtering.

## Activation

```text
# Basic semantic search
/aim-jira-search "authentication bug"

# Filter by project
/aim-jira-search "API errors" --project BMAD

# Filter by type (issue or comment)
/aim-jira-search "implementation details" --type jira_comment

# Filter by issue type
/aim-jira-search "bugs" --issue-type Bug

# Filter by status
/aim-jira-search "in progress work" --status "In Progress"

# Filter by priority
/aim-jira-search "critical issues" --priority High

# Filter by author (comments) or reporter (issues)
/aim-jira-search "alice's comments" --author alice@company.com

# Issue lookup mode (issue + all comments)
/aim-jira-search --issue BMAD-42

# Combine filters
/aim-jira-search "database" --project BMAD --issue-type Bug --status Done --limit 10
```

## Options

- `--project <key>` - Filter by Jira project key (e.g., BMAD, PROJ)
- `--type <type>` - Filter by document type (jira_issue or jira_comment)
- `--issue-type <type>` - Filter by issue type (Bug, Story, Task, Epic)
- `--status <status>` - Filter by issue status (To Do, In Progress, Done, etc.)
- `--priority <priority>` - Filter by priority (Highest, High, Medium, Low, Lowest)
- `--author <email>` - Filter by comment author or issue reporter
- `--issue <key>` - Lookup mode: retrieve issue + all comments (e.g., BMAD-42)
- `--limit <n>` - Maximum results to return (default: 5)

## Result Format

Each result includes:
- **Jira URL** - Direct link to issue/comment
- **Metadata badges** - Type, Status, Priority, Author/Reporter
- **Content snippet** - First ~300 characters
- **Relevance score** - Semantic similarity (0-100%)

---

## Qdrant Connection Details

The jira-data collection is stored in the local Qdrant instance:

| Parameter | Value |
|-----------|-------|
| **Host** | `localhost` |
| **Port** | `26350` (NOT the default 6333) |
| **API Key** | Required. Read from env: `QDRANT_API_KEY` |
| **Collection** | `jira-data` |
| **URL** | `http://localhost:26350` |

To get the API key:
```bash
export QDRANT_API_KEY="$(grep QDRANT_API_KEY ~/.ai-memory/docker/.env | cut -d= -f2)"
```

---

## Qdrant Payload Schema

Every point in `jira-data` has the following payload fields. Use these **exact names** for filtering — do NOT guess field names like `project_key` or `issue_key`.

### Common Fields (all points)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `content` | string | Full text content of issue/comment | `"[PROJ-123] Fix login bug..."` |
| `type` | string | Document type | `"jira_issue"` or `"jira_comment"` |
| `group_id` | string | Jira instance hostname (tenant isolation) | `"hidden-history.atlassian.net"` |
| `session_id` | string | Always `"jira_sync"` | `"jira_sync"` |
| `jira_project` | string | Project key | `"BMAD"` |
| `jira_issue_key` | string | Full issue key | `"BMAD-42"` |
| `jira_issue_type` | string | Issue type name | `"Bug"`, `"Story"`, `"Task"`, `"Epic"` |
| `jira_status` | string | Issue status | `"To Do"`, `"In Progress"`, `"Done"` |
| `jira_priority` | string or null | Priority level | `"High"`, `"Medium"`, `"Low"`, `null` |
| `jira_updated` | string | ISO 8601 timestamp | `"2026-02-10T14:30:00.000+0000"` |
| `jira_url` | string | Full Jira URL | `"https://company.atlassian.net/browse/BMAD-42"` |

### Issue-Only Fields (`type: "jira_issue"`)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `jira_reporter` | string | Issue reporter display name | `"Alice Smith"` |
| `jira_labels` | list[string] | Issue labels | `["backend", "auth"]` |

### Comment-Only Fields (`type: "jira_comment"`)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `jira_comment_id` | string | Jira comment ID | `"10042"` |
| `jira_author` | string | Comment author display name | `"Bob Jones"` |

### Chunking Metadata (if content was chunked)

| Field | Type | Description |
|-------|------|-------------|
| `chunk_index` | int | Chunk sequence number (0-based) |
| `total_chunks` | int | Total chunks for this document |
| `chunking_strategy` | string | Strategy used (e.g., `"topical"`) |

---

## Direct Query Examples

Use `query.py` via `run-with-env.sh` for all direct Qdrant queries. Auth and
connection are handled by the standard `memory.*` config layer — no manual API
key export required.

```bash
INSTALL="${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}"
QUERY="$INSTALL/skills/aim-jira-search/scripts/query.py"

# Search by project key (table output)
"$INSTALL/scripts/memory/run-with-env.sh" "$QUERY" \
  --project BMAD --limit 10

# Filter by issue type and status
"$INSTALL/scripts/memory/run-with-env.sh" "$QUERY" \
  --project BMAD --issue-type Bug --status Done --limit 20

# Count points and vectors in the collection
"$INSTALL/scripts/memory/run-with-env.sh" "$QUERY" --count

# Get all comments for a specific issue
"$INSTALL/scripts/memory/run-with-env.sh" "$QUERY" \
  --issue-key BMAD-42 --doc-type jira_comment --limit 50

# JSON output for programmatic use
"$INSTALL/scripts/memory/run-with-env.sh" "$QUERY" \
  --project BMAD --format json --limit 5
```

Available flags (use exact Qdrant payload field values — see schema above):
- `--project` — project key (e.g., `BMAD`)
- `--issue-type` — issue type (e.g., `Bug`, `Story`, `Task`, `Epic`)
- `--status` — status (e.g., `"In Progress"`, `Done`)
- `--issue-key` — full issue key (e.g., `BMAD-42`)
- `--doc-type` — document type (`jira_issue` or `jira_comment`)
- `--limit` — max results (default: 10)
- `--format` — `table` (default) or `json`
- `--count` — return collection info counts instead of scroll

---

## Python Implementation Reference

The `src/memory/connectors/jira/search.py` module is **not importable from
external scripts** — use `query.py` (above) for direct Qdrant access.

## Technical Details

- **Semantic Search**: Uses jina-embeddings-v2-base-en for vector similarity
- **Tenant Isolation**: Mandatory group_id filter prevents cross-instance leakage
- **Performance**: < 2s for typical searches
- **Collection**: jira-data (issues and comments)
- **Score Threshold**: Configurable via SIMILARITY_THRESHOLD (default 0.7)
- **Port**: 26350 (NOT the Qdrant default of 6333)
- **API Key**: Required — stored in `~/.ai-memory/docker/.env` as `QDRANT_API_KEY`

## Notes

- Jira instance URL is auto-detected from project configuration
- Results sorted by relevance score (highest first)
- Issue lookup mode returns chronologically sorted comments
- All filters are optional except query (or --issue for lookup mode)
- Use **exact field names** from the schema above — `jira_project` NOT `project_key`, `jira_issue_key` NOT `issue_key`
