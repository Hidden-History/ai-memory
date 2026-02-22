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
| `architecture_decision` | 90 days | Architecture decisions are long-lived |
| `agent_handoff` | 180 days | Historical session records for continuity |
| `agent_insight` | 180 days | Learned knowledge persists across many sessions |

### Implementation

Decay scoring is implemented via the Qdrant Formula Query API. The temporal score is computed server-side using the `created_at` timestamp stored in each point's payload. This avoids re-fetching or post-processing in Python — Qdrant applies the formula at query time.

### Overriding Half-Lives

To customize half-lives for your workflow, set `DECAY_TYPE_OVERRIDES` as a JSON string in your `.env`:

```bash
# Example: make guidelines decay faster, extend handoff lifetime
DECAY_TYPE_OVERRIDES='{"guideline": 30, "agent_handoff": 365}'
```

---

## Freshness Detection

### Freshness Tiers

Every memory in the system has a freshness tier based on its age:

| Tier | Age | Meaning |
|---|---|---|
| **Fresh** | < 7 days | Fully current, no action needed |
| **Aging** | 7–30 days | Worth reviewing if the topic comes up |
| **Stale** | 30–90 days | Likely outdated; re-evaluation recommended |
| **Expired** | > 90 days | Probably superseded; consider archiving or refreshing |

Freshness tiers are computed at query time and surfaced in search results and the `/freshness-report` output.

### Git Blame Integration

For `code-patterns` memories, freshness detection goes further by comparing the stored pattern against actual file modification dates via `git blame`:

1. Each `code-patterns` point stores the `source_file` path it was derived from
2. During a freshness scan, the integration runs `git blame` on each source file
3. If the file's last commit date is **newer** than the memory's `created_at`, the pattern is flagged as `needs_review`
4. This catches cases where code changed but the memory was never updated

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
| **Total** | **~2,000–3,000 tokens** | Configurable via `INJECTION_TIER1_BUDGET` |

If Qdrant is unavailable, Tier 1 falls back to reading `SESSION_WORK_INDEX.md` and the latest handoff file from `oversight/session-logs/`.

### Tier 2 — Per-Turn (Ongoing)

Injected on each conversation turn alongside the user's message. Optimized for relevance to the current topic.

| Component | Budget | Content |
|---|---|---|
| Decay-ranked search | ~1,200 tokens | Top memories matching the current turn's query |
| Active task context | ~300 tokens | Current `agent_task` state |
| **Total** | **~1,500 tokens** | Configurable via `INJECTION_TIER2_BUDGET` |

Per-turn injection uses the same decay-scoring formula so that recent, relevant memories surface ahead of older ones.

### Token Budget Configuration

```bash
# Token budget for Tier 1 (session start bootstrap)
INJECTION_TIER1_BUDGET=3000

# Token budget for Tier 2 (per-turn injection)
INJECTION_TIER2_BUDGET=1500
```

Reduce these if you find Claude Code's context window filling up too quickly. Increase them if you need deeper history.

---

## Configuration Reference

All temporal feature settings with their defaults:

```bash
# Decay Scoring
DECAY_SEMANTIC_WEIGHT=0.7          # Weight for semantic similarity (0.0–1.0)
DECAY_TEMPORAL_WEIGHT=0.3          # Weight for temporal score (0.0–1.0)
DECAY_TYPE_OVERRIDES='{}'          # JSON map of memory_type → half_life_days

# Freshness Detection
FRESHNESS_ENABLED=true             # Enable freshness tier computation
FRESHNESS_GIT_BLAME=true           # Enable git blame checks for code-patterns

# Progressive Injection
INJECTION_TIER1_BUDGET=3000        # Token budget for session start bootstrap
INJECTION_TIER2_BUDGET=1500        # Token budget for per-turn injection
INJECTION_ENABLED=true             # Master switch for progressive injection
```

> **Note**: `DECAY_SEMANTIC_WEIGHT + DECAY_TEMPORAL_WEIGHT` must equal `1.0`. The system validates this on startup and logs a warning if the values don't sum correctly, then normalizes them automatically.
