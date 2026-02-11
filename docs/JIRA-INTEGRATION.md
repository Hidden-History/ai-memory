# 🔗 Jira Cloud Integration

Jira Cloud integration for the AI Memory Module. Syncs Jira issues and comments into a dedicated `jira-data` vector collection, enabling semantic search across your Jira content alongside code memory.

Uses the [Jira Cloud REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/) with Basic Auth.

---

## Prerequisites

- **Jira Cloud** instance (not Jira Server or Data Center)
- **Jira API token** — create at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
- **Account email** with read access to target projects
- **AI Memory Module** installed and running (see [INSTALL.md](../INSTALL.md))

---

## Configuration

### Automated Setup (via Installer)

During `install.sh`, the installer prompts for optional Jira setup:

1. **Enable Jira sync?** `[y/N]`
2. **Jira instance URL** (e.g., `https://company.atlassian.net`)
3. **Jira email**
4. **Jira API token** (hidden input)
5. **Project keys** (comma-separated, e.g., `PROJ,DEV`)

The installer validates credentials via the Jira API before proceeding. On success, it offers an initial full sync and optional run-at-install.

### Environment Variables

Set these in your `.env` file:

```bash
# Jira Cloud Integration
JIRA_INSTANCE_URL=https://company.atlassian.net
JIRA_EMAIL=user@company.com
JIRA_API_TOKEN=your_api_token_here
JIRA_PROJECTS=PROJ,DEV,OPS
JIRA_SYNC_ENABLED=true
JIRA_SYNC_DELAY_MS=100
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JIRA_INSTANCE_URL` | Yes | *(empty)* | Jira Cloud URL (e.g., `https://company.atlassian.net`) |
| `JIRA_EMAIL` | Yes | *(empty)* | Jira account email for Basic Auth |
| `JIRA_API_TOKEN` | Yes | *(empty)* | API token (stored as SecretStr) |
| `JIRA_PROJECTS` | Yes | *(empty)* | Comma-separated project keys |
| `JIRA_SYNC_ENABLED` | No | `false` | Enable Jira synchronization |
| `JIRA_SYNC_DELAY_MS` | No | `100` | Delay between API requests (ms, 0-5000) |

---

## Architecture

### Collection

| Property | Value |
|----------|-------|
| **Name** | `jira-data` |
| **Conditional** | Only created when `JIRA_SYNC_ENABLED=true` |
| **Memory types** | `JIRA_ISSUE`, `JIRA_COMMENT` |
| **Chunking** | `ContentType.PROSE` (512-token chunks, 15% overlap) |
| **Tenant isolation** | `group_id` = Jira instance hostname (e.g., `company.atlassian.net`) |

### Components

```
src/memory/connectors/jira/
    ├── client.py       → Async httpx client, Basic Auth, pagination
    ├── adf_converter.py → ADF JSON → plain text conversion
    ├── composer.py      → Document text composition for embedding
    ├── sync.py          → Sync orchestrator (full/incremental)
    ├── search.py        → Semantic search + issue lookup
    └── __init__.py      → Package exports

src/memory/config.py     → Jira config fields on MemoryConfig model
scripts/jira_sync.py     → CLI entry point for sync operations
```

### Data Flow

```
Jira Cloud API
    │
    ├── JQL search (token-based pagination)
    │       → Issues with all fields
    │
    ├── Comment fetch (offset-based pagination)
    │       → Comments per issue
    │
    ▼
Document Composer
    │
    ├── Issue: [KEY] Title + metadata + ADF-converted description
    │
    ├── Comment: [KEY] Title (context) + author + ADF-converted body
    │
    ▼
Intelligent Chunker (ContentType.PROSE)
    │   512-token chunks, 15% overlap
    │
    ▼
Embedding Service (jina-embeddings-v2-base-en, 768d)
    │
    ▼
Qdrant (jira-data collection)
    │   group_id = Jira instance hostname
    │   SHA256 content_hash for deduplication
    │
    ▼
State Persistence (jira_sync_state.json)
    │   last_synced timestamp per project
```

---

## Sync Operations

### Incremental Sync (Default)

- Fetches issues updated since last sync timestamp
- JQL: `project = PROJ AND updated >= "2026-02-01 00:00"`
- Faster for regular updates
- Updates existing documents in-place

### Full Sync

- Fetches all issues and comments from scratch
- Use for initial setup or after schema changes
- Can be slow for large projects (hundreds/thousands of issues)

### Sync Pipeline

1. **JQL search** — full or incremental based on `last_synced` timestamp
2. **Token-based pagination** for issues, offset-based for comments
3. **Document composition** — issue metadata + ADF-converted description/body
4. **Intelligent chunking** — `ContentType.PROSE` (512-token chunks, 15% overlap)
5. **Embedding generation** — batch where possible
6. **Qdrant storage** — with full metadata payload
7. **State persistence** — `last_synced` timestamp per project in `jira_sync_state.json`

### Error Handling

- **Per-issue fail-open**: Log error, continue to next issue
- **Rate limiting**: Configurable delay between API requests (default 100ms)
- **Deduplication**: SHA256 content hashing prevents duplicate storage
- **Resource cleanup**: `try/finally` for async clients

### Using `/jira-sync` Skill

```bash
# Incremental sync (default) — only fetch updated issues
/jira-sync

# Full sync — fetch all issues and comments
/jira-sync --full

# Sync specific project
/jira-sync --project PROJ

# Check sync status (last sync time, items synced, errors)
/jira-sync --status

# Full sync for specific project
/jira-sync --full --project PROJ
```

