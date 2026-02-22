# ⏱️ Temporal Features

v2.0.6 adds a temporal dimension to the AI Memory Module: memories are now ranked by **when** they are relevant, not just **what** they contain. Decay scoring, freshness detection, and progressive context injection work together to ensure that the most current, applicable memories surface first.

---

## Overview

Traditional vector search ranks results by semantic similarity alone. This works well when all memories are equally current — but in a living codebase, a code pattern from six months ago may be outdated, and a CI failure from last week is more urgent than one from last year.

Temporal features address this by:

- **Decay scoring** — blending semantic similarity with a time-based score so recent memories rank higher
- **Freshness detection** — surfacing memories that may be stale due to code changes
- **Progressive context injection** — loading the right memories at the right time, within tight token budgets

---

## Decay Scoring

### Formula

Every search result receives a final score that combines semantic similarity with temporal relevance:

```
final_score = (DECAY_SEMANTIC_WEIGHT × semantic_score) + (DECAY_TEMPORAL_WEIGHT × temporal_score)
```

Default weights: `0.7` semantic + `0.3` temporal.

The temporal score uses exponential decay:

```
temporal_score = 0.5 ^ (age_days / half_life_days)
```

At `age = 0` days, `temporal_score = 1.0` (maximum). At `age = half_life_days`, `temporal_score = 0.5`. At `age = 2 × half_life_days`, `temporal_score = 0.25`. And so on.

### Half-Lives by Memory Type

Different memory types have different relevance windows. CI results become irrelevant quickly; architectural decisions remain relevant for months.

| Memory Type | Half-Life | Rationale |
|---|---|---|
| `github_ci_result` | 7 days | CI results become irrelevant within days |
| `agent_task` | 14 days | Tasks are replaced and superseded frequently |
| `github_code_blob` | 14 days | Code changes rapidly; blobs go stale fast |
| `github_commit` | 14 days | Commit context fades as code evolves |
| `conversation` | 21 days | Session context fades over weeks |
| `session_summary` | 21 days | Session summaries lose context gradually |
| `github_issue` | 30 days | Issues remain relevant through their lifecycle |
| `github_pr` | 30 days | PRs stay relevant until merged and forgotten |
| `jira_issue` | 30 days | Jira items track work in progress |
| `agent_memory` | 30 days | General agent memories refresh regularly |
| `guideline` | 60 days | Standards are semi-permanent |
| `rule` | 60 days | Rules change but not constantly |
| `agent_handoff` | 180 days | Historical session records for continuity |
| `agent_insight` | 180 days | Learned knowledge persists across many sessions |

> **Note**: Types not listed in `DECAY_TYPE_OVERRIDES` (e.g., `conversation`, `session_summary`) fall back to their collection-level defaults: `code-patterns` = 14 days, `discussions` = 21 days, `conventions` = 60 days.

### Implementation

Decay scoring is implemented via the Qdrant Formula Query API. The temporal score is computed server-side using the `created_at` timestamp stored in each point's payload. This avoids re-fetching or post-processing in Python — Qdrant applies the formula at query time.

### Overriding Half-Lives

To customize half-lives for your workflow, set `DECAY_TYPE_OVERRIDES` as a comma-separated list of `type:days` pairs in your `.env`:

```bash
# Example: make guidelines decay faster, extend handoff lifetime
DECAY_TYPE_OVERRIDES="guideline:30,agent_handoff:365"
```

---

## Freshness Detection

### Freshness Tiers

Every code-patterns memory has a freshness tier based on how many commits have touched its source file since the memory was stored:

| Tier | Threshold | Meaning |
|---|---|---|
| **Fresh** | < 3 commits | Fully current, no action needed |
| **Aging** | 3–10 commits | Worth reviewing if the topic comes up |
| **Stale** | 10–25 commits | Likely outdated; re-evaluation recommended |
| **Expired** | > 25 commits | Probably superseded; consider archiving |

Note: Freshness detection applies specifically to code-patterns memories that have `source_file` metadata. Freshness tiers are surfaced in search results and the `/freshness-report` output.

### Git-Based Verification

For `code-patterns` memories, freshness detection can optionally cross-reference against actual file history via `git log`:

