---
name: aim-status
description: 'Check AI Memory system status'
trigger: "/aim-status"
allowed-tools: Bash
---

Check AI Memory module health, statistics, and system state.

## Canonical Execution

Always run the real script through `run-with-env.sh` so the skill uses the
installed ai-memory virtualenv and the standard local service defaults.

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" aim_status.py
```

When working from an `ai-memory` repo checkout, `./scripts/memory/run-with-env.sh ...`
is an equivalent contributor shortcut.

## Examples

Run one command at a time as needed:

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" aim_status.py --section sync
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" aim_status.py --section freshness
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" aim_status.py --section decay
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" aim_status.py --section flags
```

## Implementation

- Script: `scripts/memory/aim_status.py`
- Output budget: `< 2K tokens`
- Behavior: section-aware status report with graceful fallback when services or data are unavailable

## Activation

```text
/aim-status

/aim-status --section sync
/aim-status --section freshness
/aim-status --section decay
/aim-status --section flags
```

## Output Sections

### Health
Shows service availability for Qdrant, Embedding service, and Monitoring API.

### Collections
Point counts per collection:
- **code-patterns** - Project-specific implementation patterns
- **conventions** - Cross-project shared conventions
- **discussions** - Decision context and session summaries

### Services
Detailed service status with port numbers.

### Sync Status
GitHub synchronization state from the shared install state file in
`~/.ai-memory/github-state/` for the current repo:
- Last sync time (with relative time)
- Items synced (with breakdown by type)
- Error count
- GitHub Sync enabled/disabled

Fallback: "No sync history found" if state file doesn't exist.

### Freshness Summary
Code-patterns freshness classification from `run_freshness_scan()`:
- **Fresh** - Content matches, low commit activity
- **Aging** - Some commit activity since stored
- **Stale** - Significant commit activity
- **Expired** - High activity or content changed

Fallback: "Freshness scan unavailable" if no git context.

### Decay Distribution
Temporal decay score distribution from a 50-vector sample per collection.
Decay formula: `temporal_score = 0.5 ^ (age_days / half_life)`
Bucketed into 5 bands: 0.8-1.0 (fresh), 0.6-0.8 (recent), 0.4-0.6 (aging),
0.2-0.4 (old), 0.0-0.2 (stale).

Fallback: "Decay distribution unavailable" if sampling fails.

### System Flags
Key feature toggles from configuration:
- **Auto-update**: `auto_update_enabled`
- **Freshness**: `freshness_enabled`
- **GitHub Sync**: `github_sync_enabled`
- **Parzival**: `parzival_enabled` — when disabled, the cause is shown alongside it (`disabled (cause: opt-out|failed|unknown)`), because the bare boolean cannot distinguish "declined" from "could not deploy" (AD-32)

## Notes

- Output budget: < 2K tokens total
- Each section handles graceful fallback when data unavailable
- Qdrant connection uses port 26350 with API key authentication
- Metrics pushed via `push_skill_metrics_async` on completion
