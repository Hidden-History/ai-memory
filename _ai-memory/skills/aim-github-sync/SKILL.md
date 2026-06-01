---
name: aim-github-sync
description: 'Synchronize GitHub issues, PRs, commits, and CI results to AI Memory'
allowed-tools: Bash
---

# GitHub Sync - Synchronize GitHub Content

Synchronize GitHub issues, pull requests, commits, and CI results from the configured repository into the AI Memory discussions collection.

## Activation

```text
# Incremental sync (default) - only fetch updated items
/aim-github-sync

# Full sync - fetch all items from scratch
/aim-github-sync --full

# Check sync status (last sync time, items synced, errors)
/aim-github-sync --status
```

## Options

- `--incremental` - Sync only updated items since last sync (default)
- `--full` - Full sync: fetch all items from scratch
- `--status` - Display sync status (last sync time, items synced per type)

## Sync Modes

### Incremental Sync (Default)

- Fetches items updated since last sync timestamp per document type
- Faster and more efficient for regular updates
- Priority order: PRs -> Issues -> Commits -> CI Results
- Updates existing documents via dedup/versioning protocol (SPEC-005)

### Full Sync

- Fetches all items from scratch
- Use for initial setup or after schema changes
- Warning: Can be slow for large repositories

## Configuration

Sync requires GitHub credentials in `.env`:

```env
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=owner/repo-name
GITHUB_BRANCH=main
GITHUB_SYNC_ENABLED=true
```

## Implementation Reference

This skill invokes `GitHubSyncEngine.sync()` from `src/memory/connectors/github/sync.py`:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/github_sync_runner.py" "$@"
```

### Status Mode

Uses the real CLI status path, which resolves canonical and legacy state-file
locations for the configured repo:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/github_sync.py" --status
```

## Guard

If `GITHUB_SYNC_ENABLED` is not `true`, the skill will display:

```
Error: GitHub sync is not enabled. Set GITHUB_SYNC_ENABLED=true and configure GITHUB_TOKEN and GITHUB_REPO.
```

## Technical Details

- **Rate Limiting**: Uses GitHubClient with configurable request delays
- **Pagination**: Automatic pagination for all GitHub API endpoints
- **Deduplication**: SHA256 content hashing prevents duplicate storage (SPEC-005)
- **Versioning**: Changed content creates new version, marks old as superseded
- **Collection**: discussions (shared with conversation data, filtered by source="github")
- **Tenant Isolation**: `group_id` uses normalized lowercase `owner/repo`
- **Sync Priority**: PRs (+ reviews + diffs) -> Issues (+ comments) -> Commits -> CI Results

## Notes

- Requires GitHub personal access token (classic or fine-grained)
- Sync logs written to `~/.ai-memory/logs/activity.log`
- First full sync can take several minutes for large repositories
- Incremental sync timestamps stored per repo in `~/.ai-memory/github-state/github_sync_state_<owner__repo>.json`
- Reviews and diffs are synced as part of PR sync
- Issue comments are synced as part of issue sync

## Legacy ID Audit and Migration

If GitHub data exists but status or project scoping looks inconsistent, audit for
legacy mixed IDs first:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" audit_group_ids.py
```

If the report shows legacy aliases, review the plan and then apply the migration:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" migrate_group_ids.py
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" migrate_group_ids.py --apply
```

When the install still has a flattened legacy `AI_MEMORY_PROJECT_ID`, the apply step also updates that env entry to the canonical slash-form repo ID.
