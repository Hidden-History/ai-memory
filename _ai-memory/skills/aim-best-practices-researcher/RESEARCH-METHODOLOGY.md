# Research Methodology

Detailed instructions for Phases 1-4 of best practices research.

---

## Phase 1: Check Database

### Steps

```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.expanduser("~/.ai-memory"), "src"))

from memory.search import search_memories
from memory.secrets_env import pin_qdrant_api_key, is_auth_error

# Pin QDRANT_API_KEY from .env.secrets so a stale exported key can't silently
# fail auth and degrade this search to file-only (run-with-env.sh parity).
pin_qdrant_api_key()

# The 'conventions' collection is project-scoped (PLAN-028 P1, DEC-PM298-D4).
# Resolve the project from AI_MEMORY_PROJECT_ID — never from os.getcwd(), which
# is unreliable for this forked skill subprocess. Fail loud if it is not set.
project_id = os.environ.get("AI_MEMORY_PROJECT_ID")
if not project_id:
    raise RuntimeError(
        "AI_MEMORY_PROJECT_ID is not set — cannot search the project-scoped "
        "'conventions' collection. Set AI_MEMORY_PROJECT_ID and retry."
    )

try:
    results = search_memories(
        query="topic keywords",
        collection="conventions",
        group_id=project_id,
        memory_type=["guideline", "rule"],
        limit=5,
        attach_raw_cosine=True,  # BP-058/#317: needed for the relevance gate below
    )
except Exception as e:
    # Auth failure: the knowledge base was NOT consulted. Do not present this
    # as "no results found" — results are file-only.
    if is_auth_error(str(e)):
        print("❌ Memory search auth FAILED (401) — knowledge base NOT "
              "consulted; results are file-only")
    raise

top_hit = results[0] if results else None
raw_cosine = top_hit.get("raw_score", 0.0) if top_hit else 0.0
```

### Decision Matrix

`score` is the RRF-fused / rank-normalized ordering value — it is **not** a
calibrated similarity (BP-058) and must never gate an accept/skip decision
(a garbage query and a perfect query both land a top-1 `score` near 0.95).
Gate on `raw_score` (raw cosine, requires `attach_raw_cosine=True` above)
instead, as an uncalibrated coarse prefilter, then confirm with a
content-relevance judgment — read the top hit's content and judge whether it
actually addresses the current query topic. The `raw_score` floor below
(~0.7) is a starting point, not swept for the `conventions` collection the
way the injection gate's 0.76 floor was (DEC-PM343-D7) — **the
content-relevance judgment is the authoritative gate**, not the number.

| Raw Cosine (`raw_score`) | Content Match | Age | Action |
|---|---|---|---|
| ≥0.7 | Yes | <6 months | Use it, skip to Phase 5 |
| ≥0.7 | Yes | 6-12 months | Mark "needs refresh", proceed to Phase 2 |
| ≥0.7 | Yes | >12 months | Mark "outdated", proceed to Phase 2 |
| ≥0.7 | No | Any | Proceed to Phase 2 |
| <0.7 | — | Any | Proceed to Phase 2 |

---

## Phase 2: Web Research

### Search Queries

```
WebSearch: "[topic] best practices <current year>"
WebSearch: "[topic] official documentation <current year>"
```

(Substitute the actual current year for `<current year>` in these queries.)

Prioritize results published within the last ~6 months relative to today.

### Source Prioritization

1. **Official Documentation** - Vendor/author docs
2. **GitHub / Official Repositories** - README, examples
3. **Established Tech Blogs** - Company engineering blogs
4. **Community Discussions** - Stack Overflow (highly voted)

### Freshness Thresholds

| Age | Status | Action |
|-----|--------|--------|
| <6 months | Current | Use as primary source |
| 6-12 months | Needs review | Verify with newer sources |
| >12 months | Outdated | Research for updates |

---

## Phase 3: Save to File

### Steps

1. Generate BP-ID: use **Glob** on `oversight/knowledge/best-practices/BP-*.md`,
   take the highest existing ID and add 1.
2. **Write** file: `oversight/knowledge/best-practices/BP-XXX-[topic].md`
3. Use format from OUTPUT-FORMAT.md
4. Regenerate the INDEX from disk (idempotent, not append-only):
   `"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/.venv/bin/python" "${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/_ai-memory/skills/aim-best-practices-researcher/scripts/bp_index.py" --write oversight/knowledge/best-practices`

   `index.md`'s table is wrapped in a `<!-- BEGIN bp-index (...) -->` /
   `<!-- END bp-index -->` marker pair; `--write`/`--check` key canonical-table
   selection off this region, so a renamed header or a second top-level table
   doesn't break selection. Markers absent → falls back to header-sniffing and
   refuses (writes/reports nothing) on ambiguity. Never remove the markers by hand.

### Write scope

This skill writes ONLY the BP file, `index.md` (regenerated in step 4), and the
conventions-DB store (Phase 4). Do NOT edit roadmaps, SoT, or any other
oversight file.

---

## Phase 4: Store to Database

```bash
"${AI_MEMORY_INSTALL_DIR:-$HOME/.ai-memory}/scripts/memory/run-with-env.sh" store_best_practice.py \
    --content "Concise best practice description" \
    --session-id "current-session-id" \
    --domain "topic-domain" \
    --tags topic keywords \
    --source "https://source-url.com" \
    --source-date "2026-01-29" \
    --group-id "$AI_MEMORY_PROJECT_ID"
```

Output: `Stored: <memory_id>` on success, `Duplicate skipped` if already present.

### Valid source_hook Values

- PostToolUse, Stop, SessionStart
- UserPromptSubmit, PreCompact, PreToolUse
- seed_script, manual
