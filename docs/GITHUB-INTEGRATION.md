# 🐙 GitHub Integration

GitHub integration for the AI Memory Module. Syncs pull requests, issues, commits, CI results, and code blobs into Qdrant for semantic search — so you can ask "what changed last week?" or "find PRs related to authentication" alongside your code memory.

---

## Overview

When GitHub integration is enabled, the AI Memory Module continuously ingests your repository activity into the dedicated `github` Qdrant collection. This gives Claude Code access to:

- **Pull requests** — titles, descriptions, diffs, review comments
- **Issues** — titles, body text, comments
- **Commits** — messages, file stats, author metadata
- **CI results** — workflow names, job statuses, failure logs
- **Code blobs** — file contents via AST-aware chunking

Prose content (PRs, issues, commits) is embedded using `jina-embeddings-v2-base-en` (768d); code blobs use `jina-embeddings-v2-base-code` (768d) for better code retrieval. All content is stored with rich metadata for filtering. Semantic search lets you find relevant history without knowing exact keywords.

---

## Setup Guide

### GitHub Personal Access Token

Create a fine-grained Personal Access Token at [github.com/settings/tokens](https://github.com/settings/tokens).

**For fine-grained tokens**, enable these repository permissions:
- `Contents` — read
- `Issues` — read
- `Pull requests` — read
- `Actions` — read (for CI results)
- `Metadata` — read (always required)

**For classic tokens**, the `repo` scope covers all of the above.

### Environment Variables

Set these in your `.env` file:

```bash
# GitHub Integration
GITHUB_SYNC_ENABLED=true
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_REPO=owner/repo-name
GITHUB_SYNC_INTERVAL=1800
GITHUB_CODE_BLOB_INCLUDE=*.sh,*.groovy,Makefile,CODEOWNERS,.dockerignore
GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE=512000
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_SYNC_ENABLED` | No | `false` | Enable GitHub synchronization |
| `GITHUB_TOKEN` | Yes* | *(empty)* | Personal Access Token (classic or fine-grained) |
| `GITHUB_REPO` | Yes* | *(empty)* | Repository in `owner/repo` format |
| `GITHUB_SYNC_INTERVAL` | No | `1800` | Sync frequency in seconds (default 30 minutes) |
| `GITHUB_CODE_BLOB_ENABLED` | No | `true` | Enable syncing of code blobs separately from PRs/issues/commits |
| `GITHUB_CODE_BLOB_MAX_SIZE` | No | `102400` | Standard max file size for code blob sync before include overrides |
| `GITHUB_CODE_BLOB_INCLUDE` | No | *(empty)* | Comma-separated include patterns that can override exclude, unknown-language, and standard size skips |
| `GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE` | No | `512000 bytes (5 × default GITHUB_CODE_BLOB_MAX_SIZE of 102400). Hard ceiling: 10MB.` | Hard ceiling for explicitly included files |
| `GITHUB_CODE_BLOB_EXCLUDE` | No | `node_modules,*.min.js,.git,__pycache__,*.pyc,build,dist,*.egg-info` | Comma-separated exclude patterns for code blob sync |

*Required when `GITHUB_SYNC_ENABLED=true`

### Code Blob Include Rules

- Binary files are never included, even if they match `GITHUB_CODE_BLOB_INCLUDE`
- Include patterns use the same matching model as exclude patterns:
  - `*.sh` matches by full-path suffix
  - `Makefile` matches an exact path segment

**Pattern rules:**
- `*.ext` — matches files ending with `.ext` (e.g., `*.py`, `*.yaml`)
- `token` — matches files containing `token` as a path segment (e.g., `Makefile`, `Dockerfile`)
- Bare `*` and `*.` are rejected (too broad — use explicit extensions)
- Path patterns with `/` are not supported (e.g., `src/*.py` won't work — use `*.py` instead)
- Explicit include can override:
  - `GITHUB_CODE_BLOB_MAX_SIZE`
  - `GITHUB_CODE_BLOB_EXCLUDE`
  - unknown-language rejection
- Explicit include cannot override:
  - binary-file rejection
  - `GITHUB_CODE_BLOB_INCLUDE_MAX_SIZE`

### First-Pass Native File Support

The first implementation round adds native language/classification support for:

- `.sh`, `.groovy`, `.less`, `.xml`, `.properties`
- `Makefile`
- `CODEOWNERS`
- `.dockerignore`, `.gitignore`, `.editorconfig`

### Automated Setup (via Installer)

During `install.sh`, the installer prompts for optional GitHub setup:

1. **Enable GitHub sync?** `[y/N]`
2. **GitHub repository** (e.g., `owner/repo-name`)
3. **GitHub token** (hidden input)

The installer validates the token against the GitHub API before proceeding. On success, it offers an initial full sync.

---

## Sync Behavior

### What Gets Synced

| Content Type | Memory Type | What's Captured |
|---|---|---|
| Pull Requests | `github_pr` | Title, body, diff summary, labels, state, author |
| PR Diffs | `github_pr_diff` | Extracted diff content per file in the PR |
| PR Reviews | `github_pr_review` | Review comments and review body text |
| Issues | `github_issue` | Title, body, labels, state, assignees |
| Issue Comments | `github_issue_comment` | Individual comments on issues |
| Commits | `github_commit` | Message, stats (additions/deletions), author, date |
| CI Results | `github_ci_result` | Workflow name, job status, branch, run URL |
| Code Blobs | `github_code_blob` | File contents via AST chunking, path, language |
| Releases | `github_release` | Release name, tag, body (release notes) |

### Incremental Sync (Default)

After the first run, only new or updated items are fetched. The last-seen state is tracked per content type in `~/.ai-memory/.audit/state/github_sync_state.json`:

```json
{
  "pull_requests": { "last_synced": "2026-02-15T14:30:00Z", "last_page": null },
  "issues": { "last_synced": "2026-02-15T14:30:00Z", "last_page": null },
  "commits": { "last_sha": "abc123def456...", "last_synced": "2026-02-15T14:30:00Z" },
  "workflows": { "last_synced": "2026-02-15T14:30:00Z" }
}
```

### Full Sync

Triggered on first run or when the state file is missing. Fetches all history up to the configured lookback window. Can be slow for large repositories — subsequent incremental syncs are fast.

### Data Flow

```
GitHub REST API v3
    │
    ├── /repos/{owner}/{repo}/pulls      → PRs (open + closed + merged)
    ├── /repos/{owner}/{repo}/issues     → Issues + comments
    ├── /repos/{owner}/{repo}/commits    → Commit history
    ├── /repos/{owner}/{repo}/actions/runs → CI workflow results
    └── /repos/{owner}/{repo}/contents  → Code blobs (AST chunked)
    │
    ▼
Document Composer
    │   Flattens metadata + body into structured text
    │
    ▼
Intelligent Chunker
    │   PRs/Issues/Commits: ContentType.PROSE (512-token, 15% overlap)
    │   Code Blobs: ContentType.CODE (AST-aware boundaries)
    │
    ▼
Embedding Service (dual routing: prose → jina-v2-base-en, code → jina-v2-base-code, 768d)
    │
    ▼
Qdrant (github collection for all GitHub-synced data)
    │   SHA256 content_hash for deduplication
    │   memory_type tag for filtering
    │
    ▼
State Persistence (~/.ai-memory/.audit/state/github_sync_state.json)
```

### Rate Limiting

GitHub allows 5,000 API requests per hour for authenticated requests. The sync adapter uses adaptive rate limiting with exponential backoff:

- Reads `X-RateLimit-Remaining` from every response
- Automatically slows down when remaining < 100
- Backs off and retries on 429 and 403 rate-limit responses
- Logs a warning when the rate limit drops below 500 remaining

---

## Using GitHub Data

### `/aim-github-search` Skill

Semantic search across all synced GitHub content.

```bash
# Basic semantic search
/aim-github-search "authentication flow changes"

# Filter by content type
/aim-github-search "login bug" --type issue
/aim-github-search "refactor storage" --type pr
/aim-github-search "bump version" --type commit
/aim-github-search "test failure on main" --type ci_result
/aim-github-search "token refresh logic" --type code_blob

# Filter by state
/aim-github-search "open security issues" --type issue --state open
/aim-github-search "merged last week" --type pr --state merged
/aim-github-search "closed without merge" --type pr --state closed

# Combine filters
/aim-github-search "database migration" --type pr --state merged --limit 10

# Look up a specific PR or issue by number
/aim-github-search --pr 142
/aim-github-search --issue 87
```

### `/aim-github-sync` Skill

Manually trigger a sync outside the scheduled interval.

```bash
# Incremental sync (default)
/aim-github-sync

# Full sync (re-fetch all history)
/aim-github-sync --full

# Sync only a specific content type
/aim-github-sync --type prs
/aim-github-sync --type issues
/aim-github-sync --type commits
/aim-github-sync --type ci

# Check sync status
/aim-github-sync --status
```

### Session Start Enrichment

When Parzival session agent is enabled (see [PARZIVAL-SESSION-GUIDE.md](PARZIVAL-SESSION-GUIDE.md)), GitHub data enriches your session bootstrap:

- **Merged PRs since last session** — summary of what landed
- **New issues opened** — items requiring attention
- **CI failures** — any broken builds on the main branch

This appears automatically at session start via the `SessionStart` hook's Tier 1 context injection (~2,500 token budget). The `/parzival-start` command reads local oversight files separately — it does not trigger the Qdrant-backed enrichment.

---

## Feedback Loop

When a merged PR touches files that have corresponding code-patterns in Qdrant, those patterns are automatically flagged for freshness review:

1. Sync detects a merged PR with changed files
2. Each changed file path is checked against `code-patterns` metadata
3. Matching patterns have their `freshness_status` set to `needs_review`
4. The next `/aim-freshness-report` run surfaces these flagged patterns

This creates a closed loop: code changes in GitHub automatically trigger re-evaluation of the memory patterns derived from that code.

---

## Troubleshooting

### Authentication Errors

```
GitHubAuthError: 401 Unauthorized
```

- Verify the token is still valid at [github.com/settings/tokens](https://github.com/settings/tokens) — tokens can expire or be revoked
- Confirm `GITHUB_REPO` is in `owner/repo` format (not a URL)
- Check that the token has the required repository permissions

### Rate Limit Exhausted

```
GitHubRateLimitError: 403 — rate limit exceeded, resets at 2026-02-16T15:00:00Z
```

- Wait for the rate limit window to reset (shown in the error)
- Reduce sync frequency: set `GITHUB_SYNC_INTERVAL=7200` (2 hours)
- The sync will resume automatically on the next scheduled run

### Sync Failures

Check the sync section in `/aim-status` for last sync time and error counts. For detailed logs:

```bash
# Enable debug logging
GITHUB_SYNC_LOG_LEVEL=DEBUG

# Check logs directly
tail -f ~/.ai-memory/logs/github_sync.log
```

### State Reset

To force a full re-sync from scratch:

```bash
# Remove state file and run full sync
rm ~/.ai-memory/.audit/state/github_sync_state.json
/aim-github-sync --full
```

### Search Returns No Results

- Run `/aim-github-sync --status` to verify data exists in Qdrant
- Ensure `GITHUB_SYNC_ENABLED=true` in your `.env`
- Verify the collection exists: `curl -H "api-key: $QDRANT_API_KEY" http://localhost:26350/collections/github`
- Check that `GITHUB_REPO` matches the repository you expect

---

## Automated Sync Schedule

The installer configures a Docker background service (`ai-memory-github-sync`) for automated incremental sync:

- **Service name**: `ai-memory-github-sync`
- **Schedule**: Every 30 minutes by default (configurable via `GITHUB_SYNC_INTERVAL`)
- **Mode**: Incremental (only new/updated items)
- **Log output**: `~/.ai-memory/logs/github_sync.log`

The service runs continuously in the Docker stack. Verify it is running with:

```bash
docker compose -f docker/docker-compose.yml ps
```

Expected output will include a row like:

```
ai-memory-github-sync   running   (no ports)
```

To manually trigger outside the schedule:

```bash
cd ~/.ai-memory/docker && ~/.ai-memory/.venv/bin/python ~/.ai-memory/scripts/github_sync.py --incremental
```

---

## Health Check Integration

The `/aim-status` skill and `scripts/health-check.py` include GitHub sync status:

- Last sync time and items synced per content type
- Rate limit remaining
- State file validity
- Collection document counts by `memory_type`
