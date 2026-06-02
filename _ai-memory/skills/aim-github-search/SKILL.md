---
name: aim-github-search
description: 'Search GitHub issues, PRs, commits, and CI results with semantic search and filters'
allowed-tools: Read, Bash
---

# Search GitHub - Semantic Search for GitHub Content

Search the discussions collection for GitHub-sourced content using semantic similarity with advanced filtering.

## Activation

```text
# Basic semantic search
/aim-github-search "authentication bug"

# Filter by type
/aim-github-search "API refactoring" --type github_pr
/aim-github-search "CI failures" --type github_ci_result

# Filter by state
/aim-github-search "deployment fix" --state merged

# Combine filters
/aim-github-search "security" --type github_issue --limit 10
```

## Options

- `--type <type>` - Filter by GitHub document type: `github_issue`, `github_pr`, `github_commit`, `github_ci_result`, `github_code_blob`, `github_issue_comment`, `github_pr_review`, `github_pr_diff`
- `--state <state>` - Filter by state: `open`, `closed`, `merged`
- `--limit <n>` - Maximum results to return (default: 5)

## Result Format

Each result includes:
- **GitHub URL** - Direct link
- **Metadata badges** - Type, State, Date
- **Content snippet** - First ~300 characters
- **Relevance score** - Semantic similarity with decay (0-100%)

---

## Qdrant Connection Details

GitHub content is stored in the discussions collection:

| Parameter | Value |
|-----------|-------|
| **Host** | `localhost` |
| **Port** | `26350` (NOT the default 6333) |
| **API Key** | Required. Read from env: `QDRANT_API_KEY` |
| **Collection** | `discussions` |
| **URL** | `http://localhost:26350` |

To get the API key:
```bash
export QDRANT_API_KEY="$(grep QDRANT_API_KEY ~/.ai-memory/docker/.env | cut -d= -f2)"
```

---

## Qdrant Payload Schema

Every GitHub point in `discussions` has the following payload fields. Use these **exact names** for filtering.

### Common Fields (all GitHub points)

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `content` | string | Composed document text | `"[PR #42] Add decay scoring..."` |
| `type` | string | Document type | `"github_pr"`, `"github_issue"` |
| `source` | string | Always `"github"` | `"github"` |
| `group_id` | string | normalized lowercase `owner/repo` | `"hidden-history/ai-memory"` |
| `github_id` | int | Issue/PR number | `42` |
| `state` | string | Current state | `"open"`, `"closed"`, `"merged"` |
| `url` | string | GitHub URL | `"https://github.com/..."` |
| `github_updated_at` | string | ISO 8601 from GitHub API | `"2026-02-16T..."` |
| `files_changed` | list[string] | Files touched (PRs, commits) | `["src/memory/decay.py"]` |
| `labels` | list[string] | Issue/PR labels | `["bug", "v2.0.6"]` |
| `merged_at` | string or null | PR merge timestamp | `"2026-02-16T..."` |
| `is_current` | bool | Versioning: latest version | `true` |

---

## Direct Query Examples

Use `query.py` for direct Qdrant queries. The script applies `source=github` automatically
and accepts optional `--type`, `--state`, `--limit`, and `--format` flags.

### Search by source

```bash
# Replace "owner/repo-name" with your GITHUB_REPO value (e.g., "hidden-history/ai-memory")
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/skills/aim-github-search/scripts/query.py" \
  --group-id "owner/repo-name"
```

### Filter by type and state

```bash
# Replace "owner/repo-name" with your GITHUB_REPO value
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/skills/aim-github-search/scripts/query.py" \
  --group-id "owner/repo-name" --type github_pr --state merged --limit 20
```

### Count GitHub points in collection

```bash
# Returns the exact count via the Qdrant count endpoint (exact=true)
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/skills/aim-github-search/scripts/query.py" \
  --group-id "owner/repo-name" --format count
```

---

## Query Script Reference

The parameterized query script at `skills/aim-github-search/scripts/query.py` implements
the `source=github` + `group_id` filter pattern. It accepts:

```text
python3 query.py \
  --group-id GROUP_ID          # required; e.g. "hidden-history/ai-memory"
  [--type TYPE]                # github_issue | github_pr | github_commit |
                               #   github_ci_result | github_code_blob |
                               #   github_issue_comment | github_pr_review | github_pr_diff
  [--state STATE]              # open | closed | merged
  [--limit N]                  # default: 10
  [--format table|json|count]  # default: table; count uses Qdrant count endpoint (exact=true)
  [--collection COLL]          # default: discussions
```

Run via `run-with-env.sh` so `memory.*` imports and `QDRANT_API_KEY` are resolved automatically:

```bash
bash "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" \
  "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/skills/aim-github-search/scripts/query.py" \
  --group-id "hidden-history/ai-memory" --type github_pr --state merged
```

## Technical Details

- **Semantic Search**: Uses jina-embeddings-v2-base-en for vector similarity
- **Tenant Isolation**: Mandatory group_id filter prevents cross-repo leakage
- **Performance**: < 2s for typical searches
- **Collection**: discussions (GitHub content stored alongside conversation data)
- **Score Threshold**: Configurable via SIMILARITY_THRESHOLD (default 0.7)
- **Port**: 26350 (NOT the Qdrant default of 6333)
- **API Key**: Required -- stored in `~/.ai-memory/docker/.env` as `QDRANT_API_KEY`
- **Decay Scoring**: Applied to results via existing search path

## Notes

- GitHub repo is auto-detected from project configuration
- Results sorted by relevance score (highest first)
- All filters are optional except the search query
- Use **exact field names** from the schema above -- `source` NOT `namespace`, `type` NOT `doc_type`
- The `source="github"` filter is always applied to restrict results to GitHub content
- The `group_id` filter is always applied for mandatory tenant isolation (prevents cross-repo leakage)