1. Each `code-patterns` point stores the `source_file` path it was derived from
2. During a freshness scan with `--git-check`, the system counts commits that touched each source file since the memory was stored
3. The commit count determines the freshness tier (< 3 = Fresh, 3–10 = Aging, 10–25 = Stale, > 25 = Expired)
4. If the file has been modified but the memory was never updated, the pattern is flagged as `needs_review`

### `/freshness-report` Skill

On-demand scan that surfaces stale or flagged memories:

```bash
# Full freshness report across all collections
/freshness-report

# Limit to a specific collection
/freshness-report --collection code-patterns

# Show only stale and expired memories
/freshness-report --tier stale
/freshness-report --tier expired

# Include git blame checks for code-patterns
/freshness-report --git-check
```

The report groups results by tier and shows the source that caused the flag (age vs. git blame mismatch).

### `/memory-refresh` Skill

Targeted re-evaluation for specific memories or groups:

```bash
# Re-evaluate a single memory by ID
/memory-refresh --id a1b2c3d4-...

# Refresh all stale code-patterns
/memory-refresh --collection code-patterns --tier stale

# Refresh memories flagged by GitHub feedback loop
/memory-refresh --filter needs_review
```

Refreshing prompts Claude Code to re-read the source (file, PR, issue) and store an updated memory, replacing the stale one.

---

## Progressive Context Injection

Context injection loads memories into each Claude Code session within strict token budgets, prioritizing the most relevant and recent content.

### Tier 1 — Bootstrap (Session Start)

Loaded once when the session begins. Optimized for orienting Claude Code to the current state of the project.

| Component | Budget | Content |
|---|---|---|
| Agent handoff | ~800 tokens | Most recent `agent_handoff` from Qdrant |
| Active insights | ~600 tokens | Top `agent_insight` memories (decay-ranked) |
| GitHub enrichment | ~600 tokens | Merged PRs + new issues since last session |
| **Total** | **~2,500 tokens (default)** | Configurable via `BOOTSTRAP_TOKEN_BUDGET` |

If Qdrant is unavailable, Tier 1 outputs empty context and logs a warning. Claude continues without memory injection.

### Tier 2 — Per-Turn (Ongoing)

Injected on each conversation turn alongside the user's message. Optimized for relevance to the current topic.

| Component | Budget | Content |
|---|---|---|
| Decay-ranked search | ~1,200 tokens | Top memories matching the current turn's query |
| Active task context | ~300 tokens | Current `agent_task` state |
| **Total** | **500–1,500 tokens (adaptive)** | Configurable via `INJECTION_BUDGET_FLOOR` and `INJECTION_BUDGET_CEILING` |

Per-turn injection uses the same decay-scoring formula so that recent, relevant memories surface ahead of older ones.

### Token Budget Configuration

```bash
# Token budget for Tier 1 (session start bootstrap)
BOOTSTRAP_TOKEN_BUDGET=2500

# Adaptive token budget range for Tier 2 (per-turn injection)
INJECTION_BUDGET_FLOOR=500
INJECTION_BUDGET_CEILING=1500
```

Reduce these if you find Claude Code's context window filling up too quickly. Increase them if you need deeper history.

---

## Configuration Reference

All temporal feature settings with their defaults:

```bash
# Decay Scoring
DECAY_SEMANTIC_WEIGHT=0.7          # Weight for semantic similarity (0.0–1.0); temporal weight = 1 - this value
DECAY_TYPE_OVERRIDES="github_ci_result:7,agent_task:14,github_code_blob:14,github_commit:14,github_issue:30,github_pr:30,jira_issue:30,agent_memory:30,guideline:60,rule:60,agent_handoff:180,agent_insight:180"
                                   # Per-type half-life overrides (comma-separated type:days pairs)

# Freshness Detection
FRESHNESS_ENABLED=true             # Enable freshness detection for code-patterns memories

# Progressive Injection
BOOTSTRAP_TOKEN_BUDGET=2500        # Token budget for Tier 1 (session start bootstrap)
INJECTION_BUDGET_FLOOR=500         # Minimum token budget for Tier 2 (per-turn, adaptive)
INJECTION_BUDGET_CEILING=1500      # Maximum token budget for Tier 2 (per-turn, adaptive)
INJECTION_ENABLED=true             # Master switch for progressive injection
```

> **Note**: The temporal weight is automatically computed as `1 - DECAY_SEMANTIC_WEIGHT`. Only `DECAY_SEMANTIC_WEIGHT` is configurable.