### CLI (`scripts/jira_sync.py`)

```bash
python scripts/jira_sync.py --incremental
python scripts/jira_sync.py --full --project PROJ
python scripts/jira_sync.py --status
```

---

## Search Operations

### Semantic Search

Uses `jina-embeddings-v2-base-en` for vector similarity against the `jira-data` collection.

**Available filters** (all optional except query):

| Filter | Description | Example |
|--------|-------------|---------|
| `--project <key>` | Filter by Jira project key | `PROJ`, `DEV` |
| `--type <type>` | Filter by document type | `jira_issue` or `jira_comment` |
| `--issue-type <type>` | Filter by issue type | `Bug`, `Story`, `Task`, `Epic` |
| `--status <status>` | Filter by issue status | `To Do`, `In Progress`, `Done` |
| `--priority <priority>` | Filter by priority | `Highest`, `High`, `Medium`, `Low`, `Lowest` |
| `--author <email>` | Filter by comment author or issue reporter | `alice@company.com` |
| `--limit <n>` | Maximum results | Default: `5` |

### Issue Lookup

Retrieves complete issue context — the issue document plus all comments, sorted chronologically.

```bash
/search-jira --issue PROJ-42
```

### Using `/search-jira` Skill

```bash
# Basic semantic search
/search-jira "authentication bug"

# Filter by project
/search-jira "API errors" --project PROJ

# Filter by type
/search-jira "implementation details" --type jira_comment

# Filter by issue type, status, priority
/search-jira "bugs" --issue-type Bug
/search-jira "in progress work" --status "In Progress"
/search-jira "critical issues" --priority High

# Filter by author
/search-jira "alice's comments" --author alice@company.com

# Issue lookup mode (issue + all comments)
/search-jira --issue PROJ-42

# Combine filters
/search-jira "database" --project PROJ --issue-type Bug --status Done --limit 10
```

### Result Format

Each result includes:

- **Jira URL** — Direct link to issue or comment
- **Metadata badges** — Type, Status, Priority, Author/Reporter
- **Content snippet** — First ~300 characters
- **Relevance score** — Semantic similarity (0-100%)

---

## Automated Sync Schedule

The installer configures cron jobs for automated incremental sync:

- **Schedule**: 6am and 6pm daily
- **Mode**: Incremental (only updated issues)
- **Log output**: `~/.ai-memory/logs/jira_sync.log`

```cron
# Linux/WSL (with flock overlap prevention):
0 6,18 * * * cd ~/.ai-memory/docker && flock -n ~/.ai-memory/.locks/jira_sync.lock ~/.ai-memory/.venv/bin/python ~/.ai-memory/scripts/jira_sync.py --incremental >> ~/.ai-memory/logs/jira_sync.log 2>&1 # ai-memory-jira-sync

# macOS (no flock):
0 6,18 * * * cd ~/.ai-memory/docker && ~/.ai-memory/.venv/bin/python ~/.ai-memory/scripts/jira_sync.py --incremental >> ~/.ai-memory/logs/jira_sync.log 2>&1 # ai-memory-jira-sync
```

To manually re-run:

```bash
cd ~/.ai-memory/docker && ~/.ai-memory/.venv/bin/python ~/.ai-memory/scripts/jira_sync.py --incremental
```

---

## Health Check Integration

The `/memory-status` skill and `scripts/health-check.py` include Jira data collection status:

- Collection existence and document count
- Sync state (last sync time, items synced)
- Listed as a component in health check output

---

## ADF Converter

The ADF (Atlassian Document Format) converter transforms Jira's rich text JSON into plain text for embedding.

**Supported node types:**

| Category | Node Types |
|----------|-----------|
| **Must-have** | `paragraph`, `text`, `heading`, `bulletList`, `orderedList`, `listItem`, `codeBlock`, `blockquote`, `hardBreak` |
| **Should-have** | `mention` (`@displayName`), `inlineCard` (URL extraction) |
| **Text marks** | `strong` (**bold**), `em` (*italic*), `code` (`` `inline` ``) |
| **Unknown nodes** | Logs warning, gracefully extracts nested text |

---

## Troubleshooting

### Authentication Fails

- Verify API token at [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) — tokens can expire or be revoked
- Confirm the email matches the Jira Cloud account
- Ensure the account has read access to the target projects

### No Issues Found

- Verify project keys match Jira exactly (case-sensitive: `PROJ` not `proj`)
- Check that the Jira instance URL is correct (e.g., `https://company.atlassian.net` not `https://company.jira.com`)

### Sync Is Slow

- Large projects with hundreds/thousands of issues take time on first full sync
- After initial sync, use incremental mode for fast daily updates
- Reduce project scope by syncing specific projects: `/jira-sync --project PROJ`
- Adjust `JIRA_SYNC_DELAY_MS` (lower = faster but more API pressure)

### Search Returns No Results

- Run `/jira-sync --status` to verify data exists in the collection
- Check that `group_id` matches (derived from `JIRA_INSTANCE_URL` hostname)
- Verify the `jira-data` collection exists: `curl http://localhost:26350/collections/jira-data`
- Ensure `JIRA_SYNC_ENABLED=true` in your `.env`

### Sync State Reset

If you need to force a full re-sync:

```bash
# Remove state file and run full sync
rm ~/.ai-memory/jira_sync_state.json
python scripts/jira_sync.py --full
```
