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

# The 'conventions' collection is project-scoped (PLAN-028 P1, DEC-PM298-D4).
# Resolve the project from AI_MEMORY_PROJECT_ID — never from os.getcwd(), which
# is unreliable for this forked skill subprocess. Fail loud if it is not set.
project_id = os.environ.get("AI_MEMORY_PROJECT_ID")
if not project_id:
    raise RuntimeError(
        "AI_MEMORY_PROJECT_ID is not set — cannot search the project-scoped "
        "'conventions' collection. Set AI_MEMORY_PROJECT_ID and retry."
    )

results = search_memories(
    query="topic keywords",
    collection="conventions",
    group_id=project_id,
    memory_type=["guideline", "rule"],
    limit=5
)
```

### Decision Matrix

| Score | Age | Action |
|-------|-----|--------|
| >0.7 | <6 months | Use it, skip to Phase 5 |
| >0.7 | 6-12 months | Mark "needs refresh", proceed to Phase 2 |
| >0.7 | >12 months | Mark "outdated", proceed to Phase 2 |
| <0.7 | Any | Proceed to Phase 2 |

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

### Write scope

This skill writes ONLY the BP file, `INDEX.md` (regenerated in step 4), and the
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
