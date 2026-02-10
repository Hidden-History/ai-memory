---
name: search-jira
description: 'Search Jira issues and comments with semantic search and filters'
allowed-tools: Read, Bash
---

# Search Jira - Semantic Search for Jira Content

Search the jira-data collection for issues and comments using semantic similarity with advanced filtering.

## Usage

```bash
# Basic semantic search
/search-jira "authentication bug"

# Filter by project
/search-jira "API errors" --project BMAD

# Filter by type (issue or comment)
/search-jira "implementation details" --type jira_comment

# Filter by issue type
/search-jira "bugs" --issue-type Bug

# Filter by status
/search-jira "in progress work" --status "In Progress"

# Filter by priority
/search-jira "critical issues" --priority High

# Filter by author (comments) or reporter (issues)
/search-jira "alice's comments" --author alice@company.com

# Issue lookup mode (issue + all comments)
/search-jira --issue BMAD-42

# Combine filters
/search-jira "database" --project BMAD --issue-type Bug --status Done --limit 10
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

## Examples

```bash
# Find authentication bugs in BMAD project
/search-jira "authentication failing" --project BMAD --issue-type Bug

# Find high priority work
/search-jira "urgent" --priority High --limit 10

# Find comments by specific person
/search-jira "design decisions" --type jira_comment --author alice@company.com

# Lookup complete issue context (issue + all comments)
/search-jira --issue BMAD-42

# Find in-progress stories
/search-jira "features" --issue-type Story --status "In Progress"
```

## Python Implementation Reference

This skill uses functions from `src/memory/connectors/jira/search.py`:

```python
from src.memory.connectors.jira.search import search_jira, lookup_issue

# Semantic search
results = search_jira(
    query="authentication bug",
    group_id="company.atlassian.net",
    project="BMAD",
    issue_type="Bug",
    limit=5
)

# Issue lookup
context = lookup_issue(
    issue_key="BMAD-42",
    group_id="company.atlassian.net"
)
```

## Technical Details

- **Semantic Search**: Uses jina-embeddings-v2-base-en for vector similarity
- **Tenant Isolation**: Mandatory group_id filter prevents cross-instance leakage
- **Performance**: < 2s for typical searches
- **Collection**: jira-data (issues and comments)
- **Score Threshold**: Configurable via SIMILARITY_THRESHOLD (default 0.7)

## Notes

- Jira instance URL is auto-detected from project configuration
- Results sorted by relevance score (highest first)
- Issue lookup mode returns chronologically sorted comments
- All filters are optional except query (or --issue for lookup mode)
